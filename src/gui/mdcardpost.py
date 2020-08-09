# from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (ListProperty, NumericProperty, ObjectProperty, StringProperty)
from kivy.uix.image import Image
from kivymd.uix.button import MDIconButton
from kivymd.uix.card import MDCardSwipe, MDCardSwipeFrontBox
from kivymd.uix.list import ILeftBody
from kivymd.uix.menu import MDDropdownMenu

ICON_IMAGE = '__image__'
ICON_TRASH = '__trash__'

Builder.load_string(
    """
<CardElement>
    spacing: dp(5)
    pos_hint: {'top': 1}
    orientation: 'vertical'
    size_hint_y: None
    x: dp(10)

    BoxLayout:
        id: title_box
        size_hint_y: None
        height: dp(50)
        spacing: dp(10)

        LeftIcon:
            source: root.path_to_avatar
            size_hint_x: None
            width: self.height
            allow_stretch: True

        MDLabel:
            markup: True
            text: root.name_data
            text_size: self.width, None
            theme_text_color: 'Primary'
            bold: True
            font_size: '12sp'

    BackgroundLabel:
        id: text_post
        background_color: root.background_color
        text: root.text_post
        markup: True
        font_size: '14sp'
        size_hint_y: None
        valign: 'top'
        height: self.texture_size[1]
        text_size: self.width - dp(5), None
        theme_text_color: 'Primary'

<SwipeToDeleteItem>:
    size_hint_y: None
    height: dp(335)
    anchor: 'right'
    swipe_distance: 150
    max_swipe_x: 0.92

    MDCardSwipeLayerBox:
        canvas:
            Color:
                # #263238
                rgba: root.md_bg_color

            Rectangle:
                size: self.size
        AnchorLayout:
            anchor_x: 'right'
            anchor_y: 'center'
            # Content under the card.
            MDIconButton:
                icon: "trash-can"
                pos_hint: {"center_y": .5, "right": 1}
                on_release: root.callback(root, '__trash__')

    CardElement:
        id: id_card
        md_bg_color: root.md_bg_color if root.md_bg_color[3] else self.theme_cls.bg_light
        height: root.height
        path_to_avatar: root.path_to_avatar
        text_post: root.text_post
        name_data: root.name_data
        right_menu: root.right_menu
        background_color: root.background_color
        width_mult: root.width_mult
    """
)


class LeftIcon(ILeftBody, Image):
    pass


class CardElement(MDCardSwipeFrontBox):
    path_to_avatar = StringProperty()
    text_post = StringProperty()
    name_data = StringProperty()
    right_menu = ListProperty()
    _menu_button = ObjectProperty(None, allownone=True)
    background_color = ListProperty([1, 1, 1, 0])
    md_bg_color = ListProperty([1, 1, 1, 1])
    width_mult = NumericProperty(3.5)

    def __init__(self, **kwargs):
        self.register_event_type('on_button_click')
        super().__init__(**kwargs)
        # self.bind(buttons=self.on_buttons)
        self.add_menu_items()

    def add_menu_items(self):
        if len(self.right_menu) and not self._menu_button:
            self._menu_button = MDIconButton(icon="dots-vertical", on_release=self.open_menu)
            self.ids.title_box.add_widget(
                self._menu_button
            )

    def on_right_menu(self, inst, val):
        if len(self.right_menu) and not self._menu_button:
            self.add_menu_items()
        elif not len(self.right_menu) and self._menu_button:
            self.ids.title_box.remove_widget(
                self._menu_button
            )
            self._menu_button = None

    def open_menu(self, *args, **kwargs):

        def menu_callback(instance):
            self.callback(instance.text)
            while instance:
                instance = instance.parent
                if isinstance(instance, MDDropdownMenu):
                    instance.dismiss()
                    break

        MDDropdownMenu(
            items=self.right_menu,
            width_mult=self.width_mult,
            caller=self._menu_button,
            callback=menu_callback).open()

    def callback(self, ico_name):
        self.dispatch('on_button_click', ico_name)

    def on_button_click(self, ico_name):
        pass


class SwipeToDeleteItem(MDCardSwipe):
    path_to_avatar = StringProperty()
    text_post = StringProperty()
    name_data = StringProperty()
    right_menu = ListProperty()
    background_color = ListProperty([1, 1, 1, 0])
    md_bg_color = ListProperty([1, 1, 1, 1])
    width_mult = NumericProperty(3.5)

    def __init__(self, **kwargs):
        self.register_event_type('on_button_click')
        super().__init__(**kwargs)
        self.ids.id_card.bind(on_button_click=self.callback)

    def callback(self, inst, ico_name):
        self.dispatch('on_button_click', ico_name)

    def on_button_click(self, ico_name):
        pass
