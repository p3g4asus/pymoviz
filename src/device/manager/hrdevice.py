from functools import partial

from db.hrdevice_output import HRDeviceOutput
from db.label_formatter import (DoubleFieldFormatter, SimpleFieldFormatter, TimeFieldFormatter)
from device.manager.gatt import GattDeviceManager, UuidBundle
from device.simulator.hrdevice import HRDeviceSimulator
from util.const import (DI_FIRMWARE, DI_SOFTWARE,
                        DI_HARDWARE, DI_SERIAL_NUMBER, DI_MODEL,
                        DI_MANUFACTURER, DI_BLNAME, DI_BATTERY,
                        BluetoothGattCharacteristic, BluetoothGattService,
                        GattUtils)
from util import init_logger
from util.timer import Timer

_LOGGER = init_logger(__name__)


class HRDeviceManager(GattDeviceManager):
    __simulator_class__ = HRDeviceSimulator
    __output_class__ = HRDeviceOutput
    __type__ = 'hrdevice'
    __formatters__ = dict(
        Pulse=DoubleFieldFormatter(
            name='Pulse',
            example_conf=dict(pulse=130, pulseMn=127.3),
            f1='%d',
            f2='%.1f',
            timeout='[color=#f44336]--- (---.-)[/color]',
            post='',
            pre='$D HR: ',
            fields=['pulse', 'pulseMn']),
        Joule=DoubleFieldFormatter(
            name='Joule',
            example_conf=dict(joule=1200, jouleMn=1342),
            f1='%d',
            f2='%.1f',
            timeout='[color=#f44336]---- (----.-)[/color]',
            post='',
            pre='$D Jou: ',
            fields=['joule', 'jouleMn']),
        Battery=SimpleFieldFormatter(
            name='Battery',
            example_conf={DI_BATTERY: 12},
            format_str='%d',
            timeout='[color=#f44336]---[/color]',
            pre='$D Bat: ',
            fields=[DI_BATTERY]),
        Version=SimpleFieldFormatter(
            name='Version',
            example_conf={
                DI_BLNAME: 'HR',
                DI_MANUFACTURER: 'Polar',
                DI_MODEL: 'HR Device',
                DI_SERIAL_NUMBER: '2u8uenjn',
                DI_HARDWARE: '30',
                DI_FIRMWARE: '20',
                DI_SOFTWARE: '10'},
            format_str='%s (%s - %s - %s) %s.%s.%s',
            pre='$D ver: ',
            fields=[DI_BLNAME,
                    DI_MANUFACTURER,
                    DI_MODEL,
                    DI_SERIAL_NUMBER,
                    DI_HARDWARE,
                    DI_FIRMWARE,
                    DI_SOFTWARE]),
        Time=TimeFieldFormatter(
            fields=['%ttimeR'],
            example_conf=dict(timeR=432),
            pre='$D TM: '),
        **GattDeviceManager.__formatters__
    )

    __notification_formatter__ = SimpleFieldFormatter(
        pre='',
        name='NotificationFormatter',
        example_conf=dict(time=875, pulse=98, joule=1436),
        format_str='%d:%02d:%02d %2d %4d',
        timeout='-:--:-- --- ----',
        col='',
        fields=['%ttimeR', 'pulse', 'joule']
    )
    __info_fields__ = (DI_BLNAME,
                       DI_BATTERY,
                       DI_MANUFACTURER,
                       DI_MODEL,
                       DI_SERIAL_NUMBER,
                       DI_HARDWARE,
                       DI_FIRMWARE,
                       DI_SOFTWARE,
                       '_new_')

    def set_info_field_c(self, characteristic, uuid=None, field=DI_MODEL):
        data = characteristic.getValue()
        if uuid.characteristic_id != BluetoothGattCharacteristic.BATTERY_LEVEL:
            conv = ''
            for c in data:
                if c:
                    conv += chr(c)
                elif conv:
                    self.info_fields[field] = conv
                    self.info_fields['_new_'] = True
                    return conv
        else:
            self.info_fields[field] = data[0]
            self.info_fields['_new_'] = True
            return data[0]

    def get_read_once_characteristics(self):
        rv = dict()
        u = UuidBundle(BluetoothGattService.DEVICE_INFORMATION,
                       BluetoothGattCharacteristic.MANUFACTURER_NAME_STRING,
                       partial(self.set_info_field_c, field=DI_MANUFACTURER))
        rv[u.key()] = u
        u = UuidBundle(BluetoothGattService.DEVICE_INFORMATION,
                       BluetoothGattCharacteristic.HARDWARE_REVISION_STRING,
                       partial(self.set_info_field_c, field=DI_HARDWARE))
        rv[u.key()] = u
        u = UuidBundle(BluetoothGattService.DEVICE_INFORMATION,
                       BluetoothGattCharacteristic.MODEL_NUMBER_STRING,
                       partial(self.set_info_field_c, field=DI_MODEL))
        rv[u.key()] = u
        u = UuidBundle(BluetoothGattService.DEVICE_INFORMATION,
                       BluetoothGattCharacteristic.SERIAL_NUMBER_STRING,
                       partial(self.set_info_field_c, field=DI_SERIAL_NUMBER))
        rv[u.key()] = u
        u = UuidBundle(BluetoothGattService.DEVICE_INFORMATION,
                       BluetoothGattCharacteristic.FIRMWARE_REVISION_STRING,
                       partial(self.set_info_field_c, field=DI_FIRMWARE))
        rv[u.key()] = u
        u = UuidBundle(BluetoothGattService.DEVICE_INFORMATION,
                       BluetoothGattCharacteristic.SOFTWARE_REVISION_STRING,
                       partial(self.set_info_field_c, field=DI_SOFTWARE))
        rv[u.key()] = u
        u = UuidBundle(BluetoothGattService.BATTERY_SERVICE,
                       BluetoothGattCharacteristic.BATTERY_LEVEL,
                       partial(self.set_info_field_c, field=DI_BATTERY))
        rv[u.key()] = u
        return rv

    def get_notify_characteristics(self):
        rv = dict()
        u = UuidBundle(BluetoothGattService.HEART_RATE,
                       BluetoothGattCharacteristic.HEART_RATE_MEASUREMENT,
                       self.parse_heart_rate)
        rv[u.key()] = u
        return rv

    def parse_heart_rate(self, characteristic, uuid=None):
        def isHeartRateInUINT16(flags):
            return (flags & GattUtils.FIRST_BITMASK) != 0

        def isWornStatusPresent(flags):
            return (flags & GattUtils.THIRD_BITMASK) != 0

        def isSensorWorn(flags):
            return (flags & GattUtils.SECOND_BITMASK) != 0

        def isEePresent(flags):
            return (flags & GattUtils.FOURTH_BITMASK) != 0

        def isRrIntPresent(flags):
            return (flags & GattUtils.FIFTH_BITMASK) != 0

        i = 0
        data = characteristic.getValue()
        flags = self.u8_le(data, i)
        i += 1
        hro = self.out_obj
        hro.set_id(None)
        if isHeartRateInUINT16(flags):
            hrmval = self.u16_le(data, i)
            i += 2
        else:
            hrmval = self.u8_le(data, i)
            i += 1
        hro.pulse = hrmval
        sensorWorn = -1
        eeval = 0
        rrIntervals = []
        if isWornStatusPresent(flags):
            if isSensorWorn(flags):
                sensorWorn = 1
            else:
                sensorWorn = 0
        hro.worn = sensorWorn
        if isEePresent(flags):
            eeval = self.u16_le(data, i)
            i += 2
        hro.joule = eeval
        if isRrIntPresent(flags):
            while i < len(data):
                rrIntervals.append(self.u16_le(data, i))
                i += 2
        hro.intervals_conf = rrIntervals
        if self.info_fields['_new_']:
            self.info_fields['_new_'] = False
            hro.process_kwargs(self.info_fields)
        _LOGGER.debug(f'hro Parse result {hro}')
        Timer(0, partial(self.step, hro))
