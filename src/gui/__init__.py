"""
Config Example
==============
This file contains a simple example of how the use the Kivy settings classes in
a real app. It allows the user to change the caption and font_size of the label
and stores these changes.
When the user next runs the programs, their changes are restored.
"""

import asyncio
import fnmatch
import json
import os
import time
import traceback
from functools import partial
import logging
from os.path import basename, dirname, exists, expanduser, isfile, join

from db.user import User
from db.view import View
from device.manager import GenericDeviceManager
from gui.settingbuttons import SettingButtons
from gui.typewidget import TypeWidget
from gui.typewidget_cb import TypeWidgetCB
from gui.useredit import UserWidget
from gui.velocity_tab import VelocityTab
from gui.viewedit import ViewPlayWidget, ViewWidget
from kivy.app import App
from kivy.core.window import Window
from kivy.lang import Builder
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
from util.android_alive_checker import AndroidAliveChecker
from util.const import (COMMAND_CONNECT, COMMAND_CONNECTORS, COMMAND_DELUSER,
                        COMMAND_DELVIEW, COMMAND_DEVICEFIT, COMMAND_DISCONNECT,
                        COMMAND_LISTDEVICES, COMMAND_LISTDEVICES_RV, COMMAND_LISTUSERS,
                        COMMAND_LISTUSERS_RV, COMMAND_LISTVIEWS, COMMAND_LISTVIEWS_RV,
                        COMMAND_LOGLEVEL, COMMAND_NEWDEVICE, COMMAND_NEWSESSION,
                        COMMAND_PRINTMSG,
                        COMMAND_SAVEUSER, COMMAND_SAVEVIEW, COMMAND_STOP,
                        CONFIRM_FAILED_3, CONFIRM_OK, MSG_COMMAND_TIMEOUT)
from util.osc_comunication import OSCManager
from util.timer import Timer
from util.velocity_tcp import TcpClient
from util import asyncio_graceful_shutdown, find_devicemanager_classes,\
    get_natural_color, get_verbosity, init_logger


