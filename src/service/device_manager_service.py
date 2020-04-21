import argparse
import asyncio
import glob
import json
import os
import traceback
from functools import partial
from os.path import basename, dirname, exists, isfile, join, splitext

import aiosqlite
from db.device import Device
from db.user import User
from db.view import View
from util import find_devicemanager_classes, get_verbosity, init_logger
from util.const import (COMMAND_CONFIRM, COMMAND_CONNECT, COMMAND_CONNECTORS,
                        COMMAND_DEVICEFIT, COMMAND_DELDEVICE, COMMAND_DELUSER, COMMAND_DELVIEW,
                        COMMAND_DISCONNECT, COMMAND_LISTDEVICES, COMMAND_LISTDEVICES_RV,
                        COMMAND_LISTUSERS, COMMAND_LISTUSERS_RV,
                        COMMAND_LISTVIEWS, COMMAND_LISTVIEWS_RV, COMMAND_LOGLEVEL,
                        COMMAND_NEWDEVICE, COMMAND_NEWSESSION,
                        COMMAND_PRINTMSG, COMMAND_SAVEDEVICE,
                        COMMAND_SAVEUSER, COMMAND_SAVEVIEW, COMMAND_SEARCH,
                        COMMAND_STOP, CONFIRM_FAILED_1, CONFIRM_FAILED_2,
                        CONFIRM_OK, DEVREASON_BLE_DISABLED,
                        DEVREASON_PREPARE_ERROR, DEVREASON_REQUESTED,
                        DEVSTATE_CONNECTING, DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_SEARCHING, MSG_CONNECTION_STATE_INVALID,
                        MSG_DB_SAVE_ERROR, MSG_DEVICE_NOT_STOPPED, MSG_INVALID_ITEM,
                        MSG_TYPE_DEVICE_UNKNOWN)
from util.osc_comunication import OSCManager
from util.velocity_tcp import TcpClient
from util.timer import Timer

_LOGGER = None
__prog__ = "pymoviz-server"


