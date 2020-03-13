import asyncio
import glob
import logging
from os.path import basename, dirname, isfile, join, splitext
import sys
import traceback

from kivy.utils import platform


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


def init_logger(name, level=None):
    if level is not None:
        _loglevel = level
    _LOGGER = logging.getLogger(f'PY_{name}')
    _LOGGER.setLevel(_loglevel)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(_loglevel)
    if platform == 'android':
        formatter = logging.Formatter('[%(name)s][%(levelname)s]: %(message)s')
    else:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    _LOGGER.addHandler(handler)
    return _LOGGER


def find_devicemanager_classes(_LOGGER):
    out = dict()
    modules = glob.glob(join(dirname(__file__), "..", "util", "manager", "*.py*"))
    pls = [splitext(basename(f))[0] for f in modules if isfile(f)]
    import importlib
    import inspect
    for x in pls:
        try:
            m = importlib.import_module("common.manager." + x)
            clsmembers = inspect.getmembers(m, inspect.isclass)
            for cla in clsmembers:
                typev = getattr(cla, '__type__')
                if typev:
                    out[typev] = cla
        except Exception:
            _LOGGER.warning(traceback.format_exc())
    return out
