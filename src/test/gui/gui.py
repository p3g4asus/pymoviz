"""
Config Example
==============
This file contains a simple example of how the use the Kivy settings classes in
a real app. It allows the user to change the caption and font_size of the label
and stores these changes.
When the user next runs the programs, their changes are restored.
"""

import asyncio
import json
import os
from os.path import dirname, join
import traceback

from util.bluetooth_dispatcher import BluetoothDispatcher
from kivy.app import App
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.settings import SettingsWithSpinner
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.button import MDFlatButton
from kivymd.uix.snackbar import Snackbar
from util.const import COMMAND_STOP
from util.osc_comunication import OSCManager
from util.timer import Timer
from util import asyncio_graceful_shutdown

KV = \
    '''
<SimpleGUI>
    orientation: 'vertical'
    MDFlatButton:
        text: 'Settings'
        on_release: app.on_nav_settings()
    MDFlatButton:
        text: 'Activity'
        on_release: app.permissions()
    MDFlatButton:
        text: 'Exit'
        on_release: app.on_nav_exit()
    '''


class SimpleGUI(BoxLayout):
    pass


def snack_open(msg, btn_text, btn_callback):
    col = App.get_running_app().theme_cls.primary_color
    sn = Snackbar(
        text=msg,
        button_text=btn_text,
        button_callback=btn_callback,
    )
    for x in sn.ids.box.children:
        if isinstance(x, MDFlatButton):
            x.theme_text_color = "Custom"
            x.text_color = col
            break
    sn.show()


