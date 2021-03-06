from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivy.properties import DictProperty, StringProperty

from kivymd.uix.list import OneLineListItem
from util import init_logger


_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
#:import MDList kivymd.uix.list.MDList
<TypeWidget>:
    name: 'type'
    BoxLayout:
        spacing: dp(5)
        height: self.minimum_height
        orientation: 'vertical'
        MDToolbar:
            pos_hint: {'top': 1}
            size_hint_y: None
            height: dp(60)
            title: root.title
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_type(root.ABORT)]]
            elevation: 10
        ScrollView:
            size_hint: (1, 0.8)
            MDList:
                id: id_types
    '''
)


class TypeWidget(Screen):
    ABORT = 'Cancel'
    types = DictProperty()
    title = StringProperty('Select')

    def __init__(self, **kwargs):
        self.register_event_type('on_type')
        super(TypeWidget, self).__init__(**kwargs)
        self.buttons = []
        _LOGGER.debug(f'Types {self.types}')
        for x in self.types.keys():
            b = OneLineListItem(text=x, on_release=self.dispatch_on_type)
            self.buttons.append(b)
            self.ids.id_types.add_widget(b)
        b = OneLineListItem(text=TypeWidget.ABORT, on_release=self.dispatch_on_type)
        self.ids.id_types.add_widget(b)

    def on_type(self, type, elem):
        _LOGGER.info(f"On type called {type}->{str(elem)}")

    def dispatch_on_type(self, widget):
        self.manager.remove_widget(self)
        if isinstance(widget, str):
            text = widget
        else:
            text = widget.text
        self.dispatch("on_type", text, self.types.get(text))