_LOGGER = init_logger(__name__, level=logging.DEBUG)
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
                        right_action_items: [["lan-connect", app.connect_active_views], ["lan-disconnect", app.disconnect_active_views], ["dots-vertical", app.open_menu]]

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

    def format(self, devobj, **kwargs):
        for tb in self.tab_list:
            if isinstance(tb, ViewPlayWidget):
                tb.format(devobj, **kwargs)

    def new_view_list(self, views):
        set_tab = True
        removel = list()
        for t in self.tab_list:
            if isinstance(t, ViewPlayWidget):
                set_tab = False
                if t.view not in views:
                    removel.append(t)
                else:
                    v2 = views.index(t.view)
                    if not views[v2].active:
                        removel.append(t)
        for t in removel:
            self.remove_widget(t)
        if self.tab_list or views:
            for t in views:
                if isinstance(t, View) and t.active:
                    self.add_widget(t)
            if set_tab:
                self.simulate_tab_switch(0)

    def remove_widget(self, w, *args, **kwargs):
        if isinstance(w, View):
            w = self.already_present(w)
        if w and isinstance(w, (ViewPlayWidget, VelocityTab)):
            super(MyTabs, self).remove_widget(w)
            idx = -3
            try:
                idx = self.tab_list.index(w)
                self.tab_list.remove(w)
            except ValueError:
                _LOGGER.error(traceback.format_exc())
            if len(self.tab_list) == 0:
                self.current_tab = None
                idx = -2
            elif idx > 0:
                idx = idx - 1
            elif idx == 0:
                idx = 0
            if idx >= 0:
                self.simulate_tab_switch(idx)

    def simulate_tab_switch(self, idx):
        if idx < len(self.tab_list):
            self.carousel.index = idx
            tab = self.tab_list[idx]
            tab.tab_label.state = "down"
            tab.tab_label.on_release()

    def clear_widgets(self):
        for w in self.tab_list:
            self.remove_widget(w)

    def already_present(self, view):
        if view:
            for v in self.tab_list:
                if isinstance(v, ViewPlayWidget) and v.view == view:
                    return v
        return None

    def add_widget(self, tab, *args, **kwargs):
        if isinstance(tab, View):
            view = tab
            tab = ViewPlayWidget(view=view)
        elif isinstance(tab, ViewPlayWidget):
            view = tab.view
        elif isinstance(tab, VelocityTab):
            view = None
        else:
            super(MyTabs, self).add_widget(tab, *args, **kwargs)
            return
        oldtab = self.already_present(view)
        if oldtab:
            _LOGGER.info(f'Already present: {oldtab.view} -> {oldtab.view is view}')
            if not view.active:
                self.remove_widget(oldtab)
            else:
                oldtab.set_view(view)
        elif view and not view.active:
            return
        else:
            _LOGGER.info(f'TAB not present: {view}')
            super(MyTabs, self).add_widget(tab, *args, **kwargs)
            self.tab_list.append(tab)
            _LOGGER.info(f"Gui: Adding tab len = {len(self.tab_list)}")
            self.carousel.index = len(self.tab_list) - 1
            tab.tab_label.state = "down"
            tab.tab_label.on_release()

    def on_tab_switch(self, inst, text):
        super(MyTabs, self).on_tab_switch(inst, text)
        _LOGGER.info("On tab switch to %s" % str(text))
        self.current_tab = inst.tab
        _LOGGER.info("Gui: Currenttab = %s" % str(inst.tab))


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

    def disconnect_active_views(self, *args, **kwargs):
        self.oscer.send(COMMAND_DISCONNECT)

    def connect_active_views(self, *args, **kwargs):
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
                             dct={v.name: dict(obj=v, active=True if v.active else False) for v in self.views},
                             cls=View),
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
                     cls=User)

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

    def generic_edit_item(self, *arg, dct=dict(), group=None, cls=None):
        self.current_widget = TypeWidgetCB(
            types=dct,
            group=group,
            editclass=ViewWidget if cls == View else UserWidget,
            editpars=dict(formatters=self.get_formatters()) if cls == View else dict(),
            title=f'Select {"view" if cls == View else "user"}',
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
                    item.active = 1 if active else 0
                elif active:
                    self.config.set('dbpars', 'user', f'{item.get_id()}')
                    self.config.write()
                    self.current_user = item
                items.append(item)
            if isinstance(items[0], User):
                self.on_confirm_add_item(None,
                                         items,
                                         oscercmd=COMMAND_SAVEUSER,
                                         lst=self.users)
            else:
                self.on_confirm_add_item(None,
                                         items,
                                         oscercmd=COMMAND_SAVEVIEW,
                                         lst=self.views,
                                         on_ok=self.on_view_added)

    def on_view_added(self, view):
        self.root.ids.id_tabcont.add_widget(view)

    def on_view_removed(self, view):
        self.root.ids.id_tabcont.remove_widget(view)

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
            TcpClient.reset_templates()
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
            formatters=self.get_formatters()
        )
        self.root.ids.id_screen_manager.add_widget(self.current_widget)
        self.root.ids.id_screen_manager.current = self.current_widget.name

    def on_confirm_add_item(self, inst, items, index=0, oscercmd='', lst=[], on_ok=None):
        _LOGGER.info(f'on_confirm_add_item items={items} index={index} oscercm={oscercmd}')
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
                                                         oscercmd=oscercmd,
                                                         lst=lst,
                                                         on_ok=on_ok,
                                                         index=index),
                                timeout=5)
        else:
            self.root.ids.id_screen_manager.remove_widget(self.current_widget)
            self.current_widget = None

    def on_confirm_add_item_server(self, *args, timeout=False, items=None, index=0, lst=[], oscercmd='', on_ok=None):
        error = True
        if timeout:
            msg = MSG_COMMAND_TIMEOUT
            exitv = CONFIRM_FAILED_3
            msg = f"[E {exitv}] {msg}"
        elif args[0] == CONFIRM_OK:
            view = args[1]
            _LOGGER.info(f'New item is {view}')
            if view in lst:
                lst[lst.index(view)] = view
            else:
                lst.append(view)
            # self.root.ids.id_screen_manager.add_widget(self.current_widget)
            # self.current_widget = None
            msg = f"Save {view.__table__} {view.name} OK"
            if on_ok:
                on_ok(view)
            error = False
            TcpClient.reset_templates()
        else:
            msg = args[1]
            exitv = args[0]
            msg = f"[E {exitv}] {msg}"
        toast(msg)
        if not error:
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
            ),
            dict(
                viewclass="MDMenuItem",
                text="Stop backend",
                icon="stop",
                callback=self.stop_server
            ),
            dict(
                viewclass="MDMenuItem",
                text="Exit",
                icon="exit-to-app",
                callback=self.on_nav_exit
            )
        ]
        MDDropdownMenu(items=items, width_mult=3).open(
            self.root.ids.id_toolbar.ids["right_actions"].children[0])

