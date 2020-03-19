import json
from functools import partial

from able.dispatcher import BluetoothDispatcherBase
from kivy.utils import platform
from util.const import (
    COMMAND_CONFIRM, COMMAND_WBD_CHARACTERISTICCHANGED,
    COMMAND_WBD_CHARACTERISTICREAD, COMMAND_WBD_CHARACTERISTICWRITTEN,
    COMMAND_WBD_CONNECTGATT, COMMAND_WBD_CONNECTSTATECHANGE,
    COMMAND_WBD_DESCRIPTORREAD, COMMAND_WBD_DESCRIPTORWRITTEN,
    COMMAND_WBD_DEVICEFOUND, COMMAND_WBD_DISCONNECTGATT,
    COMMAND_WBD_DISCOVERSERVICES, COMMAND_WBD_ENABLENOT,
    COMMAND_WBD_GATTRELEASE, COMMAND_WBD_READCHARACTERISTIC,
    COMMAND_WBD_SERVICES, COMMAND_WBD_STARTSCAN, COMMAND_WBD_STOPSCAN,
    COMMAND_WBD_STOPSCAN_RV, COMMAND_WBD_WRITECHARACTERISTIC,
    COMMAND_WBD_WRITEDESCRIPTOR, CONFIRM_FAILED_1, CONFIRM_FAILED_3,
    CONFIRM_OK, MSG_COMMAND_TIMEOUT, MSG_ERROR, MSG_OK)
from util.osc_comunication import OSCManager
from util.timer import Timer
from util import init_logger


_LOGGER = init_logger(__name__)


