import logging
from pprint import pformat

from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
    async_dispatcher_connect,
)

from ..pyextalife import (
    ExtaLifeAPI,
    DEVICE_MAP_TYPE_TO_MODEL,
    DEVICE_ARR_ALL_TRANSMITTER,
    PRODUCT_MANUFACTURER,
    PRODUCT_SERIES,
)
from .const import DOMAIN as DOMAIN, SIGNAL_NOTIF_STATE_UPDATED

from .device import Device

_LOGGER = logging.getLogger(__name__)


class PseudoPlatform():
    def __init__(self, config_entry: ConfigEntry, channel_data: dict):
        from .core import Core
        self._core = Core.get(config_entry.entry_id)
        self._hass = self._core.get_hass()
        self._config_entry = config_entry
        self._channel_data = channel_data.get("data")
        self._id = channel_data.get("id")
        self._serial = channel_data.get("serial")

        self._signal_data_notif_remove_callback = None
        self._signal_ext_data_notif_remove_callback = None

        # HA device id
        self._device : Device = None

    @property
    def controller(self) -> ExtaLifeAPI:
        """Return PyExtaLife's controller component associated with entity."""
        return self._core.api

    @property
    def id(self):
        return self._id

    @property
    def serial(self):
        return self._serial

    @property
    def device_type(self):
        """ Exta Life device Type """
        return self._channel_data.get("type")

    @property
    def device_info(self) -> dict:
        model = DEVICE_MAP_TYPE_TO_MODEL.get(self._channel_data.get("type"))
        return {
            "identifiers": {(DOMAIN, self._channel_data.get('serial'))},
            "name": f"{PRODUCT_MANUFACTURER} {PRODUCT_SERIES} {model}",
            "manufacturer": PRODUCT_MANUFACTURER,
            "model": model,
            "via_device": (DOMAIN, self.controller.mac),
        }

    def assign_device(self, device: Device):
        """ device : Device subclass """
        self._device = device

    @property
    def device(self) -> Device:
        return self._device

    @property
    def device_id(self):
        """ HA device id if registered """
        return self._device_id

    @staticmethod
    def get_notif_upd_signal(ch_id):
        return f"{SIGNAL_NOTIF_STATE_UPDATED}_{ch_id}"

    @staticmethod
    def get_ext_notif_upd_signal(serial):
        return f"{SIGNAL_NOTIF_STATE_UPDATED}_{serial}"

    async def async_added_to_hass(self):
        pass

    async def async_will_remove_from_hass(self) -> None:
        pass

    def _async_state_notif_update_callback(self, data):
        pass

