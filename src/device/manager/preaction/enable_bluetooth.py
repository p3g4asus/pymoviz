from functools import partial
from . import Action
from util import BluetoothDispatcher


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

    def _do_execute(self, alwaysask=None, config=None):
        self.dialog.close()
        if alwaysask is not None:
            if alwaysask is False:
                config.set('bluetooth', 'ask_enable_bluetooth', False)
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
        self.ask_for_enable = config.get('bluetooth', 'ask_enable_bluetooth')
        if self.ask_for_enable and not self.dispatcher.is_bluetooth_enabled():
            from kivymd.uix.button import MDFlatButton
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
                    text=f"Enaling Bluetooth is required for devices of type {tp}",
                    buttons=[
                        MDFlatButton(
                            text="CANCEL",
                            text_color=self.theme_cls.primary_color,
                            on_release=partial(self._do_execute, alwaysask=None)
                        ),
                        MDFlatButton(
                            text="ENABLE (always ask)",
                            text_color=self.theme_cls.primary_color,
                            on_release=partial(self._do_execute, alwaysask=True)
                        ),
                        MDFlatButton(
                            text="ENABLE (don't ask again)",
                            text_color=self.theme_cls.primary_color,
                            on_release=partial(self._do_execute, alwaysask=False, config=config)
                        ),
                    ],
                )
            self.dialog.open()
        else:
            self.dispatcher.enable()

    @classmethod
    def build_config(cls, config):
        config.setdefaults('preaction', {'ask_enable_bluetooth': True})

    @classmethod
    def build_settings(cls):
        return {
                "type": "bool",
                "title": "Ask for Bluetooth enable",
                "desc": "Ask each time for enabling Bluetooth if disabled",
                "section": "preaction",
                "key": "ask_enable_bluetooth"
            }
