import logging
from typing import (
    Any,
    Mapping,
)

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    DOMAIN as DOMAIN_CLIMATE,
)
from homeassistant.components.climate.const import (
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers.const import DOMAIN_VIRTUAL_CLIMATE_SENSOR
from .helpers.core import Core
from .helpers.entities import ExtaLifeChannelNamed
from .pyextalife import (
    ExtaLifeAction,
)

_LOGGER = logging.getLogger(__name__)


# Exta Life logic
# set temp: set state to 1. Controller returns state = 0. State = 0 means work_mode should be set to false
# set auto: set state to 0. Controller returns state = 1. State = 1 means work_mode should be set to true

# map Exta Life "work_mode" field
EXTA_HVAC_MODE = {
    True: HVACMode.AUTO,
    False: HVACMode.HEAT,
}

# map Exta Life notification "state" field
EXTA_STATE_HVAC_MODE = {
    1: HVACMode.AUTO,
    0: HVACMode.HEAT,
}

# map Exta Life "work_mode" field
HVAC_MODE_EXTA = {
    HVACMode.AUTO: True,
    HVACMode.HEAT: False
}

# map Exta Life "power" field
EXTA_HVAC_ACTION = {
    1: HVACAction.HEATING,
    0: HVACAction.IDLE
}

# map HA action to Exta Life "state" field
HVAC_ACTION_EXTA = {
    HVACAction.HEATING: 1,
    HVACAction.IDLE: 0
}

# map HA HVAC mode to Exta Life action
HA_MODE_ACTION = {
    HVACMode.AUTO: ExtaLifeAction.EXTA_LIFE_SET_RGT_MODE_AUTO,
    HVACMode.HEAT: ExtaLifeAction.EXTA_LIFE_SET_RGT_MODE_MANUAL
}


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up an Exta Life heat controllers """

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:

        channels: list[dict[str, Any]] = core.get_channels(DOMAIN_CLIMATE)
        _LOGGER.debug(f"Discovery ({DOMAIN_CLIMATE}): {channels}")
        if channels:
            async_add_entities([ExtaLifeClimateNamed(channel, config_entry) for channel in channels])

        core.pop_channels(DOMAIN_CLIMATE)
        return None

    await core.platform_register(DOMAIN_CLIMATE, async_load_entities)


class ExtaLifeClimateNamed(ExtaLifeChannelNamed, ClimateEntity):
    """Representation of Exta Life Thermostat."""

    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry):
        super().__init__(config_entry, channel)

        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_CLIMATE_SENSOR, channel)

    @property
    def supported_features(self) -> int | None:
        """Flag supported features."""
        return ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return 50

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return 5

    @property
    def target_temperature_step(self) -> float | None:
        """Return the supported step of target temperature."""
        return 0.5

    @property
    def precision(self) -> float:
        """Return the precision of the system."""
        return 0.5

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation if supported."""
        # for now there's no data source to show it. data.power does not reflect this information
        return None

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return hvac operation for example heat, cool mode."""
        return EXTA_HVAC_MODE.get(self.channel_data.get("work_mode"))

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        return [HVACMode.AUTO, HVACMode.HEAT]

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode (heat, auto => manual, auto)."""
        if await self.async_action(HA_MODE_ACTION.get(hvac_mode), value=self.channel_data.get("value")):
            self.channel_data["work_mode"] = HVAC_MODE_EXTA.get(hvac_mode)
            self.async_schedule_update_ha_state()

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return float(int(self.channel_data.get("temperature")) / 10.0)

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return float(self.channel_data.get("value") / 10.0)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperatures."""
        temperature = kwargs.get(ATTR_TEMPERATURE)

        if temperature is None:
            return
        temp_el = temperature * 10.0

        if await self.async_action(ExtaLifeAction.EXTA_LIFE_SET_TMP, value=temp_el):
            self.channel_data["value"] = temp_el
            self.channel_data["work_mode"] = HVAC_MODE_EXTA[HVACMode.HEAT]
            self.async_schedule_update_ha_state()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return device specific state attributes."""
        es_attr: dict[str, Any] = self._mapping_to_dict(super().extra_state_attributes)
        ch_data: dict[str, Any] = self.channel_data
        self._extra_state_attribute_update(ch_data, es_attr, "waiting_to_synchronize")
        self._extra_state_attribute_update(ch_data, es_attr, "temperature_old")
        return es_attr

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """ React on state notification from controller """
        super().on_state_notification(data)

        state = data.get("state")

        ch_data: dict[str, Any] = self.channel_data.copy()
        ch_data["work_mode"] = True if state == 1 else False
        ch_data["value"] = data.get("value")        # update set (target) temperature

        # update only if notification data contains new status; prevent HA event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)

            # synchronize DataManager data with processed update & entity data
            self.sync_data_update_ha()
