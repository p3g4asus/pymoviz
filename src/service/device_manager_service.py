import argparse
import asyncio
import glob
import json
import logging
import os
import traceback
from functools import partial
from os.path import basename, dirname, isfile, join, splitext

import aiosqlite
from db.device import Device
from db.label_formatter import LabelFormatter
from db.user import User
from db.view import View
from device.manager import GenericDeviceManager
from util import find_devicemanager_classes
from util.const import (COMMAND_CONFIRM, COMMAND_CONNECT, COMMAND_DELDEVICE,
                        COMMAND_DELUSER, COMMAND_DELVIEW, COMMAND_DISCONNECT,
                        COMMAND_LISTDEVICES, COMMAND_LISTDEVICES_RV,
                        COMMAND_LISTUSERS, COMMAND_LISTUSERS_RV,
                        COMMAND_LISTVIEWS, COMMAND_LISTVIEWS_RV,
                        COMMAND_NEWDEVICE, COMMAND_NEWSESSION, COMMAND_SAVEDEVICE,
                        COMMAND_SAVEUSER, COMMAND_SAVEVIEW, COMMAND_SEARCH,
                        COMMAND_STOP, CONFIRM_FAILED_1, CONFIRM_FAILED_2,
                        CONFIRM_OK, DEVREASON_BLE_DISABLED,
                        DEVREASON_PREPARE_ERROR, DEVREASON_REQUESTED,
                        DEVSTATE_CONNECTING, DEVSTATE_DISCONNECTED,
                        DEVSTATE_SEARCHING, MSG_CONNECTION_STATE_INVALID,
                        MSG_DB_SAVE_ERROR, MSG_INVALID_ITEM,
                        MSG_TYPE_DEVICE_UNKNOWN)
from util.osc_comunication import OSCManager
from util.timer import Timer

_LOGGER = logging.getLogger('PY_' + __name__)
__prog__ = "pymoviz-server"


