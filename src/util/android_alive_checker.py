from kivy.utils import platform
from util.const import PRESENCE_REQUEST_ACTION, PRESENCE_RESPONSE_ACTION
from util.timer import Timer
from util import init_logger

_LOGGER = init_logger(__name__)


class AndroidAliveChecker(object):
    def __init__(self, loop, on_result, timeout=1.2):
        self.timeout = timeout
        self.loop = loop
        self.started = False
        self.on_result = on_result
        self.timer = None
        self.was_started = False
        if platform == 'android':
            from jnius import autoclass
            from android.broadcast import BroadcastReceiver
            self.context = autoclass('org.kivy.android.PythonActivity').mActivity
            self.Intent = autoclass('android.content.Intent')
            self.br = BroadcastReceiver(
                self.on_broadcast, actions=[PRESENCE_RESPONSE_ACTION])
        else:
            self.br = None

    def on_broadcast(self, context, intent):
        _LOGGER.info('Broadcast received')
        self.loop.call_soon_threadsafe(self.on_timeout, False)

    def on_pause(self):
        if self.started:
            self.was_started = self.started
            self.stop()

    def on_resume(self):
        if self.was_started:
            self.start()

    def on_timeout(self, timeout_detected=True):
        _LOGGER.info(f'Presence received = timeout={timeout_detected}')
        self.stop()
        self.on_result(not timeout_detected)

    def start(self, bytimer=False):
        if not self.timer:
            if bytimer:
                self.timer = Timer(bytimer, self.start)
            elif not self.started:
                if self.br:
                    self.br.start()
                    self.context.sendBroadcast(self.Intent(PRESENCE_REQUEST_ACTION))
                    self.started = True
                    self.timer = Timer(self.timeout, self.on_timeout)
                else:
                    self.on_result(False)

    def stop(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.started:
            self.br.stop()
            self.started = False
