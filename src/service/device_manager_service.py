import argparse
import asyncio
import glob
import json
import os
import re
import traceback
from functools import partial
from os.path import basename, dirname, exists, isfile, join, splitext
from time import time

import aiosqlite
from db.device import Device
from db.label_formatter import StateFormatter
from db.user import User
from db.view import View
from util import find_devicemanager_classes, get_verbosity, init_logger
from util.const import (COMMAND_CONFIRM, COMMAND_CONNECT, COMMAND_CONNECTORS,
                        COMMAND_DEVICEFIT, COMMAND_DELDEVICE, COMMAND_DELUSER, COMMAND_DELVIEW,
                        COMMAND_DISCONNECT, COMMAND_LISTDEVICES, COMMAND_LISTDEVICES_RV,
                        COMMAND_LISTUSERS, COMMAND_LISTUSERS_RV,
                        COMMAND_LISTVIEWS, COMMAND_LISTVIEWS_RV, COMMAND_LOGLEVEL,
                        COMMAND_NEWDEVICE, COMMAND_NEWSESSION,
                        COMMAND_PRINTMSG, COMMAND_QUERY, COMMAND_SAVEDEVICE,
                        COMMAND_SAVEUSER, COMMAND_SAVEVIEW, COMMAND_SEARCH,
                        COMMAND_STOP, CONFIRM_FAILED_1, CONFIRM_FAILED_2,
                        CONFIRM_OK, DEVREASON_BLE_DISABLED,
                        DEVREASON_PREPARE_ERROR, DEVREASON_REQUESTED,
                        DEVSTATE_CONNECTING, DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_SEARCHING, MSG_CONNECTION_STATE_INVALID,
                        MSG_DB_SAVE_ERROR, MSG_DEVICE_NOT_STOPPED, MSG_INVALID_ITEM,
                        MSG_INVALID_PARAM, MSG_INVALID_USER,
                        MSG_TYPE_DEVICE_UNKNOWN, MSG_WAITING_FOR_CONNECTING,
                        PRESENCE_REQUEST_ACTION, PRESENCE_RESPONSE_ACTION)
from util.osc_comunication import OSCManager
from util.velocity_tcp import TcpClient
from util.timer import Timer

_LOGGER = None
__prog__ = "pymoviz-server"