class DeviceManagerService(object):
    def __init__(self, **kwargs):
        self.addit_params = dict()
        for key in kwargs:
            if not key.startswith('ab_'):
                setattr(self, key, kwargs[key])
            else:
                self.addit_params[key[3:]] = kwargs[key]
        self.db = None
        self.oscer = None
        self.devicemanager_class_by_type = dict()
        self.devicemanagers_by_id = dict()
        self.devicemanagers_by_uid = dict()
        self.users = []
        self.views = []
        self.devices = []
        self.devicemanagers_active = []
        self.devicemanagers_active_done = []
        self.timer_obj = None
        self.main_session = None
        self.last_user = None
        self.devicemanagers_active_info = dict()

    async def init_osc(self):
        self.oscer = OSCManager(self.hostlisten, self.portlisten, self.hostcommand, self.portcommand)
        await self.oscer.init(pingsend=True, on_init_ok=self.on_osc_init_ok)

    def on_osc_init_ok(self):
        self.oscer.handle(COMMAND_STOP, self.on_command_stop)
        self.oscer.handle(COMMAND_NEWDEVICE, self.on_command_newdevice)
        self.oscer.handle(COMMAND_CONNECT, self.on_command_condisc, 'c')
        self.oscer.handle(COMMAND_DISCONNECT, self.on_command_condisc, 'd')
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

    def on_command_condisc(self, cmd, *args):
        if cmd == 'c':
            self.last_user = args[0]
        for dm in self.devicemanagers_active_done.copy():
            self.devicemanagers_active.append(dm)
            self.devicemanagers_active_done.remove(dm)
        GenericDeviceManager.sort(self.devicemanagers_active)
        for _, info in self.devicemanagers_active_info:
            info['operation'] = cmd
            info['retry'] = 0
        Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))

    def on_command_listviews(self, *args):
        self.oscer.send(COMMAND_LISTVIEWS_RV, *self.views)

    def on_command_listusers(self, *args):
        self.oscer.send(COMMAND_LISTUSERS_RV, *self.users)

    def on_command_listdevices(self, *args):
        out = []
        for uid, dm in self.devicemanagers_by_uid.items():
            out.append(uid)
            out.append(dm.get_device())
        self.oscer.send(COMMAND_LISTDEVICES_RV, *out)

    async def on_command_delelem_async(self, elem, *args, lst=None, on_ok=None):
        rv = await elem.delete(self.db)
        if rv:
            if elem in lst:
                lst.remove(elem)
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, elem)
            if on_ok:
                on_ok(elem)
        else:
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(elem))

    async def on_command_saveelem_async(self, elem, *args, lst=None, on_ok=None):
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
            self.oscer.send_device(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_DB_SAVE_ERROR % str(elem))

    def on_command_dbelem(self, elem, *args, asyncmethod=None, lst=None, cls=None, on_ok=None):
        if isinstance(elem, cls):
            if self.devicemanagers_all_stopped():
                Timer(0, partial(asyncmethod, elem, lst=lst, on_ok=on_ok))
            else:
                self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_2, MSG_CONNECTION_STATE_INVALID)
        else:
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_FAILED_1, MSG_INVALID_ITEM)

    def on_event_command_handle(self, dm, command, *args):
        exitv = args[0] if args else None
        if command == COMMAND_NEWSESSION and exitv == CONFIRM_OK:
            if self.main_session:
                args[1].set_main_session_id(self.main_session.get_id())
            else:
                self.main_session = args[2]
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
        elif command == COMMAND_SAVEDEVICE and exitv == CONFIRM_OK:
            ids = f'{dm.get_id()}'
            if ids not in self.devicemanagers_by_id:
                self.devicemanagers_by_id[ids] = dm
        elif command == COMMAND_SEARCH and exitv == CONFIRM_OK:
            if self.devicemanagers_all_stopped():
                dm.search(dm.get_state() != DEVSTATE_SEARCHING)

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
            self.devicemanagers_by_uid[uid] = self.devicemanager_class_by_type[typev](self.oscer, uid, service=True, db=self.db)
            self.oscer.send(COMMAND_CONFIRM, CONFIRM_OK, uid)

    def on_command_stop(self, *args):
        self.loop.stop()

    def insert_notification():
        from jnius import autoclass
        fim = join(dirname(__file__), '..', 'images', 'device_manager.png')
        Context = autoclass('android.content.Context')
        Color = autoclass("android.graphics.Color")
        Intent = autoclass('android.content.Intent')
        PendingIntent = autoclass('android.app.PendingIntent')
        AndroidString = autoclass('java.lang.String')
        NotificationBuilder = autoclass('android.app.Notification$Builder')
        Notification = autoclass('android.app.Notification')
        NotificationChannel = autoclass('android.app.NotificationChannel')
        NotificationManager = autoclass('android.app.NotificationManager')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        service = autoclass('org.kivy.android.PythonService').mService

        NOTIFICATION_CHANNEL_ID = AndroidString(service.getPackageName().encode('utf-8'))
        channelName = AndroidString('DeviceManagerService'.encode('utf-8'))
        chan = NotificationChannel(NOTIFICATION_CHANNEL_ID, channelName, NotificationManager.IMPORTANCE_DEFAULT)
        chan.setLightColor(Color.BLUE)
        chan.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE)
        manager = service.getSystemService(Context.NOTIFICATION_SERVICE)
        manager.createNotificationChannel(chan)
        app_context = service.getApplication().getApplicationContext()
        notification_builder = NotificationBuilder(app_context, NOTIFICATION_CHANNEL_ID)
        title = AndroidString("Fit.py".encode('utf-8'))
        message = AndroidString("DeviceManagerService".encode('utf-8'))
        # app_class = service.getApplication().getClass()
        notification_intent = Intent(app_context, PythonActivity)
        notification_intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP |
                                     Intent.FLAG_ACTIVITY_SINGLE_TOP |
                                     Intent.FLAG_ACTIVITY_NEW_TASK)
        notification_intent.setAction(Intent.ACTION_MAIN)
        notification_intent.addCategory(Intent.CATEGORY_LAUNCHER)
        intent = PendingIntent.getActivity(service, 0, notification_intent, 0)
        notification_builder.setContentTitle(title)
        notification_builder.setContentText(message)
        notification_builder.setContentIntent(intent)
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
        bm = BitmapFactory.decodeFile(fim, options)
        notification_builder.setSmallIcon(Icon.createWithBitmap(bm))
        notification_builder.setAutoCancel(True)
        new_notification = notification_builder.getNotification()
        # Below sends the notification to the notification bar; nice but not a foreground service.
        # notification_service.notify(0, new_noti)
        service.setAutoRestartService(True)
        service.startForeground(1, new_notification)

    async def start(self):
        if self.android:
            self.insert_notification()
        self.devicemanager_class_by_type = find_devicemanager_classes(_LOGGER)
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

    async def load_db(self):
        self.users = await User.loadbyid(self.db)
        self.devices = await Device.loadbyid(self.db)
        self.views = await View.load1m(self.db, LabelFormatter, wherejoin='view')
        for d in self.devices:
            uid = self.generate_uid()
            typev = d.get_type()
            if typev in self.devicemanager_class_by_type:
                dm = self.devicemanager_class_by_type[typev](
                    self.oscer,
                    uid,
                    service=True,
                    db=self.db,
                    device=d,
                    params=self.addit_params,
                    on_command_handle=self.on_event_command_handle,
                    on_state_transition=self.on_event_state_transition)
                self.devicemanagers_by_id[f'{d.get_id()}'] = dm
                self.devicemanagers_by_uid[uid] = dm
        self.set_devicemanagers_active()

    async def start_remaining_connection_operations(self, bytimer=True):
        if bytimer:
            self.timer_obj = None
        elif self.timer_obj:
            self.timer_obj.cancel()
            self.timer_obj = None
        for dm in self.devicemanagers_active.copy():
            info = self.devicemanagers_active_info[dm.get_uid()]
            if info['operation'] == 'd':
                if not dm.is_connected_state():
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
                    dm.connect()
                    break
                else:
                    if info['retry'] < self.connect_retry:
                        self.timer_obj = Timer(self.connect_secs, self.start_remaining_connection_operations)
                        info['retry'] += 1
                        break

    def set_operation_ended(self, info):
        info['operation'] = ''
        info['retry'] = 0

    def on_event_state_transition(self, dm, oldstate, newstate, reason):
        info = self.devicemanagers_active_info[dm.get_uid()]
        if GenericDeviceManager.is_connected_state_s(newstate) and oldstate == DEVSTATE_CONNECTING:
            if dm in self.devicemanagers_active:
                self.devicemanagers_active.remove(dm)
                self.devicemanagers_active_done.append(dm)
            self.set_operation_ended(info)
            Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))
        elif oldstate == DEVSTATE_CONNECTING and newstate == DEVSTATE_DISCONNECTED:
            Timer(0, partial(self.start_remaining_connection_operations, bytimer=False))
        elif GenericDeviceManager.is_connected_state_s(oldstate) and newstate == DEVSTATE_DISCONNECTED:
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
            modules = glob.glob(join(dirname(__file__), "..", "common", "db", "*.py*"))
            pls = [splitext(basename(f))[0] for f in modules if isfile(f)]
            import importlib
            import inspect
            for x in pls:
                try:
                    m = importlib.import_module("db." + x)
                    clsmembers = inspect.getmembers(m, inspect.isclass)
                    for cla in clsmembers:
                        query = getattr(cla, '__create_table_query__')
                        if query:
                            await self.db.execute(query)
                except Exception:
                    _LOGGER.warning(traceback.format_exc())
            await self.db.commit()

    async def uninit_db(self):
        if self.db:
            await self.db.close()

    async def stop(self):
        self.oscer.uninit()
        await self.uninit_db()
        from jnius import autoclass
        service = autoclass('org.kivy.android.PythonService').mService
        service.stopForeground(True)
        service.stopSelf()


