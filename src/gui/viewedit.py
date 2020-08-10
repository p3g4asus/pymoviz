import re
import traceback
from functools import partial

from db.view import View
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.colorpicker import ColorPicker
from kivy.uix.screenmanager import Screen
from kivy.utils import get_color_from_hex
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import TwoLineListItem
from kivymd.uix.tab import MDTabsBase
from util import init_logger
from util.timer import Timer

from .mdcardpost import ICON_TRASH, SwipeToDeleteItem

_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
<FormatterItem>:
    height: dp(56)
    font_style: "H6"
    secondary_font_style: "H5"

<ViewWidget>:
    name: 'view_edit'
    BoxLayout:
        orientation: 'vertical'
        height: self.minimum_height
        MDToolbar:
            id: id_toolbar
            pos_hint: {'top': 1}
            title: 'New View'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_confirm(False)]]
            right_action_items: [["plus", lambda x: root.open_add_formatter_screen()]]
            elevation: 10
            size_hint_x: 1
            size_hint_y: None
            height: dp(60)
        BoxLayout:
            padding: [dp(30), dp(5)]
            size_hint: (1, None)
            height: self.minimum_height
            MDTextField:
                id: id_name
                icon_type: "without"
                error: False
                hint_text: "View name"
                helper_text_mode: "on_error"
                helper_text: "Enter at least a letter"
                on_text: root.enable_buttons(self, self.text)
                size_hint_y: None
                height: dp(60)
        ScrollView:
            size_hint: (1, None)
            height: Window.height - dp(160)
            GridLayout:
                id: id_formatters
                cols: 1
                spacing: dp(5)
                padding: dp(5)
                size_hint_y: None
                height: self.minimum_height
        BoxLayout:
            orientation: 'vertical'
<FormatterAdd>:
    name: 'formatter_add'
    BoxLayout:
        spacing: dp(5)
        orientation: 'vertical'
        height: self.minimum_height
        MDToolbar:
            pos_hint: {'top': 1}
            title: 'Add Formatter'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_confirm(None)]]
            elevation: 10
            size_hint_x: 1
            size_hint_y: None
            height: dp(60)
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


def _get_color_from_hex(col):
    if col and col in FORMATTER_COLORS:
        col = FORMATTER_COLORS[col]
    if not col or col[0] != '#':
        return (0, 0, 0, 0)
    else:
        return get_color_from_hex(col)


class ViewPlayWidget(BoxLayout, MDTabsBase):

    def __init__(self, *args, **kwargs):
        if 'view' in kwargs:
            self.view = kwargs['view']
            del kwargs['view']
        else:
            self.view = None
        super(ViewPlayWidget, self).__init__(*args, **kwargs)
        self.set_view(self.view)

    def set_view(self, view):
        self.view = view
        self.text = view.name
        try:
            for i in range(len(self.ids.id_formatters.children) - 1, -1, -1):
                fi = self.ids.id_formatters.children[i]
                if isinstance(fi, FormatterItem):
                    _LOGGER.debug(f'Removing formatter {fi.formatter.get_title()}')
                    self.ids.id_formatters.remove_widget(fi)
            for f in view.items:
                fi = FormatterItem(formatter=f)
                _LOGGER.debug(f'Adding formatter {fi.formatter.get_title()}')
                self.ids.id_formatters.add_widget(fi)
            _LOGGER.debug(f'-1={self.view} 0={self.view is view} 3={id(self.view)} 4={id(view)}')
        except Exception:
            _LOGGER.error(f'On view error {traceback.format_exc()}')

    def format(self, devobj, **kwargs):
        for fi in self.ids.id_formatters.children:
            fi.format(devobj, **kwargs)


class FormatterItem(TwoLineListItem):
    formatter = ObjectProperty()
    player = BooleanProperty(True)

    def __init__(self, *args, **kwargs):
        kwargs['_no_ripple_effect'] = kwargs.get('_no_ripple_effect', True)
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

    def format(self, devobj, **kwargs):
        f = self.formatter
        txt = ''
        for types, obj in kwargs.items():
            if (not devobj or devobj.get_id() == f.device) and types == f.type:
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
        s = self.formatter.get_title()
        self.text = f'[color={self.formatter.col}]{s}[/color]' if self.formatter.col else s
        self.secondary_text = self.formatter.set_timeout() if self.player else self.formatter.print_example()
        self.bg_color = _get_color_from_hex(self.formatter.background)