class DeviceNotiication(object):
    __state_formatter__ = StateFormatter(
        colmin=None,
        colmax=None,
        colerror=None,
        col=None,
        pre='',
        post='',
        timeout='---'
    )

    def __init__(self, dm, idnot, builder):
        self.dm = dm
        self.title = self.dm.get_device().get_alias()
        self.idnot = idnot
        self.dm_formatter = dm.get_notification_formatter()
        self.timer = None
        self.current_formatter = None
        self.builder = builder
        self.last_notify_ms = time() * 1000
        self.last_txt = ''

    def format(self, ** kwargs):
        nowms = time() * 1000
        notify_every_ms = self.builder.notify_every_ms
        if self.dm.is_connected_state():
            f = self.dm_formatter
            timeout = 7
        else:
            f = self.__state_formatter__
            timeout = 45
        if f is not self.current_formatter or\
                f is self.__state_formatter__ or\
                notify_every_ms == 0 or\
                nowms - self.last_notify_ms >= notify_every_ms:
            self.current_formatter = f
            self.last_notify_ms = nowms
            txt = ''
            for types, obj in kwargs.items():
                if types == f.type:
                    txt = f.format(obj)
                    if txt:
                        break
            if txt:
                if self.timer:
                    self.timer.cancel()
                self.timer = Timer(timeout, self.clear)
                self._notify(txt)

    def _notify(self, txt):
        if txt != self.last_txt:
            self.last_txt = txt
            b = self.builder
            b.set_service_notification(self.idnot, b.build_service_notification(self.title, txt, idnot=self.idnot))
            b.set_summary_notification()

    def clear(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        self._notify(self.current_formatter.set_timeout())


class DeviceManagerService(object):
    def __init__(self, **kwargs):
        self.debug_params = dict()
        self.addit_params = dict()
        for key, val in kwargs.items():
            mo = re.search('^debug_([^_]+)_(.+)', key)
            if mo:
                kk = mo.group(1)
                ll = self.debug_params.get(kk, dict())
                ll[mo.group(2)] = val
                self.debug_params[kk] = ll
            elif key.startswith('ab_'):
                self.addit_params[key[3:]] = val
            else:
                setattr(self, key, val)
        _LOGGER.debug(f'Addit params for DM {self.addit_params} AND {self.debug_params}')
        self.db = None
        self.oscer = None
        self.notification_formatter_info = dict()
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
        self.last_notify_ms = time() * 1000
        if self.android:
            from jnius import autoclass
            from android.broadcast import BroadcastReceiver
            self.Context = autoclass('android.content.Context')
            self.AndroidString = autoclass('java.lang.String')
            self.NotificationCompatInboxStyle = autoclass('android.app.Notification$InboxStyle')
            NotificationBuilder = autoclass('android.app.Notification$Builder')
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.service = autoclass('org.kivy.android.PythonService').mService
            NOTIFICATION_CHANNEL_ID = self.AndroidString(self.service.getPackageName().encode('utf-8'))
            self.NOTIFICATION_GROUP = 'pyMovizGroup'
            self.FOREGROUND_NOTIFICATION_ID = 4563
            app_context = self.service.getApplication().getApplicationContext()
            self.app_context = app_context
            self.notification_service = self.service.getSystemService(self.Context.NOTIFICATION_SERVICE)
            self.CONNECT_ACTION = 'device_manager_service.view.CONNECT'
            self.DISCONNECT_ACTION = 'device_manager_service.view.DISCONNECT'
            self.STOP_ACTION = 'device_manager_service.STOP'

            self.br = BroadcastReceiver(
                self.on_broadcast, actions=[self.CONNECT_ACTION,
                                            PRESENCE_REQUEST_ACTION,
                                            self.DISCONNECT_ACTION,
                                            self.STOP_ACTION])
            self.br.start()

            Intent = autoclass('android.content.Intent')
            self.Intent = Intent
            PendingIntent = autoclass('android.app.PendingIntent')
            NotificationActionBuilder = autoclass('android.app.Notification$Action$Builder')
            Notification = autoclass('android.app.Notification')
            Color = autoclass("android.graphics.Color")
            NotificationChannel = autoclass('android.app.NotificationChannel')
            NotificationManager = autoclass('android.app.NotificationManager')
            channelName = self.AndroidString('DeviceManagerService'.encode('utf-8'))
            chan = NotificationChannel(NOTIFICATION_CHANNEL_ID, channelName, NotificationManager.IMPORTANCE_DEFAULT)
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
            notification_icon = Icon.createWithBitmap(bm)

            notification_image = join(dirname(__file__), '..', 'images', 'lan-connect.png')
            bm = BitmapFactory.decodeFile(notification_image, options)
            icon = Icon.createWithBitmap(bm)
            broadcastIntent = Intent(self.CONNECT_ACTION)
            actionIntent = PendingIntent.getBroadcast(self.service,
                                                      0,
                                                      broadcastIntent,
                                                      PendingIntent.FLAG_UPDATE_CURRENT)
            connect_action = NotificationActionBuilder(
                icon,
                self.AndroidString('CONNECT'.encode('utf-8')),
                actionIntent).build()

            notification_image = join(dirname(__file__), '..', 'images', 'lan-disconnect.png')
            bm = BitmapFactory.decodeFile(notification_image, options)
            icon = Icon.createWithBitmap(bm)
            broadcastIntent = Intent(self.DISCONNECT_ACTION)
            actionIntent = PendingIntent.getBroadcast(self.service,
                                                      0,
                                                      broadcastIntent,
                                                      PendingIntent.FLAG_UPDATE_CURRENT)
            disconnect_action = NotificationActionBuilder(
                icon,
                self.AndroidString('DISCONNECT'.encode('utf-8')),
                actionIntent).build()

            notification_image = join(dirname(__file__), '..', 'images', 'stop.png')
            bm = BitmapFactory.decodeFile(notification_image, options)
            icon = Icon.createWithBitmap(bm)
            broadcastIntent = Intent(self.STOP_ACTION)
            actionIntent = PendingIntent.getBroadcast(self.service,
                                                      0,
                                                      broadcastIntent,
                                                      PendingIntent.FLAG_UPDATE_CURRENT)
            stop_action = NotificationActionBuilder(
                icon,
                self.AndroidString('STOP'.encode('utf-8')),
                actionIntent).build()

            notification_intent = Intent(app_context, self.PythonActivity)
            notification_intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP |
                                         Intent.FLAG_ACTIVITY_SINGLE_TOP |
                                         Intent.FLAG_ACTIVITY_NEW_TASK)
            notification_intent.setAction(Intent.ACTION_MAIN)
            notification_intent.addCategory(Intent.CATEGORY_LAUNCHER)
            notification_intent = PendingIntent.getActivity(self.service, 0, notification_intent, 0)
            self.notification_builder = NotificationBuilder(app_context, NOTIFICATION_CHANNEL_ID)\
                .setContentIntent(notification_intent)\
                .setSmallIcon(notification_icon)\
                .addAction(connect_action)\
                .addAction(disconnect_action)\
                .addAction(stop_action)
            self.notification_builder_no_action = NotificationBuilder(app_context, NOTIFICATION_CHANNEL_ID)\
                .setContentIntent(notification_intent)\
                .setSmallIcon(notification_icon)

    def on_broadcast(self, context, intent):
        action = intent.getAction()
        _LOGGER.info(f'on_broadcast action {action}')
        if action == self.CONNECT_ACTION:
            self.loop.call_soon_threadsafe(self.on_command_condisc, 'c', self.last_user)
        elif action == self.DISCONNECT_ACTION:
            self.loop.call_soon_threadsafe(self.on_command_condisc, 'd')
        elif action == PRESENCE_REQUEST_ACTION:
            self.app_context.sendBroadcast(self.Intent(PRESENCE_RESPONSE_ACTION))
        else:
            self.loop.call_soon_threadsafe(self.on_command_stop)

    def change_service_notification(self, dm, **kwargs):
        if self.android:
            alias = dm.get_device().get_alias()
            if alias not in self.notification_formatter_info:
                idnot = self.FOREGROUND_NOTIFICATION_ID + len(self.notification_formatter_info)
                self.notification_formatter_info[alias] =\
                    DeviceNotiication(dm,
                                      idnot,
                                      self)
            self.notification_formatter_info[alias].format(**kwargs)

    async def init_osc(self):
        self.oscer = OSCManager(hostlisten=self.hostlisten, portlisten=self.portlisten)
        await self.oscer.init(on_init_ok=self.on_osc_init_ok)

    def on_osc_init_ok(self, exception=None):
        if not exception:
            self.oscer.handle(COMMAND_STOP, self.on_command_stop)
            self.oscer.handle(COMMAND_LOGLEVEL, self.on_command_loglevel)
            self.oscer.handle(COMMAND_NEWDEVICE, self.on_command_newdevice)
            self.oscer.handle(COMMAND_QUERY, self.on_command_query, do_split=True)
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

    def on_command_condisc(self, cmd, *args, sender=None, **kwargs):
        _LOGGER.info(f'On Command condisc: {cmd}')
        if cmd == 'c':
            if args and isinstance(args[0], User) and args[0] in self.users:
                self.last_user = args[0]
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_INVALID_USER, dest=sender)
                return
        self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, cmd, dest=sender)
        for dm in self.devicemanagers_active_done.copy():
            self.devicemanagers_active.append(dm)
            self.devicemanagers_active_done.remove(dm)
        from device.manager import GenericDeviceManager
        GenericDeviceManager.sort(self.devicemanagers_active)
        for _, info in self.devicemanagers_active_info.items():
            info['operation'] = cmd
            info['retry'] = 0
        Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))

    def on_command_listviews(self, *args, sender=None, **kwargs):
        _LOGGER.info('List view before send:')
        for v in self.views:
            _LOGGER.info(f'View = {v}')
        self.oscer.send(COMMAND_LISTVIEWS_RV, *self.views, dest=sender)

    def on_command_listusers(self, *args, sender=None, **kwargs):
        self.oscer.send(COMMAND_LISTUSERS_RV, *self.users, dest=sender)

    def on_command_connectors(self, connectors_info, *args, sender=None, **kwargs):
        connectors_info = json.loads(connectors_info)
        if connectors_info:
            for ci in connectors_info:
                if not exists(ci['temp']):
                    self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, dest=sender)
                    return
            self.connectors_format = True
            Timer(0, partial(TcpClient.init_connectors_async, self.loop, connectors_info))
        self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, dest=sender)

    def on_command_listdevices(self, *args, sender=None, **kwargs):
        out = []
        for uid, dm in self.devicemanagers_by_uid.items():
            out.append(uid)
            out.append(dm.get_device())
        self.oscer.send(COMMAND_LISTDEVICES_RV, *out, dest=sender)

    async def on_command_delelem_async(self, elem, *args, lst=None, on_ok=None, sender=None, **kwargs):
        try:
            _LOGGER.info(f'on_command_delelem_async {elem}')
            rv = await elem.delete(self.db)
            if rv:
                if elem in lst:
                    lst.remove(elem)
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, elem, dest=sender)
                if on_ok:
                    on_ok(elem)
                TcpClient.reset_templates()
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(elem), dest=sender)
        except Exception:
            _LOGGER.error(f'on_command_delelem_async exception {traceback.format_exc()}')

    async def on_command_saveelem_async(self, elem, *args, lst=None, on_ok=None, sender=None, **kwargs):
        try:
            _LOGGER.info(f'on_command_saveelem_async {elem}')
            rv = await elem.to_db(self.db)
            if rv:
                if elem not in lst:
                    lst.append(elem)
                else:
                    lst[lst.index(elem)] = elem
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, elem, dest=sender)
                if on_ok:
                    on_ok(elem)
                TcpClient.reset_templates()
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(elem), dest=sender)
        except Exception:
            _LOGGER.error(f'on_command_saveelem_async exception {traceback.format_exc()}')

    def on_command_dbelem(self, elem, *args, asyncmethod=None, lst=None, cls=None, on_ok=None, sender=None, **kwargs):
        _LOGGER.info(f'on_command_dbelem {elem}')
        if isinstance(elem, cls):
            if self.devicemanagers_all_stopped():
                Timer(0, partial(asyncmethod, elem, lst=lst, on_ok=on_ok))
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID, dest=sender)
        else:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_INVALID_ITEM, dest=sender)

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
                TcpClient.format(args[1], fitobj=args[2], manager=dm, device=args[1])
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
            TcpClient.reset_templates()
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

    def on_command_newdevice(self, typev, *args, sender=None, **kwargs):
        if typev not in self.devicemanager_class_by_type:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_TYPE_DEVICE_UNKNOWN, dest=sender)
        elif not self.devicemanagers_all_stopped():
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_CONNECTION_STATE_INVALID, dest=sender)
        else:
            uid = self.generate_uid()
            self.devicemanagers_by_uid[uid] = self.devicemanager_class_by_type[typev](
                self.oscer,
                uid,
                service=True,
                db=self.db,
                loop=self.loop,
                params=self.addit_params,
                debug_params=self.debug_params.get(typev, dict()),
                on_command_handle=self.on_event_command_handle,
                on_state_transition=self.on_event_state_transition)
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, uid, dest=sender)

    async def db_query_single(self, txt):
        result = dict(error='', rows=[], cols=[], rowcount=0, changes=0, lastrowid=-1)
        try:
            async with self.db.cursor() as cursor:
                result['changes_before'] = self.db.total_changes
                await cursor.execute(txt)
                lst = result['rows']
                result['rowcount'] = cursor.rowcount
                result['lastrowid'] = cursor.lastrowid
                result['changes_after'] = self.db.total_changes
                async for row in cursor:
                    if not result['cols']:
                        result['cols'] = list(row.keys())
                    item = ''
                    for r in result['cols']:
                        item += f'\t{row[r]}'
                    lst.append(item.strip())
            await self.db.commit()
        except Exception as ex:
            result['error'] = str(ex)
            _LOGGER.error(f'Query Error {traceback.format_exc()}')
        _LOGGER.info(f'Query {txt} result obtained')
        _LOGGER.debug(f'Query result {result}')
        return result

    async def db_query(self, txt, sender=None):
        queries = re.split(r';[\r\n]*', txt)
        results = []
        for q in queries:
            q = q.strip()
            if q:
                r = await self.db_query_single(q)
                results.append(r)
        self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, results, do_split=True, dest=sender)

    def on_command_query(self, txt, *args, sender=None, **kwargs):
        _LOGGER.debug(f'on_command_query {txt}')
        if not self.db:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % self.db_fname, do_split=True, dest=sender)
        elif not txt:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_2, MSG_INVALID_PARAM, do_split=True, dest=sender)
        elif self.devicemanagers_all_stopped():
            Timer(0, partial(self.db_query, txt, sender=None))
        else:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID, do_split=True, dest=sender)

    def on_command_loglevel(self, level, notify_screen_on, notify_every_ms, *args, sender=None, **kwargs):
        init_logger(__name__, level)
        self.verbose = level
        if notify_screen_on >= 0:
            self.notify_screen_on = notify_screen_on
        if notify_every_ms >= 0:
            self.notify_every_ms = notify_every_ms

    def on_command_stop(self, *args, sender=None, **kwargs):
        self.loop.stop()

    def reset_service_notifications(self):
        for _, no in self.notification_formatter_info.items():
            no.clear()
            self.cancel_service_notification(no.idnot)
        if len(self.notification_formatter_info) > 1:
            self.cancel_service_notification(self.FOREGROUND_NOTIFICATION_ID - 1)
        self.notification_formatter_info.clear()

    def cancel_service_notification(self, idnot):
        if idnot == self.FOREGROUND_NOTIFICATION_ID:
            self.set_service_notification(idnot, self.build_service_notification())
        else:
            self.notification_service.cancel(idnot)

    def set_service_notification(self, idnot, notif):
        self.notification_service.notify(idnot, notif)

    def set_summary_notification(self):
        if len(self.notification_formatter_info) > 1:
            summary = ''
            lines = []
            message = f'{len(self.notification_formatter_info)} active devices'
            for t, no in self.notification_formatter_info.items():
                if no.last_txt:
                    lines.append(no.last_txt)
                summary += f' {no.title}'
            if summary and len(lines) > 1:
                summary = summary[1:]
                self.set_service_notification(
                    self.FOREGROUND_NOTIFICATION_ID - 1,
                    self.build_service_notification(summary, message, lines))

    def build_service_notification(self, title=None, message=None, lines=None, idnot=0):
        group = None
        nb = self.notification_builder
        if not title and not message:
            title = "Fit.py"
            message = "DeviceManagerService"
        elif len(self.notification_formatter_info) > 1:
            nb = self.notification_builder if idnot == self.FOREGROUND_NOTIFICATION_ID else self.notification_builder_no_action
            group = self.NOTIFICATION_GROUP
        title = self.AndroidString((title if title else 'N/A').encode('utf-8'))
        message = self.AndroidString(message.encode('utf-8'))
        nb.setContentTitle(title)\
            .setGroup(group)\
            .setContentText(message)\
            .setOnlyAlertOnce(self.notify_screen_on <= 0)
        if lines is not None:
            style = self.NotificationCompatInboxStyle()\
                .setSummaryText(title)\
                .setBigContentTitle(message)
            for l in lines:
                style.addLine(self.AndroidString(l.encode('utf-8')))
            nb.setStyle(style)\
                .setGroupSummary(True)
        else:
            nb.setStyle(None)\
                .setGroupSummary(False)
        return nb.getNotification()

    def insert_service_notification(self):
        self.service.setAutoRestartService(False)
        self.service.startForeground(self.FOREGROUND_NOTIFICATION_ID, self.build_service_notification())

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
        self.reset_service_notifications()
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
                    debug_params=self.debug_params.get(typev, dict()),
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
                        self.oscer.send(COMMAND_PRINTMSG, MSG_WAITING_FOR_CONNECTING.format(dm.get_device().get_alias()))
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
                if info['operation'] == 'c':
                    if dm in self.devicemanagers_active:
                        self.devicemanagers_active.remove(dm)
                        self.devicemanagers_active_done.append(dm)
                    self.set_operation_ended(info)
                Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))
            elif oldstate == DEVSTATE_CONNECTING and newstate == DEVSTATE_DISCONNECTED:
                if reason == DEVREASON_PREPARE_ERROR or reason == DEVREASON_BLE_DISABLED:
                    for dm in self.devicemanagers_active:
                        info = self.devicemanagers_active_info[dm.get_uid()]
                        self.set_operation_ended(info)
                        if dm not in self.devicemanagers_active_done:
                            self.devicemanagers_active_done.append(dm)
                    del self.devicemanagers_active[:]
                else:
                    Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))
            elif (GenericDeviceManager.is_connected_state_s(oldstate) or
                  oldstate == DEVSTATE_DISCONNECTING) and newstate == DEVSTATE_DISCONNECTED:
                oper = 'c' if info['operation'] != 'd' else 'd'
                if reason != DEVREASON_REQUESTED:
                    info['operation'] = oper
                    if dm in self.devicemanagers_active_done:
                        self.devicemanagers_active_done.remove(dm)
                    if dm not in self.devicemanagers_active:
                        self.devicemanagers_active.append(dm)
                        GenericDeviceManager.sort(self.devicemanagers_active)
                else:
                    self.set_operation_ended(info)
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
                            cla[1].set_update_columns()
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
                preact = act(self.loop)
                preact.undo(self.on_bluetooth_disabled)
                break
        self.stop_event.set()

    async def uninit_db(self):
        if self.db:
            await self.db.commit()
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
            self.reset_service_notifications()
            self.service.stopForeground(True)
            self.service.stopSelf()


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
        args['notify_screen_on'] = -1
        args['notify_every_ms'] = -1
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
