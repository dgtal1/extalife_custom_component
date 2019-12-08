"""
Support for real Exta Life light controllers (RDP, RDM, SLR) + fake lights (on/off switches: ROP,ROM devices) mapped as light in HA
"""

import logging
from pprint import pformat
from .pyextalife import ExtaLifeAPI

from homeassistant.components.light import (Light, SUPPORT_BRIGHTNESS, SUPPORT_COLOR, SUPPORT_WHITE_VALUE, ATTR_BRIGHTNESS, ATTR_HS_COLOR, ATTR_WHITE_VALUE)
from . import ExtaLifeChannel


from .pyextalife import DEVICE_ARR_ALL_LIGHT, DEVICE_ARR_LIGHT_RGB

import homeassistant.util.color as color_util
_LOGGER = logging.getLogger(__name__)


def scaleto255(value):
    """Scale the input value from 0-100 to 0-255."""
    return max(0, min(255, ((value * 255.0) / 100.0)))


def scaleto100(value):
    """Scale the input value from 0-255 to 0-100."""
    # Make sure a low but non-zero value is not rounded down to zero
    if 0 < value < 3:
        return 1
    return int(max(0, min(100, ((value * 100.0) / 255.0))))


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up ExtaLife lighs."""
    if discovery_info is None:
        return

    _LOGGER.debug("Discovery: %s", pformat(discovery_info))

    add_entities([ExtaLifeLight(device) for device in discovery_info])


class ExtaLifeLight(ExtaLifeChannel, Light):
    """Representation of an ExtaLife light-contorlling device."""

    def __init__(self, channel_data):
        super().__init__(channel_data)

        self._supported_flags = 0
        self.channel_data = channel_data.get("data")

        dev_type = self.channel_data.get("type")
        _LOGGER.debug("Light type: %s", dev_type)
        if dev_type in DEVICE_ARR_ALL_LIGHT:
            self._supported_flags |= SUPPORT_BRIGHTNESS

        if dev_type in DEVICE_ARR_LIGHT_RGB:
            self._supported_flags |= SUPPORT_COLOR | SUPPORT_WHITE_VALUE

    def turn_on(self, **kwargs):
        """Turn on the switch."""
        data = self.channel_data
        params = dict()
        rgb = w = None
        if self._supported_flags & SUPPORT_BRIGHTNESS:
            target_brightness = kwargs.get(ATTR_BRIGHTNESS)

            if target_brightness is not None:
                # We set it to the target brightness and turn it on
                if data is not None:
                    params.update({"value": scaleto100(target_brightness)})
            else:
                params.update({"value": data.get("value")})

        mode_val = self.channel_data.get("mode_val")
        _LOGGER.debug("white value: %s", kwargs)
        _LOGGER.debug("'mode_val' value: %s", mode_val)

        # WARNING: Exta LIfe 'mode_val' from command 37 is a HEX STRING, but command 20 requires INT!!! 🤦‍♂️
        if self._supported_flags & SUPPORT_WHITE_VALUE:
            if not kwargs.get(ATTR_WHITE_VALUE):
                w = int(mode_val, 16) & 255    # default
            else:
                w = int(kwargs.get(ATTR_WHITE_VALUE)) & 255

        if self._supported_flags & SUPPORT_COLOR:
            if not kwargs.get(ATTR_HS_COLOR):
                rgb = int(mode_val, 16)    # default
            else:
                hs = kwargs.get(ATTR_HS_COLOR)  # should return a tuple (h, s)
                rgb = color_util.color_hs_to_RGB(*hs)  # returns a tuple (R, G, B)
                rgb = (int(rgb[0]) << 24) | (int(rgb[1]) << 16) | (int(rgb[2]) << 8)

        if self._supported_flags & SUPPORT_WHITE_VALUE and self._supported_flags & SUPPORT_COLOR:
            # Exta Life colors in SLR22 are 4 bytes: RGBW
            rgbw = rgb & w
            params.update({"mode_val": rgbw})
            params.update({"mode": 0})  # white component only = false

        if self.action(ExtaLifeAPI.ACTN_TURN_ON, **params):
            data["power"] = 1
            mode_val = params.get("mode_val")
            # convert int back to hex string 🤦‍♂️
            if mode_val:
                params["mode_val"] = (hex(mode_val)[2:]).upper()
            data.update(params)
            self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off the switch."""
        data = self.channel_data
        params = dict()
        mode = data.get("mode")
        if mode:
            params.update({"mode": mode})
        mode_val = data.get("mode_val")
        if mode_val:
            params.update({"mode_val": int(mode_val, 16)})
        value = data.get("value")
        if value:
            params.update({"value": value})

        if self.action(ExtaLifeAPI.ACTN_TURN_OFF, **params):
            data["power"] = 0
            self.schedule_update_ha_state()

    @property
    def brightness(self):
        """ Device brightness """
        data = self.channel_data
        # brightness is only supported for native Exta Life light-controlling devices
        if data.get("type") in DEVICE_ARR_ALL_LIGHT:
            return scaleto255(data.get("value"))

    @property
    def supported_features(self):
        _LOGGER.debug("Supported flags: %s", self._supported_flags)
        return self._supported_flags

    @property
    def hs_color(self):
        """ Device colour setting """
        # TODO: need some research to implement this for SLR22
        rgbw = int(self.channel_data.get("mode_val"), 16)
        rgb = rgbw >> 8
        r = rgb >> 16
        g = (rgb >> 8) & 255
        b = rgb & 255

        hs = color_util.color_RGB_to_hs(float(r), float(g), float(b))
        return hs

    @property
    def white_value(self):
        rgbw = int(self.channel_data.get("mode_val"), 16)
        return rgbw & 255

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
        if self._supported_flags & SUPPORT_BRIGHTNESS:
            ch_data["value"] = data.get("value")

        if self._supported_flags & SUPPORT_COLOR:
            ch_data["mode_val"] = data.get("mode_val")

        # update only if notification data contains new status; prevent HS event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)
            self.async_schedule_update_ha_state(True)
