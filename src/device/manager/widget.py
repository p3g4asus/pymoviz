from functools import partial
import re

from kivy.lang import Builder
from kivy.properties import BooleanProperty, DictProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivymd.uix.list import IRightBodyTouch, ThreeLineRightIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from util import init_logger
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
    GridLayout:
        cols: 1
        rows: 5
        height: self.minimum_height
        id: id_grid
        MDToolbar:
            id: id_toolbar
            title: 'Device'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.exit()]]
            right_action_items: []
            elevation: 10
        BoxLayout:
            size_hint: (1, 0.4)
            padding: [dp(30), dp(20)]
            MDTextField:
                id: id_alias
                hint_text: 'Device alias'
                error: True
                helper_text_mode: "on_error"
                helper_text: 'Please insert a valid alias'
                on_text: root.check_alias(self, self.text)
        ScrollView:
            size_hint: (1, 0.3)
            MDList:
                id: id_btds
        GridLayout:
            rows: 2
            cols: 2
            padding: [dp(30), dp(20)]
            MDLabel:
                text: "Priority"
                markup: True
            MDSlider:
                id: id_orderd
                min: 1
                max: 100
                value: 50
            MDRectangleFlatIconButton:
                pos_hint: {'top': 1}
                id: id_search
                on_release: root.start_search()
                icon: "folder-search"
                text: "Search"
            MDProgressBar:
                min: 0
                max: 99
                id: id_progress
    '''
)


_LOGGER = init_logger(__name__)


class ConfWidget(BoxLayout):
    conf = DictProperty(dict())

    def __init__(self, **kwargs):
        super(ConfWidget, self).__init__(**kwargs)
        self.conf2gui(self.conf)

    def on_conf(self, conf):
        self.conf2gui(self.conf)

    def is_ok(self):
        pass

    def clear(self):
        pass

    def conf2gui(self, conf):
        pass

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
        _LOGGER.debug("On on_sel %s (%s)" % (str(self.device.get_address()), str(active)))


class SearchSettingsScreen(Screen):
    _device = ObjectProperty(None, allownone=True)
    deviceitem = ObjectProperty(None, allownone=True)
    conf_widget = ObjectProperty(None)
    devicetype = StringProperty()

    def __init__(self, **kwargs):
        self.register_event_type('on_save')
        self.register_event_type('on_search')
        super(SearchSettingsScreen, self).__init__(**kwargs)
        self.name = 'conf_d' + self.devicetype
        self.timer_search = None
        if self.conf_widget:
            self.ids.id_grid.add_widget(self.conf_widget)
        self.conf2gui()

    def exit(self):
        self.manager.remove_widget(self)

    def on_search(self, start):
        _LOGGER.debug('Search clicked %s' % str(start))

    def on_save(self, device):
        _LOGGER.debug('Saved device %s' % str(device))

    def conf2gui(self):
        self.clear_results()
        if self.deviceitem:
            self._device = self.deviceitem.device
            self.add_result(self.deviceitem)
            self.ids.id_toolbar.title = f'{self._device.get_alias()} Configuration'
            self.ids.id_alias.text = self._device.get_alias()
            self.ids.id_orderd.value = self._device.get_orderd()
            if self.conf_widget:
                self.conf_widget.conf2gui(self._device.get_additionalsettings())
        else:
            self._device = None
            self.ids.id_toolbar.title = f'{self.devicetype} Device Configuration'
            self.ids.id_alias.text = ''
            self.ids.id_orderd.value = 50
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
                self.ids.id_toolbar.title = f'{self.ids.id_alias.text} Configuration'
        elif not field.error:
            field.error = True
            self.ids.id_toolbar.title = f'{self.devicetype} Device Configuration'
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
            self.ids.id_search.icon = "Stop"
            self.dispatch('on_search', True)
        else:
            self.ids.id_search.text = "Search"
            self.ids.id_search.icon = "stop"
            self.dispatch('on_search', False)