class MainApp(MDApp):

    def __init__(self, *args, **kwargs):
        super(MainApp, self).__init__(*args, **kwargs)

    def build(self):
        """
        Build and return the root widget.
        """
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "LightBlue"
        # The line below is optional. You could leave it out or use one of the
        # standard options, such as SettingsWithSidebar, SettingsWithSpinner
        # etc.
        self.settings_cls = SettingsWithSpinner

        # We apply the saved configuration settings or the defaults
        root = Builder.load_string(KV)  # (client=self.client)
        return root

    async def init_osc(self):
        self.oscer = OSCManager(
            hostlisten='127.0.0.1',
            portlisten=self.config.get('local', 'frontendport'),
            hostcommand='127.0.0.1',
            portcommand=self.config.get('local', 'backendport'))
        await self.oscer.init(pingsend=False, on_init_ok=self.on_osc_init_ok, on_ping_timeout=self.on_ping_timeout)

    def on_osc_init_ok(self):
        toast('OSC Init OK')

    def on_ping_timeout(self, is_timeout):
        if is_timeout:
            if not self.server_started:
                self.start_server()
            toast('Timeout comunicating with server')
            self.server_started = True
        else:
            toast('OSC comunication OK')

    def do_pre(self, on_finish):
        class PreBluetoothDispatcher(BluetoothDispatcher):
            def __init__(self, on_finish_handler=None, *args, **kwargs):
                super(BluetoothDispatcher, self).__init__(*args, **kwargs)
                self.on_finish = on_finish_handler

            def on_scan_started(self, success):
                super(PreBluetoothDispatcher, self).on_scan_started(success)
                if success:
                    self.stop_scan()
                else:
                    self.on_finish(False)

            def on_scan_completed(self):
                self.on_finish(True)
        pbd = PreBluetoothDispatcher(on_finish_handler=on_finish)
        pbd.start_scan()

    def on_start(self):
        if self.check_host_port_config('frontend') and self.check_host_port_config('backend') and\
           self.check_other_config():
            self.do_pre(self.on_pre_finish)

    def on_pre_finish(self, *args):
        Timer(0, self.init_osc)

    def on_nav_exit(self, *args, **kwargs):
        self.true_stop()

    def on_nav_settings(self, *args, **kwargs):
        self.open_settings()

    def true_stop(self):
        self.stop_server()
        self.stop()

    def build_config(self, config):
        """
        Set the default values for the configs sections.
        """
        config.setdefaults('frontend',
                           {'host': '127.0.0.1', 'port': 33218})
        config.setdefaults('local',
                           {'frontendport': 9002, 'backendport': 9001})
        config.setdefaults('backend',
                           {'host': '127.0.0.1', 'port': 33217})
        self._init_fields()

    def _init_fields(self):
        self.oscer = None
        self.server_started = False

    def build_settings(self, settings):
        """
        Add our custom section to the default configuration object.
        """
        dn = join(dirname(__file__), '..', '..', 'config')
        # We use the string defined above for our JSON, but it could also be
        # loaded from a file as follows:
        #     settings.add_json_panel('My Label', self.config, 'settings.json')
        settings.add_json_panel('Backend', self.config, join(dn, 'backend.json'))  # data=json)
        settings.add_json_panel('Frontend', self.config, join(dn, 'frontend.json'))  # data=json)
        settings.add_json_panel('Bluetooth', self.config, join(dn, 'bluetooth.json'))  # data=json)

    def check_host_port_config(self, name):
        host = self.config.get(name, "host")
        if not host:
            snack_open(f"{name.title()} Host cannot be empty", "Settings", self.on_nav_settings)
            return False
        port = self.config.getint(name, "port")
        if not port or port > 65535 or port <= 0:
            snack_open(f"{name.title()} Port should be in the range [1, 65535]", "Settings", self.on_nav_settings)
            return False
        return True

    def check_other_config(self):
        try:
            port = int(self.config.get("local", "frontendport"))
        except Exception:
            port = -1
        if not port or port > 65535 or port <= 0:
            snack_open(f"Local Frontend Port should be in the range [1, 65535]", "Settings", self.on_nav_settings)
            return False
        try:
            port = int(self.config.get("local", "backendport"))
        except Exception:
            port = -1
        if not port or port > 65535 or port <= 0:
            snack_open(f"Local Backend Port should be in the range [1, 65535]", "Settings", self.on_nav_settings)
            return False
        return True

    def start_server(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                package_name = 'org.kivymfz.pymoviz.test'
                service_name = 'BluetoothService'
                service_class = '{}.Service{}'.format(
                    package_name, service_name.title())
                service = autoclass(service_class)
                mActivity = autoclass('org.kivy.android.PythonActivity').mActivity

                arg = dict(hostlisten=self.config.get('backend', 'host'),
                           portlisten=self.config.getint('backend', 'port'),
                           portlistenlocal=self.config.getint('local', 'backendport'),
                           hostcommand=self.config.get('frontend', 'host'),
                           portcommand=self.config.getint('frontend', 'port'),
                           portcommandlocal=self.config.getint('local', 'frontendport'),
                           verbose=True)
                argument = json.dumps(arg)
                Logger.info("Starting %s [%s]" % (service_class, argument))
                service.start(mActivity, argument)
            except Exception:
                Logger.error(traceback.format_exc())

    async def stop_server(self):
        if self.oscer:
            self.oscer.send(COMMAND_STOP)
            self.oscer.uninit()

    def on_config_change(self, config, section, key, value):
        """
        Respond to changes in the configuration.
        """
        Logger.info("main.py: App.on_config_change: {0}, {1}, {2}, {3}".format(
            config, section, key, value))
        if self.check_host_port_config('frontend') and self.check_host_port_config('backend') and\
           self.check_other_config():
            if self.oscer:
                snack_open("Configuration changes will be effective on restart", "Quit", self.on_nav_exit)
            else:
                Timer(0, self.init_osc)

    def close_settings(self, settings=None):
        """
        The settings panel has been closed.
        """
        Logger.info("main.py: App.close_settings: {0}".format(settings))
        super(MainApp, self).close_settings(settings)


def main():
    os.environ['KIVY_EVENTLOOP'] = 'async'
    if platform == "win":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    app = MainApp()
    loop.run_until_complete(app.async_run())
    loop.run_until_complete(asyncio_graceful_shutdown(loop, Logger, False))
    Logger.debug("Gui: Closing loop")
    loop.close()


if __name__ == '__main__':
    main()
