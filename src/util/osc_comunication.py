import asyncio
import random
import string
from functools import partial
import traceback

from db import SerializableDBObj
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient
from util.const import COMMAND_CONFIRM, COMMAND_CONNECTION
from util.timer import Timer
from util import init_logger

_LOGGER = init_logger(__name__)


class OSCManager(object):
    def __init__(self,
                 hostlisten='127.0.0.1',
                 portlisten=33217,
                 hostconnect=None,
                 portconnect=None):
        self.hostlisten = hostlisten
        self.portlisten = portlisten
        self.hostconnect = hostconnect
        self.portconnect = portconnect
        self.on_init_ok = None
        self.server = None
        self.transport = None
        self.protocol = None
        self.dispatcher = Dispatcher()
        self.client_connection_sender_timer = None
        self.user_on_connection_timeout = None
        self.connected_hosts = dict()
        self.callbacks = dict()
        self.cmd_queue = []

    @staticmethod
    def generate_uid():
        return ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(16))

    async def init(self,
                   loop=asyncio.get_event_loop(),
                   on_connection_timeout=None,
                   on_init_ok=None):
        if not self.transport:
            try:
                _LOGGER.info(f"OSC trying to init conpars={self.hostlisten}:{self.portlisten} -> {self.hostconnect}:{self.portconnect}")
                self.user_on_connection_timeout = on_connection_timeout
                self.server = AsyncIOOSCUDPServer(
                    (self.hostlisten, self.portlisten),
                    self.dispatcher, loop)
                if self.client_connection_sender_timer:
                    self.client_connection_sender_timer = None
                self.dispatcher.map('/*', self.device_callback, needs_reply_address=True)
                self.transport, self.protocol = await self.server.create_serve_endpoint()
            except (Exception, OSError):
                _LOGGER.error(f"OSC init exception {traceback.format_exc()}")
                self.client_connection_sender_timer = Timer(1, partial(
                    self.init,
                    loop=loop,
                    on_connection_timeout=on_connection_timeout,
                    on_init_ok=on_init_ok))
                return
            try:
                if on_init_ok:
                    on_init_ok()
                if self.hostconnect:
                    self.connection_sender_timer_init(0)
                self.handle(COMMAND_CONNECTION, self.on_command_connection)
            except Exception:
                _LOGGER.error(f'OSC post init error {traceback.format_exc()}')

    async def send_client_command_connection(self):
        # _LOGGER.debug("Connecting")
        try:
            hp = (self.hostconnect, self.portconnect)
            self.on_command_connection(hp, self.portconnect, timeout=1)
        except Exception:
            _LOGGER.error(f'Connection send error: {traceback.format_exc()}')
        self.connection_sender_timer_init()

    def connection_handler_timer_init(self, hp, intv=6):
        hpstr = f'{hp[0]}:{hp[1]}'
        if hpstr in self.connected_hosts:
            d = self.connected_hosts[hpstr]
            if d['timer']:
                d['timer'].cancel()
            d['timer'] = Timer(intv, partial(self.set_connection_timeout, hp=hp))

    def connection_sender_timer_init(self, intv=2.9):
        if self.client_connection_sender_timer:
            self.client_connection_sender_timer.cancel()
        # _LOGGER.debug(f'Rearm timer connect send {intv}')
        self.client_connection_sender_timer = Timer(intv, self.send_client_command_connection)

    def on_connection_timeout(self, hp, timeout):
        if not timeout:
            self.process_cmd_queue()
        if self.user_on_connection_timeout:
            self.user_on_connection_timeout(hp, timeout)

    def on_command_connection(self, hp, portlisten, timeout=False):
        # _LOGGER.debug(f'On command connection type={type(portlisten)}')
        hp = (hp[0], portlisten)
        hpstr = f'{hp[0]}:{hp[1]}'
        send_command = self.hostconnect is None or timeout
        new_connection = not timeout
        rearm_timer = not timeout
        if hpstr not in self.connected_hosts:
            self.connected_hosts[hpstr] = dict(
                hp=hp,
                timeout=timeout,
                timer=None,
                client=SimpleUDPClient(hp[0], hp[1])
            )
            rearm_timer = True
        elif not timeout and self.connected_hosts[hpstr]['timeout']:
            self.connected_hosts[hpstr]['timeout'] = False
            # _LOGGER.debug('Setting timeout to false')
        else:
            new_connection = False
        if new_connection:
            self.on_connection_timeout(hp, False)
            _LOGGER.info(f'Connection to {hp[0]}:{hp[1]} estabilished')
        if send_command:
            # _LOGGER.debug(f'Sending connect command as {"client" if self.hostconnect else "server"} to {hp[0]}:{hp[1]} (port={self.portlisten})')
            self.connected_hosts[hpstr]['client'].send_message(COMMAND_CONNECTION, (self.portlisten,))
        if rearm_timer:
            self.connection_handler_timer_init(hp=hp)

    async def set_connection_timeout(self, hp=None):
        hpstr = f'{hp[0]}:{hp[1]}'
        if hpstr in self.connected_hosts:
            notifytimeout = True
            if self.hostconnect:
                if self.connected_hosts[hpstr]['timeout'] is not True:
                    self.connected_hosts[hpstr]['timeout'] = True
                else:
                    notifytimeout = False
            else:
                del self.connected_hosts[hpstr]
            if notifytimeout:
                self.on_connection_timeout(hp, True)
                _LOGGER.info(f'Connection to {hp[0]}:{hp[1]} lost')

    def deserialize(self, args):
        if len(args) == 1 and args[0] == '()':
            return tuple()
        args = list(args)
        for i, s in enumerate(args):
            args[i] = SerializableDBObj.deserialize(args[i], args[i])
        return tuple(args)

    def device_callback(self, client_address, address, *oscs):
        if address != COMMAND_CONNECTION:
            _LOGGER.debug(f'Received cmd={address} par={str(oscs)}')
        warn = True
        if address in self.callbacks:
            item = None
            if len(oscs) > 0 and isinstance(oscs[0], str) and oscs[0] in self.callbacks[address]:
                _LOGGER.debug(f'Found device command (uid={oscs[0]})')
                item = self.callbacks[address][oscs[0]]
                uid = oscs[0]
                pars = oscs[1:]
                warn = False
            if '' in self.callbacks[address]:
                item = self.callbacks[address]['']
                uid = ''
                pars = oscs
                warn = False
            if item:
                if item['t']:
                    _LOGGER.debug(f'Cancelling unhandle timer add={address} uid={uid}')
                    item['t'].cancel()
                    self.unhandle_device(address, uid)
                try:
                    fixedpars = item['a'] if address != COMMAND_CONNECTION else (client_address,) + item['a']
                    item['f'](*fixedpars, *self.deserialize(pars))
                except Exception:
                    _LOGGER.error(f'Handler({fixedpars}, {pars} [{self.deserialize(pars)}]) error {traceback.format_exc()}')
        if warn:
            _LOGGER.warning(f'Handler not found ({self.callbacks})')

    def call_confirm_callback(self, *args, confirm_callback=None, confirm_params=(), timeout=False, uid=''):
        _LOGGER.debug(f'Calling confirm_callback with cp={confirm_params} args={args}')
        self.unhandle_device(COMMAND_CONFIRM, uid)
        confirm_callback(*confirm_params, *args, timeout=timeout)

    def send_device(self, address, uid, *args, confirm_callback=None, confirm_params=(), timeout=-1):
        if confirm_callback:
            _LOGGER.debug(f'Adding handle for COMMAND_CONFIRM uid={uid} tim={timeout}')
            self.handle_device(
                COMMAND_CONFIRM,
                uid,
                partial(self.call_confirm_callback,
                        uid=uid,
                        confirm_params=confirm_params,
                        confirm_callback=confirm_callback),
                timeout=timeout)
        args = (uid,) + args
        self.send(address, *args)

    def uninit(self):
        if self.transport:
            self.transport.close()
            self.transport = None
        for _, x in self.callbacks.items():
            for _, y in x.items():
                if y['t']:
                    y['t'].cancel()
        for _, x in self.connected_hosts.items():
            if x['timer']:
                x['timer'].cancel()
        if self.client_connection_sender_timer:
            self.client_connection_sender_timer.cancel()
            self.client_connection_sender_timer = None
        self.user_on_connection_timeout = None

    def process_cmd_queue(self):
        if len(self.cmd_queue):
            hpstr = f'{self.hostconnect}:{self.portconnect}'
            if not self.hostconnect or (hpstr in self.connected_hosts and not self.connected_hosts[hpstr]['timeout']):
                el = self.cmd_queue.pop(0)
                args = ('()',) if not el['args'] else el['args']
                for _, d in self.connected_hosts.items():
                    if el['address'] != COMMAND_CONNECTION:
                        _LOGGER.debug(f'Sending[{d["hp"][0]}:{d["hp"][1]}] {el["address"]} -> {args}')
                    d['client'].send_message(el['address'], args)
                self.process_cmd_queue()

    def send(self, address, *args, confirm_callback=None, confirm_params=(), timeout=-1):
        if confirm_callback:
            _LOGGER.debug(f'Adding handle for COMMAND_CONFIRM tim={timeout}')
            self.handle(
                COMMAND_CONFIRM,
                partial(self.call_confirm_callback,
                        uid='',
                        confirm_params=confirm_params,
                        confirm_callback=confirm_callback),
                timeout=timeout)
        args = list(args)
        for i, s in enumerate(args):
            if isinstance(s, SerializableDBObj):
                args[i] = s.serialize()
        self.cmd_queue.append(dict(
            address=address,
            args=tuple(args)
        ))
        self.process_cmd_queue()

    async def unhandle_by_timer(self, address, uid):
        if address in self.callbacks and uid in self.callbacks[address]:
            _LOGGER.debug(f'unhandling by timeout add={address}, uid={uid}')
            item = self.callbacks[address][uid]
            try:
                item['f'](*item['a'], timeout=True)
            except Exception:
                _LOGGER.error(f'Handler error {traceback.format_exc()}')
            _LOGGER.debug(f'Handler exited add={address}, uid={uid}')
            del self.callbacks[address][uid]

    # def some_callback(address: str, *osc_arguments: List[Any]) -> None:
    # def some_callback(address: str, fixed_argument: List[Any], *osc_arguments: List[Any]) -> None:
    def handle_device(self, address, uid, callback, *args, timeout=-1):
        self.unhandle_device(address, uid)
        d = self.callbacks[address] if address in self.callbacks else dict()
        if timeout > 0:
            t = Timer(timeout, partial(self.unhandle_by_timer, address, uid))
        else:
            t = None
        d[uid] = dict(f=callback, a=args, t=t)
        self.callbacks[address] = d
        _LOGGER.debug(f'Handle Added add={address}, uid={uid} timeout={timeout} result={self.callbacks}')

    def unhandle_device(self, address, uid):
        if address in self.callbacks and uid in self.callbacks[address]:
            if self.callbacks[address][uid]['t']:
                self.callbacks[address][uid]['t'].cancel()
            del self.callbacks[address][uid]
            _LOGGER.debug(f'Handle removed add={address}, uid={uid} result={self.callbacks}')

    def handle(self, address, callback, *args, timeout=-1):
        self.handle_device(address, '', callback, *args, timeout=timeout)

    def unhandle(self, address):
        self.unhandle_device(address, '')
