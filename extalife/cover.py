"""Support for Exta Life roller shutters: SRP, SRM, ROB(future)"""
import logging
from pprint import pformat

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
    DEVICE_CLASS_SHUTTER,
    DEVICE_CLASS_GATE,
    DEVICE_CLASS_DOOR,
    DOMAIN as DOMAIN_COVER,
)
from homeassistant.helpers.typing import HomeAssistantType

from . import ExtaLifeChannel
from .helpers.const import DOMAIN, OPTIONS_COVER_INVERTED_CONTROL
from .helpers.core import Core
from .pyextalife import ExtaLifeAPI, MODEL_ROB01, MODEL_ROB21, DEVICE_MAP_TYPE_TO_MODEL, DEVICE_ARR_COVER, DEVICE_ARR_SENS_GATE_CONTROLLER

GATE_CHN_TYPE_GATE = 0
GATE_CHN_TYPE_TILT_GATE = 1
GATE_CHN_TYPE_WICKET = 2
GATE_CHN_TYPE_MONO = 3

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """setup via configuration.yaml not supported anymore"""
    pass

async def async_setup_entry(hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities):
    """Set up Exta Life covers based on existing config."""

    core = Core.get(config_entry.entry_id)
    channels = core.get_channels(DOMAIN_COVER)

    _LOGGER.debug("Discovery: %s", pformat(channels))
    async_add_entities([ExtaLifeCover(device, config_entry) for device in channels])

    core.pop_channels(DOMAIN_COVER)

class ExtaLifeCover(ExtaLifeChannel, CoverEntity):
    """Representation of ExtaLife Cover"""

    # Exta Life extreme cover positions
    POS_CLOSED = 100
    POS_OPEN = 0

    @property
    def device_class(self):
        dev_type = self.channel_data.get("type")
        chn_type = self.channel_data.get("channel_type")
        if dev_type in DEVICE_ARR_COVER:
            return DEVICE_CLASS_SHUTTER
        elif chn_type == GATE_CHN_TYPE_WICKET:
            return DEVICE_CLASS_DOOR
        else:
            return DEVICE_CLASS_GATE


    @property
    def supported_features(self):
        dev_type = self.channel_data.get("type")
        if not self.is_exta_free:
            if dev_type in DEVICE_ARR_COVER:
                features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP
                return features
            elif dev_type in DEVICE_ARR_SENS_GATE_CONTROLLER:
                features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
                return features
        else:
            return CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    @property
    def current_cover_position(self):
        """Return current position of cover. 0 is closed, 100 is open."""
        # HA GUI buttons meaning:
        # ARROW UP   - open cover
        # ARROW DOWN - close cover
        # THIS CANNOT BE CHANGED AS IT'S HARDCODED IN HA GUI

        if self.is_exta_free or self.device_class == DEVICE_CLASS_GATE or self.device_class == DEVICE_CLASS_DOOR:
            return

        val = self.channel_data.get("value")
        pos = val if self.is_inverted_control else 100-val

        _LOGGER.debug("current_cover_position for cover: %s. Model: %s, returned to HA: %s", self.entity_id, val, pos)
        return pos

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        data = self.channel_data
        pos = int(kwargs.get(ATTR_POSITION))
        value = pos if self.is_inverted_control else 100-pos

        _LOGGER.debug("set_cover_position for cover: %s. From HA: %s, model: %s", self.entity_id, pos, value)
        if await self.async_action(ExtaLifeAPI.ACTN_SET_POS, value=value):
            data["value"] = value
            self.async_schedule_update_ha_state()

    @property
    def is_inverted_control(self):
        return self.config_entry.options.get(DOMAIN_COVER).get(OPTIONS_COVER_INVERTED_CONTROL, False)

    @property
    def is_closed(self):
        """Return if the cover is closed (affects roller icon and entity status)."""
        position = self.channel_data.get("value")
        gate_state = self.channel_data.get("channel_state")

        if position is not None:
            pos = ExtaLifeCover.POS_CLOSED
            _LOGGER.debug("is_closed for cover: %s. model: %s, returned to HA: %s", self.entity_id, position, position == pos)
            return position == pos

        if gate_state is not None:
            return gate_state == 3
        return None

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        data = self.channel_data
        pos  = 1 if self.device_class == DEVICE_CLASS_GATE or self.device_class == DEVICE_CLASS_DOOR else  ExtaLifeCover.POS_OPEN  #ROB-21 to open 'pos' must be different from 0
        if not self.is_exta_free:
            action = ExtaLifeAPI.ACTN_SET_POS if self.device_class != DEVICE_CLASS_GATE and self.device_class != DEVICE_CLASS_DOOR else ExtaLifeAPI.ACTN_SET_GATE_POS
            if await self.async_action(action, value=pos):
                data["value"] = pos
                _LOGGER.debug("open_cover for cover: %s. model: %s", self.entity_id, pos)
                self.async_schedule_update_ha_state()
        else:
            if await self.async_action(ExtaLifeAPI.ACTN_EXFREE_UP_PRESS) and await self.async_action(ExtaLifeAPI.ACTN_EXFREE_UP_RELEASE):
                self.async_schedule_update_ha_state()

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        data = self.channel_data
        pos = ExtaLifeCover.POS_CLOSED
        if not self.is_exta_free:
            action = ExtaLifeAPI.ACTN_SET_POS if self.device_class != DEVICE_CLASS_GATE and self.device_class != DEVICE_CLASS_DOOR else ExtaLifeAPI.ACTN_SET_GATE_POS
            if await self.async_action(action, value=pos):
                data["value"] = pos
                _LOGGER.debug("close_cover for cover: %s. model: %s", self.entity_id, pos)
                self.async_schedule_update_ha_state()

        elif DEVICE_MAP_TYPE_TO_MODEL.get(self.channel_data.get("type")) != MODEL_ROB01:    # ROB-01 supports only 1 toggle mode using 1 command
            if await self.async_action(ExtaLifeAPI.ACTN_EXFREE_DOWN_PRESS) and await self.async_action(ExtaLifeAPI.ACTN_EXFREE_DOWN_RELEASE):
                self.async_schedule_update_ha_state()

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self.async_action(ExtaLifeAPI.ACTN_STOP)


    def on_state_notification(self, data):
        """ React on state notification from controller """
        ch_data = self.channel_data.copy()
        if ch_data.get("value") is not None:
            ch_data["value"] = data.get("value")
        if ch_data.get("channel_state") is not None:
            ch_data["channel_state"] = data.get("channel_state")
        # update only if notification data contains new status; prevent HA event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)

            # synchronize DataManager data with processed update & entity data
            self.sync_data_update_ha()

