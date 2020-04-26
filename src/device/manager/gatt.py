from functools import partial
from device.manager import GenericDeviceManager
from device.manager.preaction.enable_bluetooth import EnableBluetooth
from util.const import (DEVREASON_OPERATION_ERROR, DEVREASON_PREPARE_ERROR,
                        DEVREASON_REQUESTED, DEVREASON_TIMEOUT,
                        DEVSTATE_CONNECTED, DEVSTATE_CONNECTING,
                        DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING)
from able import STATE_CONNECTED, STATE_DISCONNECTED, GATT_SUCCESS
from util import init_logger
from util.timer import Timer


_LOGGER = init_logger(__name__)


class UuidBundle(object):

    @staticmethod
    def get_uuid(v):
        if isinstance(v, str):
            return v
        elif isinstance(v, int):
            return '0000%04x-0000-1000-8000-00805f9b34fb' % v
        else:
            return v.getUuid().toString()

    def __init__(self, service, charact, handler=None):
        self.service = UuidBundle.get_uuid(service if service else charact.getService())
        self.characteristic = UuidBundle.get_uuid(charact)
        self.service_id = int(self.service[4:8], 16)
        self.characteristic_id = int(self.characteristic[4:8], 16)
        self.handler = handler

    def __repr__(self):
        return self.key()

    def key(self):
        return f'{self.service}|{self.characteristic}'

    def __eq__(self, other):
        try:
            return self.other.service == self.service and self.other.characteristic == self.characteristic
        except (Exception, AttributeError):
            return self.__eq__(UuidBundle(None, other))


class GattDeviceManager(GenericDeviceManager):
    __pre_action__ = EnableBluetooth

    def get_read_once_characteristics(self):
        return dict()

    def get_notify_characteristics(self):
        return dict()

    def __init__(self, *args, **kwargs):
        super(GattDeviceManager, self).__init__(*args, **kwargs)
        self.read_once_characteristics = self.get_read_once_characteristics()
        self.notify_characteristics = self.get_notify_characteristics()
        self.disconnect_reason = DEVREASON_REQUESTED
        self.operation_timer = None
        self.found_device = None

    def on_services(self, services, status):
        self.loop.call_soon_threadsafe(self.on_services_loop, services, status)

    def on_services_loop(self, services, status):
        if status == GATT_SUCCESS:
            _LOGGER.info(f'Serv disc dict {services}')
            for _, chinfo in self.read_once_characteristics.items():
                for suid, sdict in services.items():
                    if suid == chinfo.service:
                        ch = sdict[chinfo.characteristic]
                        self.read_characteristic(ch)
            for _, chinfo in self.notify_characteristics.items():
                for suid, sdict in services.items():
                    if suid == chinfo.service:
                        ch = sdict[chinfo.characteristic]
                        self.enable_notifications(ch)
            if self.notify_characteristics:
                self.operation_timer_init(10)

    @staticmethod
    def call_handler_from_characteristic(characteristic, searchdict):
        bundle = UuidBundle(None, characteristic)
        k = bundle.key()
        if k in searchdict:
            sk = searchdict[k]
            if sk.handler:
                _LOGGER.debug('%04d:%04d -> %s' % (sk.service_id, sk.characteristic_id, str(characteristic.getValue())))
                sk.handler(characteristic, uuid=sk)
                return True
        return False

    def on_characteristic_read(self, characteristic, status):
        self.loop.call_soon_threadsafe(self.on_characteristic_read_loop, characteristic, status)

    def on_characteristic_read_loop(self, characteristic, status):
        if status == GATT_SUCCESS:
            self.call_handler_from_characteristic(characteristic, self.read_once_characteristics)
        else:
            _LOGGER.debug('Failed to read characteristic')

    def on_characteristic_changed(self, characteristic):
        self.loop.call_soon_threadsafe(self.on_characteristic_changed_loop, characteristic)

    def on_characteristic_changed_loop(self, characteristic):
        self.call_handler_from_characteristic(characteristic, self.notify_characteristics)
        self.operation_timer_init(10)

    def on_connection_state_change(self, status, state):
        self.loop.call_soon_threadsafe(self.on_connection_state_change_loop, status, state)

    def on_connection_state_change_loop(self, status, state):
        if status == GATT_SUCCESS and state == STATE_CONNECTED:
            if self.state == DEVSTATE_CONNECTING:
                self.set_state(DEVSTATE_CONNECTED, DEVREASON_REQUESTED)
                self.discover_services()
        elif state == STATE_DISCONNECTED:
            if self.state == DEVSTATE_DISCONNECTING:
                self.set_state(DEVSTATE_DISCONNECTED, self.disconnect_reason)
            elif self.is_connected_state():
                self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_OPERATION_ERROR)

    def operation_timer_init(self, timeout=False, handler=None):
        if self.operation_timer:
            self.operation_timer.cancel()
        if timeout:
            if not handler:
                handler = partial(self.inner_disconnect, reason=DEVREASON_TIMEOUT)
            self.operation_timer = Timer(timeout, handler)

    def get_scan_filters(self, scanning_for_new_devices=False):
        if not scanning_for_new_devices:
            return [
                dict(deviceAddress=self.device.address)
            ]
        else:
            return None

    def process_found_device(self, device, connectobj=None):
        super(GattDeviceManager, self).process_found_device(device)
        _LOGGER.debug(f'process_found_device: state={self.state} addr_my={self.device.get_address()} addr_oth={device.get_address()}')
        if self.state == DEVSTATE_CONNECTING:
            self.operation_timer_init()
            self.found_device = connectobj
            self.stop_scan()
        elif self.state == DEVSTATE_DISCONNECTING:
            self.operation_timer_init()
            self.stop_scan()

    def on_scan_completed(self):
        super(GattDeviceManager, self).on_scan_completed()
        if self.state == DEVSTATE_DISCONNECTING:
            self.set_state(DEVSTATE_DISCONNECTED, self.disconnect_reason)
        elif self.state == DEVSTATE_CONNECTING:
            if self.found_device:
                self.connect_gatt(self.found_device)
            else:
                self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_PREPARE_ERROR)

    def inner_connect(self):
        self.operation_timer_init(timeout=30, handler=self.stop_scan)
        if not self.found_device:
            self.start_scan(self.get_scan_settings(), self.get_scan_filters())
        else:
            self.process_found_device(self.found_device)

    def inner_disconnect(self, reason=DEVREASON_REQUESTED):
        self.operation_timer_init()
        self.disconnect_reason = reason
        if self.found_device:
            try:
                self.close_gatt()
            except Exception:
                pass
        else:
            self.stop_scan()
