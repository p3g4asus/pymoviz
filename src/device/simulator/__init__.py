import abc
import logging
from time import time

from db.session import Session
from kivy.event import EventDispatcher
from util.const import DEVSTATE_INVALIDSTEP

_LOGGER = logging.getLogger('PY_' + __name__)


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

    def __init__(self, deviceid, conf, userid, db, **kwargs):
        super(DeviceSimulator, self).__init__(**kwargs)
        self.db = db
        self.deviceid = deviceid
        self.reset(conf, userid)

    async def step(self, obj):
        nowms = int(time() * 1000)
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
        return state

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
        self.db_columns = self.get_db_columns()
        self.db_table = self.get_table_name()
        self.session = None
        self.main_session_id = 0
        self.last_commit = 0
        self.inner_reset(conf, user)
