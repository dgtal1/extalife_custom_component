"""Support for Exta Life devices firmware update notifications """
import logging
from typing import (
    Any,
)

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    DOMAIN as DOMAIN_BUTTON,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import (
    EntityCategory
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers.core import Core
from .helpers.entities import (
    ExtaLifeDevice
)

_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up Exta Life covers based on existing config."""

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:
        devices: list[dict[str, Any]] = core.get_channels(DOMAIN_BUTTON)
        _LOGGER.debug(f"Discovery ({DOMAIN_BUTTON}) : {devices}")
        if devices:
            entities: list = []
            for device_data in devices:
                entities.append(ExtaLifeButton(ButtonDeviceClass.UPDATE, config_entry, device_data))
                entities.append(ExtaLifeButton(ButtonDeviceClass.RESTART, config_entry, device_data))

            if entities:
                async_add_entities(entities)

        core.pop_channels(DOMAIN_BUTTON)
        return None

    await core.platform_register(DOMAIN_BUTTON, async_load_entities)


class ExtaLifeButton(ExtaLifeDevice, ButtonEntity):

    def __init__(self, device_class: ButtonDeviceClass, config_entry: ConfigEntry, device_data: dict[str, Any]) -> None:
        super().__init__(config_entry, device_data)

        self._attr_device_class = device_class
        self._attr_translation_key = "restart" if device_class == ButtonDeviceClass.RESTART else "update"
        if device_class == ButtonDeviceClass.UPDATE:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        result: str = super().unique_id
        result += "-" + self._attr_translation_key
        return result

    async def async_press(self) -> None:
        """Press the button."""

        if self._attr_device_class == ButtonDeviceClass.RESTART:
            if await self._core.api.async_restart():
                await self._core.api.async_disconnect(True)

        elif self._attr_device_class == ButtonDeviceClass.UPDATE:
            await self._core.channel_manager.async_version_polling_task_run()
