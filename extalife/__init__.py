"""Support for ExtaLife devices."""
import logging
from typing import Optional

import voluptuous as vol

from homeassistant.const import CONF_ACCESS_TOKEN
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import (async_dispatcher_send, async_dispatcher_connect)

from .pyextalife import ExtaLifeAPI
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)
DOMAIN = "extalife"

DATA_CONTROLLER = 'controller'
DATA_STATUS_POLLER = 'update_data'

CONF_CONTROLLER_IP = 'controller_ip'
CONF_USER = 'user'
CONF_PASSWORD = 'password'
CONF_POLL_INTERVAL = 'poll_interval'        # in minutes
DEFAULT_POLL_INTERVAL = 5

SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"
SIGNAL_NOTIF_STATE_UPDATED = f"{DOMAIN}_notif_state_updated"



CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_CONTROLLER_IP,  default=''): cv.string,
                vol.Required(CONF_USER): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): cv.positive_int
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

from .pyextalife import TCPConnError

def setup(hass, base_config):
    """Set up Exta Life component."""

    conf = base_config[DOMAIN]
    hass.data[DOMAIN] = {}
    data = hass.data[DOMAIN][DATA_STATUS_POLLER] = StatusPoller(hass, conf)

    controller_ip = conf[CONF_CONTROLLER_IP] if conf[CONF_CONTROLLER_IP] != '' else None

    # Test connection
    try:
        _LOGGER.info("ExtaLife initializing...")
        if controller_ip is not None:
            _LOGGER.debug("Trying to connect to controller using IP: %s", controller_ip)
        else:
            _LOGGER.debug("No controller IP specified. Trying autodiscovery")

        # get instance: this will already try to connect and logon
        controller = ExtaLifeAPI(conf[CONF_USER], conf[CONF_PASSWORD], host=controller_ip)

        _LOGGER.debug("Connected with controller on IP: %s", controller.host)

        sw_version = controller.get_version_info()

        if sw_version is not None:
            hass.data[DOMAIN][DATA_CONTROLLER] = controller

            _LOGGER.info("EFC-01 Software version: %s", sw_version)
        else:
            _LOGGER.error(
                "Error communicating with the EFC-01 controller. Return data %s",
                sw_version
            )
            return False
    except TCPConnError:
        _LOGGER.error(
            "Could not connect to EFC-01 on IP: %s", controller.host
        )
        return False

    # trigger data update + perform discovery via calling discover_devices callback
    data.set_discovery_callback(discover_devices)
    data.update()

    # start notification listener for immediate entity status updates from controller
    data.start_listener()

    # register callback for periodic status update polling + device discovery
    async_track_time_interval(hass, data.update, timedelta(minutes=conf[CONF_POLL_INTERVAL]))

    # register callback for periodic controller ping to keep connection alive
    async_track_time_interval(hass, data.do_ping, timedelta(seconds=10))

    _LOGGER.info("Exta Life integration setup successfully!")
    return True