class DeviceManagerService(object):
    def __init__(self, **kwargs):
        self.addit_params = dict()
        for key, val in kwargs.items():
            if not key.startswith('ab_'):
                setattr(self, key, val)
            else:
                self.addit_params[key[3:]] = val
        _LOGGER.debug(f'Addit params for DM {self.addit_params}')
        self.db = None
        self.oscer = None
        self.notification_formatter_info = dict(inst=None, timer=None, manager=None)
        self.connectors_format = False
        self.devicemanager_class_by_type = dict()
        self.devicemanagers_pre_actions = dict()
        self.devicemanagers_by_id = dict()
        self.devicemanagers_by_uid = dict()
        self.connectors_info = []
        self.users = []
        self.views = []
        self.devices = []
        self.devicemanagers_active = []
        self.devicemanagers_active_done = []
        self.timer_obj = None
        self.main_session = None
        self.last_user = None
        self.devicemanagers_active_info = dict()
        self.stop_event = asyncio.Event()
        if self.android:
            from jnius import autoclass
            from android.broadcast import BroadcastReceiver
            self.Context = autoclass('android.content.Context')
            self.AndroidString = autoclass('java.lang.String')
            self.NotificationBuilder = autoclass('android.app.Notification$Builder')
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.service = autoclass('org.kivy.android.PythonService').mService
            self.NOTIFICATION_CHANNEL_ID = self.AndroidString(self.service.getPackageName().encode('utf-8'))
            self.FOREGROUND_NOTIFICATION_ID = 1462
            self.app_context = self.service.getApplication().getApplicationContext()
            self.notification_service = self.service.getSystemService(self.Context.NOTIFICATION_SERVICE)
            self.CONNECT_ACTION = 'device_manager_service.view.CONNECT'
            self.DISCONNECT_ACTION = 'device_manager_service.view.DISCONNECT'

            self.br = BroadcastReceiver(
                self.on_broadcast, actions=[self.CONNECT_ACTION, self.DISCONNECT_ACTION])
            self.br.start()

            Intent = autoclass('android.content.Intent')
            PendingIntent = autoclass('android.app.PendingIntent')
            NotificationActionBuilder = autoclass('android.app.Notification$Action$Builder')
            Notification = autoclass('android.app.Notification')
            Color = autoclass("android.graphics.Color")
            NotificationChannel = autoclass('android.app.NotificationChannel')
            NotificationManager = autoclass('android.app.NotificationManager')
            channelName = self.AndroidString('DeviceManagerService'.encode('utf-8'))
            chan = NotificationChannel(self.NOTIFICATION_CHANNEL_ID, channelName, NotificationManager.IMPORTANCE_DEFAULT)
            chan.setLightColor(Color.BLUE)
            chan.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE)
            self.notification_service.createNotificationChannel(chan)
            BitmapFactory = autoclass("android.graphics.BitmapFactory")
            Icon = autoclass("android.graphics.drawable.Icon")
            BitmapFactoryOptions = autoclass("android.graphics.BitmapFactory$Options")
            # Drawable = jnius.autoclass("{}.R$drawable".format(service.getPackageName()))
            # icon = getattr(Drawable, 'icon')
            options = BitmapFactoryOptions()
            # options.inMutable = True
            # declaredField = options.getClass().getDeclaredField("inPreferredConfig")
            # declaredField.set(cast('java.lang.Object',options), cast('java.lang.Object', BitmapConfig.ARGB_8888))
            # options.inPreferredConfig = BitmapConfig.ARGB_8888;
            notification_image = join(dirname(__file__), '..', 'images', 'device_manager.png')
            bm = BitmapFactory.decodeFile(notification_image, options)
            self.notification_icon = Icon.createWithBitmap(bm)
            notification_image = join(dirname(__file__), '..', 'images', 'lan-connect.png')
            bm = BitmapFactory.decodeFile(notification_image, options)
            connect_icon = Icon.createWithBitmap(bm)
            broadcastIntent = Intent()
            actionIntent = PendingIntent.getBroadcast(self.service,
                                                      0,
                                                      broadcastIntent,
                                                      PendingIntent.FLAG_UPDATE_CURRENT)
            self.connect_action = NotificationActionBuilder(connect_icon, self.CONNECT_ACTION, actionIntent).build()
            notification_image = join(dirname(__file__), '..', 'images', 'lan-disconnect.png')
            bm = BitmapFactory.decodeFile(notification_image, options)
            disconnect_icon = Icon.createWithBitmap(bm)
            self.disconnect_action = NotificationActionBuilder(disconnect_icon, self.DISCONNECT_ACTION, actionIntent).build()
            notification_intent = Intent(self.app_context, self.PythonActivity)
            notification_intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP |
                                         Intent.FLAG_ACTIVITY_SINGLE_TOP |
                                         Intent.FLAG_ACTIVITY_NEW_TASK)
            notification_intent.setAction(Intent.ACTION_MAIN)
            notification_intent.addCategory(Intent.CATEGORY_LAUNCHER)
            self.notification_intent = PendingIntent.getActivity(self.service, 0, notification_intent, 0)

    def on_broadcast(self, context, intent):
        action = intent.getAction()
        _LOGGER.info(f'on_broadcast action {action}')

    def change_service_notification(self, dm, **kwargs):
        if self.android:
            m = self.notification_formatter_info['manager']
            newman = None
            if (m and dm is m) or not m:
                if not m:
                    m = newman = dm
            elif m.get_priority() < dm.get_priority():
                m = newman = dm
            else:
                m = None
            if newman:
                self.notification_formatter_info['manager'] = newman
                self.notification_formatter_info['inst'] = newman.get_notification_formatter()
            if m:
                if self.notification_formatter_info['timer']:
                    self.notification_formatter_info['timer'].cancel()
                self.notification_formatter_info['timer'] = Timer(45, self.clear_notification_formatter)
                txt = ''
                f = self.notification_formatter_info['inst']
                for types, obj in kwargs.items():
                    if (m.get_id() == f.device) and types == f.type:
                        txt = f.format(obj)
                if txt:
                    alias = m.get_device().get_alias()
                    _LOGGER.debug(f'Changing notification {alias}-> {txt}')
                    self.set_service_notification(self.build_service_notification(alias, txt))

    async def clear_notification_formatter(self):
        txt = self.notification_formatter_info['inst'].set_timeout()
        m = self.notification_formatter_info['manager']
        self.set_service_notification(self.build_service_notification(m.get_device().get_alias(), txt))
        self.notification_formatter_info['inst'] = None
        self.notification_formatter_info['manager'] = None
        self.notification_formatter_info['timer'] = None

    async def init_osc(self):
        self.oscer = OSCManager(hostlisten=self.hostlisten, portlisten=self.portlisten)
        await self.oscer.init(on_init_ok=self.on_osc_init_ok)

    def on_osc_init_ok(self):
        self.oscer.handle(COMMAND_STOP, self.on_command_stop)
        self.oscer.handle(COMMAND_LOGLEVEL, self.on_command_loglevel)
        self.oscer.handle(COMMAND_NEWDEVICE, self.on_command_newdevice)
        self.oscer.handle(COMMAND_CONNECT, self.on_command_condisc, 'c')
        self.oscer.handle(COMMAND_DISCONNECT, self.on_command_condisc, 'd')
        self.oscer.handle(COMMAND_CONNECTORS, self.on_command_connectors)
        self.oscer.handle(COMMAND_LISTDEVICES, self.on_command_listdevices)
        self.oscer.handle(COMMAND_LISTUSERS, self.on_command_listusers)
        self.oscer.handle(COMMAND_LISTVIEWS, self.on_command_listviews)
        self.oscer.handle(COMMAND_SAVEVIEW, partial(self.on_command_dbelem,
                                                    asyncmethod=self.on_command_saveelem_async,
                                                    lst=self.views,
                                                    cls=View,
                                                    on_ok=self.set_devicemanagers_active))
        self.oscer.handle(COMMAND_DELVIEW, partial(self.on_command_dbelem,
                                                   asyncmethod=self.on_command_delelem_async,
                                                   lst=self.views,
                                                   cls=View,
                                                   on_ok=self.set_devicemanagers_active))
        self.oscer.handle(COMMAND_SAVEUSER, partial(self.on_command_dbelem,
                                                    asyncmethod=self.on_command_saveelem_async,
                                                    lst=self.users,
                                                    cls=User))
        self.oscer.handle(COMMAND_DELUSER, partial(self.on_command_dbelem,
                                                   asyncmethod=self.on_command_delelem_async,
                                                   lst=self.users,
                                                   cls=User))
        self.create_device_managers()

    def on_command_condisc(self, cmd, *args):
        _LOGGER.info(f'On Command condisc: {cmd}')
        if cmd == 'c':
            self.last_user = args[0]
        for dm in self.devicemanagers_active_done.copy():
            self.devicemanagers_active.append(dm)
            self.devicemanagers_active_done.remove(dm)
        from device.manager import GenericDeviceManager
        GenericDeviceManager.sort(self.devicemanagers_active)
        for _, info in self.devicemanagers_active_info.items():
            info['operation'] = cmd
            info['retry'] = 0
        Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))

    def on_command_listviews(self, *args):
        _LOGGER.info('List view before send:')
        for v in self.views:
            _LOGGER.info(f'View = {v}')
        self.oscer.send(COMMAND_LISTVIEWS_RV, *self.views)

    def on_command_listusers(self, *args):
        self.oscer.send(COMMAND_LISTUSERS_RV, *self.users)

    def on_command_connectors(self, connectors_info, *args):
        connectors_info = json.loads(connectors_info)
        if connectors_info:
            for ci in connectors_info:
                if not exists(ci['temp']):
                    self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1)
                    return
            self.connectors_format = True
            Timer(0, partial(TcpClient.init_connectors_async, self.loop, connectors_info))
        self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK)

    def on_command_listdevices(self, *args):
        out = []
        for uid, dm in self.devicemanagers_by_uid.items():
            out.append(uid)
            out.append(dm.get_device())
        self.oscer.send(COMMAND_LISTDEVICES_RV, *out)

    async def on_command_delelem_async(self, elem, *args, lst=None, on_ok=None):
        try:
            _LOGGER.info(f'on_command_delelem_async {elem}')
            rv = await elem.delete(self.db)
            if rv:
                if elem in lst:
                    lst.remove(elem)
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, elem)
                if on_ok:
                    on_ok(elem)
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(elem))
        except Exception:
            _LOGGER.error(f'on_command_delelem_async exception {traceback.format_exc()}')

    async def on_command_saveelem_async(self, elem, *args, lst=None, on_ok=None):
        try:
            _LOGGER.info(f'on_command_saveelem_async {elem}')
            rv = await elem.to_db(self.db)
            if rv:
                if elem not in lst:
                    lst.append(elem)
                else:
                    lst[lst.index(elem)] = elem
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, elem)
                if on_ok:
                    on_ok(elem)
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(elem))
        except Exception:
            _LOGGER.error(f'on_command_saveelem_async exception {traceback.format_exc()}')

    def on_command_dbelem(self, elem, *args, asyncmethod=None, lst=None, cls=None, on_ok=None):
        _LOGGER.info(f'on_command_dbelem {elem}')
        if isinstance(elem, cls):
            if self.devicemanagers_all_stopped():
                Timer(0, partial(asyncmethod, elem, lst=lst, on_ok=on_ok))
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID)
        else:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_INVALID_ITEM)

    def on_event_command_handle(self, dm, command, *args):
        _LOGGER.debug(f'On Command Handle dm={dm} comm={command} a={args}')
        exitv = args[0] if args else None
        if command == COMMAND_NEWSESSION and exitv == CONFIRM_OK:
            if self.connectors_format:
                TcpClient.format(dm.get_device(), manager=dm, session=args[2], user=self.last_user)
            self.change_service_notification(dm, manager=dm, session=args[2], user=self.last_user)
            if self.main_session:
                args[1].set_main_session_id(self.main_session.get_id())
            else:
                self.main_session = args[2]
        elif command == COMMAND_DEVICEFIT and exitv == CONFIRM_OK:
            if self.connectors_format:
                TcpClient.format(args[1], fitobj=args[2], manager=dm)
            self.change_service_notification(dm, fitobj=args[2], manager=dm)
        elif command == COMMAND_DELDEVICE and exitv == CONFIRM_OK:
            ids = f'{dm.get_id()}'
            if ids in self.devicemanagers_by_id:
                del self.devicemanagers_by_id[ids]
            ids = dm.get_uid()
            if ids in self.devicemanagers_active_info:
                del self.devicemanagers_active_info[ids]
            if ids in self.devicemanagers_by_uid:
                del self.devicemanagers_by_uid[ids]
            if dm in self.devicemanagers_active:
                self.devicemanagers_active.remove(dm)
            if dm in self.devicemanagers_active_done:
                self.devicemanagers_active_done.remove(dm)
            self.set_formatters_device()
        elif command == COMMAND_SAVEDEVICE and exitv == CONFIRM_OK:
            ids = f'{dm.get_id()}'
            if ids not in self.devicemanagers_by_id:
                self.devicemanagers_by_id[ids] = dm
            self.set_formatters_device()
            self.on_command_listviews()
        elif command == COMMAND_SEARCH and exitv == CONFIRM_OK:
            if dm.get_state() != DEVSTATE_SEARCHING:
                if self.devicemanagers_all_stopped():
                    dm.search(True)
            else:
                dm.search(False)

    def generate_uid(self):
        while True:
            uid = OSCManager.generate_uid()
            if uid not in self.devicemanagers_by_uid:
                return uid

    def devicemanagers_all_stopped(self):
        if not self.devicemanagers_active or not self.timer_obj:
            for _, x in self.devicemanagers_by_uid.items():
                if not x.is_stopped_state():
                    return False
            return True
        else:
            return False

    def on_command_newdevice(self, typev, *args):
        if typev not in self.devicemanager_class_by_type:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_TYPE_DEVICE_UNKNOWN)
        elif not self.devicemanagers_all_stopped():
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_CONNECTION_STATE_INVALID)
        else:
            uid = self.generate_uid()
            self.devicemanagers_by_uid[uid] = self.devicemanager_class_by_type[typev](
                self.oscer,
                uid,
                service=True,
                db=self.db,
                loop=self.loop,
                params=self.addit_params,
                on_command_handle=self.on_event_command_handle,
                on_state_transition=self.on_event_state_transition)
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, uid)

    def on_command_loglevel(self, level, *args):
        init_logger(__name__, level)

    def on_command_stop(self, *args):
        self.loop.stop()

    def set_service_notification(self, notif):
        self.notification_service.notify(self.FOREGROUND_NOTIFICATION_ID, notif)

    def build_service_notification(self, title, message):
        notification_builder = self.NotificationBuilder(self.app_context, self.NOTIFICATION_CHANNEL_ID)
        # app_class = service.getApplication().getClass()

        title = self.AndroidString(title.encode('utf-8'))
        message = self.AndroidString(message.encode('utf-8'))
        notification_builder.setContentTitle(title)
        notification_builder.setContentText(message)
        notification_builder.setContentIntent(self.notification_intent)
        notification_builder.setSmallIcon(self.notification_icon)
        notification_builder.setAutoCancel(True)
        notification_builder.addAction(self.connect_action)
        notification_builder.addAction(self.disconnect_action)
        return notification_builder.getNotification()

    def insert_service_notification(self):
        self.service.setAutoRestartService(False)
        self.service.startForeground(self.FOREGROUND_NOTIFICATION_ID, self.build_service_notification("Fit.py", "DeviceManagerService"))

    async def start(self):
        if self.android:
            self.insert_service_notification()
        self.devicemanager_class_by_type = find_devicemanager_classes(_LOGGER)
        for tp, cls in self.devicemanager_class_by_type.items():
            if cls.__pre_action__:
                nm = cls.__pre_action__.__name__
                if nm not in self.devicemanagers_pre_actions:
                    self.devicemanagers_pre_actions[nm] = cls.__pre_action__
        await self.init_db(self.db_fname)
        await self.load_db()
        await self.init_osc()

    def set_devicemanagers_active(self, *args, **kwargs):
        del self.devicemanagers_active_done[:]
        del self.devicemanagers_active[:]
        self.devicemanagers_active_info.clear()
        for v in self.views:
            if v.active:
                for c in v.get_connected_devices():
                    d = self.devicemanagers_by_id[str(c)]
                    if d not in self.devicemanagers_active_done:
                        self.devicemanagers_active_done.append(d)
        for d in self.devicemanagers_active_done:
            self.devicemanagers_active_info[d.get_uid()] = dict(retry=0, operation='')

    def set_formatters_device(self):
        views2save = []
        for v in self.views:
            saveview = False
            for i in range(len(v.items) - 1, -1, -1):
                lab = v.items[i]
                ids = str(lab.device)
                if ids in self.devicemanagers_by_id:
                    lab.set_device(self.devicemanagers_by_id[ids].get_device())
                else:
                    del v.items[i]
                    saveview = True
            if saveview:
                views2save.append(v)
        if views2save:
            Timer(0, partial(self.save_modified_views, views2save))

    async def save_modified_views(self, views2save):
        for v in views2save:
            rv = await v.to_db(self.db)
            _LOGGER.info(f'Saving view {v} -> {rv}')
        self.on_command_listviews()

    def create_device_managers(self):
        for d in self.devices:
            uid = self.generate_uid()
            typev = d.get_type()
            if typev in self.devicemanager_class_by_type:
                dm = self.devicemanager_class_by_type[typev](
                    self.oscer,
                    uid,
                    service=True,
                    loop=self.loop,
                    db=self.db,
                    device=d,
                    params=self.addit_params,
                    on_command_handle=self.on_event_command_handle,
                    on_state_transition=self.on_event_state_transition)
                self.devicemanagers_by_id[f'{d.get_id()}'] = dm
                self.devicemanagers_by_uid[uid] = dm
        self.set_devicemanagers_active()
        self.set_formatters_device()

    async def load_db(self):
        try:
            self.users = await User.loadbyid(self.db)
            self.devices = await Device.loadbyid(self.db)
            self.views = await View.load1m(self.db)
            # _LOGGER.debug(f'List view[0] {self.views[0]}')
        except Exception:
            _LOGGER.error(f'Load DB error {traceback.format_exc()}')

    async def start_remaining_connection_operations(self, bytimer=True):
        try:
            _LOGGER.info(f'Starting remaining con timer={bytimer}')
            if bytimer:
                self.timer_obj = None
            elif self.timer_obj:
                self.timer_obj.cancel()
                self.timer_obj = None
            for dm in self.devicemanagers_active.copy():
                info = self.devicemanagers_active_info[dm.get_uid()]
                _LOGGER.info(f'Processing[{dm.get_uid()}] {dm.get_device()} -> {info["operation"]}')
                if info['operation'] == 'd':
                    if dm.get_state() == DEVSTATE_CONNECTING:
                        break
                    elif not dm.is_connected_state():
                        self.devicemanagers_active.remove(dm)
                        self.devicemanagers_active_done.append(dm)
                    else:
                        dm.disconnect()
                        break
                elif info['operation'] == 'c':
                    if dm.is_connected_state():
                        self.devicemanagers_active.remove(dm)
                        self.devicemanagers_active_done.append(dm)
                    elif bytimer:
                        dm.set_user(self.last_user)
                        if dm.connect():
                            break
                        else:
                            self.oscer.send(COMMAND_PRINTMSG, MSG_DEVICE_NOT_STOPPED.format(dm.get_device().get_alias()))
                    else:
                        if info['retry'] < self.connect_retry:
                            self.timer_obj = Timer(
                                0 if not info['retry'] else self.connect_secs,
                                self.start_remaining_connection_operations)
                            info['retry'] += 1
                            break
                        else:
                            _LOGGER.info(f'Retry FINISH for device[{dm.get_uid()}] {dm.get_device()}')
        except Exception:
            _LOGGER.error(f'Rem op error {traceback.format_exc()}')

    def set_operation_ended(self, info):
        info['operation'] = ''
        info['retry'] = 0

    def on_event_state_transition(self, dm, oldstate, newstate, reason):
        if self.connectors_format:
            TcpClient.format(dm.get_device(), state=newstate, manager=dm)
        self.change_service_notification(dm, state=newstate, manager=dm)
        uid = dm.get_uid()
        if uid in self.devicemanagers_active_info:  # assenza significa che stiamo facendo una ricerca
            info = self.devicemanagers_active_info[uid]
            from device.manager import GenericDeviceManager
            if GenericDeviceManager.is_connected_state_s(newstate) and oldstate == DEVSTATE_CONNECTING:
                if dm in self.devicemanagers_active:
                    self.devicemanagers_active.remove(dm)
                    self.devicemanagers_active_done.append(dm)
                self.set_operation_ended(info)
                Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))
            elif oldstate == DEVSTATE_CONNECTING and newstate == DEVSTATE_DISCONNECTED:
                Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))
            elif (GenericDeviceManager.is_connected_state_s(oldstate) or
                  (oldstate == DEVSTATE_DISCONNECTING and reason != DEVREASON_REQUESTED)) and\
                    newstate == DEVSTATE_DISCONNECTED:
                self.set_operation_ended(info)
                if reason == DEVREASON_PREPARE_ERROR or reason == DEVREASON_BLE_DISABLED:
                    for dm in self.devicemanagers_active:
                        info = self.devicemanagers_active_info[dm.get_uid()]
                        self.set_operation_ended(info)
                        if dm not in self.devicemanagers_active_done:
                            self.devicemanagers_active_done.append(dm)
                    del self.devicemanagers_active[:]
                elif reason != DEVREASON_REQUESTED:
                    info['operation'] = 'c'
                    if dm in self.devicemanagers_active_done:
                        self.devicemanagers_active_done.remove(dm)
                    if dm not in self.devicemanagers_active:
                        self.devicemanagers_active.append(dm)
                        GenericDeviceManager.sort(self.devicemanagers_active)
                else:
                    self.main_session = None
                    if dm in self.devicemanagers_active:
                        self.devicemanagers_active.remove(dm)
                        self.devicemanagers_active_done.append(dm)
                Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))

    async def init_db(self, file):
        self.db = await aiosqlite.connect(file)
        if not isinstance(self.db, aiosqlite.Connection):
            self.db = None
        else:
            self.db.row_factory = aiosqlite.Row
            modules = glob.glob(join(dirname(__file__), "..", "db", "*.py*"))
            pls = [splitext(basename(f))[0] for f in modules if isfile(f)]
            import importlib
            import inspect
            for x in pls:
                try:
                    m = importlib.import_module(f"db.{x}")
                    clsmembers = inspect.getmembers(m, inspect.isclass)
                    for cla in clsmembers:
                        query = getattr(cla[1], '__create_table_query__')
                        if query:
                            # _LOGGER.debug(f'Executing query {query}')
                            await self.db.execute(query)
                    await self.db.execute('PRAGMA foreign_keys = ON')
                except Exception:
                    _LOGGER.warning(traceback.format_exc())
            await self.db.commit()

    def on_bluetooth_disabled(self, inst, wasdisabled, ok):
        self.undo_enable_operations()

    def undo_enable_operations(self):
        for nm, act in self.devicemanagers_pre_actions.items():
            if nm in self.undo_info and self.undo_info[nm]:
                del self.undo_info[nm]
                preact = act()
                preact.undo(self.on_bluetooth_disabled)
                break
        self.stop_event.set()

    async def uninit_db(self):
        if self.db:
            await self.db.close()

    async def stop(self):
        self.undo_enable_operations()
        await self.stop_event.wait()
        self.oscer.uninit()
        await self.uninit_db()
        if self.android:
            self.br.stop()
        self.stop_service()

    def stop_service(self):
        if self.android:
            from jnius import autoclass
            service = autoclass('org.kivy.android.PythonService').mService
            service.stopForeground(True)
            service.stopSelf()


