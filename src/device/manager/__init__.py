import abc
import json
import re
from functools import partial

from able import (REASON_DISCOVER_ERROR, STATE_CONNECTED, STATE_DISCONNECTED)
from db.device import Device
from db.label_formatter import StateFormatter
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import BooleanProperty, DictProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.list import IRightBodyTouch, ThreeLineRightIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from util.bluetooth_dispatcher import BluetoothDispatcher
from util.const import (COMMAND_CONFIRM, COMMAND_DELDEVICE, COMMAND_DEVICEFIT,
                        COMMAND_DEVICEFOUND, COMMAND_DEVICESTATE, COMMAND_NEWSESSION,
                        COMMAND_SAVEDEVICE, COMMAND_SEARCH, CONFIRM_FAILED_1,
                        CONFIRM_FAILED_2, CONFIRM_FAILED_3, CONFIRM_OK,
                        DEVREASON_BLE_DISABLED, DEVREASON_OPERATION_ERROR,
                        DEVREASON_PREPARE_ERROR, DEVREASON_REQUESTED,
                        DEVREASON_SIMULATOR, DEVREASON_STATECHANGE,
                        DEVSTATE_CONNECTED, DEVSTATE_CONNECTING,
                        DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_INVALIDSTEP, DEVSTATE_SEARCHING,
                        DEVSTATE_UNINIT, MSG_COMMAND_TIMEOUT,
                        MSG_CONNECTION_STATE_INVALID, MSG_DB_SAVE_ERROR,
                        REASON_NOT_ENABLED)
from util.timer import Timer

Builder.load_string(
    '''
<BTLESearchItem>:
    font_style: 'H1'
    secondary_font_style: 'H2'
    tertiary_font_style: 'H5'
    on_release: id_cb.trigger_action()
    MyCheckbox:
        id: id_cb
        disabled: root.disabled
        group: 'devices'
        on_active: root.dispatch_on_sel(self, self.active)

<SearchSettingsScreen>:
    name: 'conf_d' + root.device.get_alias()
    GridLayout:
        cols: 1
        rows: 5
        spacing: dp(5)
        height: self.minimum_height
        id: id_grid
        MDToolbar:
            id: id_toolbar
            title: root.device.get_name().title() + " Configuration"
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.exit()]]
            right_action_items: []
            elevation: 10
        MDTextField:
            size_hint: (1, 0.1)
            id: id_alias
            hint_text: 'Device alias'
            error: True
            helper_text_mode: "on_error"
            helper_text: 'Please inseart a valid alias'
            on_text: root.check_alias(self, self.text)
        MDLabel:
            size_hint: (1, 0.1)
            text: "Priority"
            markup: True
            halign: "center"
        MDSlider:
            size_hint: (1, 0.1)
                id: id_orderd
                min: 1
                max: 9999
                value: 99
        AnchorLayout:
            size_hint: (1, 0.1)
            MDRectangleFlatIconButton:
                id: id_search
                on_release: root.start_search()
                icon: "subdirectory-arrow-left"
                text: "Search"
        MDProgressBar:
            size_hint: (1, 0.1)
            min: 0
            max: 99
            id: id_progress
        ScrollView:
            size_hint: (1, 0.2)
            MDList:
                id: id_btds
    '''
)


class ConfWidget(BoxLayout, abc.ABC):
    conf = DictProperty(dict())

    def __init__(self, **kwargs):
        super(ConfWidget, self).__init__(**kwargs)
        self.conf2gui(self.conf)

    def on_conf(self, conf):
        self.conf2gui(self.conf)

    @abc.abstractmethod
    def is_ok(self):
        pass

    @abc.abstractmethod
    def clear(self):
        pass

    @abc.abstractmethod
    def conf2gui(self, conf):
        pass

    @abc.abstractmethod
    def gui2conf(self):
        pass


class MyCheckbox(MDCheckbox, IRightBodyTouch):
    pass


class BTLESearchItem(ThreeLineRightIconListItem):
    device = ObjectProperty()
    disabled = BooleanProperty(False)

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_sel')
        if 'active' in kwargs:
            act = kwargs['active']
            del kwargs['active']
        else:
            act = False
        super(BTLESearchItem, self).__init__(*args, **kwargs)
        self.set_active(act)

    def set_active(self, value):
        self.ids.id_cb.active = value

    def is_active(self):
        return self.ids.id_cb.active

    def dispatch_on_sel(self, inst, active):
        self.dispatch("on_sel", self.device, active)

    def on_sel(self, btd, active):
        Logger.debug("On on_sel %s (%s)" % (str(self.device.get_address()), str(active)))


