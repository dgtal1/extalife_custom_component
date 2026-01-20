"""
Support for real Exta Life light controllers (RDP, RDM, SLR)
and fake lights (on/off switches: ROP,ROM devices) mapped as light in HA
"""
import logging
from typing import (
    Any,
)

import homeassistant.util.color as color_util
from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityFeature,
    ATTR_BRIGHTNESS,
    ATTR_RGBW_COLOR,
    ATTR_EFFECT,
    DOMAIN as DOMAIN_LIGHT,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
)

from .helpers.const import DOMAIN_VIRTUAL_LIGHT_SENSOR
from .helpers.core import Core
from .helpers.entities import ExtaLifeChannelNamed
from .pyextalife import (  # pylint: disable=syntax-error
    ExtaLifeAction,
    ExtaLifeDeviceModel,
    DEVICE_ARR_ALL_LIGHT
)

_LOGGER = logging.getLogger(__name__)

EFFECT_1 = "Program 1"
EFFECT_2 = "Program 2"
EFFECT_3 = "Program 3"
EFFECT_4 = "Program 4"
EFFECT_5 = "Program 5"
EFFECT_6 = "Program 6"
EFFECT_7 = "Program 7"
EFFECT_8 = "Program 8"
EFFECT_9 = "Program 9"
EFFECT_10 = "Program 10"
EFFECT_FLOAT = "Floating"
EFFECT_LIST = [
    EFFECT_1,
    EFFECT_2,
    EFFECT_3,
    EFFECT_4,
    EFFECT_5,
    EFFECT_6,
    EFFECT_7,
    EFFECT_8,
    EFFECT_9,
    EFFECT_10,
    EFFECT_FLOAT,
]
EFFECT_LIST_SLR = EFFECT_LIST

MAP_MODE_VAL_EFFECT = {
    0: EFFECT_FLOAT,
    1: EFFECT_1,
    2: EFFECT_2,
    3: EFFECT_3,
    4: EFFECT_4,
    5: EFFECT_5,
    6: EFFECT_6,
    7: EFFECT_7,
    8: EFFECT_8,
    9: EFFECT_9,
    10: EFFECT_10,
}
MAP_EFFECT_MODE_VAL = {v: k for k, v in MAP_MODE_VAL_EFFECT.items()}

SUPPORT_BRIGHTNESS = [
    ExtaLifeDeviceModel.RDP21,
    ExtaLifeDeviceModel.SLN21,
    ExtaLifeDeviceModel.SLN22,
    ExtaLifeDeviceModel.SLR21,
    ExtaLifeDeviceModel.SLR22,
]
SUPPORT_COLOR = [
    ExtaLifeDeviceModel.SLN22,
    ExtaLifeDeviceModel.SLR22,
]
SUPPORT_WHITE = [
    ExtaLifeDeviceModel.SLN22,
    ExtaLifeDeviceModel.SLR22,
]
SUPPORT_EFFECT = [
    ExtaLifeDeviceModel.SLN22,
    ExtaLifeDeviceModel.SLR22,
]


def scale_to_255(value: float) -> int:
    """Scale the input value from 0-100 to 0-255."""
    return max(0, min(255, int((value * 255.0) / 100.0)))


def scale_to_100(value: float) -> int:
    """Scale the input value from 0-255 to 0-100."""
    # Make sure a low but non-zero value is not rounded down to zero
    if 0 < value < 3:
        return 1
    return int(max(0, min(100, int((value * 100.0) / 255.0))))


def mode_val_to_hex(mode_val: int | str) -> str | None:
    """convert mode_val value that can be either xeh string or int to a hex string"""
    if isinstance(mode_val, int):
        return (hex(mode_val)[2:]).upper()
    if isinstance(mode_val, str):
        return mode_val
    return None


def mode_val_to_int(mode_val: int | str) -> int | None:
    """convert mode_val value that can be either hex string or int to int"""
    if isinstance(mode_val, str):
        return int(mode_val, 16)
    if isinstance(mode_val, int):
        return mode_val
    return None


