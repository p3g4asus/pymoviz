from able import BluetoothDispatcher
from db.keiser_m3i_output import KeiserM3iOutput
from db.label_formatter import (DoubleFieldFormatter, SimpleFieldFormatter,
                                TimeFieldFormatter)
from device.simulator.keiser_m3i import \
    KeiserM3iDeviceSimulator
from device.manager import ConfWidget, GenericDeviceManager
from kivy.lang import Builder
from kivy.utils import platform
from util.const import (DEVREASON_REQUESTED, DEVREASON_TIMEOUT,
                        DEVSTATE_CONNECTED, DEVSTATE_CONNECTING,
                        DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_SEARCHING, DI_FIRMWARE, DI_SOFTWARE,
                        DI_SYSTEMID)
from util.timer import Timer

Builder.load_string(
    '''
<KeiserM3iConfWidget>:
    orientation: 'vertical'
    GridLayout:
        cols: 2
        rows: 5
        MDLabel:
            text: 'Machine ID'
        MDSlider:
            id: id_machine
            min: 1
            max: 254
            value: root.DEFAULT_MACHINE
        MDLabel:
            text: 'Buffer distanza'
        MDSlider:
            id: id_buffer
            min: 1
            max: 1000
            value: root.DEFAULT_BUFFER
    ''')


class KeiserM3iConfWidget(ConfWidget):
    DEFAULT_BUFFER = 150
    DEFAULT_MACHINE = 99

    def is_ok(self):
        return True

    def clear(self):
        self.ids.id_buffer.value = KeiserM3iConfWidget.DEFAULT_BUFFER
        self.ids.id_machine.value = KeiserM3iConfWidget.DEFAULT_MACHINE

    def conf2gui(self, conf):
        if 'buffer' in self.conf:
            self.ids.id_buffer.value = self.conf['buffer']
        if 'machine' in self.conf:
            self.ids.id_machine.value = self.conf['machine']

    def gui2conf(self):
        self.conf['buffer'] = self.ids.id_buffer.value
        self.conf['machine'] = self.ids.id_machine.value
        return self.conf


class KeiserM3iDeviceManager(GenericDeviceManager):
    __type__ = 'keyserm3i'
    __simulator_class__ = KeiserM3iDeviceSimulator
    __label_formatters__ = [
        DoubleFieldFormatter(
            name='Speed',
            example=(25, 27),
            f1='%.1f',
            f2='%.2f',
            post='Km/h',
            pre='$D SPD: ',
            fields=['speed', 'speedMn']),
        DoubleFieldFormatter(
            name='RPM',
            example=(78, 75),
            f1='%d',
            f2='%.1f',
            post='',
            pre='$D RPM: ',
            fields=['rpm', 'rpmMn']),
        DoubleFieldFormatter(
            name='Watt',
            example=(125, 127),
            f1='%d',
            f2='%.2f',
            post='',
            pre='$D WT: ',
            fields=['watt', 'wattMn']),
        SimpleFieldFormatter(
            name='Pulse',
            example=(152, 160),
            format='%d (%d)',
            pre='$D Pul: ',
            fields=['pulse', 'pulseMn']),
        SimpleFieldFormatter(
            name='Distance',
            example=(34.6),
            format='%.2f Km',
            pre='$D Dist: ',
            fields=['distance']),
        SimpleFieldFormatter(
            name='Incline',
            example=(12),
            format='%d',
            pre='$D Inc: ',
            fields=['incline']),
        SimpleFieldFormatter(
            name='Calorie',
            example=(12),
            format='%d',
            pre='$D Cal: ',
            fields=['calorie']),
        SimpleFieldFormatter(
            name='Version',
            example=(13, 22, 40),
            format='0x%02X.0x%02X (%d)',
            pre='$D ver: ',
            fields=['DI_FIRMWARE', 'DI_SOFTWARE', 'DI_SYSTEMID']),
        TimeFieldFormatter(
            name='Time',
            pre='$D TM: ',
            fields=['time'])
    ]

    @classmethod
    def do_activity_pre_operations(cls, on_finish):
        if platform == 'android':
            class PreBluetoothDispatcher(BluetoothDispatcher):
                def __init__(self, on_finish_handler=None, *args, **kwargs):
                    super(PreBluetoothDispatcher, self).__init__(*args, **kwargs)
                    self.on_finish = on_finish_handler

                def on_scan_started(self, success):
                    super(PreBluetoothDispatcher, self).on_scan_started(success)
                    if success:
                        self.stop_scan()
                    else:
                        self.on_finish(cls, False)

                def on_scan_completed(self):
                    self.on_finish(cls, True)
            pbd = PreBluetoothDispatcher(on_finish_handler=on_finish)
            pbd.start_scan()

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
        return [
            dict(deviceName="M3"),
            dict(deviceName="M3i"),
            dict(deviceName="M3s")
        ]

    @classmethod
    def get_settings_widget_class(cls):
        return KeiserM3iConfWidget

    @classmethod
    def device2line3(cls, device):
        ss = ''
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

    def rescan_timer_init(self, timeout=False):
        if self.force_rescan_timer:
            self.self.force_rescan_timer.cancel()
            self.self.force_rescan_timer = None
        if timeout:
            self.force_rescan_timer = Timer(timeout, self.restart_scan)

    async def restart_scan(self):
        if self.state == DEVSTATE_CONNECTING:
            self.rescan_timer_init()
            self.stop_scan()
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_TIMEOUT)
            return
        elif self.is_connected_state():
            self.stop_scan()
        self.start_scan(self.get_scan_settings(), self.get_scan_filters())
        self.rescan_timer_init(1800)

    def inner_disconnect(self):
        self.rescan_timer_init()
        self.stop_scan()

    def inner_connect(self):
        self.rescan_timer_init(30)
        self.start_scan(self.get_scan_settings(), self.get_scan_filters())

    @staticmethod
    def u16_le(l, h):
        return (l & 0xFF) | ((h & 0xFF) << 8)

    def on_scan_completed(self):
        super(KeiserM3iDeviceManager).on_scan_completed()
        if self.state == DEVSTATE_DISCONNECTING:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_REQUESTED)

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

    def on_device(self, device, rssi, advertisement):
        super(KeiserM3iDeviceManager, self).on_device(device, rssi, advertisement)
        if self.state != DEVSTATE_DISCONNECTING:
            if device.getAddress() == self.device.get_address():
                if self.state == DEVSTATE_CONNECTING:
                    self.set_state(DEVSTATE_CONNECTED, DEVREASON_REQUESTED)
                    self.rescan_timer_init(1800)
                if self.state != DEVSTATE_SEARCHING and self.state != DEVSTATE_DISCONNECTING:
                    k3 = self.parse_adv(advertisement)
                    if k3:
                        Timer(0, self.step(k3))