class SearchSettingsScreen(Screen):
    _device = ObjectProperty(None, allownone=True)
    deviceitem = ObjectProperty(None, allownone=True)
    conf_widget = ObjectProperty(None)

    def __init__(self, **kwargs):
        self.register_event_type('on_save')
        self.register_event_type('on_search')
        super(SearchSettingsScreen, self).__init__(**kwargs)
        self.timer_search = None
        if self.conf_widget:
            self.ids.id_grid.add_widget(self.conf_widget)
        self.conf2gui()

    def exit(self):
        self.manager.remove_widget(self)

    def on_search(self, start):
        Logger.debug('Search clicked %s' % str(start))

    def on_save(self, device):
        Logger.debug('Saved device %s' % str(device))

    def conf2gui(self):
        self.clear_results()
        if self.deviceitem:
            self._device = self.deviceitem.device
            self.add_result(self.deviceitem)
            self.ids.id_alias.text = self._device.get_alias()
            self.ids.id_orderd.value = self._device.get_orderd()
            if self.conf_widget:
                self.conf_widget.conf2gui(self._device.get_additionalsettings())
        else:
            self._device = None
            self.ids.id_alias.text = ''
            self.ids.id_orderd.value = 999
            if self.conf_widget:
                self.conf_widget.clear()

    def clear_results(self):
        lst = self.ids.id_btds.children
        self._device = None
        for i in range(len(lst)-1, -1, -1):
            self.ids.id_btds.remove_widget(lst[i])

    def check_alias(self, field, txt):
        if re.search(r'[a-zA-Z0-9_]+', txt):
            if field.error:
                field.error = False
                field.on_text(field, txt)
                self.check_all_ok()
        elif not field.error:
            field.error = True
            field.on_text(field, txt)
            self.check_all_ok()

    def add_result(self, item):
        lst = self.ids.id_btds.children
        addr = item.device.get_address()
        for i in range(len(lst)-1, -1, -1):
            if addr == lst[i].device.get_address():
                self.ids.id_btds.remove_widget(lst[i])
                if lst[i].is_active():
                    item.set_active(True)
                    self._device = item.device
                break
        self.ids.id_btds.add_widget(item)
        item.bind(on_sel=self.on_device_selected)

    def check_all_ok(self):
        if self.ids.id_search.error or not self._device or \
           (self.conf_widget and not self.conf_widget.is_ok()):
            del self.ids.id_toolbar.right_action_items[:]
        else:
            self.ids.id_toolbar.right_action_items =\
                [["content-save", lambda x: self.save_conf()]]

    def save_conf(self):
        self.gui2conf()
        self.dispatch('on_save', self._device)

    def gui2conf(self):
        self._device.set_alias(self.ids.id_alias.text)
        self._device.set_orderd(self.ids.id_orderd.value)
        if self.conf_widget:
            self._device.set_additionalsettings(self.conf_widget.gui2conf())

    def on_device_selected(self, inst, device, active):
        if active:
            self._device = device
        else:
            self._device = None
        self.check_all_ok()

    def set_searching(self, val=True, reset=True):
        if reset:
            self.ids.id_progress.value = 0
        else:
            self.ids.id_progress.value = (self.ids.id_progress.value + 10) % 100
        if self.timer_search:
            self.timer_search.cancel()
            self.timer_search = None
        if val:
            self.timer_search = Timer(0.25, partial(self.set_searching, reset=False))

    def start_search(self):
        self.clear_results()
        if self.ids.id_search.text == "Search":
            self.ids.id_search.text = "Stop"
            self.dispatch('on_search', True)
        else:
            self.ids.id_search.text = "Search"
            self.dispatch('on_search', False)


