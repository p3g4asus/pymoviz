DEVSTATE_DISCONNECTED = 0
DEVSTATE_DISCONNECTING = 2
DEVSTATE_CONNECTING = 5
DEVSTATE_CONNECTED = 1
DEVSTATE_ONLINE = 3
DEVSTATE_DPAUSE = 4
DEVSTATE_UNINIT = 6
DEVSTATE_SEARCHING = 7
DEVSTATE_INVALIDSTEP = 8
DEVSTATE_IDLE = 9

DEVREASON_REQUESTED = 20
DEVREASON_STATECHANGE = 21
DEVREASON_SIMULATOR = 22
DEVREASON_PREPARE_ERROR = 23
DEVREASON_OPERATION_ERROR = 24
DEVREASON_TIMEOUT = 25
DEVREASON_BLE_DISABLED = 26


MSG_CONNECTION_STATE_INVALID = 'Please disconnect all devices before'
MSG_DEVICE_NOT_STOPPED = 'Device {} state not stopped'
MSG_WAITING_FOR_CONNECTING = 'Device {} will be disconnected at the end of "connecting"'
MSG_TYPE_DEVICE_UNKNOWN = 'Unknown device type'
MSG_INVALID_VIEW = 'Invalid view'
MSG_INVALID_USER = 'Invalid user'
MSG_INVALID_ITEM = 'Invalid DB item'
MSG_INVALID_PARAM = 'Invalid parameter'
MSG_DB_SAVE_ERROR = 'Cannot save to database %s'
MSG_COMMAND_TIMEOUT = 'Timeout waiting for command response'
MSG_OK = 'OK'
MSG_ERROR = 'Generic error'
CONFIRM_OK = 0
CONFIRM_FAILED_1 = -1
CONFIRM_FAILED_2 = -2
CONFIRM_FAILED_3 = -10

DI_FIRMWARE = 'info_firmware'
DI_BLNAME = 'info_blname'
DI_SOFTWARE = 'info_software'
DI_SYSTEMID = 'info_systemid'
DI_BATTERY = 'info_battery'
DI_MODEL = 'info_model'
DI_MANUFACTURER = 'info_manufacturer'
DI_HARDWARE = 'info_hardware'
DI_SERIAL_NUMBER = 'info_serial'

PRESENCE_REQUEST_ACTION = 'device_manager_service.view.PRESENCE_REQUEST'
PRESENCE_RESPONSE_ACTION = 'device_manager_service.view.PRESENCE_RESPONSE'

COMMAND_SEARCH = '/device_search'
COMMAND_DEVICEFOUND = '/device_found'
COMMAND_CONNECT = '/view_connect'
COMMAND_CONNECTORS = '/serve_connectors'
COMMAND_DISCONNECT = '/view_disconnect'
COMMAND_STOPSEARCH = '/device_stopsearch'
COMMAND_SAVEDEVICE = '/device_save'
COMMAND_DELDEVICE = '/device_del'
COMMAND_NEWSESSION = '/device_session'
COMMAND_REQUESTSESSION = '/device_requestsession'
COMMAND_DEVICESTATE = '/device_state'
COMMAND_DEVICEFIT = '/device_fit'
COMMAND_NEWDEVICE = '/newdevice'
COMMAND_STOP = '/stop'
COMMAND_CONNECTION = '/connection'
COMMAND_CONFIRM = '/confirm'
COMMAND_LISTDEVICES = '/listdevices'
COMMAND_LISTDEVICES_RV = '/listdevices_rv'
COMMAND_LISTUSERS = '/listusers'
COMMAND_LISTUSERS_RV = '/listusers_rv'
COMMAND_LISTVIEWS = '/listviews'
COMMAND_LISTVIEWS_RV = '/listviews_rv'
COMMAND_SAVEVIEW = '/saveview'
COMMAND_DELVIEW = '/delview'
COMMAND_SAVEUSER = '/saveuser'
COMMAND_DELUSER = '/deluser'
COMMAND_PRINTMSG = '/printmsg'
COMMAND_LOGLEVEL = '/loglevel'
COMMAND_QUERY = '/query'
COMMAND_SPLIT = '/split'

