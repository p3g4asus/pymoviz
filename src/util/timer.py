import asyncio


class Timer:
    def __init__(self, timeout, callback):
        self._timeout = timeout
        self._callback = callback
        self._task = asyncio.ensure_future(self._job())

    async def _job(self):
        try:
            if self._timeout:
                await asyncio.sleep(self._timeout)
            await self._callback()
            # self._task.set_result(0)
        except Exception:
            # self._task.set_result(ex)
            pass

    def cancel(self):
        if not self._task.done():
            self._task.cancel()
