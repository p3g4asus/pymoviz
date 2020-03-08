import asyncio
import glob
from os.path import basename, dirname, isfile, join, splitext
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
