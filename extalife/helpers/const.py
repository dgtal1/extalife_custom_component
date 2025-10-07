"""Constants for the NEW_NAME integration."""

DOMAIN: str = "extalife"

# hass.data objects
DATA_CORE = "core"

CONF_CONTROLLER_IP = "controller_ip"
CONF_USERNAME = "user"
CONF_PASSWORD = "password"
CONF_POLL_INTERVAL = "poll_interval"  # in minutes
CONF_VER_INTERVAL = "version_interval"  # in hours
CONF_RECV_TIMEOUT = "recv_timeout" # in seconds
DEFAULT_POLL_INTERVAL = 5
DEFAULT_VER_INTERVAL = 12
DEFAULT_RECV_TIMEOUT = 5
CONF_BACKUP_PATH = "path"
CONF_BACKUP_SCHEDULE = "schedule"
CONF_BACKUP_RETENTION = "retention"

OPTIONS_GENERAL_POLL_INTERVAL = "poll_interval"
OPTIONS_GENERAL_VER_INTERVAL = "version_interval"

OPTIONS_GENERAL_DISABLE_NOT_RESPONDING = "disable_not_responding"

URL_OTO_LOTO_ME: str = "https://extalife.otoloto.me"
URL_CHANGELOG_HTML: str = f"{URL_OTO_LOTO_ME}/changelog/"
URL_CHANGELOG_JSON: str = f"{URL_OTO_LOTO_ME}/changelog/?json"
URL_FIRMWARE_HTML: str = f"{URL_OTO_LOTO_ME}/firmware/"

URL_IP_ECHO_NET: str = "https://ipecho.net/plain"

CONF_OPTIONS = "options"  # additional per-platform configuration
OPTIONS_GENERAL = "general"  # general settings
OPTIONS_SWITCH = "switch"  # additional switch configuration
OPTIONS_LIGHT = "light"  # additional light configuration
OPTIONS_LIGHT_ICONS_LIST = "icons_list"  # map switches as lights for these Exta Life icons
OPTIONS_COVER = "cover"  # additional cover configuration
OPTIONS_COVER_INVERTED_CONTROL = "inverted_control"

# signals
SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"
SIGNAL_CHANNEL_NOTIF_STATE_UPDATED = f"{DOMAIN}_channel_notif_state_updated"
SIGNAL_DEVICE_NOTIF_CONFIG_UPDATED = f"{DOMAIN}_device_notif_config_updated"


# transmitters
DOMAIN_TRANSMITTER = "transmitter"

# virtual sensors aren't attached to a channel, but to an entity
DOMAIN_VIRTUAL_SENSOR = "virtual_sensor"
DOMAIN_VIRTUAL_BINARY_SENSOR_SENSOR = "virtual_binary_sensor_sensor"
DOMAIN_VIRTUAL_LIGHT_SENSOR = "virtual_light_sensor"
DOMAIN_VIRTUAL_SWITCH_SENSOR = "virtual_switch_sensor"
DOMAIN_VIRTUAL_COVER_SENSOR = "virtual_cover_sensor"
DOMAIN_VIRTUAL_CLIMATE_SENSOR = "virtual_climate_sensor"
DOMAIN_VIRTUAL_SENSORS = (
    DOMAIN_VIRTUAL_SENSOR,
    DOMAIN_VIRTUAL_CLIMATE_SENSOR,
    DOMAIN_VIRTUAL_COVER_SENSOR,
    DOMAIN_VIRTUAL_LIGHT_SENSOR,
    DOMAIN_VIRTUAL_SWITCH_SENSOR,
    DOMAIN_VIRTUAL_BINARY_SENSOR_SENSOR,
)

# virtual sensor config dict attributes
VIRTUAL_SENSOR_PATH = "value_path"
VIRTUAL_SENSOR_DEV_CLS = "device_class"
VIRTUAL_SENSOR_UNIT = "unit"
VIRTUAL_SENSOR_FACTOR = "factor"
VIRTUAL_SENSOR_NAME_SUFFIX = "name_suffix"

# virtual sensor channel data field
VIRTUAL_SENSOR_CHN_FIELD = "_virtual_sensor"

# sensor restrictions
VIRTUAL_SENSOR_ALLOWED_CHANNELS = "allowed_channels"

# events and devices
CONF_EXTALIFE_EVENT_UNIQUE_ID = "unique_id"

CONF_EXTALIFE_EVENT_BASE = f"{DOMAIN}"
CONF_EXTALIFE_EVENT_TRANSMITTER = f"{CONF_EXTALIFE_EVENT_BASE}_transmitter"
CONF_EXTALIFE_EVENT_SCENE = f"{CONF_EXTALIFE_EVENT_BASE}_scene"

CONF_PROCESSOR_EVENT_STAT_NOTIFICATION = "notification"
CONF_PROCESSOR_EVENT_UNKNOWN = "unknown"

EVENT_TIMESTAMP = "timestamp"
EVENT_DATA = "event_data"

# device constants
TRIGGER_TYPE = "type"
TRIGGER_SUBTYPE = "subtype"

TRIGGER_BUTTON_UP = "button_up"
TRIGGER_BUTTON_DOWN = "button_down"
TRIGGER_BUTTON_SINGLE_CLICK = "button_single_click"
TRIGGER_BUTTON_DOUBLE_CLICK = "button_double_click"
TRIGGER_BUTTON_TRIPLE_CLICK = "button_triple_click"
TRIGGER_BUTTON_LONG_PRESS = "button_long_press"

TRIGGER_SUBTYPE_BUTTON_TEMPLATE = "button_{}"

TO_REDACT = {}
