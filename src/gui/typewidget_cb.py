from gui.list_item_cb import get_brand_item
from kivy.lang import Builder
from kivy.properties import DictProperty, ObjectProperty, StringProperty
from kivy.uix.screenmanager import Screen
from util import init_logger


_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
#:import MDList kivymd.uix.list.MDList
#:import Window kivy.core.window.Window
<TypeWidgetCB>:
    name: 'type_cb'
    BoxLayout:
        id: id_grid
        size_hint_y: None
        size_hint_x: 1
        height: Window.height
        orientation: 'vertical'
        spacing_y: dp(20)
        MDToolbar:
            pos_hint: {'top': 1}
            title: root.title
            id: id_toolbar
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_type(False)]]
            elevation: 10
            size_hint_y: None
            height: dp(60)
        ScrollView:
            size_hint_y: None
            height: id_grid.height - (box_buttons.height + id_toolbar.height\
                 + dp(10))
            MDList:
                id: id_types
        BoxLayout:
            id: box_buttons
            size_hint_y: None
            height: dp(20)
            spacing: dp(10)
            padding: dp(10)
            MDFlatButton:
                id: id_btnko
                text: 'Cancel'
                theme_text_color: 'Custom'
                text_color: self.theme_cls.primary_color
                on_release: root.dispatch_on_type(False)
            MDRaisedButton:
                id: id_btnok
                disabled: True
                text: 'OK'
                on_release: root.dispatch_on_type(True)
    '''
)


class TypeWidgetCB(Screen):
    types = DictProperty()
    _cptypes = DictProperty()
    group = StringProperty(None, allownone=True)
    title = StringProperty()
    editclass = ObjectProperty()
    editpars = DictProperty()

    def __init__(self, **kwargs):
        self.register_event_type('on_type')
        super(TypeWidgetCB, self).__init__(**kwargs)
        self.buttons = []
        self.edit_widget = None
        self.edit_widget_txt = None
        for x, o in self.types.items():
            b = get_brand_item(group=self.group,
                               text=x,
                               brandinfo=x,
                               active=o['active'],
                               on_brand=self.on_brand_selected)
            self.buttons.append(b)
            self.ids.id_types.add_widget(b)
        _LOGGER.info(f'Sizes {self.ids.id_grid.height} {self.ids.box_buttons.height} {self.ids.id_toolbar.height}')

    def on_type(self, lst):
        _LOGGER.info(f"On type called {str(lst)}")

    def set_btn_enabled(self):
        if len(self._cptypes) > 0:
            for b in self.buttons:
                if b.get_active():
                    self.ids.id_btnok.disabled = False
                    return
        self.ids.id_btnok.disabled = True

    def on_edit_confirm(self, inst, newobj):
        if newobj:
            if self.edit_widget_txt not in self._cptypes:
                src = self._cptypes[self.edit_widget_txt] = dict(self.types[self.edit_widget_txt])
            else:
                src = self._cptypes[self.edit_widget_txt]
            src['obj'] = newobj
            self.set_btn_enabled()
        self.manager.remove_widget(self.edit_widget)
        self.manager.current = self.name
        self.edit_widget = None
        self.edit_widget_txt = None

    def on_brand_selected(self, inst, brandinfo, active):
        if active is None:
            if self.editclass is not None:
                self.edit_widget_txt = brandinfo
                self.edit_widget = self.editclass(
                    obj=self.types[brandinfo]['obj'],
                    on_confirm=self.on_edit_confirm,
                    **self.editpars
                )
                self.manager.add_widget(self.edit_widget)
                self.manager.current = self.edit_widget.name
            else:
                inst.ids.id_cb.trigger_action()
        else:
            if brandinfo not in self._cptypes:
                src = self._cptypes[brandinfo] = dict(self.types[brandinfo])
            else:
                src = self._cptypes[brandinfo]
            src['active'] = active
            self.set_btn_enabled()

    def dispatch_on_type(self, ok):
        self.manager.remove_widget(self)
        self.dispatch("on_type", self._cptypes if ok else None)