def discover_devices(hass, hass_config):
    """
    Discover devices and register them in Home Assistant.
    """
    from .pyextalife import (DEVICE_ARR_ALL_SWITCH, DEVICE_ARR_ALL_LIGHT, DEVICE_ARR_ALL_COVER,
                             DEVICE_ARR_ALL_SENSOR, DEVICE_ARR_ALL_CLIMATE, DEVICE_ARR_ALL_SENSOR_MEAS, DEVICE_ARR_ALL_SENSOR_BINARY, DEVICE_ARR_ALL_SENSOR_MULTI,
                             DEVICE_ICON_ARR_LIGHT)
    component_configs = {}

    # get data from the StatusPoller object stored in HA object data
    channels = hass.data[DOMAIN][DATA_STATUS_POLLER].channels  # -> list
    initial_channels = hass.data[DOMAIN][DATA_STATUS_POLLER].initial_channels

    for channel in channels:
        chn_type = channel["data"]["type"]

        # do discovery only for newly discovered devices
        ch_id = channel.get("id")
        if initial_channels.get(ch_id):
            continue

        component_name = None
        if chn_type in DEVICE_ARR_ALL_SWITCH:
            icon = channel["data"]["icon"]
            if icon in DEVICE_ICON_ARR_LIGHT:
                component_name = 'light'
            else:
                component_name = 'switch'

        elif chn_type in DEVICE_ARR_ALL_LIGHT:
            component_name = 'light'

        elif chn_type in DEVICE_ARR_ALL_COVER:
            component_name = 'cover'

        elif chn_type in DEVICE_ARR_ALL_SENSOR_MEAS:
            component_name = 'sensor'

        elif chn_type in DEVICE_ARR_ALL_SENSOR_BINARY:
            component_name = 'binary_sensor'

        elif chn_type in DEVICE_ARR_ALL_SENSOR_MULTI:
            component_name = 'sensor'
            for value in ['value', 'value_1', 'value_2', 'value_3', 'value_4']:
                if channel["data"].get(value):
                    _channel = channel.copy()
                    _channel["monitored_value"] = value
                    component_configs.setdefault(component_name, []).append(_channel)
                    continue

        elif chn_type in DEVICE_ARR_ALL_CLIMATE:
            component_name = 'climate'

        if component_name is None:
            _LOGGER.warning(
                "Unsupported device type: %s, channel id: %s",
                chn_type,
                channel["id"],
            )
            continue

        component_configs.setdefault(component_name, []).append(channel)

    _LOGGER.debug("Exta Life devices found during discovery: %s", len(component_configs))

    # Load discovered devices
    for component_name, channel in component_configs.items():
        load_platform(hass, component_name, DOMAIN, channel, hass_config)

class StatusPoller:
    """Get the latest data from EFC-01, call device discovery, handle status notifications."""

    def __init__(self, hass, conf):
        """Initialize the data object."""
        self.data = None
        self._hass = hass
        self._conf = conf
        self._listeners = []
        self.channels = {}
        self.channels_indx = {}
        self.initial_channels = {}

        self._discovery_callback = None

        self._notif_listener = None

    @property
    def controller(self) -> ExtaLifeAPI:
        return self._hass.data[DOMAIN][DATA_CONTROLLER]

    def set_discovery_callback(self, callback):
        """ Stores callback for the discovery routine.
        The callback will require two parameters:
        - hass object
        - HA config dictionary
        """
        self._discovery_callback = callback

    # callback
    def on_notify(self, msg):
        _LOGGER.debug("Received msg from Notification Listener thread: %s", msg)
        data = msg.get("data")
        chan_id = str(data.get("id")) + '-' + str(data.get("channel"))

        # inform HA entity of state change via notification
        async_dispatcher_send(self._hass, ExtaLifeChannel.get_notif_upd_signal(chan_id), data)

    def start_listener(self):
        """ Start listener thread """
        self._notif_listener = self.controller.get_notif_listener(self.on_notify)
        self._notif_listener.start()

    def update(self, now=None):
        """Get the latest device&channel status data from EFC-01.
        This method is called from HA task scheduler via async_track_time_interval"""

        _LOGGER.debug("Executing EFC-01 status polling....")
        # use Exta Life TCP communication class

        # if connection error or other - will receive None
        # otherwise it contains a list of channels
        self.channels = self.controller.get_channels()

        #create indexed access: dict from list element
        # dict key = "data" section
        for elem in self.channels:
            chan = {elem["id"]: elem["data"]}
            self.channels_indx.update(chan)

        # propagate event only if called by HA
        if now is not None:
            async_dispatcher_send(self._hass, SIGNAL_DATA_UPDATED)

        _LOGGER.debug("Exta Life: status for %s devices updated", len(self.channels_indx))

        # call discovery callback
        if self._discovery_callback:
            self._discovery_callback(self._hass, self._conf)

        if now is None:
            # store initial channel list for subsequent discovery runs for detection of new devices
            # store only for the 1st call (by setup code, not by HA)
            self.initial_channels =  self.channels_indx.copy()


    def do_ping(self, now=None):
        """ Perform periodical ping to keep connection alive.
        Additionally perform reconnection if connection lost."""
        tcp = self.controller.get_tcp_adapter()
        tcp.ping()


