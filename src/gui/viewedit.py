from functools import partial
import re

from db.view import View
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.properties import BooleanProperty, ListProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.utils import get_color_from_hex
from kivymd.uix.card import MDCardPost
from kivymd.uix.list import TwoLineListItem
from kivymd.uix.tab import MDTabsBase
from util import get_natural_color, init_logger
from util.timer import Timer


_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
<FormatterItem>:
    height: dp(56)
    font_style: "H6"
    secondary_font_style: "H5"

<ViewWidget>:
    name: 'view_edit'
    GridLayout:
        spacing: dp(5)
        height: self.minimum_height
        rows: 4
        cols: 1
        MDToolbar:
            id: id_toolbar
            pos_hint: {'top': 1}
            size_hint: (1, 0.2)
            title: 'New View'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_confirm(False)]]
            right_action_items: [["plus", lambda x: root.open_add_formatter_screen()]]
            elevation: 10
        BoxLayout:
            padding: [dp(30), dp(5)]
            size_hint: (1, 0.1)
            MDTextField:
                id: id_name
                icon_type: "without"
                error: False
                hint_text: "View name"
                helper_text_mode: "on_error"
                helper_text: "Enter at least a letter"
                on_text: root.enable_buttons(self, self.text)
        ScrollView:
            size_hint: (1, 0.7)
            GridLayout:
                id: id_formatters
                cols: 1
                spacing: dp(5)
                padding: dp(5)
                size_hint_y: None
                height: self.minimum_height
<FormatterAdd>:
    name: 'formatter_add'
    GridLayout:
        spacing: dp(5)
        height: self.minimum_height
        rows: 2
        cols: 1
        MDToolbar:
            pos_hint: {'top': 1}
            size_hint: (1, 0.2)
            title: 'Add Formatter'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_confirm(None)]]
            elevation: 10
        ScrollView:
            MDList:
                id: id_formatters
