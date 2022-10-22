"""Constants for the NEW_NAME integration."""

DOMAIN = "extalife"

# hass.data objects
DATA_CORE = "core"

CONF_CONTROLLER_IP = "controller_ip"
CONF_USER = "user"
CONF_PASSWORD = "password"
CONF_POLL_INTERVAL = "poll_interval"  # in minutes
DEFAULT_POLL_INTERVAL = 5

OPTIONS_GENERAL_POLL_INTERVAL = "poll_interval"
OPTIONS_GENERAL_DISABLE_NOT_RESPONDING = "disable_not_responding"
OPTIONS_LIGHT_ICONS_LIST = "icons_list"
OPTIONS_COVER_INVERTED_CONTROL = "inverted_control"

CONF_OPTIONS = "options"  # additional per-platform configuration
OPTIONS_GENERAL = "general"  # general settings
OPTIONS_SWITCH = "switch"  # additional switch configuration
OPTIONS_LIGHT = "light"  # additional light configuration
OPTIONS_LIGHT_ICONS_LIST = (
    "icons_list"  # map switches as lights for these Exta Life icons
)
OPTIONS_COVER = "cover"  # additional cover configuration
OPTIONS_COVER_INV_CONTROL = "inverted_control"

# signals
SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"
SIGNAL_NOTIF_STATE_UPDATED = f"{DOMAIN}_notif_state_updated"


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
VIRT_SENSOR_PATH = "value_path"
VIRT_SENSOR_DEV_CLS = "device_class"
VIRT_SENSOR_UNIT = "unit"
VIRT_SENSOR_FACTOR = "factor"
VIRT_SENSOR_NAME_SUFFIX = "name_suffix"

# virtual sensor channel data field
VIRT_SENSOR_CHN_FIELD = "_virtual_sensor"

# sensor restrictions
VIRT_SENSOR_ALLOWED_CHANNELS = "allowed_channels"

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
