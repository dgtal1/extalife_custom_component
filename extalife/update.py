"""Support for Exta Life devices firmware update notifications """
import asyncio
import logging
from typing import (
    Any,
)

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
    DOMAIN as DOMAIN_UPDATE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers.device_registry import (
    DeviceInfo,
    DeviceRegistry,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers.const import DOMAIN
from .helpers.const import (
    URL_CHANGELOG_HTML,
)
from .helpers.core import Core
from .helpers.entities import (
    ExtaLifeDevice
)
from .pyextalife import (
    ExtaLifeCmd,
    ExtaLifeDeviceModel,
    ExtaLifeCmdErrorCode,
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
        devices: list[dict[str, Any]] = core.get_channels(DOMAIN_UPDATE)
        _LOGGER.debug(f"Discovery ({DOMAIN_UPDATE}) : {devices}")
        if devices:
            async_add_entities([ExtaLifeUpdate(config_entry, device_data) for device_data in devices])

        core.pop_channels(DOMAIN_UPDATE)
        return None

    await core.platform_register(DOMAIN_UPDATE, async_load_entities)


class ExtaLifeUpdate(ExtaLifeDevice, UpdateEntity):

    def __init__(self, config_entry: ConfigEntry, data: dict[str, Any]):
        super().__init__(config_entry, data)

        self._attr_device_class = UpdateDeviceClass.FIRMWARE
        self._attr_has_entity_name = True
        self._attr_translation_placeholders = self.data
        self._attr_release_url = URL_CHANGELOG_HTML
        self._attr_supported_features = UpdateEntityFeature.INSTALL
        self._attr_supported_features |= UpdateEntityFeature.BACKUP
        self._attr_supported_features |= UpdateEntityFeature.RELEASE_NOTES
        if self.device_model != ExtaLifeDeviceModel.EFC01:
            self._attr_supported_features |= UpdateEntityFeature.PROGRESS

        self._in_progress: bool | int = False
        self._err_code: ExtaLifeCmdErrorCode = ExtaLifeCmdErrorCode.SUCCESS

    # @property
    # def entity_picture(self) -> str | None:
    #     return "/local/ROB21.png"  # homeassistant.helpers.typing.UNDEFINED

    def get_placeholder(self) -> dict[str, str]:
        result: dict[str, str] = super().get_placeholder()
        result.update({"installed_version": self.installed_version,
                       "latest_version": self.latest_version,
                       "error": self._err_code,
                       "err_str": self._err_code.name.replace("_", " ")})
        return result

    async def _async_data_update_callback(self, data: dict[str, Any]) -> None:
        # TODO: missing one-liner

        # _LOGGER.debug(f"_async_data_update_callback: {self.entity_id}: received data {data}")

        self.on_state_notification(data)

    def on_state_notification(self, data: dict[str, Any]) -> None:
        # TODO: missing-oneliner
        super().on_state_notification(data)

        command: ExtaLifeCmd = data.get("command", ExtaLifeCmd.NOOP)
        if command == ExtaLifeCmd.FETCH_RECEIVER_CONFIG_DETAILS:
            if ((self.data.get("installed_version", "") != data.get("installed_version", "")) or
                    (self.data.get("web_version", "") != data.get("web_version", ""))):
                ha_device_registry: DeviceRegistry = dr.async_get(self._core.hass)
                ha_device_registry.async_update_device(self.device_entry.id,
                                                       sw_version=data.get("installed_version", ""))

                self._set_data(data)
                self.sync_data_update_ha()

        elif command == ExtaLifeCmd.UPDATE_RECEIVERS:
            state = data.get("state", 100)
            if state < 0:
                try:
                    self._err_code = ExtaLifeCmdErrorCode(state)
                except ValueError as err:
                    _LOGGER.warning(f"Device {self.device_entry.name} {self.name} firmware update failed."
                                    f"Error was {err}")
                    self._err_code = ExtaLifeCmdErrorCode.UNSUPPORTED_OPERATION

            elif state == 0:
                self._in_progress = 101

            elif state == 4:
                progress = data.get("progress_value", 0)
                if progress > self._in_progress:
                    self._in_progress = progress

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        await super().async_added_to_hass()

        _LOGGER.debug(f"async_added_to_hass: entity: {self.entity_id}")

        # register entity in Core for receiving entity own data updated notification
        self.core.async_signal_register(
            self.signal_get_device_notification_id(self.device_id),
            self._async_data_update_callback,
        )

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Install an update."""

        _LOGGER.debug(f"[{self.device_model_name}] Install request for {version}, "
                      f"requested backup => {"YES" if backup else "NO"})")
        try:
            if backup:
                path = self._core.hass.config.path(DOMAIN)
                prefix = f"Update{self.device_model.name}_0x{self._serial_no:06x}"
                await self._core.api.async_config_backup(path, prefix)

            timeout: int = 0
            self._in_progress = 1
            self._err_code: ExtaLifeCmdErrorCode = ExtaLifeCmdErrorCode.SUCCESS
            self.async_write_ha_state()

            if self.device_model == ExtaLifeDeviceModel.EFC01:

                if await self._core.api.async_update_controller():
                    while self._core.api.is_connected and self._err_code == ExtaLifeCmdErrorCode.SUCCESS:
                        # _LOGGER.debug(f"async_install: EFC-01 await for disconnect {timeout} sec(s)")
                        await asyncio.sleep(1)
                        timeout += 1
                        if timeout >= 60:
                            self._err_code = ExtaLifeCmdErrorCode.DEVICE_NOT_RESPONDING
                            break

                    _LOGGER.debug(f"async_install: EFC-01 disconnected after {timeout} sec(s)")

                    timeout = 0
                    while not self._core.api.is_connected and self._err_code == ExtaLifeCmdErrorCode.SUCCESS:
                        # _LOGGER.debug(f"async_install: EFC-01 await for connection {timeout} sec(s)")
                        await asyncio.sleep(1)
                        timeout += 1
                        if timeout >= 120:
                            self._err_code = ExtaLifeCmdErrorCode.DEVICE_NOT_AVAILABLE
                            break

                    _LOGGER.debug(f"async_install: EFC-01 reconnected after {timeout} sec(s)")
                else:
                    self._err_code = ExtaLifeCmdErrorCode.ACTIVATE_INVALID_PARAMETERS

            else:

                last_progress: int = self._in_progress
                if await self._core.api.async_update_receiver(self.device_id):
                    _LOGGER.debug(f"[{self.device_model_name}] Entering await loop")
                    while (self._in_progress <= 100) and (self._err_code == ExtaLifeCmdErrorCode.SUCCESS):
                        # _LOGGER.debug(f"async_install: {self._in_progress}%, {self._err_code.name}, {timeout} sec(s)")
                        if last_progress != self._in_progress:
                            timeout = 0
                            last_progress = self._in_progress
                            self.async_write_ha_state()
                        else:
                            timeout += 1
                        await asyncio.sleep(1)
                        if timeout >= 60:
                            self._err_code = ExtaLifeCmdErrorCode.DEVICE_NOT_RESPONDING
                            break

                    _LOGGER.debug(f"[{self.device_model_name}] Leaving await loop {self._in_progress}%, "
                                  f"{self._err_code.name}, {timeout} sec(s)")

            placeholder = self.get_placeholder()
            placeholder.update({"link": f"[{self.device_entry.name}](/config/devices/device/{self.device_entry.id})"})

            if self._err_code != ExtaLifeCmdErrorCode.SUCCESS:
                await self._core.async_logbook_write(self, "update_failed", placeholder)

                title = await self._core.async_i18n_get_notification_title("update_failed", placeholder)
                message = await self._core.async_i18n_get_notification_message("update_failed", placeholder)
                self._core.notification_push(message, title, DOMAIN_UPDATE)
            else:
                await self._core.async_logbook_write(self, "update_success", placeholder)
                await self._core.channel_manager.async_version_polling_task_run()

        finally:
            self._in_progress = False
        return

    async def async_release_notes(self) -> str | None:
        """Return full release notes."""
        import time
        from datetime import datetime, timezone

        changelog: dict[str, list[dict[str, Any]]] = await self._core.changelog_get()
        if changelog:
            device_changes: list[dict[str, Any]] = changelog.get(self.device_model.name)
            if device_changes:
                release_notes = ""
                for device_change in device_changes:
                    if release_notes:
                        release_notes += f"<hr style='color: silver;'/>"

                    channel: str = device_change.get("channel", "release")
                    ts: int = int(device_change.get("time", "0"))
                    date = datetime.fromtimestamp(ts, timezone.utc).strftime('%Y.%m.%d')
                    release_notes += f"<h3 style=\"color: {"green" if channel == "release" else "red"};\">" \
                                     f"{device_change.get("ver_str")} z {date}, <small>"\
                                     f"{int((time.time() - ts) / 86400)}" \
                                     f" dni temu</small></h3>"
                    release_notes += f"<ul>"
                    for info in device_change.get("info", []):
                        release_notes += f"<li>{info.get("text", "")}</li>"
                    release_notes += f"</ul>"
                    note: str = device_change.get("note", "")
                    if note:
                        release_notes += f'<ha-alert alert-type="warning" title="Informacja">{note}</ha-alert>'

                return release_notes
        return (f'<ha-alert title="Dziennik zmian">Dokument z listą zmian jest dostępny '
                f'<a href="{URL_CHANGELOG_HTML}">tutaj</a></ha-alert>')

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device specific attributes."""

        device_info = super().device_info

        return device_info

    @property
    def installed_version(self) -> str | None:
        """Version installed and in use."""

        return self.data.get("installed_version")

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""

        return self.data.get("web_version")

    @property
    def in_progress(self) -> bool | int | None:
        """Update installation progress."""
        return self._in_progress