class ExtaLifeChannel(Entity):
    """Base class of a ExtaLife Channel (an equivalent of HA's Entity)."""
    _cmd_in_execution = False

    def __init__(self, channel_data):
        """Channel data -- channel information from PyExtaLife."""
        # e.g. channel_data = { "id": "0-1", "data": {TCP attributes}}
        self.channel_data = channel_data.get("data")
        self.channel_id = channel_data.get("id")
        self.data_available = True


    @staticmethod
    def get_notif_upd_signal(ch_id):
        return f"{SIGNAL_NOTIF_STATE_UPDATED}_{ch_id}"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        # register data update notification dispatcher
        async_dispatcher_connect(self.hass, SIGNAL_DATA_UPDATED, self.async_update_callback)

        # register state update
        async_dispatcher_connect(self.hass, self.get_notif_upd_signal(self.channel_id), self.async_state_notif_update_callback)

    async def async_update_callback(self):
        """ Inform HA of state update from status poller"""
        _LOGGER.debug("Update callback for entty id: %s", self.entity_id)
        self.async_schedule_update_ha_state(True)

    async def async_state_notif_update_callback(self, *args):
        """ Inform HA of state change received from controller status notification """
        data = args[0]
        _LOGGER.debug("State update notification callback for entity id: %s, data: %s", self.entity_id, data)

        self.on_state_notification(data)

    def on_state_notification(self, data):
        """ must be overriden in entity subclasses """
        pass

    def get_unique_id(self):
        """ Provide unique id for HA entity registry """
        return f"extalife-{str(self.channel_data.get('serial'))}-{self.channel_id}"

    @property
    def should_poll(self):
        """
        Turn off HA polling in favour of update-when-needed status changes.
        Updates will be passed to HA by calling async_schedule_update_ha_state() for each entity
        """
        return False

    @property
    def controller(self) -> ExtaLifeAPI:
        """Return PyExtaLIfe's controller component associated with entity."""
        return self.hass.data[DOMAIN][DATA_CONTROLLER]

    @property
    def data_poller(self) -> StatusPoller:
        """Return Data poller object"""
        return self.hass.data[DOMAIN][DATA_STATUS_POLLER]

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""

        return self.get_unique_id()

    @property
    def name(self) -> Optional[str]:
        """Return the name of the device."""
        return self.channel_data["alias"]


    def action(self, action, **add_pars):
        """
        Run controller command/action.

        Actions are currently hardcoded in platforms
        """
        import time

        # wait for the previous TCP commands to finish before executing action
        # otherwise the controller may loose this command
        cnt = 0
        while ExtaLifeChannel._cmd_in_execution:
            if cnt > 30:
                break
            time.sleep(0.1)
            cnt += 1

        ExtaLifeChannel._cmd_in_execution = True

        _LOGGER.debug("Executing action %s on channel %s, params: %s", action, self.channel_id, add_pars)
        resp = self.controller.execute_action(action, self.channel_id, **add_pars)

        ExtaLifeChannel._cmd_in_execution = False
        return resp

    @property
    def available(self):
        return self.data_available

    def update(self):
        """Call to update state."""

        # data poller object contains PyExtaLife API channel data dict value pair: {("id"): ("data")}
        channel_indx = self.data_poller.channels_indx

        # read "data" section/dict by channel id
        data = channel_indx.get(self.channel_id)

        if data is None:
            self.data_available = False
            return

        self.data_available = True

        # update only if data found
        if data is not None:
            self.channel_data =  data




