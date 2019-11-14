"""Support for Exta Life on/off switches: ROP, ROM, ROG devices"""
import logging
from pprint import pformat
from .pyextalife import ExtaLifeAPI

from homeassistant.components.switch import SwitchDevice

from . import ExtaLifeChannel

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up ExtaLife switches."""
    if discovery_info is None:
        return

    _LOGGER.debug("Discovery: %s", pformat(discovery_info))

    add_entities([ExtaLifeSwitch(device) for device in discovery_info])


class ExtaLifeSwitch(ExtaLifeChannel, SwitchDevice):
    """Representation of an ExtaLife Switch."""

    def turn_on(self, **kwargs):
        """Turn on the switch."""
        if self.action(ExtaLifeAPI.ACTN_TURN_ON):
            self.channel_data["power"] = 1
            self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off the switch."""
        if self.action(ExtaLifeAPI.ACTN_TURN_OFF):
            self.channel_data["power"] = 0
            self.schedule_update_ha_state()

    @property
    def is_on(self):
        """Return true if switch is on."""
        state = self.channel_data.get("power")

        if state == 1:
            return True
        return False

    def on_state_notification(self, data):
        """ React on state notification from controller """

        state = data.get("state")
        ch_data = self.channel_data.copy()
        ch_data["power"] = 1 if state else 0

        # update only if notification data contains new status; prevent HA event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)
            self.async_schedule_update_ha_state(True)

