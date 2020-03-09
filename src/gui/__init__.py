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
import traceback
from functools import partial
from os.path import dirname, exists, expanduser, join

from db.user import User
from db.view import View
from device.manager import GenericDeviceManager
from gui.typewidget import TypeWidget
from gui.typewidget_cb import TypeWidgetCB
from gui.useredit import UserWidget
from gui.viewedit import ViewPlayWidget, ViewWidget
from kivy.app import App
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.settings import SettingsWithSpinner
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.toast.kivytoast.kivytoast import toast
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineAvatarListItem
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.tab import MDTabs
from util.const import (COMMAND_CONNECT, COMMAND_DELUSER, COMMAND_DELVIEW,
                        COMMAND_DEVICESTATE, COMMAND_DISCONNECT, COMMAND_LISTDEVICES,
                        COMMAND_LISTDEVICES_RV, COMMAND_LISTUSERS,
                        COMMAND_LISTUSERS_RV, COMMAND_LISTVIEWS,
                        COMMAND_LISTVIEWS_RV, COMMAND_NEWDEVICE,
                        COMMAND_SAVEUSER, COMMAND_SAVEVIEW, COMMAND_STOP,
                        CONFIRM_FAILED_3, CONFIRM_OK, MSG_COMMAND_TIMEOUT)
from util.osc_comunication import OSCManager
from util.timer import Timer
from util import asyncio_graceful_shutdown, find_devicemanager_classes

__prog__ = "pyMoviz"
__version__ = (1, 0, 0)

KV = \
    '''
#:import MDToolbar kivymd.uix.toolbar.MDToolbar
#:import IconLeftWidget kivymd.uix.list.IconLeftWidget
<NavigationItem>
    theme_text_color: 'Custom'
    divider: None

    IconLeftWidget:
        icon: root.icon


<ContentNavigationDrawer>

    BoxLayout:
        orientation: 'vertical'

        FloatLayout:
            size_hint_y: None
            height: "200dp"

            canvas:
                Color:
                    rgba: app.theme_cls.primary_color
                Rectangle:
                    pos: self.pos
                    size: self.size

            BoxLayout:
                id: top_box
                size_hint_y: None
                height: "200dp"
                #padding: "10dp"
                x: root.parent.x
                pos_hint: {"top": 1}

                FitImage:
                    source: root.image_path

            MDIconButton:
                icon: "close"
                x: root.parent.x + dp(10)
                pos_hint: {"top": 1}
                on_release: root.parent.toggle_nav_drawer()

            MDLabel:
                markup: True
                text: "[b]" + app.title + "[/b]\\nVersion: " + app.format_version()
                #pos_hint: {'center_y': .5}
                x: root.parent.x + dp(10)
                y: root.height - top_box.height + dp(10)
                size_hint_y: None
                height: self.texture_size[1]

        ScrollView:
            pos_hint: {"top": 1}

            GridLayout:
                id: box_item
                cols: 1
                size_hint_y: None
                height: self.minimum_height


Screen:
    name: 'full'
    NavigationLayout:

        ScreenManager:
            id: id_screen_manager
            Screen:
                name: 'main'
                BoxLayout:
                    orientation: 'vertical'

                    MDToolbar:
                        id: id_toolbar
                        title: app.title
                        md_bg_color: app.theme_cls.primary_color
                        left_action_items: [["menu", lambda x: nav_drawer.toggle_nav_drawer()]]
                        right_action_items: [["lan-connect", id_tabcont.connect_view], ["lan-disconnect", id_tabcont.disconnect_view], ["dots-vertical", app.open_menu]]

                    MyTabs:
                        manager: root.ids.id_screen_manager
                        id: id_tabcont


        MDNavigationDrawer:
            id: nav_drawer

            ContentNavigationDrawer:
                id: content_drawer
    '''


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


class ContentNavigationDrawer(BoxLayout):
    image_path = StringProperty()
    pass


class NavigationItem(OneLineAvatarListItem):
    icon = StringProperty()