class GenericDeviceManager(BluetoothDispatcher, abc.ABC):

    @classmethod
    def do_activity_pre_operations(cls, on_finish, loop):
        on_finish(True)

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

    @classmethod
    def get_scan_filters(cls, scanning_for_new_devices=False):
        return None

    @classmethod
    def get_scan_settings(cls, scanning_for_new_devices=False):
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

    @abc.abstractmethod
    def save_conf(self, widget):
        pass

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
        list_of_dm.sort(key=lambda x: x.device)

    def get_state(self):
        return self.state

    def get_formatters(self):
        ll = list(self.__formatters___)
        ll.append(StateFormatter('State'))
        for f in ll:
            ll.set_device(self.device)
        return ll

    def set_state(self, st, reason=-1):
        oldstate = self.state
        if oldstate != st:
            self.state = st
            self.send_device(COMMAND_DEVICESTATE, self.uid, oldstate, st, reason)
            self.dispatch("on_state_transition", oldstate, st, reason)

    def connect(self, *args):
        if self.is_stopped_state():
            self.set_state(DEVSTATE_CONNECTING, DEVREASON_REQUESTED)
            if self.simulator_needs_reset and self.simualtor:
                self.simulator_needs_reset = False
                self.simulator.reset(self.device.get_additionalsettings(), self.user)
            self.inner_connect()

    def disconnect(self, *args):
        if self.is_connected_state() or self.state == DEVSTATE_CONNECTING:
            self.set_state(DEVSTATE_DISCONNECTING, DEVREASON_REQUESTED)
            self.inner_disconnect()
            self.simulator_needs_reset = True

    async def step(self, obj):
        st = await self.simulator.step(obj)
        self.set_state(st, DEVREASON_SIMULATOR)
        if st != DEVSTATE_INVALIDSTEP:
            self.oscer.send_device(COMMAND_DEVICEFIT, self.uid, self.device, obj, st)

    def on_connection_state_change(self, status, state):
        if state == STATE_DISCONNECTED:
            self.set_state(DEVSTATE_DISCONNECTED, DEVREASON_STATECHANGE)
            # if oldstate != DEVSTATE_DISCONNECTING:
            #     self.connect()
        elif state == STATE_CONNECTED:
            self.set_state(DEVSTATE_CONNECTED, DEVREASON_STATECHANGE)

    def get_settings_screen(self):
        if not self.widget:
            swc = self.get_settings_widget_class()
            swi = swc() if swc else None
            self.widget = SearchSettingsScreen(
                deviceitem=self.get_device_item(self.device),
                conf_widget=swi,
                on_save=self.on_save_device,
                on_search=self.on_search_device)
        return self.widget

    def on_device(self, device, rssi, advertisement):
        if self.state == DEVSTATE_SEARCHING:
            adv = json.loads(advertisement)\
                  if advertisement and isinstance(advertisement, str) else\
                  advertisement
            d = Device(
                address=device['address'] if isinstance(device, dict) else device.getAddress(),
                name=device['name'] if isinstance(device, dict) else device.getName(),
                rssi=rssi,
                type=self.__type__,
                advertisement=adv
            )
            self.oscer.send_device(COMMAND_DEVICEFOUND, self.uid, d.serialize())

    async def on_command_savedevice_async(self, device, *args):
        rv = await device.to_db(self.db)
        if rv:
            self.device = device
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_OK, device)
            self.dispatch('on_command_handle', COMMAND_SAVEDEVICE, CONFIRM_OK)
        else:
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(device))
            self.dispatch('on_command_handle', COMMAND_SAVEDEVICE, CONFIRM_FAILED_1)

    def on_command_savedevice(self, device, *args):
        if self.is_stopped_state():
            Timer(0, partial(self.on_command_savedevice_async, device))
        else:
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID)
            self.dispatch('on_command_handle', COMMAND_SAVEDEVICE, CONFIRM_FAILED_2)

    async def on_command_deldevice_async(self, device, *args):
        rv = await device.remove(self.db)
        if rv:
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_OK, device)
            self.dispatch('on_command_handle', COMMAND_DELDEVICE, CONFIRM_OK)
        else:
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(device))
            self.dispatch('on_command_handle', COMMAND_DELDEVICE, CONFIRM_FAILED_1)

    def on_command_deldevice(self, device, *args):
        if self.is_stopped_state():
            Timer(0, partial(self.on_command_deldevice_async, device))
        else:
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID)
            self.dispatch('on_command_handle', COMMAND_DELDEVICE, CONFIRM_FAILED_2)

    def on_save_device(self, inst, device):
        self.oscer.send_device(COMMAND_SAVEDEVICE, self.uid, device, confirm_handle=self.on_confirm_save_device, timeout=5)

    def on_confirm_save_device(self, *args, timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        elif args[0] == CONFIRM_OK:
            self.device = args[1]
            self.widget.exit()
            return
        else:
            msg = args[1]
            exitv = args[0]
        toast(f"[E {exitv}] {msg}")

    def del_device(self, on_del_device=None):
        self.oscer.send_device(COMMAND_DELDEVICE,
                               self.uid,
                               self.device,
                               confirm_handle=partial(self.on_confirm_del_device,
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
        toast(f"[E {exitv}] {msg}")

    def on_command_devicefound(self, device, *args):
        if self.widget:
            self.widget.add_result(self.get_device_item(device, False))

    def on_command_newstate(self, oldstate, newstate, reason, *args):
        if newstate == DEVSTATE_CONNECTED:
            toast(self.device.get_alias() + " connected OK")
        elif newstate == DEVSTATE_CONNECTING:
            toast(self.device.get_alias() + " trying to connect...")
        elif newstate == DEVSTATE_SEARCHING:
            toast(f"Searching for device of type {self.device.get_type()}")
            if self.widget:
                self.widget.set_searching(True)
        elif newstate == DEVSTATE_DISCONNECTED and oldstate == DEVSTATE_CONNECTING:
            if reason == DEVREASON_REQUESTED:
                toast(self.device.get_alias() + " disconnected")
            elif reason == DEVREASON_PREPARE_ERROR:
                toast(self.device.get_alias() + " connection preparation error: stopping")
            elif reason == DEVREASON_BLE_DISABLED:
                toast("Need to enable bluetooth")
            else:
                toast(self.device.get_alias() + " connection failed")
        elif newstate == DEVSTATE_DISCONNECTED and oldstate == DEVSTATE_SEARCHING:
            if reason == DEVREASON_REQUESTED:
                toast("Search for device of ended")
            else:
                toast("Search init error: Is bluetooth up and running?")
            if self.widget:
                self.widget.set_searching(False)

    def on_search_device(self, inst, startcommand):
        self.oscer.send_device(COMMAND_SEARCH, self.uid, startcommand, confirm_callback=self.on_confirm_search_device, timeout=5)

    def on_confirm_search_device(self, *args, timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        elif args[0] != CONFIRM_OK:
            msg = args[1]
            exitv = args[0]
        else:
            return
        toast(f"[E {exitv}] {msg}")

    def search(self, val):
        if val and self.sate == DEVSTATE_UNINIT or self.state == DEVSTATE_DISCONNECTED:
            self.start_scan(self.get_scan_settings(scanning_for_new_devices=True),
                            self.get_scan_filters(scanning_for_new_devices=True))
            return True
        elif not val and self.state == DEVSTATE_SEARCHING:
            self.stop_scan()

    def on_command_search_device(self, inst, startcommand):
        rv = CONFIRM_OK
        if startcommand:
            if not (self.sate == DEVSTATE_UNINIT or self.state == DEVSTATE_DISCONNECTED):
                rv = CONFIRM_FAILED_1
        elif self.state != DEVSTATE_SEARCHING:
            rv = CONFIRM_FAILED_2
        if rv != CONFIRM_OK:
            self.oscer.send_device(COMMAND_CONFIRM, rv, MSG_CONNECTION_STATE_INVALID)
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
        device = device or self.device
        return BTLESearchItem(
            device=device,
            active=active,
            text=self.device2line1(device),
            secondary_text=self.device2line2(device),
            tertiary_text=self.device2line3(device)) if device.get_address() else None

    def set_user(self, user):
        self.user = user

    __events__ = list(BluetoothDispatcher.__events__)
    __events__.append('on_state_transition')
    __events__.append('on_command_handle')
    __events__ = tuple(__events__)

    def on_state_transition(self, fromv, tov, rea):
        Logger.debug(f'Device: transition from state {fromv} to {tov}')
        if tov == DEVSTATE_DISCONNECTED and fromv != DEVSTATE_DISCONNECTING:
            self.simulator.set_offsets()

    def on_command_handle(self, command, exitv):
        Logger.debug(f'Handled command {command}: {exitv}')

    def on_simulator_session(self, inst, session):
        self.dispatch('on_command_handle', COMMAND_NEWSESSION, CONFIRM_OK, inst, session)

    def __eq__(self, other):
        return self.device.__eq__(other.device)

    def get_device(self):
        return self.device

    def get_uid(self):
        return self.uid

    def get_id(self):
        return self.device.get_id()

    def __init__(self, oscer, uid, service=False, device=None, db=None, user=None, params=dict(), loop=None, **kwargs):
        super(GenericDeviceManager, self).__init__(**params)
        self.uid = uid
        self.device = device or Device(type=self.__type__)
        self.db = db
        self.params = params
        self.oscer = oscer
        self.user = user
        self.state = DEVSTATE_UNINIT
        self.widget = None
        self.loop = loop
        self.simulator_needs_reset = True
        self.simualtor = None
        if service:
            self.oscer.handle_device(COMMAND_SAVEDEVICE, self.uid, self.on_command_savedevice)
            self.oscer.handle_device(COMMAND_DELDEVICE, self.uid, self.on_command_deldevice)
            self.oscer.handle_device(COMMAND_SEARCH, self.uid, self.on_command_search_device)
            self.simulator = self.__simulator_class__(self.device.get_id(), self.device.get_additionalsettings(), self.user.get_id(), self.db, on_session=self.on_simulator_session)
        else:
            self.oscer.handle_device(COMMAND_DEVICEFOUND, self.uid, self.on_command_devicefound)
            self.oscer.handle_device(COMMAND_DEVICESTATE, self.uid, self.on_command_newstate)

        for key in kwargs:
            setattr(self, key, kwargs[key])
