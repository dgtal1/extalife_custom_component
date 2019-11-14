"""Support for Exta Life sensor devices"""
import logging
from pprint import pformat

# from homeassistant.components.extalife import ExtaLifeChannel
from . import ExtaLifeChannel

from homeassistant.const import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_ILLUMINANCE,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)

from .pyextalife import (
    DEVICE_ARR_SENS_TEMP,
    DEVICE_ARR_SENS_LIGHT,
    DEVICE_ARR_SENS_HUMID,
)

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up ExtaLife switches."""
    if discovery_info is None:
        return

    _LOGGER.debug("Discovery: %s", pformat(discovery_info))

    add_entities([ExtaLifeSensor(device) for device in discovery_info])


class ExtaLifeSensor(ExtaLifeChannel):
    """Representation of Exta Life Sensors"""

    def __init__(self, channel_data):
        super().__init__(channel_data)
        self.channel_data = channel_data.get("data")

        data = self.channel_data
        dev_type = data.get("type")
        self._unit = ""
        self._dev_class = None

        # monitor only 1 magnitude of a multisensor
        self._monitored_value = channel_data.get("monitored_value")

        if dev_type in DEVICE_ARR_SENS_TEMP:
            self._dev_class = DEVICE_CLASS_TEMPERATURE
            self._unit = TEMP_CELSIUS

        if dev_type in DEVICE_ARR_SENS_HUMID:
            self._dev_class = DEVICE_CLASS_HUMIDITY
            self._unit = "%"

        if dev_type in DEVICE_ARR_SENS_LIGHT:
            self._dev_class = DEVICE_CLASS_ILLUMINANCE
            self._unit = "lx"

        self._attributes = dict()

    def get_unique_id(self) -> str:
        """Override return a unique ID."""
        if not self._monitored_value:
            return super().get_unique_id()
        else:
            return f"extalife-{str(self.channel_data.get('serial'))}-{self.channel_id}-{self._monitored_value}"

    @property
    def state(self):
        """Return state of the sensor"""
        # multisensor?
        state = self.channel_data.get(self._monitored_value)

        if not state:
            state = self.channel_data.get("value")
            if state is None:
                state = self.channel_data.get("value_1")
            if state is None:
                state = self.channel_data.get("value_2")
            if state is None:
                state = self.channel_data.get("value_3")

        _LOGGER.debug(self.channel_data)
        _LOGGER.debug("state: %s", state)
        return state

    @property
    def device_class(self):
        return self._dev_class

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        data = self.channel_data
        if data.get("sync_time") is not None:
            self._attributes.update({"sync_time": data.get("sync_time")})
        if data.get("last_sync") is not None:
            self._attributes.update({"last_sync": data.get("last_sync")})
        if data.get("battery_status") is not None:
            self._attributes.update({"battery_status": data.get("battery_status")})

        if not self._monitored_value:
            if data.get("value_1") is not None:
                self._attributes.update({"value_1": data.get("value_1")})
            if data.get("value_2") is not None:
                self._attributes.update({"value_2": data.get("value_2")})
            if data.get("value_3") is not None:
                self._attributes.update({"value_3": data.get("value_3")})

        return self._attributes


    def on_state_notification(self, data):
        """ React on state notification from controller """

        self.channel_data.update(data)
        self.async_schedule_update_ha_state(True)