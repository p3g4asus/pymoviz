from functools import partial

from db.keiser_m3i_output import KeiserM3iOutput
from db.label_formatter import (DoubleFieldFormatter, SimpleFieldFormatter,
                                TimeFieldFormatter)
from device.simulator.keiser_m3i import \
    KeiserM3iDeviceSimulator
from device.manager import GenericDeviceManager
from util.const import (DEVREASON_REQUESTED, DEVREASON_TIMEOUT,
                        DEVSTATE_CONNECTED, DEVSTATE_CONNECTING,
                        DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_SEARCHING, DI_FIRMWARE, DI_SOFTWARE,
                        DI_SYSTEMID, DI_BLNAME)
from util import init_logger
from util.timer import Timer

_LOGGER = init_logger(__name__)


class KeiserM3iDeviceManager(GenericDeviceManager):
    __type__ = 'keiserm3i'
    __simulator_class__ = KeiserM3iDeviceSimulator
    __formatters__ = dict(
        Speed=DoubleFieldFormatter(
            name='Speed',
            example_conf=dict(speed=25, speedMn=27),
            f1='%.1f',
            f2='%.2f',
            timeout='[color=#f44336]--.- (--.--)Km/h[/color]',
            post='Km/h',
            pre='$D SPD: ',
            fields=['speed', 'speedMn']),
        RPM=DoubleFieldFormatter(
            name='RPM',
            example_conf=dict(rpm=78, rpmMn=75),
            f1='%d',
            f2='%.1f',
            timeout='[color=#f44336]-- (--.-)[/color]',
            post='',
            pre='$D RPM: ',
            fields=['rpm', 'rpmMn']),
        Watt=DoubleFieldFormatter(
            name='Watt',
            example_conf=dict(watt=125, wattMn=127),
            f1='%d',
            f2='%.2f',
            timeout='[color=#f44336]-- (--.--)[/color]',
            post='',
            pre='$D WT: ',
            fields=['watt', 'wattMn']),
        Pulse=SimpleFieldFormatter(
            name='Pulse',
            example_conf=dict(pulse=152, pulseMn=160),
            format_str='%d (%d)',
            timeout='[color=#f44336]-- (--)[/color]',
            pre='$D Pul: ',
            fields=['pulse', 'pulseMn']),
        Distance=SimpleFieldFormatter(
            name='Distance',
            example_conf=dict(distance=34.6),
            format_str='%.2fKm',
            timeout='[color=#f44336]--.--Km[/color]',
            pre='$D Dist: ',
            fields=['distance']),
        Incline=SimpleFieldFormatter(
            name='Incline',
            example_conf=dict(incline=12),
            timeout='[color=#f44336]--[/color]',
            format_str='%d',
            pre='$D Inc: ',
            fields=['incline']),
        Calorie=SimpleFieldFormatter(
            name='Calorie',
            example_conf=dict(calorie=12),
            format_str='%d',
            timeout='[color=#f44336]--[/color]',
            pre='$D Cal: ',
            fields=['calorie']),
        Version=SimpleFieldFormatter(
            name='Version',
            example_conf={
                DI_BLNAME: 'M3i',
                DI_FIRMWARE: 13,
                DI_SOFTWARE: 22,
                DI_SYSTEMID: 40},
            format_str='%s 0x%02X.0x%02X (%d)',
            pre='$D ver: ',
            fields=[DI_BLNAME, DI_FIRMWARE, DI_SOFTWARE, DI_SYSTEMID]),
        Time=TimeFieldFormatter(
            pre='$D TM: '),
        **GenericDeviceManager.__formatters__
    )
    RESCAN_TIMEOUT = 120

    @staticmethod
    def get_machine_id(bt):
        if len(bt) > 6:
            index = 0

            # Moves index past prefix bits (some platforms remove prefix bits from data)
            if bt[index] == 2 and bt[index + 1] == 1:
                index += 2
            return bt[index + 3] & 0xFF
        else:
            return None

    def __init__(self, *args, **kwargs):
        super(KeiserM3iDeviceManager, self).__init__(*args, **kwargs)
        self.force_rescan_timer = None
        self.found_timer = None
        self.disconnect_reason = DEVREASON_REQUESTED

    @classmethod
    def get_scan_settings(cls, scanning_for_new_devices=False):
        if not scanning_for_new_devices:
            return dict(
                scan_mode=2,  # SCAN_MODE_LOW_LATENCY
                match_mode=1,  # MATCH_MODE_AGGRESSIVE
                num_of_matches=3,  # MATCH_NUM_MAX_ADVERTISEMENT
                callback_type=1,  # CALLBACK_TYPE_ALL_MATCHES
                report_delay=0
            )
        else:
            return None

    @classmethod
    def get_scan_filters(cls, scanning_for_new_devices=False):
        # return None
        return [
            dict(deviceName="M3"),
            dict(deviceName="M3i"),
            dict(deviceName="M3s")
        ]

    @classmethod
    def get_settings_widget_class(cls):
        from .keiser_m3i_widget import KeiserM3iConfWidget
        return KeiserM3iConfWidget

    @classmethod
    def device2line3(cls, device):
        ss = ''
        mid = ''
        additionalsettings = device.f('additionalsettings')
        if additionalsettings and 'machine' in additionalsettings:
            mid = additionalsettings['machine']
        else:
            advertisement = device.f('advertisement')
            if advertisement:
                mid = KeiserM3iDeviceManager.get_machine_id(advertisement)
        if mid:
            ss = f'ID={mid} '
        rssi = device.f('rssi')
        return ss + (f'RSSI {rssi}' if rssi else '')

    def found_timer_init(self, timeout=False):
        if self.found_timer:
            self.found_timer.cancel()
            self.found_timer = None
        if timeout:
            self.found_timer = Timer(timeout, self.set_disconnected)

    async def set_disconnected(self):
        if self.state != DEVSTATE_SEARCHING and self.state != DEVSTATE_DISCONNECTING and\
                self.state != DEVSTATE_DISCONNECTED:
            self.rescan_timer_init()
            self.disconnect_reason = DEVREASON_TIMEOUT
            self.set_state(DEVSTATE_DISCONNECTING, self.disconnect_reason)
            self.stop_scan()

    def rescan_timer_init(self, timeout=False):
        if self.force_rescan_timer:
            _LOGGER.info('Stopping rescan timer')
            self.force_rescan_timer.cancel()
            self.force_rescan_timer = None
        if timeout:
            _LOGGER.info(f'Starting rescan timer({timeout})')
            self.force_rescan_timer = Timer(timeout, self.restart_scan)

    async def restart_scan(self):
        _LOGGER.info(f'Rescan timer done: state={self.state}')
        if self.state == DEVSTATE_CONNECTING:
            self.rescan_timer_init()
            self.stop_scan()
        elif self.is_connected_state():
            self.stop_scan()

    def inner_disconnect(self):
        self.rescan_timer_init()
        self.found_timer_init()
        self.disconnect_reason = DEVREASON_REQUESTED
        self.stop_scan()

    def inner_connect(self):
        self.rescan_timer_init(30)
        self.found_timer_init()
        self.start_scan(self.get_scan_settings(), self.get_scan_filters())

    @staticmethod
    def u16_le(l, h):
        return (l & 0xFF) | ((h & 0xFF) << 8)

    def on_scan_completed(self):
        super(KeiserM3iDeviceManager, self).on_scan_completed()
        if self.state == DEVSTATE_DISCONNECTING:
            self.set_state(DEVSTATE_DISCONNECTED, self.disconnect_reason)
        elif self.state == DEVSTATE_CONNECTING:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_TIMEOUT)
        elif self.is_connected_state():
            self.start_scan(self.get_scan_settings(), self.get_scan_filters())
            self.rescan_timer_init(KeiserM3iDeviceManager.RESCAN_TIMEOUT)

    def parse_adv(self, arr):
        if len(arr) < 4 or len(arr) > 19:
            return False
        index = 0
        if arr[index] == 2 and arr[index + 1] == 1:
            index += 2
        mayor = arr[index] & 0xFF
        index += 1
        minor = arr[index] & 0xFF
        index += 1
        if mayor == 0x06 and len(arr) > index + 13:
            k3 = KeiserM3iOutput()
            dt = arr[index] & 0xFF
            if dt == 0 or dt >= 128 or dt <= 227:
                k3.s(DI_FIRMWARE, mayor)
                k3.s(DI_SOFTWARE, minor)
                k3.s(DI_SYSTEMID, arr[index + 1])
            k3.s('orpm', KeiserM3iDeviceManager.u16_le(arr[index + 2], arr[index + 3]))  # / 10;
            k3.s('opul', KeiserM3iDeviceManager.u16_le(arr[index + 4], arr[index + 5]))  # / 10;
            # Power in Watts
            k3.s('owatt', KeiserM3iDeviceManager.u16_le(arr[index + 6], arr[index + 7]))
            # Energy as KCal ("energy burned")
            k3.s('ocal', KeiserM3iDeviceManager.u16_le(arr[index + 8], arr[index + 9]))
            # Time in Seconds (broadcast as minutes and seconds)
            time = (arr[index + 10] & 0xFF) * 60
            time += arr[index + 11]
            k3.s('otime', time)
            dist = KeiserM3iDeviceManager.u16_le(arr[index + 12], arr[index + 13])
            if (dist & 32768):
                dist = (dist & 0x7FFF) / 10.0
            else:
                dist = dist / 10.0 * 1.60934
            if minor >= 0x21 and len(arr) > (index + 14):
                # Raw Gear Value
                inc = arr[index + 14]
            else:
                inc = 0
            k3.s('odist', dist)
            k3.s('oinc', inc)
            return k3
        else:
            return None

    def process_found_device(self, device):
        super(KeiserM3iDeviceManager, self).process_found_device(device)
        _LOGGER.debug(f'process_found_device: state={self.state} addr_my={self.device.get_address()} addr_oth={device.get_address()}')
        if self.state != DEVSTATE_DISCONNECTING:
            if device.get_address() == self.device.get_address():
                if self.state == DEVSTATE_CONNECTING:
                    self.set_state(DEVSTATE_CONNECTED, DEVREASON_REQUESTED)
                    self.rescan_timer_init(KeiserM3iDeviceManager.RESCAN_TIMEOUT)
                if self.state != DEVSTATE_SEARCHING and self.state != DEVSTATE_DISCONNECTING:
                    self.found_timer_init(5)
                    k3 = self.parse_adv(device.advertisement)
                    _LOGGER.debug(f'k3 Parse result {k3}')
                    if k3:
                        Timer(0, partial(self.step, k3))
