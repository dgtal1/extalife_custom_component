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

    add_entities([ExtaLifeSwitch(device) for device in discovery_info])


class ExtaLifeSwitch(ExtaLifeChannel, CoverDevice):
    """Representation of an ExtaLife Switch."""

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
        # need to invert value for Exta Life as HA "thinks" in % of a shutter being open :(
        # return 100 - self.channel_data.get("data").get("value")
        return self.channel_data.get("value")

    def set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        data = self.channel_data
        value = int(kwargs.get(ATTR_POSITION))

        if self.action(ExtaLifeAPI.ACTN_SET_POS, value=value):
            data["value"] = value
            self.schedule_update_ha_state()

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        position = self.channel_data.get("value")
        _LOGGER.debug("is_closed state: %s", position)

        if position is None:
            return None
        return position == 100

    def open_cover(self, **kwargs):
        """Open the cover."""
        data = self.channel_data

        if self.action(ExtaLifeAPI.ACTN_OPEN):
            data["value"] = 0
            self.schedule_update_ha_state()

    def close_cover(self, **kwargs):
        """Close the cover."""
        data = self.channel_data
        if self.action(ExtaLifeAPI.ACTN_CLOSE):
            data["value"] = 100
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