class BluetoothDispatcherW(BluetoothDispatcherBase):
    _oscer = None

    def __init__(self,
                 hostlisten=None,
                 portlisten=33218,
                 hostcommand='127.0.0.1',
                 portcommand=33217, **kwargs):
        if not BluetoothDispatcherW._oscer:
            if hostlisten:
                BluetoothDispatcherW._oscer = OSCManager(
                    hostlisten=hostlisten,
                    portlisten=portlisten,
                    hostcommand=hostcommand,
                    portcommand=portcommand
                )
        _LOGGER.debug(f'Constructing BluetoothDispatcherW {kwargs} events={self.__events__}')
        super(BluetoothDispatcherW, self).__init__(**kwargs)

    def _set_ble_interface(self):
        self._ble = self._oscer
        if self._oscer:
            Timer(0, partial(
                self._oscer.init,
                pingsend=False,
                on_init_ok=self.on_osc_init_ok,
                on_ping_timeout=self.on_ping_timeout))

    def on_osc_init_ok(self):
        pass

    def on_ping_timeout(self, is_timeout):
        if is_timeout:
            _LOGGER.debug('Backend connection Timeout')
        else:
            _LOGGER.debug('Backend connection OK')

    def start_scan(self, scan_settings=None, scan_filters=None):
        """Start a scan for devices.
        Ask for runtime permission to access location.
        Start a system activity that allows the user to turn on Bluetooth,
        if Bluetooth is not enabled.
        The status of the scan start are reported with
        :func:`scan_started <on_scan_started>` event.
        """
        self._oscer.unhandle(COMMAND_WBD_DEVICEFOUND)
        self._oscer.handle(COMMAND_WBD_DEVICEFOUND, self.on_device)
        self._oscer.send(COMMAND_WBD_STARTSCAN,
                         json.dumps(scan_settings),
                         json.dumps(scan_filters),
                         confirm_callback=self.on_scan_started_wrap,
                         timeout=5)

    def stop_scan(self):
        """Stop the ongoing scan for devices.
        """
        self._oscer.handle(COMMAND_WBD_STOPSCAN_RV, self.on_scan_completed)
        self._oscer.send(COMMAND_WBD_STOPSCAN)

    def connect_gatt(self, device):
        """Connect to GATT Server hosted by device
        """
        self._oscer.unhandle(COMMAND_WBD_GATTRELEASE)
        self._oscer.unhandle(COMMAND_WBD_CONNECTSTATECHANGE)
        self._oscer.unhandle(COMMAND_WBD_CHARACTERISTICREAD)
        self._oscer.unhandle(COMMAND_WBD_CHARACTERISTICCHANGED)
        self._oscer.unhandle(COMMAND_WBD_CHARACTERISTICWRITTEN)
        self._oscer.unhandle(COMMAND_WBD_DESCRIPTORREAD)
        self._oscer.unhandle(COMMAND_WBD_DESCRIPTORWRITTEN)
        self._oscer.handle(COMMAND_WBD_CONNECTSTATECHANGE, self.on_connection_state_change)
        self._oscer.handle(COMMAND_WBD_GATTRELEASE, self.on_gatt_release)
        self._oscer.handle(COMMAND_WBD_CHARACTERISTICREAD, self.on_characteristic_read)
        self._oscer.handle(COMMAND_WBD_CHARACTERISTICCHANGED, self.on_characteristic_changed)
        self._oscer.handle(COMMAND_WBD_CHARACTERISTICWRITTEN, self.on_characteristic_write)
        self._oscer.handle(COMMAND_WBD_DESCRIPTORREAD, self.on_descriptor_read)
        self._oscer.handle(COMMAND_WBD_DESCRIPTORWRITTEN, self.on_descriptor_write)
        self._oscer.send(COMMAND_WBD_CONNECTGATT, json.dumps(device))

    def close_gatt(self):
        """Close current GATT client
        """
        self._oscer.send(COMMAND_WBD_DISCONNECTGATT)

    def on_scan_started_wrap(self, *args, timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        else:
            msg = args[1]
            exitv = args[0]
        _LOGGER.info(f"StartScan: [E {str(exitv)}]: {msg}")
        self.on_scan_started(exitv == CONFIRM_OK)

    def discover_services(self):
        """Discovers services offered by a remote device.
        The status of the discovery reported with
        :func:`services <on_services>` event.

        :return: true, if the remote services discovery has been started
        """
        self._oscer.handle(COMMAND_WBD_SERVICES, self.on_services)
        self._oscer.send(COMMAND_WBD_DISCOVERSERVICES)

    def enable_notifications(self, characteristic, enable=True):
        """Enable or disable notifications for a given characteristic

        :param characteristic: BluetoothGattCharacteristic Java object
        :param enable: enable notifications if True, else disable notifications
        :return: True, if the operation was initiated successfully
        """
        self._oscer.send(COMMAND_WBD_ENABLENOT, json.dumps(characteristic), enable)

    def on_writedescriptor_command(self, *args, timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        else:
            msg = args[1]
            exitv = args[0]
        _LOGGER.info(f"WriteDesc: [E {str(exitv)}]: {msg}")

    def write_descriptor(self, descriptor, value):
        """Set and write the value of a given descriptor to the associated
        remote device

        :param descriptor: BluetoothGattDescriptor Java object
        :param value: value to write
        """
        self._oscer.send(COMMAND_WBD_WRITEDESCRIPTOR, json.dumps(descriptor), json.dumps(value), confirm_callback=self.on_writedescriptor_command, timeout=5)

    def write_characteristic(self, characteristic, value):
        """Write a given characteristic value to the associated remote device

        :param characteristic: BluetoothGattCharacteristic Java object
        :param value: value to write
        """
        self._oscer.send(COMMAND_WBD_WRITECHARACTERISTIC, json.dumps(characteristic), json.dumps(value))

    def read_characteristic(self, characteristic):
        """Read a given characteristic from the associated remote device

        :param characteristic: BluetoothGattCharacteristic Java object
        """
        self._oscer.send(COMMAND_WBD_READCHARACTERISTIC, json.dumps(characteristic))


if platform == 'android':
    from able.android.dispatcher import BluetoothDispatcher
    from jnius import autoclass

    class BluetoothDispatcherWC(BluetoothDispatcher):
        def __init__(self,
                     hostlisten='127.0.0.1',
                     portlisten=33217,
                     hostcommand='127.0.0.1',
                     portcommand=33218, **kwargs):
            _LOGGER.warning(f'BluetoothDispatcherWC init L({hostlisten}:{portlisten}) C({hostcommand}:{portcommand})')
            self._oscer = OSCManager(
                hostlisten=hostlisten,
                portlisten=portlisten,
                hostcommand=hostcommand,
                portcommand=portcommand
            )
            super(BluetoothDispatcherWC, self).__init__(**kwargs)
            _LOGGER.warning('BluetoothDispatcherWC init end')

        def _set_ble_interface(self):
            _LOGGER.warning('Set BLE Interface full')
            super(BluetoothDispatcherWC, self)._set_ble_interface()
            Timer(0, partial(
                self._oscer.init,
                pingsend=True,
                on_init_ok=self.on_osc_init_ok))

        def start_scan_wrap(self, ssett, sfilt):
            ssett = json.loads(ssett)
            sfilt = json.loads(sfilt)
            self.start_scan(ssett, sfilt)

        def connect_gatt_wrap(self, devicedict):
            devicedict = json.loads(devicedict)
            self.connect_gatt(self._ble.getDevice(devicedict['address']))

        def write_descriptor_wrap(self, descriptor, value):
            self.write_descriptor(
                BluetoothDispatcherWC.descriptorfromdict(json.loads(descriptor)),
                json.loads(value)
            )

        def read_characteristic_wrap(self, characteristic):
            self.read_characteristic(
                BluetoothDispatcherWC.characteristicfromdict(json.loads(characteristic))
            )

        def write_characteristic_wrap(self, characteristic, value):
            self.write_characteristic(
                BluetoothDispatcherWC.characteristicfromdict(json.loads(characteristic)),
                value
            )

        def on_osc_init_ok(self):
            self._oscer.handle(COMMAND_WBD_CONNECTGATT, self.connect_gatt_wrap)
            self._oscer.handle(COMMAND_WBD_DISCONNECTGATT, self.close_gatt)
            self._oscer.handle(COMMAND_WBD_DISCOVERSERVICES, self.discover_services)
            self._oscer.handle(COMMAND_WBD_STARTSCAN, self.start_scan_wrap)
            self._oscer.handle(COMMAND_WBD_STOPSCAN, self.stop_scan)
            self._oscer.handle(COMMAND_WBD_WRITEDESCRIPTOR, self.write_descriptor_wrap)
            self._oscer.handle(COMMAND_WBD_WRITECHARACTERISTIC, self.write_characteristic_wrap)
            self._oscer.handle(COMMAND_WBD_READCHARACTERISTIC, self.read_characteristic_wrap)

        def on_gatt_release(self):
            """`gatt_release` event handler.
            Event is dispatched at every read/write completed operation
            """
            self._oscer.send(COMMAND_WBD_GATTRELEASE)

        def on_scan_started(self, success):
            """`scan_started` event handler

            :param success: true, if scan was started successfully
            """
            self._oscer.send(COMMAND_CONFIRM,
                             CONFIRM_OK if success else CONFIRM_FAILED_1,
                             MSG_OK if success else MSG_ERROR)

        def on_scan_completed(self):
            """`scan_completed` event handler
            """
            self._oscer.send(COMMAND_WBD_STOPSCAN_RV)

        def on_device(self, device, rssi, advertisement):
            """`device` event handler.
            Event is dispatched when device is found during a scan.

            :param device: BluetoothDevice Java object
            :param rssi: the RSSI value for the remote device
            :param advertisement: :class:`Advertisement` data record
            """
            self._oscer.send(COMMAND_WBD_DEVICEFOUND,
                             json.dumps(dict(name=device.getName(), address=device.getAddress())),
                             rssi,
                             json.dumps(advertisement.data))

        def on_connection_state_change(self, status, state):
            """`connection_state_change` event handler

            :param status: status of the operation,
                           `GATT_SUCCESS` if the operation succeeds
            :param state: STATE_CONNECTED or STATE_DISCONNECTED
            """
            self._oscer.send(COMMAND_WBD_CONNECTSTATECHANGE, status, state)

        @staticmethod
        def characteristic2dict(ch):
            descs = []
            descsj = ch.getDescriptors()
            for i in range(descsj.getSize()):
                descs.append(BluetoothDispatcherWC.descriptor2dict(descsj.get(i)))
            return dict(
                uuid=ch.getUuid(),
                value=ch.getValue(),
                descriptors=descs,
                permissions=ch.getPermissions(),
                properties=ch.getProperties(),
            )

        @staticmethod
        def characteristicfromdict(ch):
            BluetoothGattCharacteristic = autoclass('	android.bluetooth.BluetoothGattCharacteristic')
            bgd = BluetoothGattCharacteristic(ch['uuid'], ch['properties'], ch['permissions'])
            for i in ch['descriptors']:
                bgd.addDescriptor(BluetoothDispatcherWC.descriptorfromdict(i))
            bgd.setValue(ch['value'])
            return bgd

        @staticmethod
        def descriptor2dict(ch):
            return dict(
                uuid=ch.getUuid(),
                value=ch.getValue(),
                permissions=ch.getPermissions()
            )

        @staticmethod
        def descriptorfromdict(ch):
            BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
            bgd = BluetoothGattDescriptor(ch['uuid'], ch['permissions'])
            if ch['value']:
                bgd.setValue(ch['value'])
            return bgd

        def on_services(self, services, status):
            """`services` event handler

            :param services: :class:`Services` dict filled with discovered
                             characteristics
                             (BluetoothGattCharacteristic Java objects)
            :param status: status of the operation,
                           `GATT_SUCCESS` if the operation succeeds
            """
            dct = dict()
            for sn, ch in services.items():
                dct[sn] = BluetoothDispatcherWC.characteristic2dict(ch)
            self._oscer.send(COMMAND_WBD_SERVICES, json.dumps(dct), status)

        def on_characteristic_changed(self, characteristic):
            """`characteristic_changed` event handler

            :param characteristic: BluetoothGattCharacteristic Java object
            """
            self._oscer.send(COMMAND_WBD_CHARACTERISTICCHANGED,
                             json.dumps(BluetoothDispatcherWC.characteristic2dict(characteristic)))

        def on_characteristic_read(self, characteristic, status):
            """`characteristic_read` event handler

            :param characteristic: BluetoothGattCharacteristic Java object
            :param status: status of the operation,
                           `GATT_SUCCESS` if the operation succeeds
            """
            self._oscer.send(COMMAND_WBD_CHARACTERISTICREAD,
                             json.dumps(BluetoothDispatcherWC.characteristic2dict(characteristic)),
                             status)

        def on_characteristic_write(self, characteristic, status):
            """`characteristic_write` event handler

            :param characteristic: BluetoothGattCharacteristic Java object
            :param status: status of the operation,
                           `GATT_SUCCESS` if the operation succeeds
            """
            self._oscer.send(COMMAND_WBD_CHARACTERISTICWRITTEN,
                             json.dumps(BluetoothDispatcherWC.characteristic2dict(characteristic)),
                             status)

        def on_descriptor_read(self, descriptor, status):
            """`descriptor_read` event handler

            :param descriptor: BluetoothGattDescriptor Java object
            :param status: status of the operation,
                           `GATT_SUCCESS` if the operation succeeds
            """
            self._oscer.send(COMMAND_WBD_DESCRIPTORREAD,
                             json.dumps(BluetoothDispatcherWC.descriptor2dict(descriptor)),
                             status)

        def on_descriptor_write(self, descriptor, status):
            """`descriptor_write` event handler

            :param descriptor: BluetoothGattDescriptor Java object
            :param status: status of the operation,
                           `GATT_SUCCESS` if the operation succeeds
            """
            self._oscer.send(COMMAND_WBD_DESCRIPTORWRITTEN,
                             json.dumps(BluetoothDispatcherWC.descriptor2dict(descriptor)),
                             status)
else:
    BluetoothDispatcher = BluetoothDispatcherW
