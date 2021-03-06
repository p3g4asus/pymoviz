import abc
import json
from functools import partial
import traceback

from able import (REASON_DISCOVER_ERROR, REASON_NOT_ENABLED, STATE_CONNECTED, STATE_DISCONNECTED)
from db.device import Device
from db.label_formatter import SessionFormatter, SimpleFieldFormatter, StateFormatter, UserFormatter
from util import init_logger
from util.bluetooth_dispatcher import BluetoothDispatcher
from util.const import (COMMAND_CONFIRM, COMMAND_DELDEVICE, COMMAND_DEVICEFIT,
                        COMMAND_DEVICEFOUND, COMMAND_DEVICESTATE, COMMAND_NEWSESSION,
                        COMMAND_REQUESTSESSION,
                        COMMAND_SAVEDEVICE, COMMAND_SEARCH, CONFIRM_FAILED_1,
                        CONFIRM_FAILED_2, CONFIRM_FAILED_3, CONFIRM_OK,
                        DEVREASON_BLE_DISABLED, DEVREASON_OPERATION_ERROR,
                        DEVREASON_PREPARE_ERROR, DEVREASON_REQUESTED,
                        DEVREASON_SIMULATOR, DEVREASON_STATECHANGE,
                        DEVSTATE_CONNECTED, DEVSTATE_CONNECTING,
                        DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_INVALIDSTEP, DEVSTATE_SEARCHING,
                        DEVSTATE_UNINIT, DI_BLNAME, MSG_COMMAND_TIMEOUT,
                        MSG_CONNECTION_STATE_INVALID, MSG_DB_SAVE_ERROR)
from util.timer import Timer


_LOGGER = init_logger(__name__)
_toast = None


