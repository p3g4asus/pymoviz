import re
from functools import partial

from db.view import View
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import ListProperty, ObjectProperty
from kivy.uix.screenmanager import Screen
from kivy.utils.get_color_from_hex import hex
from kivymd.uix.card import MDCardPost
from kivymd.uix.list import TwoLineListItem
from kivymd.uix.tab import MDTabsBase

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
            left_action_items: [["arrow-left", lambda x: root.dispatch_confirm(False)]]
            right_action_items: [["plus", lambda x: root.open_add_formatter_screen()]]
            elevation: 10
        BoxLayout:
            padding: [dp(30), dp(5)]
            size_hint: (1, 0.1)
            MDTextField:
                id: id_name
                icon_type: "without"
                error: True
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
            left_action_items: [["arrow-left", lambda x: root.dispatch_confirm(None)]]
            elevation: 10
        ScrollView:
            MDList:
                id: id_formatters
<ViewPlayWidget>:
    BoxLayout:
        orientation: 'vertical'
        ScrollView:
            MDList:
                id: id_formatters
    '''
)


class ViewPlayWidget(MDTabsBase):
    view = ObjectProperty()

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_confirm')
        super(FormatterAdd, self).__init__(*args, **kwargs)

    def on_view(self, view):
        self.text = view.name
        for i in range(len(self.ids.id_formatters.children) - 1, -1, -1):
            fi = self.ids.id_formatters.children[i]
            if isinstance(fi, FormatterItem):
                self.ids.id.formatters.remove_widget(fi)
        for f in view.items:
            fi = FormatterItem(formatter=f)
            self.ids.id_formatters.add_widget(fi)

    def format(self, *args):
        for f in self.view.items:
            f.format(*args)


class FormatterItem(TwoLineListItem):
    formatter = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super(FormatterItem, self).__init__(*args, **kwargs)
        self.formatter2gui()

    def format(self, *args):
        txt = self.formatter.format(*args)
        if txt:
            self.secondary_text = txt

    def formatter2gui(self):
        # self.ids.id_dropdown.items = self.colors.keys()
        # if not self.formatter.background or self.formatter.background not in self.colors:
        #     self.formatter.background = 'WHITE'
        # self.ids.id_dropdown.current_item = self.formatter.background
        self.text = self.formatter.get_title()
        self.secondary_text = self.formatter.print_example()


class FormatterAdd(Screen):
    formatters = ListProperty()

    def dispatch_confirm(self, inst, *args):
        self.dispatch('on_confirm', inst.formatter.clone() if inst else None)

    def on_confirm(self, formatter, *args):
        Logger.debug(f"On confirm called f={formatter}")

    def __init__(self, *args, **kwargs):
        self.register_event_type('on_confirm')
        super(FormatterAdd, self).__init__(*args, **kwargs)
        for f in self.formatters:
            fi = FormatterItem(formatter=f, on_release=self.dispatch_on_confirm)
            self.ids.id_formatters.add_widget(fi)


class FormatterPost(MDCardPost):
    formatter = ObjectProperty()

    def change_bg(self, elem, *args, html=None, **kwargs):
        self.formatter.set_background(elem)
        self.background_color = hex(html)

    def __init__(self, *args, **kwargs):
        menu_items = []
        ll = list(ViewWidget.FORMATTER_COLORS.keys())
        ll.sort()
        for c in ll:
            menu_items.append(dict(
                viewclass='MDMenuItem',
                text=c,
                callback=partial(self.change_bg, html=ViewWidget.FORMATTER_COLORS[c])
            ))
        f = kwargs['formatter']
        callback = kwargs['callback']
        if f.background:
            kwargs['background_color'] = hex(ViewWidget.FORMATTER_COLORS[f.background])
        super(FormatterPost, self).__init__(
            tile_font_style='H3',
            path_to_avatar=f.deviceobj.get_icon(),
            right_menu=menu_items,
            name_data=f'Name: {f.name}\nDevice: {f.deviceobj.get_alias()}',
            swipe=True,
            text_post=f.print_example(),
            callback=partial(callback, formatter=f), **kwargs)


class ViewWidget(Screen):
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
        'DEEP PURPLE': '#b39ddb'
    }
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
            self.view = View(name='noname', active=False)
        if self.view.items is None:
            self.view.items = []
        self.formatter_add = None
        self.view2gui()

    def on_confirm(self, view):
        Logger.debug(f"On confirm called {str(view)}")

    def on_view(self, view):
        self.view2gui()
        Logger.debug(f"On view called {str(view)}")

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
        for i, pst in enumerate(self.ids.id_formatters.children):
            pst.formatter.set_order(i)

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
        self.set_enabled(not dis and len(self.ids.id_formatters.children))

    def set_enabled(self, valid):
        if valid:
            self.ids.id_toolbar.right_action_items = [
                ["plus", lambda x: self.open_add_formatter_screen()],
                ["floppy", lambda x: self.dispatch_confirm()],
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

    def dispatch_confirm(self, confirm=True):
        if confirm:
            self.gui2view()
        self.dispatch('on_confirm', self.view if confirm else None)
