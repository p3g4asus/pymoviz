from functools import partial
from . import Action
from util.bluetooth_dispatcher import BluetoothDispatcher
from util import init_logger

_LOGGER = init_logger(__name__)


class MyBluetoothDispatcher(BluetoothDispatcher):
    def __init__(self, on_enable=None, on_disable=None):
        self.on_enable = on_enable
        self.on_disable = on_disable
        super(MyBluetoothDispatcher, self).__init__()

    def on_bluetooth_enabled(self, wasenabled):
        super(MyBluetoothDispatcher, self).on_bluetooth_enabled(wasenabled)
        if self.on_enable:
            self.on_enable(wasenabled)

    def on_bluetooth_disabled(self, wasdisabled):
        super(MyBluetoothDispatcher, self).on_bluetooth_enabled(wasdisabled)
        if self.on_disable:
            self.on_disable(wasdisabled)


class EnableBluetooth(Action):
    def __init__(self):
        self.dispatcher = MyBluetoothDispatcher(on_enable=self.on_bluetooth_enabled,
                                                on_disable=self.on_bluetooth_disabled)
        self.ask_for_enable = True
        self.dialog = None
        self.on_enable = None
        self.on_disable = None

    def _do_execute(self, *args, config=None):
        if args is not None:
            if args[0].find('never') >= 0:
                config.set('preaction', 'ask_enable_bluetooth', '0')
                config.write()
            self.dispatcher.enable()
        else:
            self.dispatcher.on_enable(EnableBluetooth, False, False)

    def undo(self, on_finish):
        self.on_disable = on_finish
        self.dispatcher.disable()

    def on_bluetooth_enabled(self, wasenabled):
        self.on_enable(EnableBluetooth, wasenabled, True)

    def on_bluetooth_disabled(self, wasdisabled):
        self.on_disable(EnableBluetooth, wasdisabled, True)

    def execute(self, config, device_types, on_finish):
        self.on_enable = on_finish
        try:
            self.ask_for_enable = int(config.get('preaction', 'ask_enable_bluetooth'))
        except Exception:
            self.ask_for_enable = 1
        _LOGGER.info(f'ask_for_enable={self.ask_for_enable} be={self.dispatcher.is_bluetooth_enabled()} oe={on_finish}')
        if not self.dispatcher.is_bluetooth_enabled():
            if self.ask_for_enable:
                from kivymd.uix.dialog import MDDialog
                tp = ''
                for i, devt in enumerate(device_types):
                    if len(device_types) > 1 and i == len(device_types) - 1:
                        tp += f'and {devt}'
                    elif i > 0:
                        tp += f', {devt}'
                    else:
                        tp += devt
                self.dialog = MDDialog(
                        text=f"Enabling Bluetooth is required for devices of type {tp}.\nPress back to avoid.",
                        text_button_ok="ENABLE (always ask)",
                        text_button_cancel="ENABLE (never ask again)",
                        events_callback=partial(self._do_execute, config=config)
                )
                self.dialog.open()
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
