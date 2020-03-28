import abc
from time import time
import traceback

from db.session import Session
from kivy.event import EventDispatcher
from util import init_logger
from util.const import DEVSTATE_INVALIDSTEP

_LOGGER = init_logger(__name__)


class DeviceSimulator(abc.ABC, EventDispatcher):
    __events__ = (
        'on_session',
    )
    @abc.abstractmethod
    def inner_step(self, obj, nowms):
        pass

    def set_offsets(self):
        pass

    @abc.abstractmethod
    def inner_reset(self, conf, userid):
        pass

    def __init__(self, db, deviceid, conf, user, on_session=None, **kwargs):
        super(DeviceSimulator, self).__init__()
        self.db = db
        self.deviceid = deviceid
        if on_session:
            self.bind(on_session=on_session)
        self.reset(conf, user)

    async def step(self, obj):
        try:
            nowms = int(time() * 1000)
            self.log(f'Step ms {nowms}')
            state = self.inner_step(obj, nowms)
            if state != DEVSTATE_INVALIDSTEP:
                if not self.session:
                    self.session = Session(device=self.deviceid, user=self.userid, settings=self.conf, datestart=nowms)
                    if (await self.session.to_db(self.db, True)):
                        self.dispatch("on_session", self.session)
                elif self.main_session_id < 0:
                    self.main_session_id = -self.main_session_id
                    self.session.mainid = self.main_session_id
                    await self.session.to_db(self.db, True)
                self.nUpdates = self.nUpdates + 1
                commit = nowms - self.last_commit > 10000
                await obj.to_db(self.db, commit)
                if commit:
                    self.last_commit = nowms
                obj.s('updates', self.nUpdates)
            return state
        except Exception:
            _LOGGER.error(f'Step error: {traceback.format_exc()}')
            return DEVSTATE_INVALIDSTEP

    def log(self, s):
        _LOGGER.debug("%s: %s" % (self.__class__.__name__, s))

    def on_session(self, session):
        self.log("New session s=%s" % session)

    def set_main_session_id(self, sid):
        self.main_session_id = -sid

    def reset(self, conf, user):
        self.conf = conf
        self.user = user
        self.userid = user.get_id()
        self.nUpdates = 0
        self.state = DEVSTATE_INVALIDSTEP
        self.session = None
        self.lastUpdateTime = 0
        self.main_session_id = 0
        self.last_commit = 0
        self.inner_reset(conf, user)
