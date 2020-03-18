import re
from datetime import datetime

from db.user import User
from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivy.uix.screenmanager import Screen
from util import init_logger


_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
#:import ButtonDatePicker gui.buttondatepicker.ButtonDatePicker
<FormatterItem>:
    height: dp(56)
    font_style: "H6"
    secondary_font_style: "H5"

<UserWidget>:
    name: 'user_edit'
    GridLayout:
        height: self.minimum_height
        rows: 3
        cols: 1
        MDToolbar:
            id: id_toolbar
            pos_hint: {'top': 1}
            size_hint: (1, 0.2)
            title: 'New User'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_confirm(False)]]
            elevation: 10
        BoxLayout:
            padding: [dp(30), dp(20)]
            spacing: dp(30)
            size_hint: (1, 0.1)
            MDTextField:
                pos_hint: {'top': 0.8}
                id: id_name
                icon_type: "without"
                error: True
                hint_text: "Name"
                helper_text_mode: "on_error"
                helper_text: "Enter at least a letter"
                on_text: root.enable_buttons(self, self.text)
        GridLayout:
            padding: [dp(30), dp(20)]
            cols: 2
            rows: 4
            MDLabel:
                text: 'Male'
            MDSwitch:
                id: id_sex
            MDLabel:
                text: 'Weight (Kg)'
            MDSlider:
                id: id_weight
                min: 10
                max: 500
                value: 70
            MDLabel:
                text: 'Height (cm)'
            MDSlider:
                id: id_height
                min: 130
                max: 270
                value: 170
            MDLabel:
                text: 'Birthday'
            ButtonDatePicker:
                size_hint: (0.85, 0.25)
                id: id_birth
                font_size: "12sp"
                dateformat: '%d/%m/%Y'
                on_date_picked: root.set_birthday(self.date)
    '''
)


class UserWidget(Screen):
    obj = ObjectProperty()

    def __init__(self, **kwargs):
        self.register_event_type('on_confirm')
        super(UserWidget, self).__init__(**kwargs)
        self.user = self.obj
        if self.user:
            self.user = self.user.clone()
        else:
            self.user = User(name='John Doe', weight=75, height=175, male=True, birthday=0)
        self.user2gui()

    def set_birthday(self, dt):
        _LOGGER.debug(f'Set birthday {dt}')
        if dt:
            self.user.birthday = datetime.timestamp(dt)
            self.set_enabled(self.user.birthday > 0 and not self.ids.id_name.error)

    def set_enabled(self, valid):
        if valid:
            self.ids.id_toolbar.right_action_items = [
                ["floppy", lambda x: self.dispatch_confirm()],
            ]
        else:
            self.ids.id_toolbar.right_action_items = []

    def user2gui(self):
        self.ids.id_name.text = self.user.name
        self.ids.id_sex.active = self.user.male > 0
        self.ids.id_weight.value = self.user.weight
        self.ids.id_height.value = self.user.height
        if self.user.birthday:
            self.ids.id_birth.set_date(datetime.fromtimestamp(self.user.birthday))

    def gui2user(self):
        self.user.name = self.ids.id_name.text
        self.user.male = self.ids.id_sex.active
        self.user.weight = self.ids.id_weight.value
        self.user.height = self.ids.id_height.value

    def on_confirm(self, user):
        # self.manager.remove_widget(self)
        _LOGGER.debug(f"On confirm called {str(user)}")

    def enable_buttons(self, inst, text, *args, **kwargs):
        dis = not text or not re.search(r"[A-Za-z]", text)
        if inst.error and not dis:
            inst.error = False
            inst.on_text(inst, text)
        elif not inst.error and dis:
            inst.error = True
            inst.on_text(inst, text)
        self.set_enabled(not inst.error and self.user.birthday > 0)

    def dispatch_confirm(self, confirm=True):
        if confirm:
            self.gui2user()
        self.dispatch('on_confirm', self.user if confirm else None)