class MyTabs(MDTabs):

    def __init__(self, *args, **kwargs):
        super(MyTabs, self).__init__(*args, **kwargs)
        self.tab_list = []
        self.current_tab = None

    def remove_widget(self, w, *args, **kwargs):
        super(MyTabs, self).remove_widget(w)
        if isinstance(w, View):
            w = self.already_present(w)
        if isinstance(w, ViewPlayWidget):
            idx = -3
            try:
                idx = self.tab_list.index(w)
                self.tab_list.remove(w)
            except ValueError:
                Logger.error(traceback.format_exc())
            if len(self.tab_list) == 0:
                self.current_tab = None
                idx = -2
            elif idx > 0:
                idx = idx - 1
            elif idx == 0:
                idx = 0
            if idx >= 0:
                self.carousel.index = idx
                tab = self.tab_list[idx]
                tab.tab_label.state = "down"
                tab.tab_label.on_release()

    def clear_widgets(self):
        for w in self.tab_list:
            self.remove_widget(w)

    def already_present(self, view):
        for v in self.tab_list:
            if v.view == view:
                return v
        return None

    def add_widget(self, tab, *args, **kwargs):
        super(MyTabs, self).add_widget(tab, *args, **kwargs)
        if isinstance(tab, View):
            view = tab
            tab = ViewPlayWidget(view=view)
        elif isinstance(tab, ViewPlayWidget):
            view = tab.view
        oldtab = self.already_present(view)
        if oldtab:
            oldtab.view = view
        else:
            self.tab_list.append(tab)
            Logger.debug(f"Gui: Adding tab len = {len(self.tab_list)}")
            self.carousel.index = len(self.tab_list) - 1
            tab.tab_label.state = "down"
            tab.tab_label.on_release()

    def on_tab_switch(self, inst, text):
        super(MyTabs, self).on_tab_switch(inst, text)
        Logger.debug("On tab switch to %s" % str(text))
        self.current_tab = inst.tab
        Logger.debug("Gui: Currenttab = %s" % str(inst.tab))


