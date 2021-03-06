from . import Action
from kivy.utils import get_color_from_hex
from util.bluetooth_dispatcher import BluetoothDispatcher
from util import init_logger

_LOGGER = init_logger(__name__)


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
        super(EnableBluetooth, self).__init__(loop)
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
        from kivymd.uix.button import MDRaisedButton
        from kivymd.uix.list import OneLineListItem
        from kivymd.uix.dialog import MDDialog
        tp = ''
        for i, devt in enumerate(device_types):
            if len(device_types) > 1 and i == len(device_types) - 1:
                tp += f' and {devt}'
            elif i > 0:
                tp += f', {devt}'
            else:
                tp += devt
        self.dialog = MDDialog(
            type="simple",
            title=f"Enabling Bluetooth is required for devices of type {tp}",
            items=[
                OneLineListItem(
                    text="ENABLE (always ask)",
                    _txt_left_pad=0,
                    _txt_right_pad=0,
                    _txt_top_pad=0,
                    _txt_bot_pad=0,
                    bg_color=get_color_from_hex('#ecff33'),
                    on_release=lambda x: self._do_execute(True, config)),
                OneLineListItem(
                    text="ENABLE (never ask again)",
                    _txt_left_pad=0,
                    _txt_right_pad=0,
                    _txt_top_pad=0,
                    _txt_bot_pad=0,
                    bg_color=get_color_from_hex('#58ff33'),
                    on_release=lambda x: self._do_execute(False, config))
            ],
            buttons=[
                MDRaisedButton(
                    text="CANCEL", on_release=lambda x: self._do_execute(None, config)
                )
            ]
        )
        self.dialog.ids.title.font_style = "Body1"
        self.dialog.ids.box_items.padding = (0, 0)
        # self.dialog.ids.button_box.orientation = 'vertical'
        # self.dialog.ids.root_button_box.anchor_x = 'center'
        # self.dialog.ids.root_button_box.anchor_y = 'bottom'
        # self.dialog.ids.root_button_box.height = dp(160)
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
