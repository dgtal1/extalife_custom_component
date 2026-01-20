"""Provides device automations for Exta Life."""
from __future__ import annotations

import logging
from typing import (
    Any,
)

import voluptuous as vol
from homeassistant.components.automation import AutomationActionType
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .helpers.const import DOMAIN, CONF_EXTALIFE_EVENT_UNIQUE_ID, TRIGGER_TYPE, TRIGGER_SUBTYPE

_LOGGER = logging.getLogger(__name__)


TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(TRIGGER_TYPE): str, vol.Required(TRIGGER_SUBTYPE): str}
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]] | None:
    """List device triggers for Exta Life devices."""
    from .helpers.core import Core
    triggers = []

    _LOGGER.debug(f"async_get_triggers() device_id: {device_id}")

    device_registry = hass.helpers.device_registry.async_get()
    device = device_registry.async_get(device_id)
    if device is None:
        return

    core = None
    for cfg_entry in device.config_entries:
        core = Core.get(cfg_entry)
        if core:
            break

    int_device = await core.device_manager.async_get_by_registry_id(device.id)
    if int_device is None:
        return

    for trigger in int_device.triggers:
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                TRIGGER_TYPE: trigger.get(TRIGGER_TYPE),
                TRIGGER_SUBTYPE: trigger.get(TRIGGER_SUBTYPE)
            }
        )
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: AutomationActionType,
    automation_info: dict,
) -> CALLBACK_TYPE | None:
    """Attach a trigger to an automation"""
    from .helpers.core import Core

    _LOGGER.debug(f"async_attach_trigger() config: {config}, action: {action}, automation_info: {automation_info}")

    device_registry = hass.helpers.device_registry.async_get()
    device = device_registry.async_get(config[CONF_DEVICE_ID])
    if device is None:
        _LOGGER.warning(f"async_attach_trigger() device_id: {config[CONF_DEVICE_ID]} "
                        f"doesn't exist in Device Registry anymore")
        return

    core = None
    for entry_id in device.config_entries:
        core = Core.get(entry_id)
        if core:
            break

    int_device = await core.device_manager.async_get_by_registry_id(device.id)
    _LOGGER.debug(f"int_device: {int_device}")
    if int_device is None:
        return

    dev_trigger = None
    for trigger in int_device.triggers:
        if (trigger.get(TRIGGER_TYPE) == config.get(TRIGGER_TYPE) and
                config.get(TRIGGER_SUBTYPE) == trigger.get(TRIGGER_SUBTYPE)):
            dev_trigger = trigger
            break

    if dev_trigger is None:
        return

    # we'll use event platform as the one to listen to the device trigger
    event_config = {
        event.CONF_PLATFORM: "event",
        event.CONF_EVENT_TYPE: int_device.event.event,
        event.CONF_EVENT_DATA: {CONF_EXTALIFE_EVENT_UNIQUE_ID: int_device.event.unique_id, **dev_trigger},
    }

    _LOGGER.debug(f"async_attach_trigger() event_config: {event_config}")

    event_config = event.TRIGGER_SCHEMA(event_config)

    return await event.async_attach_trigger(hass, event_config, action, automation_info, platform_type="device")