# https://stackoverflow.com/questions/42159927/http-basic-auth-on-twisted-klein-server
# https://github.com/racker/python-twisted-core/blob/master/doc/examples/dbcred.py

    def __init__(self, loop=asyncio.get_event_loop(), *args, **kwargs):
        super(MainApp, self).__init__(*args, **kwargs)
        self.loop = loop
        self._init_fields()

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
            portlisten=int(self.config.get('frontend', 'port')),
            hostconnect=self.config.get('backend', 'host'),
            portconnect=int(self.config.get('backend', 'port')))
        await self.oscer.init(on_init_ok=self.on_osc_init_ok,
                              on_connection_timeout=self.on_connection_timeout,
                              loop=self.loop)

    def get_formatters(self):
        formatters = []
        for _, dm in self.devicemanagers_by_uid.items():
            formatters.extend(dm.get_formatters().values())
        return formatters

    def find_connectors_info(self):
        connectors_info = []
        off = 0
        if not exists(self.connectors_path):
            os.mkdir(self.connectors_path)
        for file in os.listdir(self.connectors_path):
            fp = join(self.connectors_path, file)
            bn = basename(file)
            if isfile(fp) and fnmatch.fnmatch(file, '*.vm'):
                if bn[0] == '_':
                    if bn.startswith('_main_'):
                        try:
                            self.velocity_tabs.append(VelocityTab(velocity=fp, loop=self.loop, name=bn[6:-3].title()))
                        except Exception:
                            _LOGGER.error(f'Template error {traceback.format_exc()}')
                else:
                    section = bn[:-3]
                    title = section.title()
                    cnf = [
                        {
                            "type": "title",
                            "title": fp
                        },
                        {
                            "type": "string",
                            "title": "Host",
                            "desc": f"{title} Host",
                            "section": section,
                            "key": "host"
                        },
                        {
                            "type": "numeric",
                            "title": "Port",
                            "desc": f"{title} Port",
                            "section": section,
                            "key": "port"
                        }
                    ]
                    self.config.setdefaults(
                        section,
                        {'host': '127.0.0.1', 'port': 6000 + off})
                    off += 1
                    connectors_info.append(dict(section=section,
                                                config=cnf,
                                                temp=fp,
                                                hp=None))
        return connectors_info

    def on_command_connectors_confirm(self, *args, timeout=False):
        if not timeout and args[0] != CONFIRM_OK:
            self.all_format = [self.root.ids.id_tabcont.format, TcpClient.format]
            Timer(0, partial(TcpClient.init_connectors_async, self.loop, self.connectors_info))
        else:
            self.all_format = [self.root.ids.id_tabcont.format]\
                if not self.velocity_tabs else\
                [self.root.ids.id_tabcont.format, TcpClient.format]
        self.on_osc_init_ok_cmd_next(
            COMMAND_LISTDEVICES
            if not timeout else
            COMMAND_CONNECTORS)

    def on_osc_init_ok_cmd_next(self, nextcmd):
        if self.init_osc_cmd:
            self.init_osc_cmd = nextcmd
            if self.init_osc_timer:
                self.init_osc_timer.cancel()
            self.init_osc_timer = Timer(0, self.on_osc_init_ok_cmd) if self.init_osc_cmd else None
            if not nextcmd:
                if self.auto_connect_done == -1:
                    if int(self.config.get('preaction', 'autoconnect')):
                        self.connect_active_views()
                    if self.should_close and platform == 'android' and int(self.config.get('preaction', 'closefrontend')):
                        self.stop_me()
                if self.auto_connect_done < 0 and platform == 'android' and\
                        not int(self.config.get('misc', 'screenon')):
                    self.set_screen_on(False)
                self.auto_connect_done = 0

    async def on_osc_init_ok_cmd(self):
        if self.init_osc_cmd == COMMAND_CONNECTORS:
            self.oscer.send(COMMAND_CONNECTORS,
                            json.dumps(self.connectors_info),
                            confirm_callback=self.on_command_connectors_confirm,
                            timeout=5)
        elif self.init_osc_cmd:
            self.init_osc_timer = Timer(5, self.on_osc_init_ok_cmd)
            self.oscer.send(self.init_osc_cmd)

    def on_osc_init_ok(self, exception=None):
        if exception:
            toast('OSC bind error: {0}.'.format(exception))
            snack_open('Wrong IP/Port?', "Settings", self.on_nav_settings)
        else:
            _LOGGER.info('Osc init ok')
            self.oscer.handle(COMMAND_LISTDEVICES_RV, self.on_list_devices_rv)
            self.oscer.handle(COMMAND_LISTVIEWS_RV, self.on_list_views_rv)
            self.oscer.handle(COMMAND_LISTUSERS_RV, self.on_list_users_rv)
            self.oscer.handle(COMMAND_PRINTMSG, self.on_printmsg)
            _LOGGER.info('Osc init ok done')

    def on_printmsg(self, msg):
        toast(msg)

    def on_list_devices_rv(self, *ld):
        self.devicemanagers_by_uid.clear()
        for x in range(0, len(ld), 2):
            dev = ld[x + 1]
            uid = ld[x]
            if dev.type in self.devicemanager_class_by_type:
                self.devicemanagers_by_uid[uid] = self.devicemanager_class_by_type[dev.type](
                    self.oscer,
                    uid,
                    service=False,
                    device=dev,
                    on_state_transition=self.on_state_transition,
                    on_command_handle=self.on_command_handle,
                    loop=self.loop)
        self.on_osc_init_ok_cmd_next(COMMAND_LISTUSERS)

    def on_state_transition(self, inst, oldstate, newstate, reason):
        dev = inst.get_device()
        for f in self.all_format:
            f(dev, state=newstate, manager=inst)

    def on_command_handle(self, inst, command, exitv, *args):
        dev = inst.get_device()
        if command == COMMAND_NEWSESSION:
            _LOGGER.info(f'New session received: {args[0]}')
            for f in self.all_format:
                f(dev, session=args[0], user=self.current_user, manager=inst)
        elif command == COMMAND_DEVICEFIT:
            for f in self.all_format:
                f(dev, device=args[0], fitobj=args[1], state=args[2], manager=inst)

    def on_list_users_rv(self, *ld):
        self.users = list(ld)
        useri = int(self.config.get('dbpars', 'user'))
        self.current_user = None
        for u in self.users:
            if useri < 0 or useri == u.rowid:
                self.current_user = u
                break
        self.on_osc_init_ok_cmd_next(COMMAND_LISTVIEWS)

    def on_list_views_rv(self, *ld):
        self.views = list(ld)
        self.root.ids.id_tabcont.new_view_list(self.views)
        self.on_osc_init_ok_cmd_next(None)
        _LOGGER.info(f'List of views {self.views}')

    def is_pre_init_ok(self):
        for v in self.views:
            for did in v.get_connected_devices():
                for _, dm in self.devicemanagers_by_uid.items():
                    dev = dm.get_device()
                    pa = dm.__pre_action__
                    if did == dev.get_id() and pa:
                        if not self.devicemanagers_pre_init_ok[pa.__name__]:
                            return False
                        break
        return True

    def on_pause(self):
        self.alive_checker.on_pause()
        self.notify_timeout = False
        return True

    def do_pre_finish(self, cls, undo, ok):
        # toast(f'Pre operations for devices of type {cls.__type__}...{"OK" if ok else "FAIL"}')
        _LOGGER.info(f'Pre operations {cls.__name__}...{"OK" if ok else "FAIL"} undo={undo}')
        self.devicemanagers_pre_init_undo[cls.__name__] = undo
        self.devicemanagers_pre_init_ok[cls.__name__] = ok
        self.do_pre()

    def do_pre(self):
        for nmact, actdata in self.devicemanagers_pre_actions.items():
            if self.devicemanagers_pre_init_undo[nmact] is None:
                try:
                    _LOGGER.info(f"Pre operations {nmact}...")
                    preact = actdata['cls'](self.loop)
                    preact.execute(self.config, actdata['types'], self.do_pre_finish)
                    return
                except Exception:
                    _LOGGER.error(f'Pre action error {traceback.format_exc()}')
        if not self.devicemanagers_pre_init_done:
            _LOGGER.info('Pre init done: starting server')
            self.devicemanagers_pre_init_done = True
            self.start_server()
            self.auto_connect_done = -1
            if not self.oscer:
                Timer(8, self.init_osc)

    def on_connection_timeout(self, hp, is_timeout):
        if is_timeout:
            self.last_timeout_time = time.time()
            _LOGGER.info(f'Timeout comunicating with the service ({hp[0]}:{hp[1]})')
            self.alive_checker.start()
            if self.notify_timeout and (self.auto_connect_done != -2 or platform != 'android'):
                toast(f'Timeout comunicating with the service ({hp[0]}:{hp[1]})')
        else:
            _LOGGER.info(f'Debug verb = {get_verbosity(self.config)}')
            self.alive_checker.stop()
            self.oscer.send(COMMAND_LOGLEVEL,
                            get_verbosity(self.config),
                            int(self.config.get('misc', 'notify_screen_on')),
                            int(self.config.get('misc', 'notify_every_ms')))
            if (time.time() - self.last_timeout_time) > 10 or self.init_osc_cmd is False:
                TcpClient.reset_templates()
                self.init_osc_cmd = COMMAND_CONNECTORS
                self.init_osc_timer = Timer(0, self.on_osc_init_ok_cmd)
            if self.notify_timeout:
                toast(f'Serivice connection OK ({hp[0]}:{hp[1]})')
            else:
                self.notify_timeout = True

    def save_window_size(self):
        _LOGGER.debug(f'Window size ({Window.width}, {Window.height})')
        self.config.set('size', 'width', Window.width)
        self.config.set('size', 'height', Window.height)
        self.config.write()
        toast('Window size saved')

    def save_window_pos(self):
        _LOGGER.debug(f'Window pos ({Window.top}, {Window.left})')
        self.config.set('pos', 'top', Window.top)
        self.config.set('pos', 'left', Window.left)
        self.config.write()
        toast('Window position saved')

    def _on_keyboard(self, win, scancode, *largs):
        modifiers = largs[-1]
        _LOGGER.info(f'Keys: {scancode} and {largs}')
        if platform != 'android' and scancode == 100 and set(modifiers) & {'ctrl'} and\
                not (set(modifiers) & {'shift', 'alt', 'meta'}):
            self.stop_server()
            return True
        elif scancode == 27:
            if self.root.ids.nav_drawer.state == 'open':
                self.root.ids.nav_drawer.animation_close()
            else:
                self.stop_me()
            return True
        return False

    def set_screen_on(self, val):
        if platform == 'android':
            from android.runnable import run_on_ui_thread
            @run_on_ui_thread
            def _set_screen_on(val):
                from jnius import autoclass
                FLAG_KEEP_SCREEN_ON = 128
                win = autoclass('org.kivy.android.PythonActivity').mActivity.getWindow()
                win.setFlags(0 if not val else FLAG_KEEP_SCREEN_ON, FLAG_KEEP_SCREEN_ON)
            _set_screen_on(val)

    def on_alive_checker_response(self, alive):
        if not alive:
            self.init_pre_fields()
            self.do_pre()
        else:
            if not self.devicemanagers_pre_init_done:
                for d in self.devicemanagers_pre_init_undo.keys():
                    if self.devicemanagers_pre_init_undo[d] is None:
                        self.devicemanagers_pre_init_undo[d] = False
                        self.devicemanagers_pre_init_ok[d] = True
                self.devicemanagers_pre_init_done = True
            # se trovo il server giá attivo non devo mai chiudere l'interfaccia
            self.should_close = False
            if not self.oscer:
                Timer(0, self.init_osc)

    def on_start(self):
        init_logger(__name__, get_verbosity(self.config))
        if platform != 'android':
            width = int(self.config.get('size', 'width'))
            if width > 0:
                Window.size = (width, int(self.config.get('size', 'height')))
            width = int(self.config.get('pos', 'left'))
            if width >= -6000:
                Window.top = int(self.config.get('pos', 'top'))
                Window.left = width
            if int(self.config.get('window', 'alwaysontop')):
                from KivyOnTop import register_topmost
                register_topmost(Window, self.title)
        Window.bind(on_keyboard=self._on_keyboard)
        self.set_screen_on(True)
        for vt in self.velocity_tabs:
            self.root.ids.id_tabcont.add_widget(vt)
        if self.check_host_port_config('frontend') and self.check_host_port_config('backend') and\
           self.check_other_config():
            for ci in self.connectors_info.copy():
                section = ci['section']
                if not self.check_host_port_config(section):
                    self.connectors_info.remove(ci)
                else:
                    ci['hp'] = (self.config.get(section, 'host'),
                                int(self.config.get(section, 'port')))
            self.alive_checker.start()

        self.root.ids.content_drawer.image_path = join(
            dirname(__file__), '..', "images", "navdrawer.png")
        col = get_natural_color(False)
        for items in {
            "home-outline": ("Home", self.on_nav_home),
            "settings-outline": ("Settings", self.on_nav_settings),
            "exit-to-app": ("Exit", self.on_nav_exit),
        }.items():
            self.root.ids.content_drawer.ids.box_item.add_widget(
                NavigationItem(
                    text=items[1][0],
                    icon=items[0],
                    background_color=col,
                    on_release=items[1][1]
                )
            )

    def on_nav_home(self, *args, **kwargs):
        self.root.ids.nav_drawer.toggle_nav_drawer()
        self.root.ids.id_tabcont.simulate_tab_switch(0)

    def on_nav_exit(self, *args, **kwargs):
        self.true_stop()

    def on_nav_settings(self, *args, **kwargs):
        self.open_settings()

    def true_stop(self):
        self.stop_server()
        self.stop_me()

    def stop_me(self):
        if self.oscer:
            self.oscer.uninit()
        if self.alive_checker:
            self.alive_checker.stop()
        self.stop()

    def on_resume(self):
        self.alive_checker.on_resume()

    def build_config(self, config):
        """
        Set the default values for the configs sections.
        """
        config.setdefaults('dbpars', {'user': -1})
        if platform != 'android':
            config.setdefaults('size', {'width': -200, 'height': -200})
            config.setdefaults('pos', {'left': -20000, 'top': -20000})
            config.setdefaults('window', {'alwaysontop': '0'})
        config.setdefaults('frontend',
                           {'host': '127.0.0.1', 'port': 11002})
        config.setdefaults('backend',
                           {'host': '127.0.0.1', 'port': 11001})
        config.setdefaults('bluetooth',
                           {'connect_secs': 5, 'connect_retry': 10})
        config.setdefaults('log',
                           {'verbosity': 'INFO'})
        config.setdefaults('debug',
                           {'debug_keiserm3i_rescan_timeout': 900})
        config.setdefaults('preaction',
                           {'autoconnect': '0'})
        config.setdefaults('misc',
                           {'notify_screen_on': '0' if platform == 'android' else '-1',
                            'notify_every_ms': '0' if platform == 'android' else '-1'})
        if platform == 'android':
            config.setdefaults('misc',
                               {'screenon': '0'})
            config.setdefaults('preaction',
                               {'closefrontend': '0'})
        self.db_path = self.db_dir()
        self.connectors_path = join(self.db_path, 'connectors')
        self.connectors_info = self.find_connectors_info()
        for _, actdata in self.devicemanagers_pre_actions.items():
            actdata['cls'].build_config(config)

    def _init_fields(self):
        self.title = __prog__
        self.oscer = None
        self.current_user = None
        self.connectors_info = []
        self.all_format = []
        self.velocity_tabs = []
        self.notify_timeout = True
        self.users = []
        self.should_close = True
        self.alive_checker = AndroidAliveChecker(self.loop, self.on_alive_checker_response)
        self.current_widget = None
        self.devicemanager_class_by_type = find_devicemanager_classes(_LOGGER)
        self.devicemanagers_by_uid = dict()
        self.views = []
        self.init_osc_cmd = False
        self.init_osc_timer = None
        self.db_path = ''
        self.last_timeout_time = 0
        self.connectors_path = ''
        self.auto_connect_done = -2
        self.init_pre_fields()

    def init_pre_fields(self):
        self.devicemanagers_pre_init_done = False
        self.devicemanagers_pre_actions = dict()
        for tp, cls in self.devicemanager_class_by_type.items():
            if cls.__pre_action__:
                nm = cls.__pre_action__.__name__
                if nm in self.devicemanagers_pre_actions:
                    self.devicemanagers_pre_actions[nm]['types'].append(tp)
                else:
                    self.devicemanagers_pre_actions[nm] = dict(
                        types=[tp],
                        done=False,
                        cls=cls.__pre_action__
                    )
        self.devicemanagers_pre_init_undo = dict.fromkeys(self.devicemanagers_pre_actions.keys(), None)
        self.devicemanagers_pre_init_ok = dict.fromkeys(self.devicemanagers_pre_actions.keys(), False)

    def build_settings(self, settings):
        """
        Add our custom section to the default configuration object.
        """
        dn = join(dirname(__file__), '..', 'config')
        # We use the string defined above for our JSON, but it could also be
        # loaded from a file as follows:
        #     settings.add_json_panel('My Label', self.config, 'settings.json')
        settings.register_type('buttons', SettingButtons)
        settings.add_json_panel('Backend', self.config, join(dn, 'backend.json'))  # data=json)
        settings.add_json_panel('Frontend', self.config, join(dn, 'frontend.json'))
        settings.add_json_panel('Bluetooth', self.config, join(dn, 'bluetooth.json'))  # data=json)
        lst = [dict(type="buttons",
                    title="Connectors dir",
                    desc=self.connectors_path,
                    section="misc",
                    key="connectors",
                    buttons=[dict(title="Open", id="btn_open")])]
        if platform == 'android':
            lst.extend([dict(type='bool',
                             title='Keep Screen on',
                             desc='Keep screen awake (battery drain)',
                             section='misc',
                             key='screenon'),
                        dict(type='bool',
                             title='Screen awake on notification',
                             desc='Awake screen on each new data (battery drain)',
                             section='misc',
                             key='notify_screen_on'),
                        dict(type='numeric',
                             title='Limit notifications (ms)',
                             desc='Do not notify faster than (ms): 0 unlimited',
                             section='misc',
                             key='notify_every_ms')])
        lst.extend([dict(type='title',
                         title='Preliminary actions rules'),
                    dict(type='bool',
                         title='Auto-Connect',
                         desc='Auto-Connect active views on start',
                         section='preaction',
                         key='autoconnect')])
        if platform == 'android':
            lst.append(dict(type='bool',
                            title='Auto-Close',
                            desc='Auto-Close frontend after starting backend',
                            section='preaction',
                            key='closefrontend'))
        for _, actdata in self.devicemanagers_pre_actions.items():
            sett = actdata['cls'].build_settings()
            if sett:
                lst.append(sett)
        settings.add_json_panel('Misc', self.config, data=json.dumps(lst))
        for ci in self.connectors_info:
            settings.add_json_panel(ci['section'].title(), self.config, data=json.dumps(ci['config']))
        if platform != "android":
            settings.add_json_panel('Window', self.config, join(dn, 'window.json'))
        settings.add_json_panel('Log', self.config, join(dn, 'log.json'))
        if self.config.get('log', 'verbosity') == 'DEBUG':
            settings.add_json_panel('Debug', self.config, join(dn, 'debug.json'))

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

                arg = dict(db_fname=join(self.db_path, 'maindb.db'),
                           hostlisten=self.config.get('backend', 'host'),
                           portlisten=int(self.config.getint('backend', 'port')),
                           connect_secs=int(self.config.getint('bluetooth', 'connect_secs')),
                           connect_retry=int(self.config.getint('bluetooth', 'connect_retry')),
                           undo_info=self.devicemanagers_pre_init_undo,
                           verbose=get_verbosity(self.config),
                           notify_screen_on=int(self.config.get('misc', 'notify_screen_on')),
                           notify_every_ms=int(self.config.get('misc', 'notify_every_ms')),
                           **self.config.items('debug'))
                argument = json.dumps(arg)
                _LOGGER.info("Starting %s [%s]" % (service_class, argument))
                service.start(mActivity, argument)
            except Exception:
                _LOGGER.error(traceback.format_exc())

    def stop_server(self, *args, **kwargs):
        if self.oscer:
            self.oscer.send(COMMAND_STOP)

    async def start_windows_explorer(self):
        await asyncio.create_subprocess_shell(
            f'start "ciao" "{self.connectors_path}"')

    def start_android_explorer(self):
        from jnius import autoclass, cast
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        u = Uri.parse(self.connectors_path)
        intent = Intent(Intent.ACTION_VIEW, u)
        intent.setDataAndType(u, "resource/folder")
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        currentActivity = cast('android.app.Activity', PythonActivity.mActivity)
        if intent.resolveActivityInfo(currentActivity.getPackageManager(), 0):
            currentActivity.startActivity(intent)

    def on_config_change(self, config, section, key, value):
        """
        Respond to changes in the configuration.
        """
        _LOGGER.info("main.py: App.on_config_change: {0}, {1}, {2}, {3}".format(
            config, section, key, value))
        if section == 'window' and key == 'alwaysontop':
            from KivyOnTop import register_topmost, unregister_topmost
            if int(value):
                register_topmost(Window, self.title)
            else:
                unregister_topmost(Window, self.title)
        elif section == 'possize':
            if key == 'pos':
                self.save_window_pos()
            elif key == 'size':
                self.save_window_size()
        elif section == 'misc' and key == 'screenon':
            if self.auto_connect_done >= 0:
                self.set_screen_on(int(value))
        elif section == 'misc' and key == 'connectors':
            if platform == 'android':
                self.start_android_explorer()
            elif platform == 'win':
                Timer(0, self.start_windows_explorer)
        elif (section == 'log' and key == 'verbosity') or\
                (section == 'misc' and key == 'notify_screen_on') or\
                (section == 'misc' and key == 'notify_every_ms'):
            verb = get_verbosity(self.config)
            init_logger(__name__, verb)
            if self.oscer:
                self.oscer.send(COMMAND_LOGLEVEL,
                                verb,
                                int(self.config.get('misc', 'notify_screen_on')),
                                int(self.config.get('misc', 'notify_every_ms')))
        elif self.check_host_port_config('frontend') and self.check_host_port_config('backend') and\
                self.check_other_config():
            if self.oscer:
                snack_open("Configuration changes will be effective on restart", "Quit", self.on_nav_exit)
            else:
                Timer(0, self.init_osc)

    def close_settings(self, settings=None):
        """
        The settings panel has been closed.
        """
        _LOGGER.info("main.py: App.close_settings: {0}".format(settings))
        super(MainApp, self).close_settings(settings)


def main():
    os.environ['KIVY_EVENTLOOP'] = 'async'
    if platform == "win":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    app = MainApp(loop=loop)
    loop.run_until_complete(app.async_run())
    loop.run_until_complete(asyncio_graceful_shutdown(loop, _LOGGER, False))
    _LOGGER.info("Gui: Closing loop")
    loop.close()


if __name__ == '__main__':
    main()