COMMAND_WBD_CHARACTERISTICCHANGED = '/wbd_characteristic_changed'
COMMAND_WBD_CHARACTERISTICREAD = '/wbd_characteristic_read'
COMMAND_WBD_CHARACTERISTICWRITTEN = '/wbd_characteristic_written'
COMMAND_WBD_CONNECTGATT = '/wbd_connectgatt'
COMMAND_WBD_CONNECTSTATECHANGE = '/wbd_connectstatechange'
COMMAND_WBD_DESCRIPTORREAD = '/wbd_descriptorread'
COMMAND_WBD_DESCRIPTORWRITTEN = '/wbd_descriptorwritten'
COMMAND_WBD_DEVICEFOUND = '/wbd_devicefound'
COMMAND_WBD_DISCONNECTGATT = '/wbd_disconnectgatt'
COMMAND_WBD_DISCOVERSERVICES = '/wbd_discoverservices'
COMMAND_WBD_ENABLENOT = '/wbd_enablenot'
COMMAND_WBD_GATTRELEASE = '/wbd_gattrelease'
COMMAND_WBD_READCHARACTERISTIC = '/wbd_readcharacteristic'
COMMAND_WBD_SERVICES = '/wbd_services'
COMMAND_WBD_STARTSCAN = '/wbd_startscan'
COMMAND_WBD_STOPSCAN = '/wbd_stopscan'
COMMAND_WBD_STOPSCAN_RV = '/wbd_stopscan_rv'
COMMAND_WBD_WRITECHARACTERISTIC = '/wbd_writecharacteristic'
COMMAND_WBD_WRITEDESCRIPTOR = '/wbd_writedescriptor'


class GattUtils:
    FIRST_BITMASK = 0x01
    SECOND_BITMASK = FIRST_BITMASK << 1
    THIRD_BITMASK = FIRST_BITMASK << 2
    FOURTH_BITMASK = FIRST_BITMASK << 3
    FIFTH_BITMASK = FIRST_BITMASK << 4
    SIXTH_BITMASK = FIRST_BITMASK << 5
    SEVENTH_BITMASK = FIRST_BITMASK << 6
    EIGTH_BITMASK = FIRST_BITMASK << 7


class BluetoothGattService:
    ALERT_NOTIFICATION_SERVICE = 0x1811
    BATTERY_SERVICE = 0x180F
    BLOOD_PRESSURE = 0x1810
    CURRENT_TIME_SERVICE = 0x1805
    CYCLING_POWER = 0x1818
    CYCLING_SPEED_AND_CADENCE = 0x1816
    DEVICE_INFORMATION = 0x180A
    GENERIC_ACCESS = 0x1800
    GENERIC_ATTRIBUTE = 0x1801
    GLUCOSE = 0x1808
    HEALTH_THERMOMETER = 0x1809
    HEART_RATE = 0x180D
    HUMAN_INTERFACE_DEVICE = 0x1812
    IMMEDIATE_ALERT = 0x1802
    LINK_LOSS = 0x1803
    LOCATION_AND_NAVIGATION = 0x1819
    NEXT_DST_CHANGE_SERVICE = 0x1807
    PHONE_ALERT_STATUS_SERVICE = 0x180E
    REFERENCE_TIME_UPDATE_SERVICE = 0x1806
    RUNNING_SPEED_AND_CADENCE = 0x1814
    SCAN_PARAMETERS = 0x1813
    TX_POWER = 0x1804
    AUTOMATION_IO = 0x1815
    BATTERY_S_1_1 = 0x180F
    IMMEDIATE_ALERT_S_1_1 = 0x1802
    LINK_LOSS_S_1_1 = 0x1803
    NETWORK_AVAILABILITY_SERVICE = 0x180B
    TX_POWER_S_1_1 = 0x1804