def main():
    p4a = os.environ.get('PYTHON_SERVICE_ARGUMENT', '')
    global _LOGGER

    if len(p4a):
        args = json.loads(p4a)
        # hostlisten
        # portlisten
        # hostconnect
        # portconnect
        # connect_retry
        # connect_secs
        # db_fname
    else:
        parser = argparse.ArgumentParser(prog=__prog__)
        parser.add_argument('--portlisten', type=int, help='port number', required=False, default=11001)
        parser.add_argument('--hostlisten', required=False, default="0.0.0.0")
        parser.add_argument('--ab_portconnect', type=int, help='port number', required=False, default=9004)
        parser.add_argument('--ab_hostconnect', required=False, default="127.0.0.1")
        parser.add_argument('--ab_portlisten', type=int, help='port number', required=False, default=9003)
        parser.add_argument('--ab_hostlisten', required=False, default="0.0.0.0")
        parser.add_argument('--connect_retry', type=int, help='connect retry', required=False, default=10)
        parser.add_argument('--connect_secs', type=int, help='connect secs', required=False, default=5)
        parser.add_argument('--db_fname', required=False, help='DB file path', default=join(dirname(__file__), '..', 'maindb.db'))
        parser.add_argument('--verbose', required=False, default="INFO")
        argall = parser.parse_known_args()
        args = dict(vars(argall[0]))
        args['undo_info'] = dict()
        import sys
        sys.argv[1:] = argall[1]
    args['android'] = len(p4a)
    _LOGGER = init_logger(__name__, get_verbosity(args['verbose']))
    _LOGGER.info(f"Server: p4a = {p4a}")
    _LOGGER.debug(f"Server: test debug {args}")
    loop = asyncio.get_event_loop()
    dms = DeviceManagerService(loop=loop, **args)
    try:
        loop.run_until_complete(dms.start())
        loop.run_forever()
    except Exception:
        _LOGGER.error(f'DMS error {traceback.format_exc()}')
    finally:
        try:
            loop.run_until_complete(dms.stop())
            _LOGGER.info("Server: Closing loop")
            loop.close()
        except Exception:
            _LOGGER.error("Server: " + traceback.format_exc())


if __name__ == '__main__':
    main()