class FormatterAdd(Screen):
    formatters = ListProperty()

    def dispatch_on_confirm(self, inst, *args):
        self.dispatch('on_confirm', inst.formatter.clone() if inst else None)

    def on_confirm(self, formatter, *args):
        _LOGGER.info(f"On confirm called f={formatter}")

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_confirm')
        super(FormatterAdd, self).__init__(*args, **kwargs)
        for f in self.formatters:
            fi = FormatterItem(formatter=f,
                               player=False,
                               _no_ripple_effect=False,
                               on_release=self.dispatch_on_confirm)
            self.ids.id_formatters.add_widget(fi)


class FormatterPost(SwipeToDeleteItem):
    formatter = ObjectProperty()
    remove_handler = ObjectProperty(None, allownone=True)

    def on_button_click(self, name):
        if name == ICON_TRASH:
            if self.remove_handler:
                self.remove_handler(self, formatter=self.formatter)
        else:
            self.show_color_dialog(name)

    def show_color_dialog(self, colname):
        setcol = self.formatter.get_colors_to_set()[colname]
        hex_color = setcol.get(self.formatter)
        if hex_color and hex_color[0] == '#':
            colors = dict(hex_color=hex_color)
        elif hex_color and hex_color in FORMATTER_COLORS:
            colors = dict(hex_color=FORMATTER_COLORS[hex_color])
        else:
            colors = dict(color=(0, 0, 0, 0))
        cp = ColorPicker(size_hint_y=None,
                         height=dp(300),
                         **colors)
        dialog = MDDialog(
            title="Color choice",
            type="custom",
            content_cls=cp,
            buttons=[
                MDRaisedButton(
                    text="Cancel", on_release=partial(self.on_new_color, renc=cp, colname=colname)
                ),
                MDFlatButton(
                    text="OK", on_release=partial(self.on_new_color, renc=cp, colname=colname)
                ),
            ]
        )
        dialog.open()

    def on_new_color(self, but, *args, renc=None, colname=''):
        if but.text == 'OK':
            setcol = self.formatter.get_colors_to_set()[colname]
            setcol.set(self.formatter, renc.hex_color)
            self.md_bg_color = _get_color_from_hex(self.formatter.background)
            self.text_post = self.formatter.print_example()

        while but:
            but = but.parent
            if isinstance(but, MDDialog):
                but.dismiss()
                break

    def __init__(self, formatter=None, remove_handler=None):
        menu_items = []
        ll = formatter.get_colors_to_set().keys()
        for c in ll:
            menu_items.append(dict(
                text=c,
                font_style="Caption",
                height="36dp",
                top_pad="10dp",
                bot_pad="10dp",
                divider=None
            ))
        _LOGGER.debug(f'Creating post from {formatter}')
        super(FormatterPost, self).__init__(
            formatter=formatter,
            remove_handler=remove_handler,
            path_to_avatar=formatter.deviceobj.get_icon(),
            right_menu=menu_items,
            name_data=f'Name: {formatter.name}\nDevice: {formatter.deviceobj.get_alias()}',
            text_post=formatter.print_example(),
            height=dp(80),
            md_bg_color=_get_color_from_hex(formatter.background))


class ViewWidget(Screen):
    obj = ObjectProperty(None, allownone=True)
    view = ObjectProperty(None, allownone=True)
    formatters = ListProperty()

    def __init__(self, **kwargs):
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
        _LOGGER.info(f"On confirm called {str(view)}")

    def on_view(self, *args):
        self.view2gui()
        _LOGGER.info(f"On view called {str(self.view)}")

    def remove_card(self, elem, *args, formatter=None):
        self.view.items.remove(formatter)
        self.ids.id_formatters.remove_widget(elem)
        if not len(self.ids.id_formatters.children):
            self.set_enabled(False)

    def formatter2widget(self, f):
        pst = FormatterPost(formatter=f, remove_handler=self.remove_card)
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
