from . import Action
from util.bluetooth_dispatcher import BluetoothDispatcher
from util import init_logger

_LOGGER = init_logger(__name__)


_GUI = '''
#:import images_path kivymd.images_path

<EnableBluetoothContentDialog>
    orientation: 'vertical'
    padding: dp(15)
    spacing: dp(10)

    MDLabel:
        id: title
        text: root.title
        font_style: 'H6'
        halign: 'left'
        valign: 'top'
        size_hint_y: None
        text_size: self.width, None
        height: self.texture_size[1]

    ScrollView:
        id: scroll
        size_hint_y: None
        height:
            root.height - (box_buttons.height + title.height + dp(48)\
            + sep.height)

        canvas:
            Rectangle:
                pos: self.pos
                size: self.size
                #source: f'{images_path}dialog_in_fade.png'
                source: f'{images_path}transparent.png'

        MDLabel:
            text: '\\n' + root.text + '\\n'
            size_hint_y: None
            height: self.texture_size[1]
            valign: 'top'
            halign: 'left'
            markup: True

    MDSeparator:
        id: sep

    BoxLayout:
        orientation: 'vertical'
        id: box_buttons
        size_hint_y: None
        height: dp(120)
        spacing: dp(10)
        MDFlatButton:
            id: id_cancelbtn
            text: 'CANCEL'
        MDRaisedButton:
            id: id_askbtn
            text: 'ENABLE (always ask)'
        MDRaisedButton:
            id: id_noaskbtn
            text: 'ENABLE (never ask again)'
'''


class MyBluetoothDispatcher(BluetoothDispatcher):
    def __init__(self, loop, on_enable=None, on_disable=None):
        self.on_enable = on_enable
        self.on_disable = on_disable
        self.loop = loop
        super(MyBluetoothDispatcher, self).__init__()

    def on_bluetooth_enabled(self, wasenabled):
        super(MyBluetoothDispatcher, self).on_bluetooth_enabled(wasenabled)
        if self.on_enable:
            self.loop.call_soon_threadsafe(self.on_enable, wasenabled)

    def on_bluetooth_disabled(self, wasdisabled):
        super(MyBluetoothDispatcher, self).on_bluetooth_disabled(wasdisabled)
        if self.on_disable:
            self.loop.call_soon_threadsafe(self.on_disable, wasdisabled)


class EnableBluetooth(Action):
    def __init__(self, loop):
        super(EnableBluetooth).__init__(loop)
        self.dispatcher = MyBluetoothDispatcher(loop,
                                                on_enable=self.on_bluetooth_enabled,
                                                on_disable=self.on_bluetooth_disabled)
        self.ask_for_enable = True
        self.dialog = None
        self.on_enable = None
        self.on_disable = None

    def _do_execute(self, alwaysask, config):
        self.dialog.dismiss()
        if alwaysask is not None:
            if not alwaysask:
                config.set('preaction', 'ask_enable_bluetooth', '0')
                config.write()
            self.dispatcher.enable()
        else:
            self.on_enable(EnableBluetooth, False, False)

    def undo(self, on_finish):
        self.on_disable = on_finish
        self.dispatcher.disable()

    def on_bluetooth_enabled(self, wasenabled):
        self.on_enable(EnableBluetooth, wasenabled, True)

    def on_bluetooth_disabled(self, wasdisabled):
        self.on_disable(EnableBluetooth, wasdisabled, True)

    def build_dialog(self, config, device_types):
        from kivy.uix.modalview import ModalView
        from kivymd.theming import ThemableBehavior
        from kivy.properties import StringProperty
        from kivy.lang import Builder
        from kivymd.uix.card import MDCard

        Builder.load_string(_GUI)

        class EnableBluetoothContentDialog(MDCard):
            text = StringProperty()
            title = StringProperty()

            def __init__(self, action, config=None, device_types=None, **kwargs):
                super(EnableBluetoothContentDialog, self).__init__(**kwargs)
                tp = ''
                for i, devt in enumerate(device_types):
                    if len(device_types) > 1 and i == len(device_types) - 1:
                        tp += f'and {devt}'
                    elif i > 0:
                        tp += f', {devt}'
                    else:
                        tp += devt
                self.text = f"Enabling Bluetooth is required for devices of type {tp}"
                self.title = 'Enable Bluetooth?'
                self.ids.id_cancelbtn.bind(on_release=lambda x: action._do_execute(None, config))
                self.ids.id_askbtn.bind(on_release=lambda x: action._do_execute(True, config))
                self.ids.id_noaskbtn.bind(on_release=lambda x: action._do_execute(False, config))

        class EnableBluetoothDialog(ThemableBehavior, ModalView):
            def __init__(self, action, config=None, device_types=None, **kwargs):
                super().__init__(**kwargs)
                self.add_widget(EnableBluetoothContentDialog(action, config=config, device_types=device_types))

        self.dialog = EnableBluetoothDialog(self, config=config, device_types=device_types)
        self.dialog.open()

    def execute(self, config, device_types, on_finish):
        self.on_enable = on_finish
        try:
            self.ask_for_enable = int(config.get('preaction', 'ask_enable_bluetooth'))
        except Exception:
            self.ask_for_enable = 1
        _LOGGER.info(f'ask_for_enable={self.ask_for_enable} be={self.dispatcher.is_bluetooth_enabled()} oe={on_finish}')
        if not self.dispatcher.is_bluetooth_enabled():
            if self.ask_for_enable:
                self.build_dialog(config, device_types)
            else:
                self.dispatcher.enable()
        else:
            self.on_bluetooth_enabled(False)

    @classmethod
    def build_config(cls, config):
        config.setdefaults('preaction', {'ask_enable_bluetooth': '1'})

    @classmethod
    def build_settings(cls):
        return {
                "type": "bool",
                "title": "Ask for Bluetooth enable",
                "desc": "Ask each time for enabling Bluetooth if disabled",
                "section": "preaction",
                "key": "ask_enable_bluetooth"
            }
