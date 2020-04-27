from time import time
import traceback

from device.simulator import DeviceSimulator
from util.const import DEVSTATE_DPAUSE, DEVSTATE_INVALIDSTEP, DEVSTATE_ONLINE


class KeiserM3iDeviceSimulator(DeviceSimulator):
    EQUAL_TIME_THRESHOLD = 8
    VALID_PULSE_THRESHOLD = 50
    PAUSE_DELAY_DETECT_THRESHOLD = 10000

    def _set_offsets(self):
        self.time_o = self.time_old
        self.calorie_o = self.calorie_old
        self.distance_o = self.distance_old

    def fillTimeRFields(self, f, updateTime):
        f.timeRms = self.sumTime
        f.timeRAbsms = updateTime - (self.session.datestart if self.session else 0)
        f.timeR = int(self.sumTime / 1000.0 + 0.5)

    def inner_reset(self, conf, user):
        self.buffSize = conf['buffer']
        self.dist_buff = [0.0] * self.buffSize
        self.dist_buff_time = [0] * self.buffSize
        self.dist_buff_idx = 0
        self.dist_buff_size = 0
        self.dist_acc = 0.0
        self.old_dist = -1.0
        self.timeRms_acc = 0
        self.old_timeRms = 0
        self.time_o = 0
        self.time_old = 0
        self.calorie_o = 0
        self.calorie_old = 0
        self.distance_o = 0.0
        self.distance_old = 0.0
        self.nPulses = 0
        self.sumWatt = 0
        self.sumTime = 0
        self.sumSpeed = 0.0
        self.sumPulse = 0
        self.sumRpm = 0
        self.lastUpdatePostedTime = 0
        self.equalTime = 0
        self.old_time_orig = -1
        self.nActiveUpdates = 0

    def calcSpeed(self, f, pause):
        realdist = f.distance + self.distance_o
        realtime = f.time + self.time_o
        if self.old_dist < 0:
            self.old_dist = realdist
            self.old_timeRms = realtime
            self.log(f"Init: old_dist = {realdist} old_time = {realtime}")
            f.speed = 0
            self.lastUpdatePostedTime = f.timeRAbsms
        else:
            logv = ''
            acc_time = realtime - self.old_timeRms
            acc = realdist - self.old_dist
            if not pause and (acc > 1e-6 or acc_time > 0):
                rem = 0.0
                rem_time = 0
                if self.dist_buff_size == self.buffSize:
                    if self.dist_buff_idx == self.buffSize:
                        self.dist_buff_idx = 0
                    rem = self.dist_buff[self.dist_buff_idx]
                    self.dist_acc -= rem
                    rem_time = self.dist_buff_time[self.dist_buff_idx]
                    self.timeRms_acc -= rem_time
                else:
                    self.dist_buff_size += 1
                self.dist_buff_time[self.dist_buff_idx] = acc_time
                self.dist_buff[self.dist_buff_idx] = acc
                self.dist_buff_idx += 1
                self.dist_acc += acc
                self.timeRms_acc += acc_time
                self.lastUpdatePostedTime = f.timeRAbsms

                self.old_dist = realdist
                self.old_timeRms = realtime
                logv = f"D = ({realdist},{acc}->{rem},{self.dist_acc}) T = ({realtime},{acc_time}->{rem_time},{self.timeRms_acc}) => "
            else:
                if f.timeRAbsms - self.lastUpdatePostedTime >= 1000:
                    self.lastUpdatePostedTime = f.timeRAbsms
                logv = f"P D = ({realdist},- -> -,{self.dist_acc}) T = ({realtime} ,- -> -,{self.timeRms_acc}) => "

            if self.timeRms_acc == 0:
                f.speed = 0
            else:
                f.speed = self.dist_acc / (self.timeRms_acc / 3600.00)
            self.log(logv + str(f.speed))
        return f.speed

    def inPause(self):
        return self.equalTime >= self.EQUAL_TIME_THRESHOLD or time() * 1000 - self.lastUpdateTime >= self.PAUSE_DELAY_DETECT_THRESHOLD

    def detectPause(self, f):
        if f.time == self.old_time_orig:
            if self.equalTime < self.EQUAL_TIME_THRESHOLD:
                self.equalTime += 1
            self.log(f"EqualTime {self.equalTime}")
        else:
            self.equalTime = 0
            self.old_time_orig = f.time

    def inner_step(self, f, nowms):
        try:
            if self.old_time_orig > f.time:
                self._set_offsets()
            f.s('pulseMn', 0.0)
            f.s('rpmMn', 0.0)
            f.s('speedMn', 0.0)
            f.s('wattMn', 0.0)
            out = self.step_cyc(f, nowms)
            f.pulse //= 10
            f.pulseMn /= 10.0
            f.rpm //= 10
            f.rpmMn /= 10.0
            self.log(f"Returning {out}")
            return out
        except Exception:
            self.error(f'Step error {traceback.format_exc()}')
            return DEVSTATE_INVALIDSTEP

    def step_cyc(self, f, nowms):
        now = nowms
        wasinpause = self.inPause()
        self.detectPause(f)
        if not wasinpause and not self.inPause():
            self.sumTime += (now - self.lastUpdateTime)
            self.fillTimeRFields(f, now)
            self.nActiveUpdates += 1
            self.sumSpeed += self.calcSpeed(f, False)
            self.sumRpm += f.rpm
            self.sumWatt += f.watt
            if f.pulse > self.VALID_PULSE_THRESHOLD:
                self.sumPulse += f.pulse
                self.nPulses += 1
        else:
            self.fillTimeRFields(f, now)
            self.calcSpeed(f, True)
        if self.nPulses > 0:
            f.pulseMn = self.sumPulse / self.nPulses
        if self.nActiveUpdates > 0:
            f.rpmMn = self.sumRpm / self.nActiveUpdates
            f.wattMn = self.sumWatt / self.nActiveUpdates
            f.speedMn = self.sumSpeed / self.nActiveUpdates
            if self.sumTime <= 0:
                f.distanceR = 0.0
            else:
                f.distanceR = f.speedMn * (self.sumTime / 3600000.0)
        f.time += self.time_o
        f.calorie += self.calorie_o
        f.distance += self.distance_o
        self.time_old = f.time
        self.calorie_old = f.calorie
        self.distance_old = f.distance
        self.lastUpdateTime = now
        return DEVSTATE_DPAUSE if self.inPause() else DEVSTATE_ONLINE