def modeval_upd(old: int | str, new: int | str) -> int | str | None:
    """Update mode_val contextually. Convert to type of the old value and update"""
    if isinstance(old, int):
        if isinstance(new, int):
            return new
        return mode_val_to_int(new)

    if isinstance(old, str):
        if isinstance(new, str):
            return new
        return mode_val_to_hex(new)

    return None


# noinspection PyUnusedLocal
async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None) -> None:
    """setup via configuration.yaml not supported anymore"""


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up an Exta Life light based on existing config."""

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:

        channels: list[dict[str, Any]] = core.get_channels(DOMAIN_LIGHT)

        _LOGGER.debug(f"Discovery ({DOMAIN_LIGHT}): {channels}")
        if channels:
            async_add_entities([ExtaLifeLightNamed(channel, config_entry) for channel in channels])

        core.pop_channels(DOMAIN_LIGHT)
        return None

    await core.platform_register(DOMAIN_LIGHT, async_load_entities)


class ExtaLifeLightNamed(ExtaLifeChannelNamed, LightEntity):
    """Representation of an ExtaLife light controlling device."""

    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry):
        super().__init__(config_entry, channel)

        self._supported_features: LightEntityFeature = LightEntityFeature(0)
        self._effect_list = None

        self._supports_color = self.device_model in SUPPORT_COLOR
        self._supports_white_v = self.device_model in SUPPORT_WHITE
        self._supports_brightness = self.device_model in SUPPORT_BRIGHTNESS

        # set light capabilities (properties)
        if self._supports_color and self._supports_white_v:
            self._attr_supported_color_modes = {ColorMode.RGBW}
            self._attr_color_mode = ColorMode.RGBW
        elif self._supports_color:
            self._attr_supported_color_modes = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB
        elif self._supports_brightness:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

        if self.device_model in SUPPORT_EFFECT:
            self._supported_features |= LightEntityFeature.EFFECT
            self._effect_list = EFFECT_LIST_SLR

        _LOGGER.debug(f"Light type: {self.device_model.name}")

        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_LIGHT_SENSOR, channel)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        data: dict[str, Any] = self.channel_data
        params = dict()
        rgb = None
        if self._supports_brightness:
            target_brightness = kwargs.get(ATTR_BRIGHTNESS)

            if target_brightness is not None:
                # We set it to the target brightness and turn it on
                if data is not None:
                    params.update({"value": scale_to_100(target_brightness)})
            else:
                params.update({"value": data.get("value")})

        mode_val = self.channel_data.get("mode_val")
        mode_val_int = mode_val_to_int(mode_val)
        effect = kwargs.get(ATTR_EFFECT)
        _LOGGER.debug(f"kwargs: {kwargs}")
        _LOGGER.debug(f"turn_on for entity: {self.entity_id}({self.channel_id}). "
                      f"'mode_val' value: {mode_val}; mode_val_int: {mode_val_int}")

        r = g = b = w = 0
        if ATTR_RGBW_COLOR in kwargs:
            r, g, b, w = kwargs[ATTR_RGBW_COLOR]

        # WARNING: Exta Life 'mode_val' from command 37 is a HEX STRING, but command 20 requires INT!!! 🤦‍♂️
        if self._supports_white_v and effect is None:
            if ATTR_RGBW_COLOR in kwargs:
                w = int(w) & 255
            else:
                w = mode_val_int & 255  # default

        if self._supports_color and effect is None:
            if ATTR_RGBW_COLOR in kwargs:
                rgb = (r << 16) | (g << 8) | b
            else:
                rgb = mode_val_int >> 8  # default

        if self._supports_white_v and self._supports_color and effect is None:
            # Exta Life colors in SLR22 are 4 bytes: RGBW
            _LOGGER.debug(f"RGB value: {rgb}. W value: {w}")
            rgbw = (rgb << 8) | w  # merge RGB & W
            params.update({"mode_val": rgbw})
            params.update(
                {"mode": 1}
            )  # mode - still light or predefined programs; set it as still light

        if effect is not None:
            params.update({"mode": 2})  # mode - turn on effect
            params.update(
                {"mode_val": MAP_EFFECT_MODE_VAL[effect]}
            )  # mode - one of effects

        if not self.is_exta_free:
            if await self.async_action(ExtaLifeAction.EXTA_LIFE_TURN_ON, **params):
                # update channel data with new values
                data["power"] = 1
                mode_val_new = params.get("mode_val")
                if mode_val_new is not None:
                    # convert new value to the format of the old value from channel
                    params["mode_val"] = modeval_upd(mode_val, mode_val_new)

                data.update(params)
                self.async_schedule_update_ha_state()
        else:
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_ON_PRESS, **params) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_ON_RELEASE, **params)):
                self._assumed_on = True
                self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        data = self.channel_data
        params = dict()
        mode = data.get("mode")
        if mode is not None:
            params.update({"mode": mode})
        mode_val = data.get("mode_val")
        if mode_val is not None:
            params.update({"mode_val": mode_val_to_int(mode_val)})
        value = data.get("value")
        if value is not None:
            params.update({"value": value})

        if not self.is_exta_free:
            if await self.async_action(ExtaLifeAction.EXTA_LIFE_TURN_OFF, **params):
                data["power"] = 0
                data["mode"] = mode
                self.async_schedule_update_ha_state()
        else:
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_OFF_PRESS, **params) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_TURN_OFF_RELEASE, **params)):
                self._assumed_on = False
                self.schedule_update_ha_state()

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        mode = self.channel_data.get("mode")
        if mode is None or mode != 2:
            return None
        mode_val = self.channel_data.get("mode_val")
        if mode_val is None:
            return None
        return MAP_MODE_VAL_EFFECT[mode_val_to_int(mode_val)]

    @property
    def effect_list(self) -> list[str] | None:
        """Return the list of supported effects."""
        return self._effect_list

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        data = self.channel_data
        # brightness is only supported for native Exta Life light-controlling devices
        if self.device_model in DEVICE_ARR_ALL_LIGHT:
            return scale_to_255(data.get("value"))

    @property
    def supported_features(self) -> LightEntityFeature:
        """Flag supported features."""
        _LOGGER.debug(f"Supported flags: {self._supported_features}")
        return self._supported_features

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value [float, float]."""
        rgbw = mode_val_to_int(self.channel_data.get("mode_val"))
        rgb = rgbw >> 8
        r = rgb >> 16
        g = (rgb >> 8) & 255
        b = rgb & 255

        hs = color_util.color_RGB_to_hs(float(r), float(g), float(b))
        return hs

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        """Return the rgbw color value [int, int, int, int]."""
        rgbw = mode_val_to_int(self.channel_data.get("mode_val"))
        rgb = rgbw >> 8
        r = rgb >> 16
        g = (rgb >> 8) & 255
        b = rgb & 255
        w = rgbw & 255
        return r, g, b, w

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        if self.is_exta_free:
            return self._assumed_on

        state = self.channel_data.get("power")

        _LOGGER.debug(f"is_on for entity: {self.entity_id}, state: {state}")

        if state == 1:
            return True
        return False

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """React on state notification from controller"""
        super().on_state_notification(data)
        state = data.get("state")
        ch_data = self.channel_data.copy()

        ch_data["power"] = 1 if state else 0
        if self._supports_brightness:
            ch_data["value"] = data.get("value")

        if self._supports_color:
            mode_val = ch_data.get("mode_val")
            ch_data["mode_val"] = modeval_upd(mode_val, data.get("mode_val"))

        # update only if notification data contains new status; prevent HS event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)

            # synchronize DataManager data with processed update & entity data
            self.sync_data_update_ha()
