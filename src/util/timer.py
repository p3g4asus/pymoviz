import asyncio
from functools import partial


class Timer:
    def __init__(self, timeout, callback, loop=None):
        self._timeout = timeout
        self._callback = callback
        self._task = asyncio.ensure_future(self._job(), loop=loop)
        fname = callback.__name__ if not isinstance(callback, partial) else callback.func.__name__
        self._task.name = f'_timer_{fname}'

    @staticmethod
    def task_is_timer(task):
        return hasattr(task, 'name') and task.name.startswith('_timer_')

    async def _job(self):
        try:
            if self._timeout:
                await asyncio.sleep(self._timeout)
            await self._callback()
            # self._task.set_result(0)
        except (asyncio.CancelledError, Exception):
            # self._task.set_result(ex)
            pass

    def cancel(self):
        if not self._task.done():
            self._task.cancel()