def main():
    p4a = os.environ.get('PYTHON_SERVICE_ARGUMENT', '')
    _LOGGER.info("Starting server p4a = %s" % p4a)
    if len(p4a):
        args = json.loads(p4a)
        # hostlisten
        # portlisten
        # hostcommand
        # portcommand
        # connect_retry
        # connect_secs
        # db_fname
    else:
        parser = argparse.ArgumentParser(prog=__prog__)
        parser.add_argument('--portcommand', type=int, help='port number', required=False, default=9002)
        parser.add_argument('--hostcommand', required=False, default="127.0.0.1")
        parser.add_argument('--portlisten', type=int, help='port number', required=False, default=9001)
        parser.add_argument('--hostlisten', required=False, default="0.0.0.0")
        parser.add_argument('--ab_portcommand', type=int, help='port number', required=False, default=9004)
        parser.add_argument('--ab_hostcommand', required=False, default="127.0.0.1")
        parser.add_argument('--ab_portlisten', type=int, help='port number', required=False, default=9003)
        parser.add_argument('--ab_hostlisten', required=False, default="0.0.0.0")
        parser.add_argument('--connect_retry', type=int, help='connect retry', required=False, default=10)
        parser.add_argument('--connect_secs', type=int, help='connect secs', required=False, default=5)
        parser.add_argument('--db_fname', required=False, help='DB file path', default=join(dirname(__file__), '..', 'maindb.db'))
        parser.add_argument("-v", "--verbose", help="increase output verbosity",
                            action="store_true")
        args = vars(parser.parse_args())
    args['android'] = len(p4a)
    if args["verbose"]:
        logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    dms = DeviceManagerService(loop=loop, **args)
    try:
        loop.run_until_complete(dms.start())
        loop.run_forever()
    finally:
        try:
            loop.run_until_complete(dms.stop())
            _LOGGER.debug("Server: Closing loop")
            loop.close()
        except Exception:
            _LOGGER.error("Server: " + traceback.format_exc())
