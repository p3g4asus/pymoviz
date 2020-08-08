import re

from kivy.lang import Builder
from kivy.properties import DictProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivymd.uix.list import ThreeLineListItem
from util import init_logger
from util.timer import Timer


Builder.load_string(
    '''
<BTLESearchItem>:

<SearchResultsScreen>:
    name: 'search_result'
    BoxLayout:
        orientation: 'vertical'
        MDToolbar:
            id: id_toolbar
            title: 'Search Results'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch('on_search_stop', None)]]
            elevation: 10
            size_hint_y: None
            height: dp(60)
        BoxLayout:
            size_hint_y: None
            height: self.minimum_height
            padding: [dp(30), dp(20)]
            MDProgressBar:
                min: 0
                max: 99
                value: 0
                id: id_progress
                size_hint_y: None
                height: dp(30)
        ScrollView:
            MDList:
                id: id_btds

<SearchSettingsScreen>:
    BoxLayout:
        orientation: 'vertical'
        height: self.minimum_height
        spacing_y: 0
        id: id_grid
        pos_hint: {'top': 1}
        size_hint_y: 1
        MDToolbar:
            id: id_toolbar
            title: 'Search Results'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.exit()]]
            right_action_items: [["folder-search", lambda x: root.start_search()]]
            elevation: 10
            size_hint_x: 1
            size_hint_y: None
            height: dp(60)
        BoxLayout:
            padding: [dp(30), dp(20)]
            size_hint_y: None
            height: dp(60)
            id: id_alias_cont
            MDTextField:
                pos_hint: {'top': 1}
                id: id_alias
                hint_text: 'Device alias'
                error: True
                helper_text_mode: "on_error"
                helper_text: 'Please insert a valid alias'
                on_text: root.check_alias(self, self.text)
                size_hint_y: None
                height: dp(60)
        ThreeLineListItem:
            id: id_label
        BoxLayout:
            id: id_priority
            size_hint_y: None
            height: self.minimum_height
            padding: [dp(30), dp(0)]
            MDLabel:
                size_hint_x: 0.4
                text: "Priority"
                markup: True
                size_hint_y: None
                height: dp(60)
            MDSlider:
                size_hint_x: 0.6
                id: id_orderd
                min: 1
                max: 100
                value: 50
                size_hint_y: None
                height: dp(60)
    '''
)


_LOGGER = init_logger(__name__)


class ConfWidget(object):
    conf = DictProperty(dict())

    def __init__(self, **kwargs):
        super(ConfWidget, self).__init__(**kwargs)
        self.conf2gui(self.conf)

    def on_conf(self, *args):
        self.conf2gui(self.conf)

    def is_ok(self):
        pass

    def clear(self):
        pass

    def conf2gui(self, conf):
        pass

    def gui2conf(self):
        pass


class BTLESearchItem(ThreeLineListItem):
    device = ObjectProperty()


class SearchResultsScreen(Screen):
    def __init__(self, **kwargs):
        self.register_event_type('on_search_stop')
        super(SearchResultsScreen, self).__init__(**kwargs)
        self.timer_search = None
        self.set_searching()

    def on_search_stop(self, select):
        _LOGGER.info(f'on_search_stop {select}')

    def set_searching(self, reset=False):
        if reset:
            self.ids.id_progress.value = 0
        else:
            self.ids.id_progress.value = (self.ids.id_progress.value + 10) % 100
        if self.timer_search:
            self.timer_search.cancel()
            self.timer_search = None
        if not reset:
            self.timer_search = Timer(0.10, self.set_searching)

    def stop(self):
        self.set_searching(reset=True)
        self.manager.remove_widget(self)

    def add_result(self, item):
        lst = self.ids.id_btds.children
        addr = item.device.get_address()
        for i in range(len(lst)-1, -1, -1):
            if addr == lst[i].device.get_address():
                self.ids.id_btds.remove_widget(lst[i])
                break
        self.ids.id_btds.add_widget(item)
        item.bind(on_release=self.on_device_selected)

    def on_device_selected(self, inst):
        self.dispatch('on_search_stop', inst)


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
        self.search_screen = None
        self.ids.id_grid.add_widget(self.conf_widget if self.conf_widget else BoxLayout(orientation='horizontal'))
        self.conf2gui()

    def exit(self):
        self.manager.remove_widget(self)

    def on_search(self, start):
        _LOGGER.debug('Search clicked %s' % str(start))

    def on_save(self, device):
        _LOGGER.debug('Saved device %s' % str(device))

    def conf2gui(self):
        self.device2label(self.deviceitem)
        if self.deviceitem:
            self._device = self.deviceitem.device
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
        if self.search_screen:
            self.search_screen.add_result(item)

    def check_all_ok(self):
        if self.ids.id_alias.error or not self._device or \
           (self.conf_widget and not self.conf_widget.is_ok()):
            if len(self.ids.id_toolbar.right_action_items) > 1:
                del self.ids.id_toolbar.right_action_items[1]
        else:
            self.ids.id_toolbar.right_action_items.append(
                ["content-save", lambda x: self.save_conf()])

    def save_conf(self):
        self.gui2conf()
        self.dispatch('on_save', self._device)

    def gui2conf(self):
        self._device.set_alias(self.ids.id_alias.text)
        self._device.set_orderd(self.ids.id_orderd.value)
        if self.conf_widget:
            self._device.set_additionalsettings(self.conf_widget.gui2conf())

    def on_search_stop(self, inst, deviceitem):
        if deviceitem:
            self.deviceitem = deviceitem
            self._device = deviceitem.device
            self.device2label(deviceitem)
            self.check_all_ok()
        self.dispatch('on_search', False)

    def device2label(self, deviceitem):
        if deviceitem:
            self.ids.id_label.text = deviceitem.text
            self.ids.id_label.secondary_text = deviceitem.secondary_text
            self.ids.id_label.tertiary_text = deviceitem.tertiary_text
        else:
            self.ids.id_label.text = 'Please click search'
            self.ids.id_label.secondary_text = 'UP Right'
            self.ids.id_label.tertiary_text = 'to find device'

    def set_searching(self, val=True):
        if val and not self.search_screen:
            self.search_screen = SearchResultsScreen(on_search_stop=self.on_search_stop)
            self.manager.add_widget(self.search_screen)
            self.manager.current = self.search_screen.name
        elif not val and self.search_screen:
            self.search_screen.stop()
            self.manager.current = self.name
            self.search_screen = None

    def start_search(self, start=True):
        self.dispatch('on_search', start)
