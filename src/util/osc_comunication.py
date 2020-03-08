import asyncio
import logging
import random
import string
from functools import partial

from db import SerializableDBObj
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient
from util.const import COMMAND_CONFIRM, COMMAND_PING
from util.timer import Timer

_LOGGER = logging.getLogger('PY_' + __name__)


class OSCManager(object):
    def __init__(self,
                 hostlisten='127.0.0.1',
                 portlisten=33217,
                 hostcommand='127.0.0.1',
                 portcommand=33218):
        self.hostlisten = hostlisten
        self.hostcommand = hostcommand
        self.portlisten = portlisten
        self.portcommand = portcommand
        self.on_init_ok = None
        self.client = None
        self.server = None
        self.transport = None
        self.protocol = None
        self.dispatcher = Dispatcher()
        self.ping = None
        self.ping_timeout = None
        self.user_on_ping_timeout = None
        self.callbacks = dict()
        self.cmd_queue = []

    @staticmethod
    def generate_uid():
        return ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(16))

    async def init(self,
                   loop=asyncio.get_event_loop(),
                   pingsend=False,
                   on_ping_timeout=None,
                   on_init_ok=None):
        if not self.transport:
            try:
                self.user_on_ping_timeout = on_ping_timeout
                self.server = AsyncIOOSCUDPServer(
                    (self.hostlisten, self.portlisten),
                    self.dispatcher, loop)
                if self.ping:
                    self.ping = None
                self.dispatcher.map('/device*', self.device_callback)
                self.transport, self.protocol = await self.server.create_serve_endpoint()
                self.client = SimpleUDPClient(self.hostcommand, self.portcommand)
            except (Exception, OSError):
                self.ping = Timer(1, partial(
                    self.init,
                    loop=loop,
                    ping=pingsend,
                    on_ping_timeout=on_ping_timeout,
                    on_init_ok=on_init_ok))
                return
            if on_init_ok:
                on_init_ok()
            if pingsend:
                self.ping_sender_timer_init(0)
            else:
                self.ping_handler_timer_init()
                self.ping_timeout = None
                self.handle(COMMAND_PING, self.on_command_ping)

    async def send_command_ping(self):
        self.send(COMMAND_PING)
        self.ping_sender_timer_init()

    def ping_handler_timer_init(self, intv=6):
        if self.ping:
            self.ping.cancel()
        self.ping = Timer(intv, self.set_ping_timeout)

    def ping_sender_timer_init(self, intv=2.9):
        if self.ping:
            self.ping.cancel()
        self.ping = Timer(intv, self.send_command_ping)

    def on_ping_timeout(self, timeout):
        if not timeout:
            self.process_cmd_queue()
        if self.user_on_ping_timeout:
            self.user_on_ping_timeout(timeout)

    def on_command_ping(self):
        if self.ping_timeout is not False:
            self.ping_timeout = False
            self.on_ping_timeout(False)
        self.ping_handler_timer_init()

    async def set_ping_timeout(self):
        self.ping_timeout = True
        self.on_ping_timeout(True)

    def deserialize(self, args):
        for i, s in enumerate(args):
            args[i] = SerializableDBObj.deserialize(args[i], args[i])
        return args

    def device_callback(self, address, *oscs):
        _LOGGER.debug(f'Received cmd={address} par={str(oscs)}')
        if address in self.callbacks:
            warn = True
            if len(oscs) > 0 and isinstance(oscs[0], str) and oscs[0] in self.callbacks[address]:
                _LOGGER.warning(f'Found device command (uid={oscs[0]})')
                item = self.callbacks[address][oscs[0]]
                item['f'](*item['a'], *self.deserialize(oscs[1:]))
                uid = oscs[0]
                warn = False
            if '' in self.callbacks[address]:
                item = self.callbacks[address]['']
                item['f'](*item['a'], *self.deserialize(oscs))
                uid = ''
                warn = False
            if warn:
                _LOGGER.warning('Handler not found')
            elif item['t']:
                item['t'].cancel()
                self.unhandle_device(address, uid)

    def call_confirm_callback(self, exitv, *args, confirm_callback=None, confirm_params=(), timeout=False, uid=''):
        self.unhandle_device(COMMAND_CONFIRM, uid)
        confirm_callback(*confirm_params, exitv, *args, timeout=timeout)

    def send_device(self, address, uid, *args, confirm_callback=None, confirm_params=(), timeout=-1):
        if confirm_callback:
            self.handle_device(
                COMMAND_CONFIRM,
                uid,
                partial(self.call_confirm_callback,
                        uid=uid,
                        confirm_params=confirm_params,
                        confirm_callback=confirm_callback),
                timeout=timeout)
        args.insert(0, uid)
        self.send(address, *args)

    def uninit(self):
        if self.transport:
            self.transport.close()
            self.transport = None
        for _, x in self.callbacks.items():
            for _, y in x.items():
                if y['t']:
                    y['t'].cancel()
        if self.ping:
            self.ping.cancel()
            self.ping = None
        self.user_on_ping_timeout = None

    def process_cmd_queue(self):
        if len(self.cmd_queue):
            if self.ping_timeout is False:
                el = self.cmd_queue.pop(0)
                self.client.send_message(el['address'], *el['args'])
                self.process_cmd_queue()

    def send(self, address, *args, confirm_callback=None, confirm_params=(), timeout=-1):
        if confirm_callback:
            self.handle(
                COMMAND_CONFIRM,
                partial(self.call_confirm_callback,
                        uid='',
                        confirm_params=confirm_params,
                        confirm_callback=confirm_callback),
                timeout=timeout)
        for i, s in enumerate(args):
            if isinstance(s, SerializableDBObj):
                args[i] = s.serialize()
        self.cmd_queue.append(dict(
            address=address,
            args=args
        ))
        self.process_cmd_queue()

    async def unhandle_by_timer(self, address, uid):
        if address in self.callbacks and uid in self.callbacks[address]:
            item = self.callbacks[address][uid]
            item['f'](*item['a'], timeout=True)
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

    def unhandle_device(self, address, uid):
        if address in self.callbacks and uid in self.callbacks[address]:
            if self.callbacks[address][uid]['t']:
                self.callbacks[address][uid]['t'].cancel()
            del self.callbacks[address][uid]

    def handle(self, address, callback, *args, timeout=-1):
        self.handle_device(address, '', callback, *args, timeout=timeout)

    def unhandle(self, address, callback):
        self.unhandle_device(address, '')
