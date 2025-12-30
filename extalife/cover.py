"""Support for Exta Life roller shutters: SRP, SRM, ROB(future)"""
import logging
from typing import (
    Any,
)

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
    DOMAIN as DOMAIN_COVER,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers.const import (
    OPTIONS_COVER_INVERTED_CONTROL,
    DOMAIN_VIRTUAL_COVER_SENSOR
)
from .helpers.core import Core
from .helpers.entities import ExtaLifeChannelNamed
from .pyextalife import (
    ExtaLifeAction,
    DEVICE_ARR_COVER,
    DEVICE_ARR_SENS_GATE_CONTROLLER
)

GATE_CHN_TYPE_GATE = 0
GATE_CHN_TYPE_TILT_GATE = 1
GATE_CHN_TYPE_WICKET = 2
GATE_CHN_TYPE_MONO = 3

GATE_CHN_STATE_NONE = 0
GATE_CHN_STATE_OPEN = 1
GATE_CHN_STATE_TILT = 2
GATE_CHN_STATE_CLOSE = 3

COVER_ACTION_NONE = ""
COVER_ACTION_CLOSING = "closing"
COVER_ACTION_OPENING = "opening"

_LOGGER = logging.getLogger(__name__)

COVER_CHANNEL_ID = "4-12"

# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up Exta Life covers based on existing config."""

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:

        channels: list[dict[str, Any]] = core.get_channels(DOMAIN_COVER)
        _LOGGER.debug(f"Discovery ({DOMAIN_COVER}): {channels}")
        if channels:
            async_add_entities([ExtaLifeCoverNamed(channel, config_entry) for channel in channels])

        core.pop_channels(DOMAIN_COVER)
        return None

    await core.platform_register(DOMAIN_COVER, async_load_entities)