class GenericDeviceManager(BluetoothDispatcher, abc.ABC):

    __simulator_class__ = None
    __output_class__ = None
    __formatters__ = dict(
        State=StateFormatter(),
        Session=SessionFormatter(),
        User=UserFormatter(),
        Updates=SimpleFieldFormatter(
            name='Updates',
            pre='$D n: ',
            format_str='%d',
            example_conf=dict(updates=45),
            fields=['updates']
        )
    )

    __notification_formatter__ = StateFormatter()
    __notification_formatter__.change_fields({'post': '',
                                              'pre': '',
                                              'col': 0,
                                              'colmax': 0,
                                              'colmin': 0,
                                              'colerror': 0,
                                              'timeout': '---'})
    __pre_action__ = None
    __info_fields__ = ()

    @staticmethod
    def is_connected_state_s(st):
        return st != DEVSTATE_DISCONNECTED and st != DEVSTATE_DISCONNECTING and\
            st != DEVSTATE_UNINIT and st != DEVSTATE_SEARCHING and st != DEVSTATE_CONNECTING

    def is_connected_state(self):
        return GenericDeviceManager.is_connected_state_s(self.state)

    @staticmethod
    def is_stopped_state_s(st):
        return st == DEVSTATE_UNINIT or st == DEVSTATE_DISCONNECTED

    def is_stopped_state(self):
        return GenericDeviceManager.is_stopped_state_s(self.state)

    @staticmethod
    def is_active_state_s(st):
        return\
            st != DEVSTATE_UNINIT and\
            st != DEVSTATE_CONNECTING and\
            st != DEVSTATE_DISCONNECTING and\
            st != DEVSTATE_CONNECTED and\
            st != DEVSTATE_DISCONNECTED

    def is_active_state(self):
        return GenericDeviceManager.is_active_state_s(self.state)

    @classmethod
    def get_settings_widget_class(cls):
        return None

    def get_scan_filters(self, scanning_for_new_devices=False):
        return None

    def get_scan_settings(self, scanning_for_new_devices=False):
        return None

    @classmethod
    def device2line1(cls, device):
        return device.get_name() or 'N/A'

    @classmethod
    def device2line2(cls, device):
        return device.get_address()

    @classmethod
    def device2line3(cls, device):
        rssi = device.f('rssi')
        return f'RSSI {rssi}' if rssi else ''

    # __simulator_class__
    # __type__

    # ll = list(cls.__formatters___)
    # ll.append(StateFormatter('State'))

    @abc.abstractmethod
    def inner_connect(self):
        pass

    @abc.abstractmethod
    def inner_disconnect(self):
        pass

    @staticmethod
    def sort(list_of_dm):
        list_of_dm.sort(key=lambda x: x.device, reverse=True)

    def get_state(self):
        return self.state

    def get_formatters(self):
        out = dict()
        for nm, form in self.__formatters__.items():
            form = form.clone()
            form.set_device(self.device)
            out[nm] = form
        return out

    def get_notification_formatter(self):
        if self.__notification_formatter__:
            form = self.__notification_formatter__.clone()
            form.set_device(self.device)
            return form
        else:
            return None

    def set_state(self, st, reason=-1):
        oldstate = self.state
        if oldstate != st:
            self.state = st
            self.oscer.send_device(COMMAND_DEVICESTATE, self._uid, oldstate, st, reason)
            self.dispatch("on_state_transition", oldstate, st, reason)

    def connect(self, *args):
        _LOGGER.info(f'Connecting[{self.get_uid()}] {self.device.get_alias()}')
        if self.is_stopped_state():
            self.set_state(DEVSTATE_CONNECTING, DEVREASON_REQUESTED)
            if self.simulator_needs_reset:
                self.simulator_needs_reset = False
                if not self.simulator:
                    self.simulator = self.__simulator_class__(
                        self.db,
                        self.device.get_id(),
                        self.device.get_additionalsettings(),
                        self.user,
                        on_session=self.on_simulator_session)
                else:
                    self.simulator.reset(self.device.get_additionalsettings(), self.user)
            self.inner_connect()
            return True
        else:
            _LOGGER.info(f'Device {self.device.get_alias()} is not stopped ({self.state})')
            return False

    def disconnect(self, *args):
        if self.is_connected_state() or self.state == DEVSTATE_CONNECTING:
            self.set_state(DEVSTATE_DISCONNECTING, DEVREASON_REQUESTED)
            self.inner_disconnect()
            self.simulator_needs_reset = True
            self.last_session = None

    async def step(self, obj):
        st = None
        try:
            st = await self.simulator.step(obj)
            if self.is_connected_state():
                self.set_state(st, DEVREASON_SIMULATOR)
                nm = self.device.get_name()
                obj.s(DI_BLNAME, nm if nm else 'N/A')
                if st != DEVSTATE_INVALIDSTEP:
                    self.oscer.send_device(COMMAND_DEVICEFIT, self._uid, self.device, obj, st)
                    self.dispatch('on_command_handle', COMMAND_DEVICEFIT, CONFIRM_OK, self.device, obj, st)
        except Exception:
            _LOGGER.error(f'Step error (state={st}, obj={obj}): {traceback.format_exc()}')

    def on_connection_state_change(self, status, state):
        if state == STATE_DISCONNECTED:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_STATECHANGE)
            # if oldstate != DEVSTATE_DISCONNECTING:
            #     self.connect()
        elif state == STATE_CONNECTED:
            self.set_state(DEVSTATE_CONNECTED, DEVREASON_STATECHANGE)

    def get_settings_screen(self):
        if not self.widget:
            from .widget import SearchSettingsScreen
            swc = self.get_settings_widget_class()
            swi = swc() if swc else None
            self.widget = SearchSettingsScreen(
                deviceitem=self.get_device_item(self.device, active=True),
                devicetype=self.device.get_type(),
                conf_widget=swi,
                on_save=self.on_save_device,
                on_search=self.on_search_device)
        return self.widget

    def process_found_device(self, device, connectobj=None):
        pass

    def on_device(self, device, rssi, advertisement):
        self.loop.call_soon_threadsafe(self.main_loop_on_device, device, rssi, advertisement)

    def main_loop_on_device(self, device, rssi, advertisement):
        adv = []
        connectobj = None
        if advertisement:
            if isinstance(advertisement, str):
                adv = json.loads(advertisement)
            elif advertisement.data:
                adv = [x for x in advertisement.data]
        if isinstance(device, str):
            device = json.loads(device)
        elif not isinstance(device, dict):
            connectobj = device
            device = dict(
                address=device.getAddress(),
                name=device.getName()
            )
        d = Device(
            address=device['address'],
            name=device['name'],
            rssi=rssi,
            type=self.__type__,
            advertisement=adv
        )
        if self.state == DEVSTATE_SEARCHING:
            self.oscer.send_device(COMMAND_DEVICEFOUND, self._uid, d.serialize())
        self.process_found_device(d, connectobj=connectobj)

    async def on_command_savedevice_async(self, device, *args, sender=None, **kwargs):
        rv = await device.to_db(self.db)
        if rv:
            self.device = device
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_OK, device, dest=sender)
            self.dispatch('on_command_handle', COMMAND_SAVEDEVICE, CONFIRM_OK)
        else:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(device), dest=sender)
            self.dispatch('on_command_handle', COMMAND_SAVEDEVICE, CONFIRM_FAILED_1)

    def on_command_savedevice(self, device, *args, sender=None, **kwargs):
        if self.is_stopped_state():
            Timer(0, partial(self.on_command_savedevice_async, device, sender=sender))
        else:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID, dest=sender)
            self.dispatch('on_command_handle', COMMAND_SAVEDEVICE, CONFIRM_FAILED_2)

    async def on_command_deldevice_async(self, device, *args, sender=None, **kwargs):
        rv = await device.remove(self.db)
        if rv:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_OK, device, dest=sender)
            self.dispatch('on_command_handle', COMMAND_DELDEVICE, CONFIRM_OK)
        else:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(device), dest=sender)
            self.dispatch('on_command_handle', COMMAND_DELDEVICE, CONFIRM_FAILED_1)

    def on_command_deldevice(self, device, *args, sender=None, **kwargs):
        if self.is_stopped_state():
            Timer(0, partial(self.on_command_deldevice_async, device, sender=sender))
        else:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID, dest=sender)
            self.dispatch('on_command_handle', COMMAND_DELDEVICE, CONFIRM_FAILED_2)

    def on_save_device(self, inst, device):
        self.oscer.send_device(COMMAND_SAVEDEVICE,
                               self._uid,
                               device,
                               confirm_callback=self.on_confirm_save_device,
                               timeout=5)

    def on_confirm_save_device(self, *args, timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        elif args[0] == CONFIRM_OK:
            self.device = args[1]
            _LOGGER.info(f'Saved device {self.device}')
            self.widget.exit()
            return
        else:
            msg = args[1]
            exitv = args[0]
        _toast(f"[E {exitv}] {msg}")

    def del_device(self, on_del_device=None):
        self.oscer.send_device(COMMAND_DELDEVICE,
                               self._uid,
                               self.device,
                               confirm_callback=partial(self.on_confirm_del_device,
                                                        on_del_device=on_del_device),
                               timeout=5)

    def on_confirm_del_device(self, *args, timeout=False, on_del_device=None):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        elif args[0] == CONFIRM_OK:
            if on_del_device:
                on_del_device(CONFIRM_OK, self)
            return
        else:
            msg = args[1]
            exitv = args[0]
        _toast(f"[E {exitv}] {msg}")

    def on_command_devicefound(self, device, *args, **kwargs):
        if self.widget:
            self.widget.add_result(self.get_device_item(device, active=False))

    def on_command_newstate(self, oldstate, newstate, reason, *args, **kwargs):
        if newstate == DEVSTATE_CONNECTED:
            _toast(self.device.get_alias() + " connected OK")
        elif newstate == DEVSTATE_CONNECTING:
            _toast(self.device.get_alias() + " trying to connect...")
        elif newstate == DEVSTATE_SEARCHING:
            _toast(f"Searching for device of type {self.device.get_type()}")
            if self.widget:
                self.widget.set_searching(True)
        elif newstate == DEVSTATE_DISCONNECTED and oldstate == DEVSTATE_CONNECTING:
            if reason == DEVREASON_REQUESTED:
                _toast(self.device.get_alias() + " disconnected")
            elif reason == DEVREASON_PREPARE_ERROR:
                _toast(self.device.get_alias() + " connection preparation error: stopping")
            elif reason == DEVREASON_BLE_DISABLED:
                _toast("Need to enable bluetooth")
            else:
                _toast(self.device.get_alias() + " connection failed")
        elif newstate == DEVSTATE_DISCONNECTED and oldstate == DEVSTATE_SEARCHING:
            if reason == DEVREASON_REQUESTED:
                _toast("Search for device of ended")
            else:
                _toast("Search init error: Is bluetooth up and running?")
            if self.widget:
                self.widget.set_searching(False)
        self.dispatch("on_state_transition", oldstate, newstate, reason)

    def on_search_device(self, inst, startcommand):
        # self.oscer.send_device(COMMAND_SEARCH, self._uid, startcommand, confirm_callback=self.on_confirm_search_device, timeout=5)
        self.oscer.send_device(COMMAND_SEARCH, self._uid, startcommand)

    def on_confirm_search_device(self, *args, timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        elif args[0] != CONFIRM_OK:
            msg = args[1]
            exitv = args[0]
        else:
            return
        _toast(f"[E {exitv}] {msg}")

    def search(self, val):
        _LOGGER.info(f'Search requested: state {self.state}, val={val}')
        if val and self.state == DEVSTATE_UNINIT or self.state == DEVSTATE_DISCONNECTED:
            self.start_scan(self.get_scan_settings(scanning_for_new_devices=True),
                            self.get_scan_filters(scanning_for_new_devices=True))
            return True
        elif not val and self.state == DEVSTATE_SEARCHING:
            self.stop_scan()

    def on_command_request_session(self, sender=None, **kwargs):
        if self.last_session:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_OK, self.last_session, dest=sender)
        else:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, CONFIRM_FAILED_1, dest=sender)

    def on_command_search_device(self, startcommand, sender=None, **kwargs):
        rv = CONFIRM_OK
        if startcommand:
            if not (self.state == DEVSTATE_UNINIT or self.state == DEVSTATE_DISCONNECTED):
                rv = CONFIRM_FAILED_1
        elif self.state != DEVSTATE_SEARCHING:
            rv = CONFIRM_FAILED_2
        if rv != CONFIRM_OK:
            self.oscer.send_device(COMMAND_CONFIRM, self._uid, rv, MSG_CONNECTION_STATE_INVALID, dest=sender)
        self.dispatch('on_command_handle', COMMAND_SEARCH, rv)

    def on_scan_completed(self):
        if self.state == DEVSTATE_SEARCHING:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_REQUESTED)

    def on_error(self, reason, msg):
        if reason == REASON_NOT_ENABLED:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_BLE_DISABLED)
        elif reason != REASON_DISCOVER_ERROR:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_PREPARE_ERROR)
        else:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_OPERATION_ERROR)

    def on_scan_started(self, success):
        if success and (self.state == DEVSTATE_UNINIT or self.state == DEVSTATE_DISCONNECTED):
            self.set_state(DEVSTATE_SEARCHING, DEVREASON_REQUESTED)
        elif not success:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_PREPARE_ERROR)

    def get_device_item(self, device, active=False):
        from .widget import BTLESearchItem
        device = device or self.device
        add = device.get_address()
        return BTLESearchItem(
            device=device,
            text=self.device2line1(device) if add else '',
            secondary_text=self.device2line2(device) if add else '',
            tertiary_text=self.device2line3(device) if add else '') if add else None

    def set_user(self, user):
        self.user = user

    __events__ = list(BluetoothDispatcher.__events__)
    __events__.append('on_state_transition')
    __events__.append('on_command_handle')
    __events__ = tuple(__events__)

    def on_state_transition(self, fromv, tov, rea):
        _LOGGER.info(f'Device: transition from state {fromv} to {tov}')
        if tov == DEVSTATE_DISCONNECTED and\
            (fromv != DEVSTATE_DISCONNECTING or rea != DEVREASON_REQUESTED)\
                and self.simulator:
            self.simulator.set_offsets()

    def on_command_handle(self, command, exitv, *args):
        _LOGGER.debug(f'Handled command {command}: {exitv}')

    def on_command_newsession(self, session, *args, **kwargs):
        self.dispatch('on_command_handle', COMMAND_NEWSESSION, CONFIRM_OK, session)
        self.last_session = session

    def on_confirm_request_session(self, *args, timeout=False):
        if not timeout and args[0] == CONFIRM_OK:
            self.on_command_newsession(args[1])

    def on_command_devicefit(self, device, fitobj, st, **kwargs):
        if not self.last_session:
            self.oscer.send_device(COMMAND_REQUESTSESSION,
                                   self._uid,
                                   confirm_callback=self.on_confirm_request_session,
                                   timeout=5)
        self.dispatch('on_command_handle', COMMAND_DEVICEFIT, CONFIRM_OK, device, fitobj, st)

    def on_simulator_session(self, inst, session):
        self.oscer.send_device(COMMAND_NEWSESSION, self._uid, session)
        self.last_session = session
        self.dispatch('on_command_handle', COMMAND_NEWSESSION, CONFIRM_OK, inst, session)

    def __eq__(self, other):
        return self.device.__eq__(other.device)

    def get_priority(self):
        return self.device.orderd

    def get_device(self):
        return self.device

    def get_uid(self):
        return self._uid

    def get_id(self):
        return self.device.get_id()

    @staticmethod
    def u16_le(arr, idx):
        return (arr[idx] & 0xFF) | ((arr[idx + 1] & 0xFF) << 8)

    @staticmethod
    def u8_le(arr, idx):
        return arr[idx] & 0xFF

    def __init__(self, oscer, uid, service=False, device=None, db=None, user=None,
                 params=dict(), debug_params=dict(), loop=None, on_command_handle=None, on_state_transition=None):
        _LOGGER.info(f'Initing DM: {self.__class__.__name__} service={service} par={params}')
        super(GenericDeviceManager, self).__init__(**params)
        if on_command_handle:
            self.bind(on_command_handle=on_command_handle)
        if on_state_transition:
            self.bind(on_state_transition=on_state_transition)
        self._uid = uid
        self.device = device or Device(type=self.__type__)
        self.db = db
        self.debug_params = debug_params
        self.oscer = oscer
        self.user = user
        self.state = DEVSTATE_UNINIT
        self.widget = None
        self.loop = loop
        self.simulator_needs_reset = True
        self.simulator = None
        self.last_session = None
        self.info_fields = dict.fromkeys(self.__info_fields__, 'N/A')

        if service:
            self.oscer.handle_device(COMMAND_SAVEDEVICE, self._uid, self.on_command_savedevice)
            self.oscer.handle_device(COMMAND_DELDEVICE, self._uid, self.on_command_deldevice)
            self.oscer.handle_device(COMMAND_SEARCH, self._uid, self.on_command_search_device)
            self.oscer.handle_device(COMMAND_REQUESTSESSION, self._uid, self.on_command_request_session)
        else:
            global _toast
            from kivymd.toast.kivytoast.kivytoast import toast
            _toast = toast
            self.oscer.handle_device(COMMAND_DEVICEFOUND, self._uid, self.on_command_devicefound)
            self.oscer.handle_device(COMMAND_DEVICESTATE, self._uid, self.on_command_newstate)
            self.oscer.handle_device(COMMAND_NEWSESSION, self._uid, self.on_command_newsession)
            self.oscer.handle_device(COMMAND_DEVICEFIT, self._uid, self.on_command_devicefit)
