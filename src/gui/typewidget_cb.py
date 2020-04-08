from gui.list_item_cb import get_brand_item
from kivy.lang import Builder
from kivy.properties import DictProperty, ObjectProperty, StringProperty
from kivy.uix.screenmanager import Screen
from util import get_natural_color, init_logger


_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
#:import MDList kivymd.uix.list.MDList
<TypeWidgetCB>:
    name: 'type_cb'
    GridLayout:
        spacing: dp(5)
        height: self.minimum_height
        rows: 3
        cols: 1
        MDToolbar:
            pos_hint: {'top': 1}
            size_hint: (1, 0.2)
            title: root.title
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_type(False)]]
            elevation: 10
        ScrollView:
            size_hint: (1, 0.8)
            MDList:
                id: id_types
        BoxLayout:
            id: box_buttons
            AnchorLayout:
                anchor_x: "right"
                size_hint_y: None
                height: dp(30)
                BoxLayout:
                    size_hint_x: None
                    spacing: dp(5)
                    MDRaisedButton:
                        id: id_btnok
                        disabled: True
                        text: 'OK'
                        on_release: root.dispatch_on_type(True)
                    MDFlatButton:
                        id: id_btnko
                        text: 'Cancel'
                        theme_text_color: 'Custom'
                        text_color: self.theme_cls.primary_color
                        on_release: root.dispatch_on_type(False)
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
        col = get_natural_color(False)
        for x, o in self.types.items():
            b = get_brand_item(group=self.group,
                               text=x,
                               brandinfo=x,
                               active=o['active'],
                               background_color=col,
                               on_brand=self.on_brand_selected)
            self.buttons.append(b)
            self.ids.id_types.add_widget(b)

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