class MainApp(MDApp):

    @staticmethod
    def db_dir():
        if platform == "android":
            from jnius import autoclass
            Environment = autoclass('android.os.Environment')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            ctx = PythonActivity.mActivity
            strg = ctx.getExternalFilesDirs(None)
            dest = strg[0]
            for f in strg:
                if Environment.isExternalStorageRemovable(f):
                    dest = f
                    break
            pth = dest.getAbsolutePath()
        else:
            home = expanduser("~")
            pth = join(home, '.kivymoviz')
        if not exists(pth):
            os.mkdir(pth)
        return pth

    def format_version(self):
        return "%d.%d.%d" % __version__

    def disconnect_view(self, *args, **kwargs):
        self.oscer.send(COMMAND_DISCONNECT)

    def connect_view(self, *args, **kwargs):
        if not self.is_pre_init_ok():
            toast('Cannot perform connection: pre init failed')
        elif not self.current_user:
            snack_open('Please select a user first', 'Select', self.generic_edit_user)
        else:
            self.oscer.send(COMMAND_CONNECT, self.current_user)

    def generic_edit(self, *args, **kwargs):
        self.current_widget = TypeWidget(
            types=dict(
                device=self.device_edit,
                view=partial(self.generic_edit_item,
                             dct={v.name: dict(obj=v, active=v.active) for v in self.views},
                             nameitem='view',
                             oscercmd=COMMAND_SAVEVIEW),
                user=self.generic_edit_user
            ),
            title='Edit what?',
            on_type=self.generic_op_type
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def generic_edit_user(self, *args):
        self.generic_edit_item(
                     dct={v.name: dict(obj=v, active=v == self.current_user) for v in self.users},
                     group='users',
                     nameitem='user',
                     oscercmd=COMMAND_SAVEUSER)

    def on_device_edit(self, inst, name, device):
        if device:
            self.current_widget = device.get_settings_screen()
            self.root.ids.id_screen_manager.add_widget(self.current_widget)
            self.root.ids.id_screen_manager.current = self.current_widget.name

    def device_edit(self):
        self.current_widget = TypeWidget(
            types={v.get_device().get_alias(): v for _, v in self.devicemanagers_by_uid.items()},
            title='Select device',
            on_type=self.on_device_edit
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def generic_edit_item(self, *arg, dct=dict(), nameitem='', group=None):
        self.current_widget = TypeWidgetCB(
            types=dct,
            title=f'Select {nameitem}',
            on_type=self.on_generic_edit_item
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def on_generic_edit_item(self, inst, actions):
        if actions:
            items = []
            for name, obj in actions.items():
                item = obj['obj']
                active = obj['active']
                if isinstance(item, View):
                    item.active = active
                elif active:
                    self.config.set('dbpars', 'user', f'{item.get_id()}')
                    self.config.write()
                    self.current_user = item
                items.append(item)
            if isinstance(items[0], User):
                self.on_confirm_add_item(None,
                                         oscercmd=COMMAND_SAVEUSER,
                                         lst=self.users)
            else:
                self.on_confirm_add_item(None,
                                         oscercmd=COMMAND_SAVEVIEW,
                                         lst=self.views,
                                         on_ok=self.on_view_added)

    def on_view_added(self, view):
        self.root.id_tabcont.add_widget(view)

    def on_view_removed(self, view):
        self.root.id_tabcont.remove_widget(view)

    def generic_delete(self, *args, **kwargs):
        self.current_widget = TypeWidget(
            types=dict(
                device=partial(self.generic_del_item,
                               dct={v.get_device().get_alias(): v for _, v in self.devicemanagers_by_uid.items()},
                               nameitem='device',
                               oscercmd=''),
                view=partial(self.generic_del_item,
                             dct={v.name: v for v in self.views},
                             nameitem='view',
                             oscercmd=COMMAND_DELVIEW),
                user=partial(self.generic_del_item,
                             dct={v.name: v for v in self.users},
                             nameitem='user',
                             oscercmd=COMMAND_DELUSER)
            ),
            title='Del what?',
            on_type=self.generic_op_type
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def on_generic_del_item(self, inst, name, item, nameitem=None, oscercmd=''):
        if item:
            dialog = MDDialog(
                title=f"Confirm delete {nameitem}",
                size_hint=(0.8, 0.3),
                text_button_ok="Yes",
                text=f"Delete {nameitem} {name}?",
                text_button_cancel="Cancel",
                events_callback=partial(
                    self.on_confirm_del_item,
                    item=item,
                    oscercmd=oscercmd,
                    name=name)
            )
            dialog.open()

    def on_confirm_del_item_server(self, *args, name='', timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        elif args[0] == CONFIRM_OK:
            if isinstance(args[1], GenericDeviceManager):
                del self.devicemanagers_by_uid[args[1].get_uid()]
            elif isinstance(args[1], View):
                self.views.remove(args[1])
                self.on_view_removed(args[1])
            elif isinstance(args[1], User):
                self.users.remove(args[1])
            toast(f'{name} deleted from {args[1].__table__}.')
            return
        else:
            msg = args[1]
            exitv = args[0]
        toast(f"[E {exitv}] {msg}")

    def on_confirm_del_item(self, *args, item=None, name='', oscercmd=''):
        if args[0] == 'Yes':
            if isinstance(item, GenericDeviceManager):
                item.del_device(on_del_device=self.on_confirm_del_item_server)
            else:
                self.oscer.send(oscercmd,
                                item,
                                confirm_callback=partial(
                                    self.on_confirm_del_item_server,
                                    name=name),
                                timeout=5)

    def generic_del_item(self, *arg, dct=dict(), nameitem='', oscercmd=''):
        self.current_widget = TypeWidget(
            types=dct,
            title=f'Select {nameitem}',
            on_type=partial(self.on_generic_del_item, nameitem=nameitem, oscercmd=oscercmd)
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def generic_add(self, *args, **kwargs):
        self.current_widget = TypeWidget(
            types=dict(
                device=self.generic_add_device,
                view=self.generic_add_view,
                user=self.generic_add_user
            ),
            title='Add what?',
            on_type=self.generic_op_type
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def generic_op_type(self, inst, txt, method):
        if method:
            method()

    def generic_add_device(self):
        self.current_widget = TypeWidget(
            types=self.devicemanager_class_by_type,
            title='Select device type',
            on_type=self.generic_add_device_type
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def generic_add_device_type(self, inst, txt, typeclass):
        if typeclass:
            self.oscer.send(COMMAND_NEWDEVICE,
                            txt,
                            confirm_callback=self.on_generic_add_device_type,
                            confirm_params=(typeclass,),
                            timeout=5)

    def on_generic_add_device_type(self, typeclass, *args, timeout=False):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
        elif args[0] == CONFIRM_OK:
            uid = args[1]
            self.devicemanagers_by_uid[uid] = typeclass(self.oscer, uid)
            self.current_widget = self.devicemanagers_by_uid[uid].get_settings_screen()
            self.root.ids.id_screen_manager.add_widget(self.current_widget)
            self.root.ids.id_screen_manager.current = self.current_widget.name
            return
        else:
            msg = args[1]
            exitv = args[0]
        toast(f"[E {exitv}] {msg}")

    def generic_add_user(self):
        self.current_widget = UserWidget(
            on_confirm=partial(self.on_confirm_add_item,
                               oscercmd=COMMAND_SAVEUSER,
                               lst=self.users)
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def generic_add_view(self):
        self.current_widget = ViewWidget(
            on_confirm=partial(self.on_confirm_add_item,
                               oscercmd=COMMAND_SAVEVIEW,
                               lst=self.views,
                               on_ok=self.on_view_added),
            formatters=self.formatters
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def on_confirm_add_item(self, inst, items, index=0, oscercmd='', lst=[], on_ok=None):
        if items:
            if isinstance(items, list):
                view = items[index] if index < len(items) else None
                index = index+1
            else:
                view = items
                items = None
            if view:
                self.oscer.send(oscercmd,
                                view,
                                confirm_callback=partial(self.on_confirm_add_item_server,
                                                         items=items,
                                                         oscercmnd=oscercmd,
                                                         lst=lst,
                                                         on_ok=on_ok,
                                                         index=index),
                                timeout=5)

    def on_confirm_add_item_server(self, *args, timeout=False, items=None, index=0, lst=[], oscercmd='', on_ok=None):
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
            msg = f"[E {exitv}] {msg}"
        elif args[0] != CONFIRM_OK:
            view = args[1]
            if view in lst:
                lst[lst.index(view)] = view
            else:
                lst.append(view)
            msg = f"Save {view.__table__} {view.name} OK"
            if on_ok:
                on_ok(view)
        else:
            msg = args[1]
            exitv = args[0]
            msg = f"[E {exitv}] {msg}"
        toast(msg)
        if items:
            self.on_confirm_add_item(None, items, index=index, lst=lst, oscercmd=oscercmd, on_ok=on_ok)

    def open_menu(self, *args, **kwargs):
        items = [
            dict(
                viewclass="MDMenuItem",
                text="Add...",
                icon="plus",
                callback=self.generic_add
            ),
            dict(
                viewclass="MDMenuItem",
                text="Edit...",
                icon="square-edit-outline",
                callback=self.generic_edit
            ),
            dict(
                viewclass="MDMenuItem",
                text="Delete...",
                icon="delete",
                callback=self.generic_delete
            )
        ]
        MDDropdownMenu(items=items, width_mult=3).open(
            self.root.ids.id_toolbar.ids["right_actions"].children[0])

# https://stackoverflow.com/questions/42159927/http-basic-auth-on-twisted-klein-server
# https://github.com/racker/python-twisted-core/blob/master/doc/examples/dbcred.py

    def __init__(self, *args, **kwargs):
        super(MainApp, self).__init__(*args, **kwargs)
        self.loop = asyncio.get_event_loop()

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
            hostlisten=self.config.get('frontend', 'host'),
            portlisten=self.config.get('frontend', 'port'),
            hostcommand=self.config.get('backend', 'host'),
            portcommand=self.config.get('backend', 'port'))
        await self.oscer.init(pingsend=False, on_init_ok=self.on_osc_init_ok, on_ping_timeout=self.on_ping_timeout)

    def on_osc_init_ok(self):
        self.oscer.handle(COMMAND_LISTDEVICES_RV, self.on_list_devices_rv)
        self.oscer.handle(COMMAND_DEVICESTATE, self.on_devicestate)
        self.oscer.handle(COMMAND_LISTVIEWS_RV, self.on_list_views_rv)
        self.oscer.handle(COMMAND_LISTUSERS_RV, self.on_list_users_rv)
        self.send(COMMAND_LISTDEVICES)
        self.send(COMMAND_LISTUSERS)
        self.send(COMMAND_LISTVIEWS)

    def on_list_devices_rv(self, *ld):
        for x in range(0, len(ld), 2):
            dev = ld[x + 1]
            uid = ld[x]
            if dev.type in self.devicemanager_class_by_type:
                self.devicemanagers_by_uid[uid] = self.devicemanager_class_by_type[dev.type](
                    self.oscer, uid, service=False, device=dev, loop=self.loop)
                self.formatters.extend(self.devicemanagers_by_uid[uid].get_formatters())

    def on_list_users_rv(self, *ld):
        self.users = list(ld)
        useri = self.config.get('dbpars', 'user')
        for u in self.users:
            if useri < 0 or useri == u.rowid:
                self.current_user = u
                return
        self.current_user = None

    def on_list_views_rv(self, *ld):
        self.views = list(ld)

    def is_pre_init_ok(self):
        for v in self.views:
            for d in v.get_connected_devices():
                if not self.devicemanagers_pre_init[d.get_type()]:
                    return False
        return True

    def do_pre_finish(self, cls, ok):
        toast(f'Pre operations for devices of type {cls.__type__}...{"OK" if ok else "FAIL"}')
        self.devicemanagers_pre_init[cls.__type__] = ok
        self.do_pre()

    def do_pre(self):
        for d, init in self.devicemanagers_pre_init.items():
            if init is None:
                cls = self.devicemanager_class_by_type[d]
                toast(f"Pre operations for devices of type {cls.__type__}...")
                cls.do_activity_pre_operations(on_finish=self.do_pre_finish, loop=self.loop)
                return
        if not self.devicemanagers_pre_init_done:
            self.devicemanagers_pre_init_done = True
            self.start_server()

    def on_ping_timeout(self, is_timeout):
        if is_timeout:
            self.do_pre()
            toast('Timeout comunicating with the service')
        else:
            if not self.devicemanagers_pre_init_done:
                for d in self.devicemanagers_pre_init.keys():
                    if self.devicemanagers_pre_init[d] is None:
                        self.devicemanagers_pre_init[d] = True
                self.devicemanagers_pre_init_done = True
            toast('Serivice connection OK')

    def on_start(self):
        if self.check_host_port_config('frontend') and self.check_host_port_config('backend') and\
           self.check_other_config():
            Timer(0, self.init_osc)
        self.root.ids.content_drawer.image_path = join(
            dirname(__file__), '..', "images", "navdrawer.png")
        for items in {
            "home-outline": ("Home", self.on_nav_home),
            "settings-outline": ("Settings", self.on_nav_settings),
            "exit-to-app": ("Exit", self.on_nav_exit),
        }.items():
            self.root.ids.content_drawer.ids.box_item.add_widget(
                NavigationItem(
                    text=items[1][0],
                    icon=items[0],
                    on_release=items[1][1]
                )
            )

    def on_nav_home(self, *args, **kwargs):
        Logger.debug("On Nav Home")

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
        config.setdefaults('dbpars', {'user', -1})
        config.setdefaults('frontend',
                           {'host': '127.0.0.1', 'port': 9001})
        config.setdefaults('backend',
                           {'host': '127.0.0.1', 'port': 9002})
        config.setdefaults('bluetooth',
                           {'connect_secs': 5, 'connect_retry': 10})
        self._init_fields()

    def _init_fields(self):
        self.title = __prog__
        self.oscer = None
        self.current_user = None
        self.users = []
        self.formatters = []
        self.current_widget = None
        self.devicemanager_class_by_type = find_devicemanager_classes(Logger)
        self.devicemanagers_by_uid = dict()
        self.views = []
        self.devicemanagers_pre_init_done = False
        self.devicemanagers_pre_init = dict.fromkeys(self.devicemanager_class_by_type.keys(), None)

    def build_settings(self, settings):
        """
        Add our custom section to the default configuration object.
        """
        dn = join(dirname(__file__), '..', 'config')
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
            to = int(self.config.get("bluetooth", "connect_secs"))
        except Exception:
            to = -1
        if to <= 0:
            snack_open('Please insert a number of seconds value (int>=0)', "Settings", self.on_nav_settings)
            return False
        try:
            to = int(self.config.get("bluetooth", "connect_retry"))
        except Exception:
            to = -1
        if to <= 1:
            snack_open('Please insert a valid retry value (int>=1)', "Settings", self.on_nav_settings)
            return False
        return True

    def start_server(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                package_name = 'org.kivymfz.pymoviz'
                service_name = 'DeviceManagerService'
                service_class = '{}.Service{}'.format(
                    package_name, service_name.title())
                service = autoclass(service_class)
                mActivity = autoclass('org.kivy.android.PythonActivity').mActivity

                arg = dict(db_fname=join(MainApp.db_dir(), 'maindb.db'),
                           hostlisten=self.config.get('backend', 'host'),
                           portlisten=self.config.getint('backend', 'port'),
                           hostcommand=self.config.get('frontend', 'host'),
                           portcommand=self.config.getint('frontend', 'port'),
                           connect_secs=self.config.getint('bluetooth', 'connect_secs'),
                           connect_retry=self.config.getint('bluetooth', 'connect_retry'),
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