<ViewPlayWidget>:
    orientation: 'vertical'
    ScrollView:
        MDList:
            id: id_formatters
    '''
)


FORMATTER_COLORS = {
    'WHITE': '#FFFFFF',
    'AMBER': '#ffe082',
    'PINK': '#f48fb1',
    'PURPLE': '#ce93d8',
    'BLUE': '#90caf9',
    'GREEN': '#a5d6a7',
    'GREY': '#cfd8dc',
    'RED': '#ef9a9a',
    'BROWN': '#d7ccc8',
    'ORANGE': '#ffcc80',
    'DEEP ORANGE': '#ffccbc',
    'LIME': '#e6ee9c',
    'YELLOW': '#fff59d',
    'LIGHT BLUE': '#b3e5fc',
    'DEEP PURPLE': '#b39ddb',
    'NATURAL': None
}


def init_formatter_colors():
    if not FORMATTER_COLORS['NATURAL']:
        FORMATTER_COLORS['NATURAL'] = get_natural_color()


class ViewPlayWidget(BoxLayout, MDTabsBase):
    view = ObjectProperty()

    def __init__(self, *args, **kwargs):
        init_formatter_colors()
        super(ViewPlayWidget, self).__init__(*args, **kwargs)
        self.on_view(self.view)

    def on_view(self, *args):
        self.text = self.view.name
        try:
            for i in range(len(self.ids.id_formatters.children) - 1, -1, -1):
                fi = self.ids.id_formatters.children[i]
                if isinstance(fi, FormatterItem):
                    self.ids.id.formatters.remove_widget(fi)
            for f in self.view.items:
                fi = FormatterItem(formatter=f)
                self.ids.id_formatters.add_widget(fi)
        except Exception:
            pass

    def format(self, device, **kwargs):
        for fi in self.ids.id_formatters.children:
            fi.format(device, **kwargs)


class FormatterItem(TwoLineListItem):
    formatter = ObjectProperty()
    player = BooleanProperty(True)

    def __init__(self, *args, **kwargs):
        super(FormatterItem, self).__init__(*args, **kwargs)
        self.timer_format = None
        self.formatter2gui()

    def on_formatter(self, *args):
        self.formatter2gui()

    def rearm_fomat_timer(self):
        if self.timer_format:
            self.timer_format.cancel()
            self.timer_format = None
        if self.formatter.timeouttime > 0:
            self.timer_format = Timer(self.formatter.timeouttime, self.set_timeout)

    def set_timeout(self):
        self.secondary_text = self.formatter.set_timeout()

    def format(self, device, **kwargs):
        f = self.formatter
        txt = ''
        for types, obj in kwargs.items():
            if (not device or device.get_id() == f.device) and types == f.type:
                txt = f.format(obj)
        if txt:
            if self.player:
                self.rearm_fomat_timer()
            self.secondary_text = txt

    def formatter2gui(self):
        # self.ids.id_dropdown.items = self.colors.keys()
        # if not self.formatter.background or self.formatter.background not in self.colors:
        #     self.formatter.background = 'WHITE'
        # self.ids.id_dropdown.current_item = self.formatter.background
        self.text = self.formatter.get_title()
        self.secondary_text = self.formatter.set_timeout() if self.player else self.formatter.print_example()
        self.background_color = self.secondary_background_color =\
            get_color_from_hex(FORMATTER_COLORS[
                self.formatter.background if self.formatter.background is not None
                else 'NATURAL'])


class FormatterAdd(Screen):
    formatters = ListProperty()

    def dispatch_on_confirm(self, inst, *args):
        self.dispatch('on_confirm', inst.formatter.clone() if inst else None)

    def on_confirm(self, formatter, *args):
        _LOGGER.debug(f"On confirm called f={formatter}")

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_confirm')
        super(FormatterAdd, self).__init__(*args, **kwargs)
        for f in self.formatters:
            fi = FormatterItem(formatter=f,
                               player=False,
                               on_release=self.dispatch_on_confirm)
            self.ids.id_formatters.add_widget(fi)


class FormatterPost(MDCardPost):
    formatter = ObjectProperty()

    def change_bg(self, elem, *args, html=None, **kwargs):
        self.formatter.set_background(elem)
        self.background_color = get_color_from_hex(html)

    def __init__(self, formatter=None, callback=None):
        menu_items = []
        ll = list(FORMATTER_COLORS.keys())
        ll.sort()
        for c in ll:
            menu_items.append(dict(
                viewclass='MDMenuItem',
                text=c,
                callback=partial(self.change_bg, html=FORMATTER_COLORS[c])
            ))
        _LOGGER.debug(f'Creating post from {formatter}')
        super(FormatterPost, self).__init__(
            formatter=formatter,
            tile_font_style='H3',
            path_to_avatar=formatter.deviceobj.get_icon(),
            right_menu=menu_items,
            name_data=f'Name: {formatter.name}\nDevice: {formatter.deviceobj.get_alias()}',
            swipe=True,
            text_post=formatter.print_example(),
            card_size=(Window.width - 10, dp(80)),
            callback=partial(callback, formatter=formatter),
            background_color=get_color_from_hex(FORMATTER_COLORS[
                formatter.background if formatter.background is not None else 'NATURAL']))


class ViewWidget(Screen):
    obj = ObjectProperty(None, allownone=True)
    view = ObjectProperty(None, allownone=True)
    formatters = ListProperty()

    def __init__(self, **kwargs):
        init_formatter_colors()
        self.register_event_type('on_confirm')
        super(ViewWidget, self).__init__(**kwargs)
        self.view = self.obj
        if self.view:
            self.view = self.view.clone()
        else:
            self.view = View(name='noname', active=False, items=[])
        if self.view.items is None:
            self.view.set_items([])
        self.formatter_add = None

    def on_confirm(self, view):
        _LOGGER.debug(f"On confirm called {str(view)}")

    def on_view(self, *args):
        self.view2gui()
        _LOGGER.debug(f"On view called {str(self.view)}")

    def callback_card(self, elem, *args, formatter=None):
        self.view.items.remove(formatter)
        self.ids.id_formatters.remove_widget(elem)
        if not len(self.ids.id_formatters.children):
            self.set_enabled(False)

    def formatter2widget(self, f):
        pst = FormatterPost(formatter=f, callback=self.callback_card)
        return pst

    def gui2view(self):
        self.view.name = self.ids.id_name.text
        self.view.active = True
        i = 0
        for pst in reversed(self.ids.id_formatters.children):
            pst.formatter.set_order(i)
            i = i + 1

    def view2gui(self):
        self.ids.id_name.text = self.view.name
        for i in range(len(self.ids.id_formatters.children) - 1, -1, -1):
            self.ids.id_formatters.remove_widget(self.ids.id_formatters.children[i])
        for i in self.view.items:
            self.ids.id_formatters.add_widget(self.formatter2widget(i))
        self.enable_buttons(self.ids.id_name, self.view.name)

    def enable_buttons(self, inst, text, *args, **kwargs):
        dis = not text or not re.search(r"[A-Za-z]", text)
        if inst.error and not dis:
            inst.error = False
            inst.on_text(inst, text)
        elif not inst.error and dis:
            inst.error = True
            inst.on_text(inst, text)
        self.ids.id_toolbar.title = 'New View' if dis else f'{text} View'
        self.set_enabled(not dis and len(self.ids.id_formatters.children))

    def set_enabled(self, valid):
        if valid:
            self.ids.id_toolbar.right_action_items = [
                ["plus", lambda x: self.open_add_formatter_screen()],
                ["floppy", lambda x: self.dispatch_on_confirm()],
            ]
        else:
            self.ids.id_toolbar.right_action_items = [
                ["plus", lambda x: self.open_add_formatter_screen()]
            ]

    def open_add_formatter_screen(self):
        if not self.formatter_add:
            self.formatter_add = FormatterAdd(formatters=self.formatters, on_confirm=self.add_formatter)
        self.manager.add_widget(self.formatter_add)
        self.manager.current = self.formatter_add.name

    def add_formatter(self, inst, formatter, *args):
        self.manager.remove_widget(self.formatter_add)
        self.manager.current = self.name
        if formatter:
            self.ids.id_formatters.add_widget(self.formatter2widget(formatter))
            self.view.items.append(formatter)
        self.enable_buttons(self.ids.id_name, self.ids.id_name.text)

    def dispatch_on_confirm(self, confirm=True):
        if confirm:
            self.gui2view()
        self.dispatch('on_confirm', self.view if confirm else None)
