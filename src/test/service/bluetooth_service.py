import asyncio
import json
import os
import traceback
from os.path import dirname, join

from util.bluetooth_dispatcher import BluetoothDispatcherWC
from util.const import COMMAND_STOP
from util.osc_comunication import OSCManager
from util import get_verbosity, init_logger

_LOGGER = None


class BluetoothService(object):
    def __init__(self, **kwargs):
        self.oscer = None
        self.bluetooth = None
        for key in kwargs:
            setattr(self, key, kwargs[key])

    async def init_osc(self):
        _LOGGER.debug("Initing OSC")
        self.oscer = OSCManager('127.0.0.1', self.portlistenlocal)
        await self.oscer.init(on_init_ok=self.on_osc_init_ok)

    def on_osc_init_ok(self):
        _LOGGER.debug("OSC init ok")
        try:
            self.oscer.handle(COMMAND_STOP, self.on_command_stop)
            _LOGGER.debug(f"Trying to construct BluetoothDispatcherWC: L({self.hostlisten}:{self.portlisten})")
            self.bluetooth = BluetoothDispatcherWC(
                portlisten=self.portlisten,
                hostlisten=self.hostlisten
            )
            _LOGGER.debug('Constructed BluetoothDispatcherWC')
        except Exception:
            _LOGGER.error(f"BluetoothDispatcher construct error {traceback.format_exc()}")

    def on_command_stop(self, *args):
        self.loop.stop()

    def insert_notification(self):
        from jnius import autoclass
        fim = join(dirname(__file__), '..', '..', 'images', 'bluetooth.png')
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
        channelName = AndroidString('BluetoothService'.encode('utf-8'))
        chan = NotificationChannel(NOTIFICATION_CHANNEL_ID, channelName, NotificationManager.IMPORTANCE_DEFAULT)
        chan.setLightColor(Color.BLUE)
        chan.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE)
        manager = service.getSystemService(Context.NOTIFICATION_SERVICE)
        manager.createNotificationChannel(chan)
        app_context = service.getApplication().getApplicationContext()
        notification_builder = NotificationBuilder(app_context, NOTIFICATION_CHANNEL_ID)
        title = AndroidString("Fit.py".encode('utf-8'))
        message = AndroidString("BluetoothService".encode('utf-8'))
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
        service.setAutoRestartService(False)
        service.startForeground(1, new_notification)

    async def start(self):
        _LOGGER.debug("Starting...")
        self.insert_notification()
        await self.init_osc()

    async def stop(self):
        self.oscer.uninit()
        from jnius import autoclass
        service = autoclass('org.kivy.android.PythonService').mService
        service.stopForeground(True)
        service.stopSelf()


def exception_handle(loop, context):
    if 'exception' in context and isinstance(context['exception'], asyncio.CancelledError):
        pass
    else:
        _LOGGER.error(f'Loop exception: {context["message"]} exc={context["exception"]}')


def main():
    p4a = os.environ.get('PYTHON_SERVICE_ARGUMENT', '')
    args = json.loads(p4a)
    global _LOGGER
    _LOGGER = init_logger(__name__, level=get_verbosity(args['verbose']))
    _LOGGER.info(f"Server: p4a = {p4a}")
    _LOGGER.debug(f"Server: test debug")
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(exception_handle)
    dms = BluetoothService(loop=loop, **args)
    try:
        loop.run_until_complete(dms.start())
        loop.run_forever()
    except Exception:
        _LOGGER.error("Server: E0 " + traceback.format_exc())
    finally:
        try:
            loop.run_until_complete(dms.stop())
            _LOGGER.debug("Server: Closing loop")
            loop.close()
        except Exception:
            _LOGGER.error("Server: " + traceback.format_exc())


if __name__ == '__main__':
    main()
