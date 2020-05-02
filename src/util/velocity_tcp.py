import asyncio
import re
import traceback
from functools import partial
from os.path import basename, dirname

from airspeed import CachingFileLoader
from util import init_logger
import util.const
from util.timer import Timer

_LOGGER = init_logger(__name__)


class VelocityUtils(object):
    @staticmethod
    def format(s, *args):
        return s % args

    @staticmethod
    def print_time(tm):
        hrs = tm // 3600
        tm -= hrs * 3600
        mins = tm // 60
        tm -= mins * 60
        secs = tm % 60
        return '%d:%02d:%02d' % (hrs, mins, secs)


class TcpClient(asyncio.Protocol):
    RECONNECT_INTERVAL = 5.0
    _STASTR = '_________sta_________'
    _STOSTR = '_________sto_________'
    _OPEN_CLIENTS = dict()
    _LOCK = asyncio.Lock()
    _LOADER = None
    _TIMEOUTS = dict()
    _DEFAULT_VARS = dict(const=util.const,
                         devs=dict(),
                         util=VelocityUtils,
                         stastr=_STASTR,
                         stostr=_STOSTR,
                         macros=dict(),
                         logger=_LOGGER,
                         aliases=[])
    _VARS = _DEFAULT_VARS.copy()

    @staticmethod
    def reset_templates():
        dest = TcpClient._DEFAULT_VARS.copy()
        for _, tcp in TcpClient._OPEN_CLIENTS.copy().items():
            if tcp['obj']:
                dest[tcp['obj'].vm_var] = dict(macro=0)
        TcpClient._VARS = dest

    @staticmethod
    async def set_open_clients(hp, dct, action=None):
        hpstr = f'{hp[0]}:{hp[1]}'
        async with TcpClient._LOCK:
            if not dct:
                if hpstr in TcpClient._OPEN_CLIENTS:
                    del TcpClient._OPEN_CLIENTS[hpstr]
            else:
                if hpstr not in TcpClient._OPEN_CLIENTS:
                    TcpClient._OPEN_CLIENTS[hpstr] = dict()
                TcpClient._OPEN_CLIENTS[hpstr].update(dct)
        if action:
            action()

    @staticmethod
    def load_template(template_file, vm_var, **kwargs):
        if TcpClient._LOADER is None:
            dir = dirname(template_file)
            TcpClient._LOADER = CachingFileLoader(dir)
        if vm_var not in TcpClient._VARS:
            TcpClient._VARS[vm_var] = dict(macro=0, **kwargs)
        return TcpClient._LOADER.load_template(template_file)

    def __init__(self,
                 hp=None,
                 template_file=None,
                 loop=asyncio.get_event_loop(),
                 write_out=None,
                 *args, **kwargs):
        self.transport = None
        if hp is None:
            hp = (template_file, 0)
        self.hp = hp
        self.loop = loop
        self.template_file = template_file
        self.vm_var = f'_{basename(template_file)[:-3]}_m'
        self.template = TcpClient.load_template(template_file, self.vm_var, **kwargs)
        self.stopped = False
        self.stop_event = asyncio.Event()
        self.write_out = write_out if write_out else self._network_write
        Timer(0, partial(TcpClient.set_open_clients, hp, dict(obj=self)))
        super(TcpClient, self).__init__()

    def get_var(self, v):
        if v is None:
            return self._VARS[self.vm_var]
        else:
            return self._VARS[self.vm_var].get(v)

    @staticmethod
    def set_timeout(alias):
        TcpClient._VARS[alias]['fitobj'] = None

    @staticmethod
    def update_namespace(devobj, **kwargs):
        v = TcpClient._VARS
        alias = None
        if devobj:
            alias = devobj.get_alias()
            if alias not in v:
                v[alias] = dict()
                v['devs'][alias] = v[alias]
                TcpClient._VARS['aliases'].append(alias)
            v = v[alias]
        for key, value in kwargs.items():
            if key == 'fitobj' and alias:
                if alias in TcpClient._TIMEOUTS:
                    TcpClient._TIMEOUTS[alias].cancel()
                TcpClient._TIMEOUTS[alias] = Timer(5, partial(TcpClient.set_timeout, alias))
            v[key] = value
        return TcpClient._VARS

    @staticmethod
    def format(devobj, **kwargs):
        dictvars = TcpClient.update_namespace(devobj, **kwargs)
        for _, tcp in TcpClient._OPEN_CLIENTS.copy().items():
            if tcp['obj']:
                tcp['obj']._format(dictvars)
        return dictvars

    def _format(self, dct):
        if not self.stopped:
            rv = ''
            if self.template:
                try:
                    _LOGGER.debug(f'Merging {self.vm_var} with {dct}')
                    out = self.template.merge(dct, loader=self._LOADER)
                    if 'stastr' in dct[self.vm_var] and 'stostr' in dct[self.vm_var]:
                        stastr = dct[self.vm_var]['stastr']
                        stostr = dct[self.vm_var]['stostr']
                        while True:
                            mo = re.search(stastr + r'[\n\r]*', out)
                            if mo:
                                out = out[mo.end():]
                            else:
                                break
                            mo = re.search(stostr + r'[\n\r]*', out)
                            if mo:
                                rv += out[:mo.start()]
                                out = out[mo.end():]
                            else:
                                break
                    else:
                        rv = out
                except Exception:
                    _LOGGER.error(f'VTL error {traceback.format_exc()}')
                # self._VARS[self.vm_var] = 1
            if rv:
                self.write_out(rv)

    def _network_write(self, out):
        if self.transport:
            self.transport.write(out.encode())

    def connection_made(self, transport):
        self.transport = transport
        _LOGGER.info(f'Connection to {self.hp[0]}:{self.hp[1]} estabilished')

    def data_received(self, data):
        _LOGGER.debug(f'Data received {data.decode()}')

    def send_data_to_tcp(self, data):
        self.transport.write(data.encode())

    def _stop(self):
        _LOGGER.info('Stop called')
        self.stopped = True
        if self.transport:
            try:
                self.transport.close()
            except Exception:
                pass
            finally:
                self.transport = None

    @staticmethod
    async def stop(hp):
        async with TcpClient._LOCK:
            hpstr = f'{hp[0]}:{hp[1]}'
            if hpstr in TcpClient._OPEN_CLIENTS:
                dd = TcpClient._OPEN_CLIENTS[hpstr]
                dd['stopped'] = True
                dd['timer'].cancel()
                await dd['event'].wait()
                if dd['obj']:
                    dd['obj']._stop()
                    try:
                        asyncio.wait_for(dd['obj'].stop_event.wait(), 7.0)
                    except Exception:
                        _LOGGER.warning(f'Timeout waiting for {hpstr} stop')
                del TcpClient._OPEN_CLIENTS[hpstr]

    @staticmethod
    async def init_connectors_async(loop, connectors_info):
        for ci in connectors_info:
            _LOGGER.info(f'Init connectors {ci["hp"][0]}:{ci["hp"][1]} ({ci["temp"]})')
            await TcpClient.do_connect(ci['hp'], loop, ci['temp'])

    @staticmethod
    async def _do_connect(hp, loop, template_file):
        dd = None
        async with TcpClient._LOCK:
            dd = TcpClient._OPEN_CLIENTS[f'{hp[0]}:{hp[1]}']
        try:
            _LOGGER.debug(f'Trying to _TCPconnect {hp[0]}:{hp[1]} ({template_file})')
            await asyncio.wait_for(
                loop.create_connection(
                    partial(TcpClient,
                            hp=hp,
                            loop=loop,
                            template_file=template_file), hp[0], hp[1]), 7.0)
        except asyncio.CancelledError:
            pass
        except (OSError, Exception):
            if not dd['stopped']:
                _LOGGER.debug(f'Error connecting to {hp[0]}:{hp[1]}: {traceback.format_exc()}')
                dd['timer'] = Timer(
                    TcpClient.RECONNECT_INTERVAL,
                    partial(TcpClient._do_connect,
                            hp,
                            loop,
                            template_file))
                return
        dd['event'].set()

    @staticmethod
    async def do_connect(hp, loop, template_file, intv=0):
        try:
            hpstr = f'{hp[0]}:{hp[1]}'
            _LOGGER.debug(f'Trying to TCPconnect {hpstr} ({template_file})')
            connect = False
            async with TcpClient._LOCK:
                if hpstr not in TcpClient._OPEN_CLIENTS:
                    TcpClient._OPEN_CLIENTS[hpstr] =\
                             dict(stopped=False,
                                  obj=None,
                                  event=asyncio.Event(),
                                  timer=None)
                    connect = True
            if connect:
                await TcpClient._do_connect(
                                      hp,
                                      loop,
                                      template_file)
        except Exception:
            _LOGGER.error(f'do_conn exception {traceback.format_exc()}')

    def on_connection_lost_done(self):
        hpstr = f'{self.hp[0]}:{self.hp[1]}'
        _LOGGER.info(f'Connection to {hpstr} LOST')
        if self.stopped:
            _LOGGER.info(f'{hpstr} Stopped: exiting')
            self.stop_event.set()
        else:
            _LOGGER.info(f'{hpstr} Trying to reconnect in {self.RECONNECT_INTERVAL}s')
            self.stop_event.set()
            Timer(self.RECONNECT_INTERVAL, partial(self.do_connect, self.hp, self.loop, self.template_file))

    def connection_lost(self, exc):
        self.transport = None
        Timer(0, partial(TcpClient.set_open_clients, self.hp, None, self.on_connection_lost_done))
