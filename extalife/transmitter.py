"""Support for Exta Life transmitter devices"""
import logging
from typing import (
    Any,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .helpers.common import PseudoPlatform
from .helpers.const import DOMAIN_TRANSMITTER
from .helpers.core import Core
from .helpers.typing import DeviceManagerType

_LOGGER = logging.getLogger(__name__)

CORE_STORAGE_ID = 'transmitter_mgr'


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry):
    """Set up Exta Life transmitters based on existing config."""

    core = Core.get(config_entry.entry_id)

    async def async_loader_entities() -> None:

        channels = core.get_channels(DOMAIN_TRANSMITTER)
        _LOGGER.debug(f"Discovery ({DOMAIN_TRANSMITTER}): {channels}")

        if channels:
            manager = core.storage_get(CORE_STORAGE_ID)  # transmitter_mgr
            if manager is None:
                manager = TransmitterManager(core.config_entry)
                core.storage_add(CORE_STORAGE_ID, manager)

            for transmitter in channels:
                await manager.add(transmitter)

        core.pop_channels(DOMAIN_TRANSMITTER)

    await core.platform_register(DOMAIN_TRANSMITTER, async_loader_entities)


# noinspection PyUnusedLocal
async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Unload Exta Life transmitters based on existing config."""

    core = Core.get(config_entry.entry_id)
    manager = core.storage_get(CORE_STORAGE_ID)
    if manager is None:
        return

    await manager.unload_transmitters()
    core.storage_remove(CORE_STORAGE_ID)


class ExtaLifeTransmitter(PseudoPlatform):
    def __init__(self, config_entry: ConfigEntry, channel: dict[str, Any]):
        super().__init__(config_entry, channel)

        self._event_processor = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        core = Core.get(self._config_entry.entry_id)
        self._signal_data_notif_remove_callback = core.async_signal_register(
            self.get_notif_upd_signal(self.id),
            self._sync_state_notif_update_callback,
        )

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        self._signal_data_notif_remove_callback()

    def _sync_state_notif_update_callback(self, data) -> None:
        if self.device:
            _LOGGER.debug(f"_sync_state_notif_update_callback: {data}")
            self._device.controller_event(data)

        # pass notification to device for processing
        if self.device:
            self._device.controller_event(data)


class TransmitterManager:
    def __init__(self, config_entry: ConfigEntry):
        self._core: Core = Core.get(config_entry.entry_id)
        self._hass: HomeAssistant = self._core.hass

        self._config_entry = config_entry

        self._transmitters: dict[id, ExtaLifeTransmitter] = {}

    @property
    def device_manager(self) -> DeviceManagerType:
        # return self._hass.data[DOMAIN][DATA_DEV_MANAGER]
        return self._core.device_manager

    async def add(self, channel: dict):
        """ Add transmitter instance to buffer """
        transmitter = ExtaLifeTransmitter(self._config_entry, channel)
        data = {transmitter.id: transmitter}
        self._transmitters.update(data)

        await self.register_device(transmitter)
        await transmitter.async_added_to_hass()

    async def register_device(self, transmitter: ExtaLifeTransmitter) -> None:
        """ Register transmitter in Device Registry """

        device = await self.device_manager.async_add(transmitter.device_type, transmitter.device_info)
        transmitter.assign_device(device)

    async def unload_transmitters(self) -> None:
        """ Unload transmitters: cleanup, unregister signals etc """
        for tr_id, transmitter in self._transmitters.items():
            await transmitter.async_will_remove_from_hass()
