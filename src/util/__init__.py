import asyncio
import glob
import logging
from logging.handlers import SocketHandler
from os.path import basename, dirname, isfile, join, splitext
import sys
import traceback


async def asyncio_graceful_shutdown(loop, logger, perform_loop_stop=True):
    """Cleanup tasks tied to the service's shutdown."""
    try:
        logger.info("Shutdown: Performing graceful stop")
        tasks = [t for t in asyncio.all_tasks() if t is not
                 asyncio.current_task()]

        [task.cancel() for task in tasks]

        logger.info(f"Shutdown: Cancelling {len(tasks)} outstanding tasks")
        await asyncio.gather(*tasks)
    except (asyncio.exceptions.CancelledError, Exception):
        logger.error(f"Shutdown: {traceback.format_exc()}")
    finally:
        if perform_loop_stop:
            logger.info("Shutdown: Flushing metrics")
            loop.stop()


_loglevel = logging.WARNING
_LOGGERS = dict()
_socket_handler = None


def init_logger(name, level=None, hp=None):
    global _LOGGERS
    global _loglevel
    global _socket_handler
    nm = f'PY_{name}'
    loggerobj = _LOGGERS.get(nm, None)
    if hp is not None and _socket_handler is None:
        _socket_handler = SocketHandler(*hp)
        _socket_handler.setLevel(_loglevel)
        for _, log in _LOGGERS.items():
            log['lo'].addHandler(_socket_handler)
    if level is not None and level != _loglevel:
        _loglevel = level
        if _socket_handler:
            _socket_handler.setLevel(_loglevel)
        for _, log in _LOGGERS.items():
            # print(f'Resetting level {nm} level {_loglevel}')
            log['lo'].setLevel(_loglevel)
            log['ha'].setLevel(_loglevel)
    # print(f'Init logger {name} level {_loglevel}')
    if loggerobj:
        return loggerobj
    _LOGGER = logging.getLogger(nm)
    _LOGGER.setLevel(_loglevel)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(_loglevel)
    _LOGGERS[nm] = dict(lo=_LOGGER, ha=handler)
    # if platform == 'android':
    formatter = logging.Formatter('[%(name)s][%(levelname)s]: %(message)s')
    # else:
    #    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    _LOGGER.addHandler(handler)
    if _socket_handler is not None:
        _LOGGER.addHandler(_socket_handler)
    return _LOGGER


def find_devicemanager_classes(_LOGGER):
    out = dict()
    modules = glob.glob(join(dirname(__file__), "..", "device", "manager", "*.py*"))
    pls = [splitext(basename(f))[0] for f in modules if isfile(f)]
    import importlib
    import inspect
    for x in pls:
        if not x.startswith('__') and not x.endswith('widget'):
            try:
                _LOGGER.info(f'Processing {x}...')
                m = importlib.import_module(f"device.manager.{x}")
                clsmembers = inspect.getmembers(m, inspect.isclass)
                for cla in clsmembers:
                    try:
                        _LOGGER.info(f'...Processing {cla[1]}')
                        typev = getattr(cla[1], '__type__')
                        if typev:
                            out[typev] = cla[1]
                            _LOGGER.info(f'Adding {cla[1]}')
                    except Exception:
                        # _LOGGER.warning(traceback.format_exc())
                        pass
            except Exception:
                _LOGGER.warning(traceback.format_exc())
    return out


def get_natural_color(hex=True):
    from kivy.app import App
    from kivy.utils import get_color_from_hex
    from kivymd.color_definitions import colors
    hexval = '#' + colors[App.get_running_app().theme_cls.theme_style]["Background"]
    return hexval if hex else get_color_from_hex(hexval)


def get_verbosity(config):
    if isinstance(config, str):
        verb = config
    elif isinstance(config, int):
        return config
    else:
        verb = config.get('log', 'verbosity')
    verbosity_table = dict(CRITICAL=logging.CRITICAL,
                           ERROR=logging.ERROR,
                           WARNING=logging.WARNING,
                           INFO=logging.INFO,
                           DEBUG=logging.DEBUG,
                           NOTSET=logging.NOTSET)
    return verbosity_table.get(verb, logging.INFO)
