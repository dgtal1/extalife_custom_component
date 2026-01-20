"""Support for Exta Life binary sensor devices e.g. leakage sensor, door/window open sensor"""
import logging
from typing import (
    Any,
    Mapping
)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    DOMAIN as DOMAIN_BINARY_SENSOR
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers.const import DOMAIN_VIRTUAL_BINARY_SENSOR_SENSOR
from .helpers.core import Core
from .helpers.entities import ExtaLifeChannelNamed
from .pyextalife import (  # pylint: disable=syntax-error
    DEVICE_ARR_SENS_WATER,
    DEVICE_ARR_SENS_MOTION,
    DEVICE_ARR_SENS_OPEN_CLOSE,
)

_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up Exta Life binary sensors based on existing config."""

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:

        channels: list[dict[str, Any]] = core.get_channels(DOMAIN_BINARY_SENSOR)
        _LOGGER.debug(f"Discovery: ({DOMAIN_BINARY_SENSOR}): {channels}")
        if channels:
            async_add_entities([ExtaLifeBinarySensorNamed(channel, config_entry) for channel in channels])

        core.pop_channels(DOMAIN_BINARY_SENSOR)
        return None

    await core.platform_register(DOMAIN_BINARY_SENSOR, async_load_entities)


class ExtaLifeBinarySensorNamed(ExtaLifeChannelNamed, BinarySensorEntity):
    """Representation of an ExtaLife binary sensors"""

    def __init__(self, channel, config_entry: ConfigEntry):
        super().__init__(config_entry, channel)

        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_BINARY_SENSOR_SENSOR, channel)

    @property
    def is_on(self) -> bool | None:
        """Return state of the sensor"""

        # Exta Life detection sensors keep their boolean status in field value_3
        state = self.channel_data.get("value_3")

        if self.device_model in DEVICE_ARR_SENS_WATER:
            value = state

        elif self.device_model in DEVICE_ARR_SENS_MOTION:
            value = state

        elif self.device_model in DEVICE_ARR_SENS_OPEN_CLOSE:
            value = not state
        else:
            value = state

        _LOGGER.debug(
            f"state update 'is_on' for entity: {self.entity_id}, id: {self.channel_id}. Status to be updated: {value}",
        )
        return value

    @property
    def device_class(self) -> str | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        if self.device_model in DEVICE_ARR_SENS_WATER:
            return BinarySensorDeviceClass.MOISTURE

        if self.device_model in DEVICE_ARR_SENS_MOTION:
            return BinarySensorDeviceClass.MOTION

        if self.device_model in DEVICE_ARR_SENS_OPEN_CLOSE:
            return BinarySensorDeviceClass.OPENING

        return super().device_class

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return device specific state attributes."""
        es_attr: dict[str, Any] = self._mapping_to_dict(super().extra_state_attributes)
        ch_data: dict[str, Any] = self.channel_data

        # general sensor attributes
        self._extra_state_attribute_update(ch_data, es_attr, "sync_time")
        self._extra_state_attribute_update(ch_data, es_attr, "last_sync")

        # motion sensor attributes
        if self.device_class == BinarySensorDeviceClass.MOTION:
            es_attr.update({"tamper": ch_data.get("tamper")})
            es_attr.update({"tamper_sync_time": ch_data.get("tamper_sync_time")})

        return es_attr

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """ React on state notification from controller """

        super().on_state_notification(data)

        state = data.get("state")
        ch_data = self.channel_data.copy()

        ch_data["value_3"] = state

        _LOGGER.debug(
            f"on_state_notification for entity: {self.entity_id}, id: {self.channel_id}. Status to be updated: {state}",
        )

        # update only if notification data contains new status; prevent HS event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)

            # synchronize DataManager data with processed update & entity data
            self.sync_data_update_ha()
