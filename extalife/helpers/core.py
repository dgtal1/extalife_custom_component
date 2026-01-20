import asyncio
import datetime
import importlib
import json
import logging
from contextlib import suppress
from datetime import (
    datetime,
    timedelta
)
from typing import (
    Any,
    Awaitable,
    Callable,
)

import homeassistant.const
import requests
from homeassistant.components.logbook import async_log_entry
from homeassistant.components.persistent_notification import async_create as async_create_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.translation import async_get_translations
from homeassistant.loader import (
    Integration,
)

from .const import (
    DATA_CORE,
    DOMAIN,
    CONF_EXTALIFE_EVENT_SCENE,
    URL_CHANGELOG_JSON,
    URL_IP_ECHO_NET,
)
from .services import ExtaLifeServices
from .typing import (
    ChannelDataManagerType,
    CoreType,
    DeviceManagerType,
    ExtaLifeControllerType
)
from ..pyextalife import (
    ExtaLifeAPI,
    ExtaLifeCmd,
    ExtaLifeResponse
)

MAP_NOTIF_CMD_TO_EVENT = {
    ExtaLifeCmd.ACTIVATE_SCENE: CONF_EXTALIFE_EVENT_SCENE
}

_LOGGER = logging.getLogger(__name__)


class Core:
    _inst: dict[str, CoreType] = dict()
    _hass: HomeAssistant = None
    _services: ExtaLifeServices = None

    _is_stopping = False

    @classmethod
    def create(cls, hass: HomeAssistant, integration: Integration, config_entry: ConfigEntry) -> CoreType:
        """Create Core instance for a given Config Entry"""
        cls._hass = hass
        inst = Core(integration, config_entry)

        hass.data[DOMAIN][DATA_CORE] = cls._inst

        # register callback for HomeAssistant Stop event
        cls._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, cls._on_homeassistant_stop)
        return inst

    @classmethod
    def get(cls, config_entry_id: str) -> CoreType:  # forward
        """Get instance of the Core object based on Config Entry ID"""
        return cls._inst.get(config_entry_id)

    @classmethod
    def get_hass(cls) -> HomeAssistant:
        """Return HomeAssistant instance"""
        return cls._hass

    def __init__(self, integration: Integration, config_entry: ConfigEntry):
        """initialize instance"""
        from .device import DeviceManager
        from ..transmitter import TransmitterManager
        from .. import ChannelDataManager

        self._integration = integration
        self._ver_check_web: bool = False
        self._inst[config_entry.entry_id] = self
        self._changelog: dict[str, Any] = {"next": 0, "data": []}
        self._config_entry: ConfigEntry = config_entry
        self._device_manager: DeviceManager = DeviceManager(config_entry, self)
        self._transmitter_manager = TransmitterManager(config_entry)
        self._api = ExtaLifeAPI(
            self.hass.loop,
            on_connect_callback=self._on_api_connect_callback,
            on_disconnect_callback=self._on_api_disconnect_callback,
            on_notification_callback=self._on_api_notification_callback
        )

        self._signal_callbacks: dict[str, Callable[[], None]] = {}
        self._track_time_callbacks: list[Callable] = []
        self._platforms: dict[str, list[dict[str, Any]]] = {}
        self._platform_loader: dict[str, Callable[[], Awaitable]] = {}
        self._platforms_cust: dict[str, list[dict[str, Any]]] = {}
        self._channel_manager: ChannelDataManager = ChannelDataManager(self, self.hass, self.config_entry)
        self._queue = asyncio.Queue()
        self._queue_task = Core.get_hass().loop.create_task(self._queue_worker())
        self._signals = {}

        self._options_change_remove_callback = config_entry.add_update_listener(
            self._options_change_callback
        )

        self._controller_entity: ExtaLifeControllerType | None = None

        self._storage = {}

        self._is_unloading = False

    # noinspection PyUnusedLocal
    async def _options_change_callback(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Options update listener"""

        await self.channel_manager.async_status_polling_task_setup(False)
        await self.channel_manager.async_version_polling_task_setup(False)

    async def platform_load(self, platform: str) -> bool:
        """Check if platform has been loaded if so will load awaiting channels and return true otherwise false"""

        if platform in self._platform_loader:
            _LOGGER.debug(f"Loading entities for {platform}")
            await self._platform_loader[platform]()
            return True

        return False

    async def platform_register(self, platform: str, async_load_entities: Callable[[], Awaitable]) -> None:
        """registers platform loader for new entities and try to load all waiting channels"""

        _LOGGER.debug(f"Platform '{platform}' has been registered")
        self._platform_loader.setdefault(platform, async_load_entities)
        await self.platform_load(platform)

    @staticmethod
    def _import_executor_callback(module: str, func: str) -> Callable[[HomeAssistant, ConfigEntry], Awaitable] | None:

        result = None
        package = ".".join(__package__.split(".")[:-1])  # 1 level above current package
        try:
            _LOGGER.debug("_import_executor_callback(), module: %s, from: %s", module, package)
            imp_module = importlib.import_module("." + module, package)

            _LOGGER.debug("_import_executor_callback(), func: %s", func)
            result = getattr(imp_module, func)
        except Exception as err:
            _LOGGER.warning("async_setup_custom_platforms(), failed to import module %s from package %s, %s",
                            module, package, repr(err))
        return result

    async def unload_entry_from_hass(self) -> bool:
        """Called when ConfigEntry is unloaded from Home Assistant"""
        self._is_unloading = True

        await Core._callbacks_cleanup(self.config_entry.entry_id)
        await self.channel_manager.async_status_polling_task_setup(False, False)
        await self.channel_manager.async_version_polling_task_setup(False, False)

        await self.api.async_disconnect()

        # unload services when the last entry is unloaded
        if len(self._inst) == 1 and self._services:
            await self._services.async_unregister_services()

        for platform in self._platforms:
            await self.hass.config_entries.async_forward_entry_unload(
                self.config_entry, platform
            )

        await self.async_unload_custom_platforms()

        await self.unregister_controller()

        # remove instance only after everything is unloaded
        self._inst.pop(self.config_entry.entry_id)

        return True

    # noinspection PyUnusedLocal
    @classmethod
    async def _on_homeassistant_stop(cls, event) -> None:
        """Called when Home Assistant is shutting down"""
        cls._is_stopping = True

        await cls._callbacks_cleanup()
        for inst in cls._inst.values():
            await Core._callbacks_cleanup(inst.config_entry.entry_id)
            await inst.channel_manager.async_status_polling_task_setup(False, False)
            await inst.channel_manager.async_version_polling_task_setup(False, False)

            await inst.api.async_disconnect()

    @classmethod
    async def _callbacks_cleanup(cls, entry_id: str | None = None) -> None:
        """Cleanup signal callbacks and callback-handling asyncio queues"""
        instances = (
            [cls.get(entry_id)]
            if entry_id
            else [inst_obj for inst_id, inst_obj in cls._inst.items()]
        )
        for inst in instances:
            inst._queue.put_nowait(None)  # terminate callback worker
            inst.unregister_signal_callbacks()
            inst.unregister_track_time_callbacks()

            if inst._options_change_remove_callback:
                try:
                    inst._options_change_remove_callback()
                except ValueError:
                    pass

            inst._queue_task.cancel()
            try:
                await inst._queue_task
            except asyncio.CancelledError:
                pass

    async def async_register_services(self) -> None:
        """ " Register services, but only once"""
        if self._services is None:
            self._services = ExtaLifeServices(self._hass)
            await self._services.async_register_services()

    async def _on_api_connect_callback(self) -> None:
        """Execute actions on (re)connection to controller"""

        await self.channel_manager.async_status_polling_task_setup()
        await self.channel_manager.async_version_polling_task_setup()

        # Update controller software info, but only on reconnect event
        # during first fire up, entity is still empty
        if self._controller_entity is not None:
            self._controller_entity.schedule_update_ha_state()

    async def _on_api_disconnect_callback(self) -> int:
        """Execute actions on disconnection with controller"""

        if self._is_unloading or self._is_stopping:
            return 0

        await self.channel_manager.async_status_polling_task_setup(False, False)
        await self.channel_manager.async_version_polling_task_setup(False, False)

        # Update controller software info
        if self._controller_entity is not None:
            self._controller_entity.schedule_update_ha_state()

        return 10

    async def _on_api_notification_callback(self, notification: ExtaLifeResponse) -> None:
        if self._is_unloading or self._is_stopping:
            return

        notification_data = notification[0]
        notification_data.update({"command": notification.command})
        # forward only state notifications to data manager to update channels
        if notification.command == ExtaLifeCmd.CONTROL_DEVICE:
            self.channel_manager.channel_on_notify(notification_data)
        elif notification.command == ExtaLifeCmd.UPDATE_RECEIVERS:
            self.channel_manager.device_on_notify(notification_data)

        self._put_notification_on_event_bus(notification)

    async def unregister_controller(self) -> None:
        """Unregister controller from Device Registry"""
        if self._controller_entity:
            await self._controller_entity.unregister_controller()
        self._controller_entity = None

    async def register_controller(self) -> None:
        """Register controller in Device Registry and create its entity"""

        from .entities import ExtaLifeController

        await ExtaLifeController.register_controller(self.config_entry, self.api.serial_no)

    def ver_check_required(self) -> bool:
        return self.api.ver_check_required()

    @property
    def ver_check_web(self) -> bool:
        return self._ver_check_web

    def ver_check_set(self, next_update: int, last_update: bool = False) -> bool:

        if next_update < 0:
            self._ver_check_web = False
        elif next_update > 0:
            self._ver_check_web = True
        if self.api.ver_check_set(next_update, last_update) and self._controller_entity is not None:
            self._controller_entity.schedule_update_ha_state()
            return True

        return False

    def controller_entity_added_to_hass(self, entity: ExtaLifeControllerType) -> None:
        """Callback called by controller entity when the entity is added to HA

        entity - ExtaLifeController object"""
        self._controller_entity = entity

    def _put_notification_on_event_bus(self, notification: ExtaLifeResponse) -> None:
        """ This method raises a notification on HA Event Bus """

        event = MAP_NOTIF_CMD_TO_EVENT.get(notification.command)
        if event:
            self._hass.bus.async_fire(event, event_data=notification[0])

    async def get_external_ip(self) -> str:
        """returns HA external ip"""

        def http_fetch_ip() -> str:
            # noinspection PyBroadException
            try:
                timeout = 5, 5
                headers: dict[str, str] = {
                    "Content-Type": "text/plain",
                    "Accept": "text/plain",
                    "Agent": self.http_agent,
                }
                request = requests.get(URL_IP_ECHO_NET, headers=headers, timeout=timeout)
                return request.content.decode()

            except Exception:
                pass
            return "0.0.0.0"

        return await self.hass.async_add_executor_job(http_fetch_ip, **{})

    @property
    def api(self) -> ExtaLifeAPI:
        return self._api

    @property
    def channel_manager(self) -> ChannelDataManagerType:
        return self._channel_manager

    @property
    def config_entry(self) -> ConfigEntry:
        return self._config_entry

    @property
    def hass(self) -> HomeAssistant:
        return Core._hass

    @property
    def http_agent(self) -> str:

        return f"{self._config_entry.domain}/{self._integration.version} "\
               f"({homeassistant.const.APPLICATION_NAME}/{homeassistant.const.__version__})"

    @property
    def device_manager(self) -> DeviceManagerType:
        return self._device_manager

    @property
    def signal_remove_callbacks(self) -> dict[str, Callable]:
        return self._signal_callbacks

    def add_signal_remove_callback(self, callback: Callable, cb_type: str) -> None:
        self._signal_callbacks[cb_type] = callback

    def unregister_signal_callbacks(self) -> None:
        for cb_type, callback in self.signal_remove_callbacks.items():
            callback()

    def unregister_track_time_callbacks(self) -> None:
        """Call delete callbacks for time interval registered callbacks"""
        for callback in self._track_time_callbacks:
            callback()

        self._track_time_callbacks = []

    def push_channels(self, platform: str, channels_data: list[dict[str, Any]], custom=False, append=False):
        """Store channel data temporarily for platform setup

        custom - custom, virtual platform"""
        if custom:
            if append:
                self._platforms_cust.setdefault(platform, [])
                for channel_data in channels_data:
                    self._platforms_cust[platform].append(channel_data)
            else:
                self._platforms_cust[platform] = channels_data
        else:
            if append:
                self._platforms.setdefault(platform, [])
                for channel_data in channels_data:
                    self._platforms[platform].append(channel_data)
            else:
                self._platforms[platform] = channels_data

    def get_channels(self, platform: str) -> list[dict[str, Any]]:
        """Return list of channel data per platform"""

        channels: list[dict[str, Any]] = self._platforms.get(platform)
        if channels is None:
            channels = self._platforms_cust.get(platform)
        return channels

    def pop_channels(self, platform: str) -> None:
        """Delete list of channel data per platform"""
        if self._platforms.get(platform) is None:
            self._platforms_cust[platform] = []
        else:
            self._platforms[platform] = []

    async def async_setup_custom_platform(self, platform: str):
        """Setup other, custom (pseudo)platforms"""

        async_setup_entry: Callable[[HomeAssistant, ConfigEntry], Awaitable] = \
            await self._hass.async_add_import_executor_job(self._import_executor_callback,
                                                           platform, "async_setup_entry")

        if async_setup_entry is not None:
            await async_setup_entry(self.hass, self.config_entry)
            _LOGGER.debug(f"Custom platform '{platform}' has been configured")

    async def async_unload_custom_platforms(self) -> None:
        """Unload other, custom (pseudo)platforms"""

        for platform, channels in self._platforms_cust.items():

            if platform.startswith("virtual"):
                # virtual platforms does not have import module so cannot be unloaded
                continue

            async_unload_entry: Callable[[HomeAssistant, ConfigEntry], Awaitable] = \
                await self._hass.async_add_import_executor_job(self._import_executor_callback,
                                                               platform, "async_unload_entry")
            if async_unload_entry is not None:
                await async_unload_entry(self.hass, self.config_entry)

    def storage_add(self, inst_id: str, inst_obj) -> None:
        self._storage.update({inst_id: inst_obj})

    def storage_get(self, inst_id: str) -> Any:
        return self._storage.get(inst_id)

    def storage_remove(self, inst_id: str) -> None:
        self._storage.pop(inst_id)

    def async_track_time_interval(
            self, callback: Callable[[datetime], Awaitable | None], interval: timedelta):
        """Add a listener that fires repetitively at every timedelta interval."""

        remove_callback = async_track_time_interval(self.hass, callback, interval)
        self._track_time_callbacks.append(remove_callback)

        def _managed_remove_callback() -> None:
            i = 0
            for cb in self._track_time_callbacks:
                if cb == remove_callback:
                    remove_callback()
                    self._track_time_callbacks.pop(i)
                    break
                i += 1

        return _managed_remove_callback

    def signal_get_global_id(self, signal: str) -> str:
        """create global signal name uniq to entire HA"""

        return f"{self._config_entry.entry_id}-{signal}"

    def async_signal_register(self, signal: str, target) -> Callable:
        """Connect a callable function to a signal.

        This method must be run in the event loop.
        """
        signal_global: str = self.signal_get_global_id(signal)
        self._signals.setdefault(signal_global, []).append(target)

        _LOGGER.debug(f"async_signal_register(), signal: {signal}, signal_ext: {signal_global}, target: {target}")

        def async_remove_signal() -> None:
            """Remove signal listener."""
            _LOGGER.debug(f"async_remove_signal(), signal: {signal}, signal_ext: {signal_global}, target: {target}")
            try:
                self._signals[signal_global].remove(target)
            except (KeyError, ValueError):
                # KeyError is key target listener did not exist
                # ValueError if listener did not exist within signal
                _LOGGER.warning(f"Unable to remove unknown dispatcher {target}")

        return async_remove_signal

    def async_signal_send(self, signal: str, *args: Any) -> None:
        """Send signal and data.

        This method must be run in the event loop.
        """
        signal_global: str = self.signal_get_global_id(signal)
        target_list = self._signals.get(signal_global, [])

        _LOGGER.debug(f"async_signal_send(), signal: {signal}, signal_int: {signal_global}, "
                      f"target_list: {target_list}, *args: {args}")

        for target in target_list:
            _LOGGER.debug(f"async_signal_send(), target: {target}")
            coroutine = target(*args)
            self._hass.async_create_task(coroutine)

    def async_signal_send_sync(self, signal: str, args) -> None:
        """Send signal and data.

        This method must be run in the event loop.
        """
        signal_global: str = self.signal_get_global_id(signal)
        target_list = self._signals.get(signal_global, [])

        for target in target_list:
            _LOGGER.debug(f"queue.put {target}")
            self._queue.put_nowait({"signal": signal_global, "data": args})

    async def _queue_worker(self) -> None:
        _LOGGER.debug("_queue_worker started")
        while True:
            msg = await self._queue.get()

            if msg is None:
                break

            _LOGGER.debug(f"queue.get(): {msg}")
            signal = msg.get("signal")
            data = msg.get("data")

            for callback in self._signals.get(signal):
                _LOGGER.debug(f"_queue_worker callback: {callback}({data})")
                callback(data)

        _LOGGER.debug("_queue_worker done")

    async def changelog_get(self) -> dict[str, Any]:
        """returns Zamel Changelog"""

        def http_fetch_changelog() -> str:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": self.http_agent
            }
            timeout = 3, 3
            request = requests.get(URL_CHANGELOG_JSON, headers=headers, timeout=timeout)

            return request.content.decode()

        # noinspection PyBroadException
        try:
            if self._changelog["next"] == 0 or datetime.now().timestamp() > self._changelog["next"]:
                changelog = json.loads(await self.hass.async_add_executor_job(http_fetch_changelog, **{}))
                self._changelog.update({"next": datetime.now().timestamp() + 6 * 3600, "data": changelog})

        except ConnectionError as conn_err:
            _LOGGER.warning(f"Failed to get changelog: {conn_err}")
            self._changelog.update({"next": datetime.now().timestamp() + 60})

        except Exception as err:
            _LOGGER.warning(f"Failed to get changelog: {err}")
            self._changelog.update({"next": datetime.now().timestamp() + 3600})

        return self._changelog["data"]

    async def i18n_get(
            self,
            category: str,
            key: str,
            placeholders: dict[str, str] | None = None,
    ) -> str:
        """Return a translated exception message.
        Defaults to English, requires translations to already be cached.
        """
        localize_key = f"component.{DOMAIN}.{category}.{key}"

        translations = await async_get_translations(self.hass, self.hass.config.language, category)
        if localize_key in translations:
            if message := translations[localize_key]:
                message = message.rstrip(".")
            if not placeholders:
                return message
            with suppress(KeyError):
                message = message.format(**placeholders)
            return message

        # We return the translation key when was not found in the cache
        return key

    async def async_logbook_write(self, entity: Entity, message_key, placeholder: dict[str, str]) -> None:
        name: str = f"{entity.device_entry.name} {entity.name}"
        message: str = await self.i18n_get("logbook", message_key, placeholder)
        async_log_entry(self.hass, name, message, DOMAIN, entity.entity_id)

    async def async_i18n_get_notification_title(self, key: str, placeholder: dict[str, str]) -> str:
        return await self.i18n_get("notifications", f"{key}.title", placeholder)

    async def async_i18n_get_notification_message(self, key: str, placeholder: dict[str, str]) -> str:
        return await self.i18n_get("notifications", f"{key}.message", placeholder)

    def notification_push(self, message, title, notification_id: str = "") -> None:

        notification_id = DOMAIN + ("." + notification_id) if notification_id else ""
        async_create_notification(self.hass, message, title, notification_id)
