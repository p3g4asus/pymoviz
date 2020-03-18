import asyncio
import glob
import logging
from os.path import basename, dirname, isfile, join, splitext
import sys
import traceback


async def asyncio_graceful_shutdown(loop, logger, perform_loop_stop=True):
    """Cleanup tasks tied to the service's shutdown."""
    try:
        logger.debug("Shutdown: Performing graceful stop")
        tasks = [t for t in asyncio.all_tasks() if t is not
                 asyncio.current_task()]

        [task.cancel() for task in tasks]

        logger.debug(f"Shutdown: Cancelling {len(tasks)} outstanding tasks")
        await asyncio.gather(*tasks)
    except Exception:
        import traceback
        logger.error("Shutdown: " + traceback.format_exc())
    finally:
        if perform_loop_stop:
            logger.debug("Shutdown: Flushing metrics")
            loop.stop()


_loglevel = logging.WARNING
_LOGGERS = dict()
_socket_handler = None


def init_logger(name, level=None, hp=None):
    global _LOGGERS
    global _loglevel
    global _socket_handler
    if hp is not None and _socket_handler is None:
        _socket_handler = logging.handlers.SocketHandler(*hp)
        _socket_handler.setLevel(_loglevel)
        for _, log in _LOGGERS.items():
            log['lo'].addHandler(_socket_handler)
    if level is not None:
        _loglevel = level
        if _socket_handler:
            _socket_handler.setLevel(_loglevel)
        for _, log in _LOGGERS.items():
            log['lo'].setLevel(_loglevel)
            log['ha'].setLevel(_loglevel)
    nm = f'PY_{name}'
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
                _LOGGER.debug(f'Processing {x}...')
                m = importlib.import_module(f"device.manager.{x}")
                clsmembers = inspect.getmembers(m, inspect.isclass)
                for cla in clsmembers:
                    try:
                        _LOGGER.debug(f'...Processing {cla[1]}')
                        typev = getattr(cla[1], '__type__')
                        if typev:
                            out[typev] = cla[1]
                            _LOGGER.debug(f'Adding {cla[1]}')
                    except Exception:
                        # _LOGGER.warning(traceback.format_exc())
                        pass
            except Exception:
                _LOGGER.warning(traceback.format_exc())
    return out