class BluetoothGattCharacteristic:
    ALERT_CATEGORY_ID = 0x2A43
    ALERT_CATEGORY_ID_BIT_MASK = 0x2A42
    ALERT_LEVEL = 0x2A06
    ALERT_NOTIFICATION_CONTROL_POINT = 0x2A44
    ALERT_STATUS = 0x2A3F
    APPEARANCE = 0x2A01
    BATTERY_LEVEL = 0x2A19
    BLOOD_PRESSURE_FEATURE = 0x2A49
    BLOOD_PRESSURE_MEASUREMENT = 0x2A35
    BODY_SENSOR_LOCATION = 0x2A38
    BOOT_KEYOBARD_INPUT_REPORT = 0x2A22
    BOOT_KEYOBARD_OUTPUT_REPORT = 0x2A32
    BOOT_MOUSE_INPUT_REPORT = 0x2A33
    CSC_FEATURE = 0x2A5C
    CSC_MEASUREMENT = 0x2A5B
    CURRENT_TIME = 0x2A2B
    CYCLING_POWER_CONTROL_POINT = 0x2A66
    CYCLING_POWER_FEATURE = 0x2A65
    CYCLING_POWER_MEASUREMENT = 0x2A63
    CYCLING_POWER_VECTOR = 0x2A64
    DATE_TIME = 0x2A08
    DAY_DATE_TIME = 0x2A0A
    DAY_OF_WEEK = 0x2A09
    DEVICE_NAME = 0x2A00
    DST_OFFSET = 0x2A0D
    EXACT_TIME_256 = 0x2A0C
    FIRMWARE_REVISION_STRING = 0x2A26
    GLUCOSE_FEATURE = 0x2A51
    GLUCOSE_MEASUREMENT = 0x2A18
    GLUCOSE_MEASUREMENT_CONTROL = 0x2A34
    HARDWARE_REVISION_STRING = 0x2A27
    HEART_RATE_CONTROL_POINT = 0x2A39
    HEART_RATE_MEASUREMENT = 0x2A37
    HID_CONTROL_POINT = 0x2A4C
    HID_INFORMATION = 0x2A4A
    IEEE11073_20601_REGULATORY_CERTIFICATION_DATA_LIST = 0x2A2A
    INTERMEDIATE_CUFF_PRESSURE = 0x2A36
    INTERMEDIATE_TEMPERATURE = 0x2A1E
    LN_CONTROL_POINT = 0x2A6B
    LN_FEATURE = 0x2A6A
    LOCAL_TIME_INFORMATION = 0x2A0F
    LOCATION_AND_SPEED = 0x2A67
    MANUFACTURER_NAME_STRING = 0x2A29
    MEASUREMENT_INTERVAL = 0x2A21
    MODEL_NUMBER_STRING = 0x2A24
    NAVIGATION = 0x2A68
    NEW_ALERT = 0x2A46
    PERIPERAL_PREFFERED_CONNECTION_PARAMETERS = 0x2A04
    PERIPHERAL_PRIVACY_FLAG = 0x2A02
    PN_PID = 0x2A50
    POSITION_QUALITY = 0x2A69
    PROTOCOL_MODE = 0x2A4E
    RECONNECTION_ADDRESS = 0x2A03
    RECORD_ACCESS_CONTROL_POINT = 0x2A52
    REFERENCE_TIME_INFORMATION = 0x2A14
    REPORT = 0x2A4D
    REPORT_MAP = 0x2A4B
    RINGER_CONTROL_POINT = 0x2A40
    RINGER_SETTING = 0x2A41
    RSC_FEATURE = 0x2A54
    RSC_MEASUREMENT = 0x2A53
    SC_CONTROL_POINT = 0x2A55
    SCAN_INTERVAL_WINDOW = 0x2A4F
    SCAN_REFRESH = 0x2A31
    SENSOR_LOCATION = 0x2A5D
    SERIAL_NUMBER_STRING = 0x2A25
    SERVICE_CHANGED = 0x2A05
    SOFTWARE_REVISION_STRING = 0x2A28
    SUPPORTED_NEW_ALERT_CATEGORY = 0x2A47
    SUPPORTED_UNREAD_ALERT_CATEGORY = 0x2A48
    SYSTEM_ID = 0x2A23
    TEMPERATURE_MEASUREMENT = 0x2A1C
    TEMPERATURE_TYPE = 0x2A1D
    TIME_ACCURACY = 0x2A12
    TIME_SOURCE = 0x2A13
    TIME_UPDATE_CONTROL_POINT = 0x2A16
    TIME_UPDATE_STATE = 0x2A17
    TIME_WITH_DST = 0x2A11
    TIME_ZONE = 0x2A0E
    TX_POWER_LEVEL = 0x2A07
    UNREAD_ALERT_STATUS = 0x2A45
    AGGREGATE_INPUT = 0x2A5A
    ANALOG_INPUT = 0x2A58
    ANALOG_OUTPUT = 0x2A59
    DIGITAL_INPUT = 0x2A56
    DIGITAL_OUTPUT = 0x2A57
    EXACT_TIME_100 = 0x2A0B
    NETWORK_AVAILABILITY = 0x2A3E
    SCIENTIFIC_TEMPERATURE_IN_CELSIUS = 0x2A3C
    SECONDARY_TIME_ZONE = 0x2A10
    STRING = 0x2A3D
    TEMPERATURE_IN_CELSIUS = 0x2A1F
    TEMPERATURE_IN_FAHRENHEIT = 0x2A20
    TIME_BROADCAST = 0x2A15
    BATTERY_LEVEL_STATE = 0x2A1B
    BATTERY_POWER_STATE = 0x2A1A
    PULSE_OXIMETRY_CONTINUOUS_MEASUREMENT = 0x2A5F
    PULSE_OXIMETRY_CONTROL_POINT = 0x2A62
    PULSE_OXIMETRY_FEATURES = 0x2A61
    PULSE_OXIMETRY_PULSATILE_EVENT = 0x2A60
    PULSE_OXIMETRY_SPOT_CHECK_MEASUREMENT = 0x2A5E
    RECORD_ACCESS_CONTROL_POINT_TESTVERSION = 0x2A52
    REMOVABLE = 0x2A3A
    SERVICE_REQUIRED = 0x2A3B
