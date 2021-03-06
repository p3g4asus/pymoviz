import asyncio
import json
import random
import re
import string
from functools import partial
from time import time
import traceback

from db import SerializableDBObj
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient
from util.const import COMMAND_CONFIRM, COMMAND_CONNECTION, COMMAND_SPLIT
from util.timer import Timer
from util import init_logger

_LOGGER = init_logger(__name__)


class OSCManager(object):
    PKT_SPLIT = 65000

    def __init__(self,
                 hostlisten='127.0.0.1',
                 portlisten=33217,
                 hostconnect=None,
                 portconnect=None):
        self.hostlisten = hostlisten
        self.portlisten = portlisten
        self.hostconnect = hostconnect
        self.portconnect = portconnect
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
                   on_init_ok=None,
                   _error_notify=True):
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
            except (Exception, OSError) as exception:
                _LOGGER.error(f"OSC init exception {traceback.format_exc()}")
                if on_init_ok and _error_notify:
                    on_init_ok(exception)
                self.client_connection_sender_timer = Timer(1, partial(
                    self.init,
                    loop=loop,
                    on_connection_timeout=on_connection_timeout,
                    on_init_ok=on_init_ok,
                    _error_notify=False))
                return
            try:
                if on_init_ok:
                    on_init_ok(None)
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

    def on_command_connection(self, hp, portlisten, timeout=False, sender=None):
        # _LOGGER.debug(f'On command connection type={type(portlisten)}')
        conn_from = hp
        hp = (hp[0], portlisten)
        hpstr = f'{hp[0]}:{hp[1]}'
        send_command = self.hostconnect is None or timeout
        new_connection = not timeout
        rearm_timer = not timeout
        if hpstr not in self.connected_hosts:
            self.connected_hosts[hpstr] = dict(
                hp=hp,
                conn_from=conn_from,
                timeout=timeout,
                timer=None,
                client=SimpleUDPClient(hp[0], hp[1])
            )
            rearm_timer = True
        elif not timeout and self.connected_hosts[hpstr]['timeout']:
            self.connected_hosts[hpstr]['timeout'] = False
            self.connected_hosts[hpstr]['conn_from'] = conn_from
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
            _LOGGER.debug(f'Received cmd={address} cla={client_address} par={str(oscs)}')
        warn = True
        uid = ''
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
                if not isinstance(item['split'], bool) and address != COMMAND_SPLIT:
                    if not pars or not isinstance(pars[0], str):
                        return
                    mo = re.search(r'^#([0-9]+)/([0-9]+)#(.*)', pars[0])
                    if mo:
                        n1 = int(mo.group(1))
                        n2 = int(mo.group(2))
                        n3 = item['split']
                        if n1 == n3 + 1 or n1 == n3 or n1 == 1:
                            item['split'] = n1
                            if n1 == 1:
                                item['strsplit'] = mo.group(3)
                            elif n1 == n3 + 1:
                                item['strsplit'] += mo.group(3)
                            self.send(COMMAND_SPLIT, n1, n2, uid=uid)
                            if n1 != n2 and item['t']:
                                item['t'].cancel()
                                item['t'] = Timer(30,
                                                  partial(self.unhandle_by_timer, address, uid))
                        else:
                            return
                        if n1 != n2:
                            return
                        else:
                            item['split'] = 0
                            pars = tuple(json.loads(item['strsplit']))
                    else:
                        _LOGGER.warning('String is not splitted when split expected')
                        return
                if item['t']:
                    _LOGGER.debug(f'Cancelling unhandle timer add={address} uid={uid}')
                    item['t'].cancel()
                    self.unhandle_device(address, uid)
                try:
                    fixedpars = item['a'] if address != COMMAND_CONNECTION else (client_address,) + item['a']
                    item['f'](*fixedpars, *self.deserialize(pars), sender=client_address)
                except Exception:
                    _LOGGER.error(f'Handler({fixedpars}, {pars} [{self.deserialize(pars)}]) error {traceback.format_exc()}')
        if warn:
            _LOGGER.warning(f'Handler not found for {address} (uid={uid}) ({self.callbacks})')

    def call_confirm_callback(self, *args, confirm_callback=None, confirm_params=(), timeout=False, uid='', sender=None):
        _LOGGER.debug(f'Calling confirm_callback with cp={confirm_params} args={args}')
        self.unhandle_device(COMMAND_CONFIRM, uid)
        confirm_callback(*confirm_params, *args, timeout=timeout)

    def send_device(self, address, uid, *args, do_split=False, confirm_callback=None, confirm_params=(), timeout=-1, dest=None):
        args = (uid,) + args
        self.send(address,
                  *args,
                  uid=uid,
                  do_split=do_split,
                  confirm_callback=confirm_callback,
                  confirm_params=confirm_params,
                  timeout=timeout,
                  dest=None)

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
                if 'handles' in el:
                    for p in el['handles']:
                        self.handle_device(p['address'],
                                           p['uid'],
                                           p['callback'],
                                           *p['args'],
                                           **p['kwargs'],
                                           last_sent=time())
                for _, d in self.connected_hosts.items():
                    # if el['address'] != COMMAND_CONNECTION:
                    #     _LOGGER.debug(f'Maybe Sending {el["dest"]} = {hpstr}')
                    if not el['dest'] or d['conn_from'] == el['dest']:
                        if el['address'] != COMMAND_CONNECTION:
                            _LOGGER.debug(f'Sending[{d["hp"][0]}:{d["hp"][1]}] {el["address"]} -> {args}')
                        d['client'].send_message(el['address'], args)
                self.process_cmd_queue()

    def call_split_callback(self, *args, timeout=False, uid='', item=None, last_sent=0, sender=None):
        idx = 0 if not uid else 1
        timeout = timeout or item['splits'] != args[idx + 1] or item['split'] != args[idx + 0]
        return self.send_split(
                       retry=item['retry'],
                       uid=uid,
                       last_sent=last_sent,
                       strsplit=item['strsplit'],
                       split=item['split'],
                       splits=item['splits'],
                       currentsplit='' if not timeout else item['currentsplit'],
                       sendto=item['sendto'],
                       dest=item['dest'])

    def send_split(self,
                   retry=-1,
                   uid='',
                   strsplit='',
                   split=0,
                   splits=0,
                   last_sent=0,
                   currentsplit='',
                   sendto=COMMAND_CONFIRM,
                   dest=None,
                   handles=None):
        if not currentsplit:
            split = split + 1
            if split > splits:
                return False
            retry = 0
            currentsplit = f'#{split}/{splits}#{strsplit[0:OSCManager.PKT_SPLIT]}'
            strsplit = strsplit[OSCManager.PKT_SPLIT:]
        else:
            retry = retry + 1
            _LOGGER.info(f'Timeout detected passed = {time()-last_sent} Split {split} / {splits} Retry {retry}')
            if retry >= 10:
                return False
        args = [uid, currentsplit] if uid else [currentsplit]
        item = dict(timeout=0.5 * (retry + 1),
                    retry=retry,
                    do_split=True,
                    split=split,
                    dest=dest,
                    strsplit=strsplit,
                    currentsplit=currentsplit,
                    splits=splits,
                    sendto=sendto)
        if handles is None:
            handles = []
        handles.append(dict(
                    address=COMMAND_SPLIT,
                    uid=uid,
                    args=(),
                    callback=partial(self.call_split_callback,
                                     uid=uid,
                                     item=item),
                    kwargs=item))
        self.cmd_queue.append(dict(
            address=sendto,
            dest=dest,
            args=tuple(args),
            handles=handles
        ))
        self.process_cmd_queue()
        return True

    def send(self, address, *args, confirm_callback=None, confirm_params=(), do_split=False, timeout=-1, uid='', dest=None):
        if confirm_callback:
            _LOGGER.debug(f'Adding handle for COMMAND_CONFIRM tim={timeout}')
            handles = [dict(
                address=COMMAND_CONFIRM,
                uid=uid,
                callback=partial(
                        self.call_confirm_callback,
                        uid=uid,
                        confirm_params=confirm_params,
                        confirm_callback=confirm_callback),
                kwargs=dict(timeout=timeout, do_split=do_split),
                args=())]
        else:
            handles = []
        args = list(args)
        for i, s in enumerate(args):
            if isinstance(s, SerializableDBObj):
                args[i] = s.serialize()
        if do_split:
            strsplit = json.dumps(args[(1 if uid else 0):])
            n1 = len(strsplit)
            n2 = n1 // OSCManager.PKT_SPLIT + (1 if n1 % OSCManager.PKT_SPLIT else 0)
            self.send_split(
                uid=uid,
                dest=dest,
                strsplit=strsplit,
                splits=n2,
                sendto=address,
                handles=handles)
        else:
            self.cmd_queue.append(dict(
                dest=dest,
                address=address,
                args=tuple(args),
                handles=handles
            ))
            self.process_cmd_queue()

    async def unhandle_by_timer(self, address, uid):
        if address in self.callbacks and uid in self.callbacks[address]:
            _LOGGER.debug(f'unhandling by timeout add={address}, uid={uid}')
            item = self.callbacks[address][uid]
            del self.callbacks[address][uid]
            try:
                if 'last_sent' in item:
                    kwargs = dict(last_sent=item['last_sent'])
                else:
                    kwargs = dict()
                item['f'](*item['a'], timeout=True, **kwargs)
            except Exception:
                _LOGGER.error(f'Handler error {traceback.format_exc()}')
            _LOGGER.debug(f'Handler exited add={address}, uid={uid}')

    # def some_callback(address: str, *osc_arguments: List[Any]) -> None:
    # def some_callback(address: str, fixed_argument: List[Any], *osc_arguments: List[Any]) -> None:
    def handle_device(self, address, uid, callback, *args, timeout=-1, do_split=False, **kwargs):
        self.unhandle_device(address, uid)
        d = self.callbacks[address] if address in self.callbacks else dict()
        if timeout > 0:
            t = Timer(timeout, partial(self.unhandle_by_timer, address, uid))
        else:
            t = None
        if do_split:
            if address == COMMAND_SPLIT:
                kwargs = dict(**kwargs)
            else:
                kwargs = dict(split=0, strsplit='')
        else:
            kwargs = dict(split=False)
        d[uid] = dict(f=callback, a=args, t=t, **kwargs)
        self.callbacks[address] = d
        _LOGGER.debug(f'Handle Added add={address}, uid={uid} timeout={timeout} result={self.callbacks}')

    def unhandle_device(self, address, uid):
        if address in self.callbacks and uid in self.callbacks[address]:
            if self.callbacks[address][uid]['t']:
                self.callbacks[address][uid]['t'].cancel()
            del self.callbacks[address][uid]
            _LOGGER.debug(f'Handle removed add={address}, uid={uid} result={self.callbacks}')

    def handle(self, address, callback, *args, timeout=-1, do_split=False):
        self.handle_device(address, '', callback, *args, timeout=timeout, do_split=do_split)

    def unhandle(self, address):
        self.unhandle_device(address, '')
