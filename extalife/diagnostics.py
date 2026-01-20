"""Diagnostics support for Exta Life integration."""
from __future__ import annotations

import logging
from typing import Any
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .helpers.const import TO_REDACT
from .helpers.core import Core
from .pyextalife import (
    ExtaLifeDataList,
)

_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    core: Core = Core.get(config_entry.entry_id)
    backup: ExtaLifeDataList = await core.api.async_get_config_backup()
    return {
        "external_ip": await core.get_external_ip(),
        "entry": {
            "data": async_redact_data(config_entry.data, TO_REDACT),
            "options": async_redact_data(config_entry.options, TO_REDACT),
        },
        "controller_config": backup if backup else []
    }
