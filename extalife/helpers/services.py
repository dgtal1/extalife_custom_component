""" definition of all services for this integration """
import asyncio
import logging
import os.path
from typing import (
    Any,
)

import voluptuous as vol
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
)
from homeassistant.helpers import (
    config_validation as cv,
    entity_registry as er,
)
from homeassistant.helpers.entity_registry import (
    RegistryEntry,
)

from .const import (
    CONF_BACKUP_PATH,
    CONF_BACKUP_SCHEDULE,
    CONF_BACKUP_RETENTION,
    DOMAIN,
)
from .typing import CoreType

# services
SVC_RESTART = "restart"  # restart controller
SVC_TEST_BUTTON = "test_button"
SVC_REFRESH_STATE = "refresh_state"  # execute status refresh, fetch new status from controller
SVC_CONFIG_BACKUP = "config_backup"  # create controller configuration backup
SVC_CONFIG_RESTORE = "config_restore"  # restore controller configuration from backup

_LOGGER = logging.getLogger(__name__)

SCHEMA_BASE = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
    }
)
SCHEMA_REFRESH_STATE = SCHEMA_RESTART = SCHEMA_BASE

SCHEMA_CONFIG = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_BACKUP_PATH, default=""): cv.path,
        vol.Optional(CONF_BACKUP_SCHEDULE, default=""): cv.string,
        vol.Optional(CONF_BACKUP_RETENTION, default=0): cv.positive_int,
    }
)
SCHEMA_CONFIG_BACKUP = SCHEMA_CONFIG
SCHEMA_CONFIG_RESTORE = SCHEMA_CONFIG

SCHEMA_TEST_BUTTON = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required('button'): str,
        vol.Required('channel_id'): str,
        vol.Required('event'): str,
    }
)


class ExtaLifeServices:
    """ handle Exta Life services """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass: HomeAssistant = hass
        self._services: list[str] = []

    def _get_core(self, entry: RegistryEntry | str) -> CoreType:
        """ Resolve the Core helper class """
        from .core import Core

        if isinstance(entry, str):
            entry = self._get_entry(entry)

        return Core.get(entry.config_entry_id)

    def _get_entry(self, entity_id: str) -> RegistryEntry | None:
        """ Resolve ConfigEntry.entry_id for entity_id """
        # registry = asyncio.run_coroutine_threadsafe(er.async_get_registry(self._hass), self._hass.loop).result()
        registry = er.async_get(self._hass)
        if registry:
            return registry.async_get(entity_id)
        return None

    async def async_register_services(self) -> None:
        """ register all Exta Life integration services """

        def register_service(name: str, entry: Any, schema: vol.Schema) -> None:
            self._hass.services.async_register(DOMAIN, name, entry, schema)
            self._services.append(name)

        register_service(SVC_RESTART, self._handle_restart, SCHEMA_RESTART)
        register_service(SVC_REFRESH_STATE, self._handle_refresh_state, SCHEMA_REFRESH_STATE)
        register_service(SVC_TEST_BUTTON, self._handle_test_button, SCHEMA_TEST_BUTTON)
        register_service(SVC_CONFIG_BACKUP, self._handle_config_backup, SCHEMA_CONFIG_BACKUP)
        register_service(SVC_CONFIG_RESTORE, self._handle_config_restore, SCHEMA_CONFIG_RESTORE)

    async def async_unregister_services(self) -> None:
        """ Unregister all Exta Life integration services """
        for service in self._services:
            self._hass.services.async_remove(DOMAIN, service)

    def _handle_restart(self, call: ServiceCall) -> None:
        """ service: 'extalife.restart' """
        entity_id = call.data.get(CONF_ENTITY_ID)

        core = self._get_core(entity_id)
        if core and core.api:
            asyncio.run_coroutine_threadsafe(core.api.async_restart(), self._hass.loop)

    def _handle_refresh_state(self, call: ServiceCall) -> None:
        """ service: extalife.refresh_state """
        entity_id = call.data.get(CONF_ENTITY_ID)

        core = self._get_core(entity_id)
        if core and core.api:
            asyncio.run_coroutine_threadsafe(core.channel_manager.async_status_polling_task_setup(), self._hass.loop)

    def _get_backup_path(self, path: str | None) -> str:
        if not path:
            return self._hass.config.path(DOMAIN)
        elif not os.path.isabs(path):
            return self._hass.config.path(DOMAIN, path)
        return path

    def _handle_config_backup(self, call: ServiceCall) -> None:
        # TODO: missing one-liner
        entity_id: str = call.data.get(CONF_ENTITY_ID)

        entry: RegistryEntry | None = self._get_entry(entity_id)
        if entry:
            core: CoreType | None = self._get_core(entry)
            if core and core.api:
                path: str = self._get_backup_path(call.data.get(CONF_BACKUP_PATH, ""))
                prefix: str = call.data.get(CONF_BACKUP_SCHEDULE, "")
                retention: int = call.data.get(CONF_BACKUP_RETENTION)

                asyncio.run_coroutine_threadsafe(
                    core.api.async_config_backup(path, schedule=prefix, retention=retention), self._hass.loop
                )

    def _handle_config_restore(self, call: ServiceCall) -> None:
        # TODO: missing one-liner
        entity_id = call.data.get(CONF_ENTITY_ID)
        path: str = call.data.get(CONF_BACKUP_PATH)
        if not path:
            path = self._hass.config.path()
        core = self._get_core(entity_id)
        asyncio.run_coroutine_threadsafe(core.api.async_config_restore(path), self._hass.loop)

    def _handle_test_button(self, call: ServiceCall) -> None:
        from .common import PseudoPlatform

        button = call.data.get('button')
        entity_id = call.data.get(CONF_ENTITY_ID)
        channel_id = call.data.get('channel_id')
        event = call.data.get('event')

        data = {'button': button}
        core = self._get_core(entity_id)

        signal = PseudoPlatform.get_notif_upd_signal(channel_id)

        num = 0

        def click() -> None:
            nonlocal num
            seq = 1
            num += 1
            signal_data = {"button": button, 'click': num, 'sequence': seq, 'state': 1}
            core.async_signal_send_sync(signal, signal_data)

            signal_data = signal_data.copy()
            seq += 1
            signal_data['state'] = 0
            signal_data['sequence'] = seq

            core.async_signal_send_sync(signal, signal_data)

        if event == 'triple':
            click()
            click()
            click()

        elif event == 'double':
            click()
            click()

        elif event == 'single':
            click()

        elif event == 'down':
            data['state'] = 1
            core.async_signal_send_sync(signal, data)

        elif event == 'up':
            data['state'] = 0
            core.async_signal_send_sync(signal, data)
