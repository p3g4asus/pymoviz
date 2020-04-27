from device.simulator import DeviceSimulator
from util.const import DEVSTATE_DPAUSE, DEVSTATE_INVALIDSTEP, DEVSTATE_ONLINE


class HRDeviceSimulator(DeviceSimulator):
    PAUSE_DELAY_DETECT_THRESHOLD = 10000

    def inner_reset(self, conf, user):
        self.lastStart = -1
        self.timeTotms = 0
        self.sessionStart = 0
        self.nBeats = 0.0
        self.pulseSum = 0
        self.jouleSum = 0
        self.lastTimeTot = 0
        self.wasActive = False
        self.lastUpdateTime = -1
        self.last_w = None
        self.nActiveUpdates = 0

    def inner_step(self, w, nowms):
        active = w.pulse > 0 and w.worn != 0
        w.s('jouleMn', 0)
        w.s('pulseMn', 0)
        w.s('timeR', 0)
        if active:
            if self.sessionStart == 0:
                self.sessionStart = nowms
            if self.lastStart < 0:
                self.lastStart = nowms
            diff = nowms - self.lastStart
            if diff > 0 and (self.lastUpdateTime < 0 or nowms - self.lastUpdateTime < self.PAUSE_DELAY_DETECT_THRESHOLD):
                self.timeTotms = diff
                if self.lastUpdateTime > 0:
                    self.nBeats += w.pulse * ((nowms - self.lastUpdateTime) / 60000.0)
                w.nBeatsR = int(self.nBeats + 0.5)
                self.nActiveUpdates += 1
                self.pulseSum += w.pulse
                if w.joule >= 0:
                    self.jouleSum += w.joule
                    w.jouleMn = self.jouleSum / self.nActiveUpdates
                w.pulseMn = self.pulseSum / self.nActiveUpdates
                w.timeRms = self.lastTimeTot + self.timeTotms
                w.timeRAbsms = nowms - self.sessionStart
                w.timeR = int(w.timeRms / 1000.0 + 0.5)
                self.lastUpdateTime = nowms
                self.last_w = w
            elif diff > 0:
                active = False
        if not active:
            if self.wasActive:
                self.lastStart = -1
                self.lastUpdateTime = -1
                self.lastTimeTot += self.timeTotms
        elif self.last_w:
            w.jouleMn = self.last_w.jouleMn
            w.pulseMn = self.last_w.pulseMn
            w.timeRms = self.last_w.timeRms
            w.timeRAbsms = self.last_w.timeRAbsms
            w.timeR = self.last_w.timeR
        self.wasActive = active
        if self.last_w:
            return DEVSTATE_DPAUSE if not active else DEVSTATE_ONLINE
        else:
            return DEVSTATE_INVALIDSTEP
