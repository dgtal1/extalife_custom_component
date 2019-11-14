"""Support for Exta Life binary devices e.g. leakage sensor, door/window sensor"""
import logging
from pprint import pformat

from . import ExtaLifeChannel
from homeassistant.const import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_ILLUMINANCE,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)

from .pyextalife import DEVICE_ARR_SENS_WATER, DEVICE_ARR_SENS_MOTION

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up ExtaLife switches."""
    if discovery_info is None:
        return

    _LOGGER.debug("Discovery: %s", pformat(discovery_info))

    add_entities([ExtaLifeBinarySensor(device) for device in discovery_info])


class ExtaLifeBinarySensor(ExtaLifeChannel):
    """Representation of an ExtaLife binary sensors"""

    def __init__(self, channel_data):
        super().__init__(channel_data)
        self._channel_data = channel_data

        dev_type = channel_data.get("data").get("type")
        if dev_type in DEVICE_ARR_SENS_WATER:
            self._dev_class = "moisture"

        if dev_type in DEVICE_ARR_SENS_MOTION:
            self._dev_class = "motion"

        self._attributes = dict()

    @property
    def is_on(self):
        """Return state of the sensor"""
        state = self._channel_data.get("data").get("value")
        if state is None:
            state = self._channel_data.get("data").get("value_1")
        if state is None:
            state = self._channel_data.get("data").get("value_2")
        if state is None:
            state = self._channel_data.get("data").get("value_3")

        _LOGGER.debug(self._channel_data)
        _LOGGER.debug("state: %s", state)
        if state == 1 or state:
            return True
        return False

    @property
    def device_class(self):
        return self._dev_class

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        data = self.channel_data.get("data")
        # general sensor attributes
        if data.get("sync_time") is not None:
            self._attributes.update({"sync_time": data.get("sync_time")})
        if data.get("last_sync") is not None:
            self._attributes.update({"last_sync": data.get("last_sync")})
        if data.get("battery_status") is not None:
            self._attributes.update({"battery_status": data.get("battery_status")})

        # motion sensor attributes
        if self._dev_class == "motion":
            self._attributes.update({"tamper": data.get("tamper")})
            self._attributes.update({"tamper_sync_time": data.get("tamper_sync_time")})

        return self._attributes

    def on_state_notification(self, data):
        """ React on state notification from controller """

        self.channel_data.update(data)
        self.async_schedule_update_ha_state(True)
