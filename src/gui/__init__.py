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
import traceback
from functools import partial
import logging
from os.path import basename, dirname, exists, expanduser, isfile, join

from db.user import User
from db.view import View
from device.manager import GenericDeviceManager
from gui.typewidget import TypeWidget
from gui.typewidget_cb import TypeWidgetCB
from gui.useredit import UserWidget
from gui.velocity_tab import VelocityTab
from gui.viewedit import ViewPlayWidget, ViewWidget
from kivy.app import App
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
from util.const import (COMMAND_CONNECT, COMMAND_CONNECTORS, COMMAND_DELUSER,
                        COMMAND_DELVIEW, COMMAND_DEVICEFIT, COMMAND_DISCONNECT,
                        COMMAND_LISTDEVICES, COMMAND_LISTDEVICES_RV, COMMAND_LISTUSERS,
                        COMMAND_LISTUSERS_RV, COMMAND_LISTVIEWS,
                        COMMAND_LISTVIEWS_RV, COMMAND_NEWDEVICE, COMMAND_NEWSESSION,
                        COMMAND_SAVEUSER, COMMAND_SAVEVIEW, COMMAND_STOP,
                        CONFIRM_FAILED_3, CONFIRM_OK, MSG_COMMAND_TIMEOUT)
from util.osc_comunication import OSCManager
from util.timer import Timer
from util.velocity_tcp import TcpClient
from util import asyncio_graceful_shutdown, find_devicemanager_classes, init_logger


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
        removel = list()
        for t in self.tab_list:
            if isinstance(t, ViewPlayWidget) and t.view not in views:
                removel.append(t)
        for t in removel:
            self.remove_widget(t)
        for t in views:
            self.add_widget(t)

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
            _LOGGER.debug(f'Already present: {oldtab.view} -> {oldtab.view is view}')
            oldtab.view = view
            oldtab.on_view(view)
        else:
            _LOGGER.debug(f'TAB not present: {view}')
            super(MyTabs, self).add_widget(tab, *args, **kwargs)
            self.tab_list.append(tab)
            _LOGGER.debug(f"Gui: Adding tab len = {len(self.tab_list)}")
            self.carousel.index = len(self.tab_list) - 1
            tab.tab_label.state = "down"
            tab.tab_label.on_release()

    def on_tab_switch(self, inst, text):
        super(MyTabs, self).on_tab_switch(inst, text)
        _LOGGER.debug("On tab switch to %s" % str(text))
        self.current_tab = inst.tab
        _LOGGER.debug("Gui: Currenttab = %s" % str(inst.tab))


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
        _LOGGER.debug(f'on_confirm_add_item items={items} index={index} oscercm={oscercmd}')
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
            formatters.extend(dm.get_formatters())
        return formatters

    def find_connectors_info(self):
        dir_additonals = join(self.db_dir(), 'connectors')
        connectors_info = []
        off = 0
        if not exists(dir_additonals):
            os.mkdir(dir_additonals)
        for file in os.listdir(dir_additonals):
            fp = join(dir_additonals, file)
            bn = basename(file)
            if isfile(fp) and fnmatch.fnmatch(file, '*.vm'):
                if bn[0] == '_':
                    if bn == '_main.vm':
                        self.velocity_tab = VelocityTab(velocity=fp, loop=self.loop)
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
                                                hp=(self.config.get(section, 'host'),
                                                    int(self.config.get(section, 'port')))))
        return connectors_info

    def on_command_connectors_confirm(self, *args, timeout=False):
        if not timeout and args[0] != CONFIRM_OK:
            self.all_format = [self.root.ids.id_tabcont.format, TcpClient.format]
            Timer(0, partial(TcpClient.init_connectors_async, self.loop, self.connectors_info))
        else:
            self.all_format = [self.root.ids.id_tabcont.format]\
                if not self.velocity_tab else\
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

    async def on_osc_init_ok_cmd(self):
        if self.init_osc_cmd == COMMAND_CONNECTORS:
            self.oscer.send(COMMAND_CONNECTORS,
                            json.dumps(self.connectors_info),
                            confirm_callback=self.on_command_connectors_confirm,
                            timeout=5)
        elif self.init_osc_cmd:
            self.init_osc_timer = Timer(5, self.on_osc_init_ok_cmd)
            self.oscer.send(self.init_osc_cmd)

    def on_osc_init_ok(self):
        _LOGGER.debug('Osc init ok')
        self.oscer.handle(COMMAND_LISTDEVICES_RV, self.on_list_devices_rv)
        self.oscer.handle(COMMAND_LISTVIEWS_RV, self.on_list_views_rv)
        self.oscer.handle(COMMAND_LISTUSERS_RV, self.on_list_users_rv)
        self.init_osc_cmd = COMMAND_CONNECTORS
        self.init_osc_timer = Timer(0, self.on_osc_init_ok_cmd)
        _LOGGER.debug('Osc init ok done')

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
            f(dev, state=newstate)

    def on_command_handle(self, inst, command, exitv, *args):
        dev = inst.get_device()
        if command == COMMAND_NEWSESSION:
            _LOGGER.debug(f'New session received: {args[0]}')
            for f in self.all_format:
                f(dev, session=args[0], user=self.current_user)
        elif command == COMMAND_DEVICEFIT:
            for f in self.all_format:
                f(dev, device=args[0], fitobj=args[1], state=args[2])

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
        _LOGGER.debug(f'List of views {self.views}')

    def is_pre_init_ok(self):
        for v in self.views:
            for did in v.get_connected_devices():
                for _, dm in self.devicemanagers_by_uid.items():
                    dev = dm.get_device()
                    if did == dev.get_id():
                        if not self.devicemanagers_pre_init[dev.get_type()]:
                            return False
                        break
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

    def on_connection_timeout(self, hp, is_timeout):
        if is_timeout:
            self.do_pre()
            toast(f'Timeout comunicating with the service ({hp[0]}:{hp[1]})')
        else:
            if not self.devicemanagers_pre_init_done:
                for d in self.devicemanagers_pre_init.keys():
                    if self.devicemanagers_pre_init[d] is None:
                        self.devicemanagers_pre_init[d] = True
                self.devicemanagers_pre_init_done = True
            toast(f'Serivice connection OK ({hp[0]}:{hp[1]})')

    def on_start(self):
        if self.velocity_tab:
            self.root.ids.id_tabcont.add_widget(self.velocity_tab)
        if self.check_host_port_config('frontend') and self.check_host_port_config('backend') and\
           self.check_other_config():
            for ci in self.connectors_info.copy():
                if not self.check_host_port_config(ci['section']):
                    self.connectors_info.remove(ci)
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
        _LOGGER.debug("On Nav Home")

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
        config.setdefaults('dbpars', {'user': -1})
        config.setdefaults('frontend',
                           {'host': '127.0.0.1', 'port': 11002})
        config.setdefaults('backend',
                           {'host': '127.0.0.1', 'port': 11001})
        config.setdefaults('bluetooth',
                           {'connect_secs': 5, 'connect_retry': 10})
        self.connectors_info = self.find_connectors_info()

    def _init_fields(self):
        self.title = __prog__
        self.oscer = None
        self.current_user = None
        self.connectors_info = []
        self.all_format = []
        self.velocity_tab = None
        self.users = []
        self.current_widget = None
        self.devicemanager_class_by_type = find_devicemanager_classes(_LOGGER)
        self.devicemanagers_by_uid = dict()
        self.views = []
        self.init_osc_cmd = None
        self.init_osc_timer = None
        self.devicemanagers_pre_init_done = False
        self.devicemanagers_pre_init = dict.fromkeys(self.devicemanager_class_by_type.keys(), None)

    def build_settings(self, settings):
        """
        Add our custom section to the default configuration object.
        """
        dn = join(dirname(__file__), '..', 'config')
        dir_additonals = join(self.db_dir(), 'connectors')
        # We use the string defined above for our JSON, but it could also be
        # loaded from a file as follows:
        #     settings.add_json_panel('My Label', self.config, 'settings.json')
        settings.add_json_panel('Backend', self.config, join(dn, 'backend.json'))  # data=json)
        settings.add_json_panel('Frontend', self.config, join(dn, 'frontend.json'))
        with open(join(dn, 'bluetooth.json')) as json_file:
            blue = json.load(json_file)
            blue[2]['title'] += dir_additonals
            settings.add_json_panel('Bluetooth', self.config, data=json.dumps(blue))  # data=json)
        for ci in self.connectors_info:
            settings.add_json_panel(ci['section'].title(), self.config, data=json.dumps(ci['config']))

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
                           portlisten=int(self.config.getint('backend', 'port')),
                           connect_secs=int(self.config.getint('bluetooth', 'connect_secs')),
                           connect_retry=int(self.config.getint('bluetooth', 'connect_retry')),
                           verbose=True)
                argument = json.dumps(arg)
                _LOGGER.info("Starting %s [%s]" % (service_class, argument))
                service.start(mActivity, argument)
            except Exception:
                _LOGGER.error(traceback.format_exc())

    async def stop_server(self):
        if self.oscer:
            self.oscer.send(COMMAND_STOP)
            self.oscer.uninit()

    def on_config_change(self, config, section, key, value):
        """
        Respond to changes in the configuration.
        """
        _LOGGER.info("main.py: App.on_config_change: {0}, {1}, {2}, {3}".format(
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
    _LOGGER.debug("Gui: Closing loop")
    loop.close()


if __name__ == '__main__':
    main()
