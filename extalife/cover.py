"""Support for Exta Life roller shutters: SRP, SRM"""
import logging
from pprint import pformat

from homeassistant.components.cover import (
    CoverDevice,
    ATTR_POSITION,
    DEVICE_CLASS_SHUTTER,
    SUPPORT_OPEN,
    SUPPORT_CLOSE,
    SUPPORT_SET_POSITION,
    SUPPORT_STOP,
)

from . import ExtaLifeChannel

from .pyextalife import ExtaLifeAPI

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up ExtaLife switches."""
    if discovery_info is None:
        return

    _LOGGER.debug("Discovery: %s", pformat(discovery_info))

    add_entities([ExtaLifeCover(device) for device in discovery_info])


class ExtaLifeCover(ExtaLifeChannel, CoverDevice):
    """Representation of an ExtaLife Cover."""

    # Exta Life extreme cover positions
    POS_CLOSED = 100
    POS_OPEN = 0

    @property
    def is_inverted_control(self):
        from . import (DOMAIN, CONF_OPTIONS, CONF_OPTIONS_COVER, CONF_OPTIONS_COVER_INV_CONTROL)
        return self.hass.data[DOMAIN][CONF_OPTIONS][CONF_OPTIONS_COVER][CONF_OPTIONS_COVER_INV_CONTROL]

    @property
    def device_class(self):
        return DEVICE_CLASS_SHUTTER

    @property
    def supported_features(self):
        features = SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_SET_POSITION | SUPPORT_STOP
        return features
    
    @property
    def current_cover_position(self):
        """Return current position of cover. 0 is closed, 100 is open."""
        
        # HA GUI buttons meaning:
        # ARROW UP   - open cover
        # ARROW DOWN - close cover
        # THIS CANNOT BE CHANGED AS IT'S HARDCODED IN HA GUI

        val = self.channel_data.get("value")
        pos = val if self.is_inverted_control else 100-val       
        
        _LOGGER.debug("current_cover_position for cover: %s. Model: %s, returned to HA: %s", self.entity_id, val, pos)
        return pos        

    def set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        data = self.channel_data
        pos = int(kwargs.get(ATTR_POSITION))
        value = pos if self.is_inverted_control else 100-pos        

        _LOGGER.debug("set_cover_position for cover: %s. From HA: %s, model: %s", self.entity_id, pos, value)
        if self.action(ExtaLifeAPI.ACTN_SET_POS, value=value):
            data["value"] = value
            self.schedule_update_ha_state()

    @property
    def is_closed(self):
        """Return if the cover is closed (affects roller icon and entity status)."""
        position = self.channel_data.get("value")
        _LOGGER.debug("is_closed state: %s", position)

        if position is None:
            return None
        pos = ExtaLifeCover.POS_CLOSED
        _LOGGER.debug("is_closed for cover: %s. model: %s, returned to HA: %s", self.entity_id, position, position == pos)
        return position == pos

    def open_cover(self, **kwargs):
        """Open the cover."""
        data = self.channel_data
        pos  = ExtaLifeCover.POS_OPEN

        if self.action(ExtaLifeAPI.ACTN_SET_POS, value=pos):
            data["value"] = pos
            _LOGGER.debug("open_cover for cover: %s. model: %s", self.entity_id, pos)
            self.schedule_update_ha_state()

    def close_cover(self, **kwargs):
        """Close the cover."""
        data = self.channel_data
        pos  = ExtaLifeCover.POS_CLOSED
        
        if self.action(ExtaLifeAPI.ACTN_SET_POS, value=pos):
            data["value"] = pos
            _LOGGER.debug("close_cover for cover: %s. model: %s", self.entity_id, pos)
            self.schedule_update_ha_state()

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        if self.action(ExtaLifeAPI.ACTN_STOP):
            self.schedule_update_ha_state()

    def on_state_notification(self, data):
        """ React on state notification from controller """
        ch_data = self.channel_data.copy()
        ch_data["value"] = data.get("value")

        # update only if notification data contains new status; prevent HA event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)
            self.async_schedule_update_ha_state(True)