class ExtaLifeCoverNamed(ExtaLifeChannelNamed, CoverEntity):
    """Representation of ExtaLife Cover"""

    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry):
        super().__init__(config_entry, channel)

        self._action = COVER_ACTION_NONE
        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_COVER_SENSOR, channel)

    # Exta Life extreme cover positions
    POS_OPEN = 0
    POS_CLOSED = 100

    @property
    def is_gate( self ) ->  bool:
        return ( self.device_class == CoverDeviceClass.GATE ) or ( self.device_class == CoverDeviceClass.DOOR )

    @property
    def device_class(self) -> CoverDeviceClass:
        """Return the class of this device, from component DEVICE_CLASSES."""
        chn_type = self.channel_data.get("channel_type")
        if self.device_model in DEVICE_ARR_COVER:
            return CoverDeviceClass.SHUTTER
        elif chn_type == GATE_CHN_TYPE_WICKET:
            return CoverDeviceClass.DOOR
        else:
            return CoverDeviceClass.GATE

    @property
    def supported_features(self) -> CoverEntityFeature | int | None:
        """Flag supported features."""
        dev_type = self.channel_data.get("type")
        if not self.is_exta_free:
            if dev_type in DEVICE_ARR_COVER:
                features = (CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE |
                            CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP)
                return features
            elif dev_type in DEVICE_ARR_SENS_GATE_CONTROLLER:
                features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
                return features
        else:
            return CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

        return None

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover. 0 is closed, 100 is open."""
        if self.is_exta_free or self.is_gate:
            return None

        val = self.channel_data.get("value")
        pos = val if self.is_inverted_control else 100-val

        # _LOGGER.debug(f"current_cover_position for cover: {self.entity_id}. Model: {val}, returned to HA: {pos}")
        return pos

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        if self.is_gate:
            return  None

        data = self.channel_data
        pos = int(kwargs.get(ATTR_POSITION))
        value = pos if self.is_inverted_control else 100-pos

        # _LOGGER.debug(f"set_cover_position for cover: {self.entity_id}. From HA: {pos}, model: {value}")
        if await self.async_action(ExtaLifeAction.EXTA_LIFE_SET_POS, value=value):
            data["value"] = value
            self.async_schedule_update_ha_state()

        return None

    @property
    def is_inverted_control(self) -> bool:
        """Wherever to use inverted logic of open/close for 0-100"""
        return self.config_entry.options.get(DOMAIN_COVER).get(OPTIONS_COVER_INVERTED_CONTROL, False)

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed (affects roller icon and entity status)."""
        if self.channel_id == COVER_CHANNEL_ID:
            _LOGGER.debug( "cover.is_closed property query" )
        pos = self.channel_data.get("value")
        gate_state = self.channel_data.get("channel_state")

        if pos is not None:
            return pos == ExtaLifeCoverNamed.POS_CLOSED

        if gate_state is not None:
            return gate_state == GATE_CHN_STATE_CLOSE

        return None

    @property
    def is_closing( self ) -> bool | None:
        if self.channel_id == COVER_CHANNEL_ID:
            _LOGGER.debug( "cover.is_closing property query" )
        if self._action != COVER_ACTION_NONE:
            return self._action == COVER_ACTION_CLOSING
        return None

    @property
    def is_opening(self) -> bool | None:
        if self.channel_id == COVER_CHANNEL_ID:
            _LOGGER.debug( "cover.is_opening property query" )
        if self._action != COVER_ACTION_NONE:
            return  self._action == COVER_ACTION_OPENING
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self.channel_id == COVER_CHANNEL_ID:
            _LOGGER.debug( "cover.async_open_cover execute" )

        data = self.channel_data
        # ROB-21 to open 'pos' must be different from 0
        pos = 1 if self.is_gate else ExtaLifeCoverNamed.POS_OPEN

        if not self.is_exta_free:
            if self.is_gate:
                action = ExtaLifeAction.EXTA_LIFE_GATE_POS
            else:
                action = ExtaLifeAction.EXTA_LIFE_SET_POS

            if await self.async_action(action, value=pos):
                if self.is_gate:
                    self._action = COVER_ACTION_OPENING
                else:
                    data["value"] = pos
                _LOGGER.debug(f"open_cover for cover: {self.entity_id}. pos: {pos}")
                self.async_schedule_update_ha_state()
        else:
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_UP_PRESS) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_UP_RELEASE)):
                self.async_schedule_update_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""

        if self.channel_id == COVER_CHANNEL_ID:
            _LOGGER.debug( "cover.async_close_cover execute" )

        data = self.channel_data
        pos = ExtaLifeCoverNamed.POS_CLOSED
        if not self.is_exta_free:
            if self.is_gate:
                action = ExtaLifeAction.EXTA_LIFE_GATE_POS
            else:
                action = ExtaLifeAction.EXTA_LIFE_SET_POS

            if await self.async_action(action, value=pos):
                if self.is_gate:
                    self._action = COVER_ACTION_CLOSING
                else:
                    data["value"] = pos

                _LOGGER.debug(f"close_cover for cover: {self.entity_id}. pos: {pos}")
                self.async_schedule_update_ha_state()

        else:
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_DOWN_PRESS) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_DOWN_RELEASE)):
                self.async_schedule_update_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        if self.channel_id == COVER_CHANNEL_ID:
            _LOGGER.debug( "cover.async_stop_cover execute" )
        await self.async_action( ExtaLifeAction.EXTA_LIFE_STOP )

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """ React on state notification from controller """
        super().on_state_notification(data)

        if self.channel_id == COVER_CHANNEL_ID:
            _LOGGER.debug( f"cover.on_state_notification execute channel_state={data["channel_state"]}" )

        ch_data = self.channel_data.copy()
        if ch_data.get("value") is not None:
            ch_data["value"] = data.get("value")
        if ch_data.get("channel_state") is not None:
            ch_data["channel_state"] = data.get("channel_state")

        # update only if notification data contains new status; prevent HA event bus overloading
        if ch_data != self.channel_data:
            self._action = ""
            self.channel_data.update(ch_data)
            # synchronize DataManager data with processed update & entity data
            self.sync_data_update_ha()
