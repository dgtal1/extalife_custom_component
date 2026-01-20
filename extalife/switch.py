"""Support for Exta Life on/off switches: ROP, ROM, ROG devices"""
import logging
from typing import (
    Any,
)

from homeassistant.components.switch import (
    SwitchEntity,
    DOMAIN as DOMAIN_SWITCH
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers.const import DOMAIN_VIRTUAL_SWITCH_SENSOR
from .helpers.core import Core
from .helpers.entities import ExtaLifeChannelNamed
from .pyextalife import (
    ExtaLifeAction,
)

_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up Exta Life switches based on existing config."""

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:

        channels: list[dict[str, Any]] = core.get_channels(DOMAIN_SWITCH)
        _LOGGER.debug(f"Discovery ({DOMAIN_SWITCH}): {channels}")
        if channels:
            async_add_entities([ExtaLifeSwitchNamed(channel, config_entry) for channel in channels])

        core.pop_channels(DOMAIN_SWITCH)
        return None

    await core.platform_register(DOMAIN_SWITCH, async_load_entities)


class ExtaLifeSwitchNamed(ExtaLifeChannelNamed, SwitchEntity):
    """Representation of an ExtaLife Switch."""
    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry):
        super().__init__(config_entry, channel)

        self._assumed_on: bool = False

        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_SWITCH_SENSOR, channel)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        if not self.is_exta_free:
            if await self.async_action(ExtaLifeAction.EXTA_LIFE_TURN_ON):
                field = "power" if self.channel_data.get("output_state") is None else "output_state"
                self.channel_data[field] = 1
                self.async_schedule_update_ha_state()
        else:
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_ON_PRESS) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_ON_RELEASE)):
                self._assumed_on = True
                self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        if not self.is_exta_free:
            if await self.async_action(ExtaLifeAction.EXTA_LIFE_TURN_OFF):
                field = "power" if self.channel_data.get("output_state") is None else "output_state"
                self.channel_data[field] = 0
                self.async_schedule_update_ha_state()
        else:
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_OFF_PRESS) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_OFF_RELEASE)):
                self._assumed_on = False
                self.async_schedule_update_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        if self.is_exta_free:
            return self._assumed_on

        field = "power" if self.channel_data.get("output_state") is None else "output_state"
        state = self.channel_data.get(field)

        if state == 1 or state is True:
            return True
        return False

    def on_state_notification(self, data) -> None:
        """ React on state notification from controller """

        state = data.get("state")
        ch_data = self.channel_data.copy()

        if ch_data.get("power") is not None:
            ch_data["power"] = 1 if state else 0
        elif ch_data.get("output_state") is not None:
            ch_data["output_state"] = state

        # update only if notification data contains new status; prevent HA event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)

            # synchronize DataManager data with processed update & entity data
            self.sync_data_update_ha()
