"""Support for ExtaLife devices."""
import datetime
import logging
from datetime import timedelta
from typing import (
    Any,
    Callable,
)

import voluptuous as vol
from homeassistant.components.binary_sensor import DOMAIN as DOMAIN_BINARY_SENSOR
from homeassistant.components.button import DOMAIN as DOMAIN_BUTTON
from homeassistant.components.climate import DOMAIN as DOMAIN_CLIMATE
from homeassistant.components.cover import DOMAIN as DOMAIN_COVER
from homeassistant.components.light import DOMAIN as DOMAIN_LIGHT
from homeassistant.components.sensor import DOMAIN as DOMAIN_SENSOR
from homeassistant.components.switch import DOMAIN as DOMAIN_SWITCH
from homeassistant.components.update import DOMAIN as DOMAIN_UPDATE
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    ConfigEntryAuthFailed,
)
from homeassistant.helpers import (
    device_registry as dr,
    config_validation as cv,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import (
    Integration,
    async_get_integration,
)

from .config_flow import get_default_options
from .helpers.const import (
    DOMAIN,
    CONF_CONTROLLER_IP,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_VER_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VER_INTERVAL,
    OPTIONS_COVER_INVERTED_CONTROL,
    SIGNAL_DATA_UPDATED,
    DOMAIN_TRANSMITTER,
    CONF_OPTIONS,
    OPTIONS_LIGHT,
    OPTIONS_LIGHT_ICONS_LIST,
    OPTIONS_COVER,
    OPTIONS_GENERAL,
    OPTIONS_GENERAL_POLL_INTERVAL,
    OPTIONS_GENERAL_VER_INTERVAL,
)
from .helpers.core import Core
from .helpers.entities import (
    ExtaLifeChannel,
    ExtaLifeDevice,
)
from .pyextalife import (
    ExtaLifeAPI,
    ExtaLifeCmd,
    ExtaLifeConnParams,
    ExtaLifeData,
    ExtaLifeDeviceModel,
    ExtaLifeError,
    ExtaLifeCmdError,
    DEVICE_ARR_ALL_SWITCH,
    DEVICE_ARR_ALL_LIGHT,
    DEVICE_ARR_ALL_COVER,
    DEVICE_ARR_ALL_CLIMATE,
    DEVICE_ARR_ALL_SENSOR_MEAS,
    DEVICE_ARR_ALL_SENSOR_BINARY,
    DEVICE_ARR_ALL_SENSOR_MULTI,
    DEVICE_ARR_ALL_TRANSMITTER,
    DEVICE_ARR_ALL_IGNORE,
    EFC01_EXTA_APP_ID
)

_LOGGER = logging.getLogger(__name__)

OPTIONS_DEFAULTS = get_default_options()

# schema validations
OPTIONS_CONF_SCHEMA = {
    vol.Optional(OPTIONS_GENERAL, default=OPTIONS_DEFAULTS[OPTIONS_GENERAL]): {
        vol.Optional(
            OPTIONS_GENERAL_POLL_INTERVAL,
            default=OPTIONS_DEFAULTS[OPTIONS_GENERAL][OPTIONS_GENERAL_POLL_INTERVAL],
        ): cv.positive_int,
        vol.Optional(
            OPTIONS_GENERAL_VER_INTERVAL,
            default=OPTIONS_DEFAULTS[OPTIONS_GENERAL][OPTIONS_GENERAL_VER_INTERVAL],
        ): cv.positive_int,
    },
    vol.Optional(OPTIONS_LIGHT, default=OPTIONS_DEFAULTS[OPTIONS_LIGHT]): {
        vol.Optional(
            OPTIONS_LIGHT_ICONS_LIST,
            default=OPTIONS_DEFAULTS[OPTIONS_LIGHT][OPTIONS_LIGHT_ICONS_LIST],
        ): cv.ensure_list,
    },
    vol.Optional(OPTIONS_COVER, default=OPTIONS_DEFAULTS[OPTIONS_COVER]): {
        vol.Optional(
            OPTIONS_COVER_INVERTED_CONTROL,
            default=OPTIONS_DEFAULTS[OPTIONS_COVER][OPTIONS_COVER_INVERTED_CONTROL],
        ): cv.boolean,
    },
}

# CONFIG_SCHEMA = {}

# noinspection PyUnusedLocal
async def async_migrate_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(f"Migrating from version {config_entry.version}")

    #  Flatten configuration but keep old data if user rollbacks HASS
    if config_entry.version == 1:

        options = {**config_entry.options}
        options.setdefault(
            OPTIONS_GENERAL,
            {
                OPTIONS_GENERAL_POLL_INTERVAL: config_entry.data.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                ),
                OPTIONS_GENERAL_VER_INTERVAL: config_entry.data.get(
                    CONF_VER_INTERVAL, DEFAULT_VER_INTERVAL
                )
            },
        )
        config_entry.options = {**options}

        new = {**config_entry.data}
        try:
            new.pop(CONF_POLL_INTERVAL)
            # get rid of erroneously migrated options from integration 1.0
            new.pop(CONF_OPTIONS)
        except KeyError:  # pylint: disable=bare-except
            pass
        config_entry.data = {**new}

        config_entry.version = 2

    _LOGGER.info(f"Migration to version {config_entry.version} successful")

    return True


# noinspection PyUnusedLocal
async def async_setup(
        hass: HomeAssistant,
        hass_config: ConfigType) -> bool:
    """Set up Exta Life component from configuration.yaml. This will basically
    forward the config to a Config Flow and will migrate to Config Entry"""

    _LOGGER.debug(f"hass_config: {hass_config}")

    if not hass.config_entries.async_entries(DOMAIN) and DOMAIN in hass_config:
        hass.data.setdefault(DOMAIN, {CONF_OPTIONS: hass_config[DOMAIN].get(CONF_OPTIONS, None)})
        _LOGGER.debug(f"async_setup, hass.data.domain: {hass.data.get(DOMAIN)}")

        result = hass.async_create_task(  # pylint: disable=unused-variable
            hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=hass_config[DOMAIN])
        )

    return True


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Set up Exta Life component from a Config Entry"""

    _LOGGER.debug(f"async_setup_entry: starting for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    hass.data.setdefault(DOMAIN, {})

    integration: Integration = await async_get_integration(hass, DOMAIN)
    Core.create(hass, integration, config_entry)
    config_entry.runtime_data = Core
    result = await async_initialize(hass, config_entry)

    _LOGGER.debug(f"async_setup_entry: finished for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    return result


# noinspection PyUnusedLocal
async def async_unload_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Unload a config entry: unload platform entities, stored data, deregister signal listeners"""

    _LOGGER.debug(f"async_unload_entry: starting for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    core = Core.get(config_entry.entry_id)
    result = await core.unload_entry_from_hass()

    _LOGGER.debug(f"async_unload_entry: finished for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    return result


# noinspection PyUnusedLocal
async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a nexia config entry from a device."""
    return True


async def async_initialize(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Initialize Exta Life integration based on a Config Entry"""

    def init_options() -> None:
        """Populate default options for Exta Life."""

        default = get_default_options()
        options = {**config_entry.options}
        # migrate options after creation of ConfigEntry
        if not options:
            yaml_conf = hass.data.get(DOMAIN)
            yaml_options = None
            if yaml_conf is not None:
                yaml_options = yaml_conf.get(CONF_OPTIONS)

            _LOGGER.debug(f"init_options, yaml_options {yaml_options}")

            options = default if yaml_options is None else yaml_options

        # set default values if something is missing
        options_def = options.copy()
        for k, v in default.items():
            options_def.setdefault(k, v)

        # check for changes and if options should be persisted
        if options_def != options or not config_entry.options:
            hass.config_entries.async_update_entry(config_entry, options=options_def)

    init_options()

    core = Core.get(config_entry.entry_id)

    controller = core.api
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    controller_ip: str = config_entry.data[CONF_CONTROLLER_IP]

    _LOGGER.debug(f"[{config_entry.title}] exta life initializing '{config_entry.title}'... "
                  f"[Debugger attached: {"YES" if ExtaLifeAPI.is_debugger_active() else "NO"}]")

    if controller_ip:
        _LOGGER.debug(f"[{config_entry.title}] trying to connect to controller using IP: {controller_ip}")
        controller_host, controller_port = ExtaLifeConnParams.get_host_and_port(controller_ip)
        autodiscover: bool = False
    else:
        _LOGGER.info(f"[{config_entry.title}] controller IP is not specified. Will use autodiscovery mode")
        controller_host = ""
        controller_port = 0
        autodiscover: bool = True

    # try to connect and logon to controller
    try:
        await controller.async_connect(username, password, controller_host, controller_port,
                                       timeout=5.0, autodiscover=autodiscover)

    except ExtaLifeError as err:
        if isinstance(err, ExtaLifeCmdError):
            raise ConfigEntryAuthFailed(err.message)
        else:
            _LOGGER.error(f"[{config_entry.title}] unable to connect to EFC @ {controller_ip}, {err.message}")
            raise ConfigEntryNotReady

        # await core.unload_entry_from_hass()
        # return False

    if controller_ip is None or (controller.host != controller_host) or (controller.port != controller_port):
        # passed controller ip has changed during autodiscovery
        # should store new controller.host to HA configuration
        cur_data = {**config_entry.data}
        cur_data.update({CONF_CONTROLLER_IP: ExtaLifeConnParams.get_addr(controller.host, controller.port)})
        hass.config_entries.async_update_entry(config_entry, data=cur_data)
        _LOGGER.info(f"[{config_entry.title}] controller IP updated to: {controller.host}")

    if controller.version_installed is not None:
        _LOGGER.debug(f"[{config_entry.title}] EFC software version: {controller.version_installed}")
    else:
        _LOGGER.error("[{config_entry.title}] error communicating with the EFC-01 controller.")
        return False

    await core.register_controller()

    # publish services to HA service registry
    await core.async_register_services()

    _LOGGER.info(f"[{config_entry.title}] exta life integration setup finished successfully!")
    return True


class ChannelDataManager:
    """Get the latest data from EFC-01, call device discovery, handle status notifications."""

    def __init__(self, core: Core, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the Channel Data Manager object."""

        self._core: Core = core
        self._hass: HomeAssistant = hass
        self._config_entry: ConfigEntry = config_entry

        self._channels_data: dict[str, dict[str, Any]] = {}
        self._devices_data: dict[int, dict[str, Any]] = {}

        self._channels_known: list[str] = []
        self._status_polling_task_stop: Callable[[], None] | None = None
        self._version_polling_task_stop: Callable[[], None] | None = None

    def _channel_known(self, channel_id: str) -> bool:
        """append channel_id to list of known channels
        returns true if channel is not known and false otherwise"""

        if channel_id not in self._channels_known:
            self._channels_known.append(channel_id)
            return False
        return True

    def channel_get_data(self, channel_id: str) -> dict[str, Any] | None:
        """get data associated with requested channel_id"""

        # channel data manager contains PyExtaLife API channel data dict value pair: {("id"): ("data")}
        return self._channels_data.get(channel_id)

    def channel_update_data(self, channel_id: str, channel_data: dict[str, Any]) -> None:
        """Update data of a channel e.g. after notification data received and processed
        by an entity"""

        self._channels_data.update({channel_id: channel_data})

    def channel_on_notify(self, data: ExtaLifeData) -> None:
        # TODO: missing one-liner

        _LOGGER.debug(f"[{self._core.config_entry.title}] channel_on_notify: received {data}")

        channel_id: str = ExtaLifeAPI.device_make_channel_id(data)

        # inform HA entity of state change via notification
        signal: str = ExtaLifeChannel.signal_get_channel_notification_id(channel_id)
        if ExtaLifeAPI.device_has_sub_channels(channel_id):
            self._core.async_signal_send(signal, data)
        else:
            self._core.async_signal_send_sync(signal, data)

    def devices_get(
            self, device_filter: Callable[[dict[str, Any]], bool] | None = None
    ) -> dict[int, dict[str, Any]]:
        # TODO: missing one-liner

        if device_filter:
            result: dict[int, dict[str, Any]] = {}
            for device_id, device_data in self._devices_data:
                if device_filter(device_data):
                    result.setdefault(device_id, device_data)
            return result

        return self._devices_data

    def device_get_data(self, device_id: int) -> dict[str, Any] | None:
        # TODO: missing-oneliner

        return self._devices_data.get(device_id)

    def device_update_data(self, device_id: int, device_data: dict[str, Any]) -> None:
        """Update data of a device e.g. after notification data received and processed
        by an entity"""

        self._devices_data.update({device_id: device_data})

    def device_register(
            self, device_id: int, device_type: ExtaLifeDeviceModel, serial_no: int
    ) -> dict[str, Any] | None:
        # TODO: missing one-liner

        if device_id not in self._devices_data.keys():
            device_data: dict[str, Any] = {"id": device_id, "type": device_type, "serial": serial_no}
            self._devices_data.update({device_id: device_data})
            return device_data

        return None

    def device_on_notify(self, data: ExtaLifeData) -> None:
        # TODO: missing one-liner

        _LOGGER.debug(f"[{self._core.config_entry.title}] device_on_notify: received {data}")

        device_id = data.get("id", -1)
        signal: str = ExtaLifeDevice.signal_get_device_notification_id(device_id)

        # inform HA entity of state change via notification
        self._core.async_signal_send(signal, data)

    async def async_status_polling_task_setup(self, poll_now: bool = True, poll_periodic: bool = True) -> None:
        """Executes status polling triggered externally, not via periodic callback + resets next poll time"""

        self._status_polling_task_remove()

        if poll_now:
            await self._async_status_polling_task()

        if poll_periodic:
            self._status_polling_task_configure()

    def _status_polling_task_remove(self) -> None:
        """Stop status polling task scheduler"""

        if self._status_polling_task_stop is not None:
            self._status_polling_task_stop()
            _LOGGER.debug(f"[{self._core.config_entry.title}] status polling task has been removed")

        self._status_polling_task_stop = None

    def _status_polling_task_configure(self) -> None:
        """(Re)set periodic callback for status polling based on interval from integration options"""

        # register callback for periodic status update polling + device discovery
        status_poll_interval: int = self._config_entry.options.get(OPTIONS_GENERAL).get(
            OPTIONS_GENERAL_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )

        _LOGGER.debug(f"[{self._core.config_entry.title}] periodic status poll task interval "
                      f"has been set to {status_poll_interval} minute(s)")
        self._status_polling_task_stop = self._core.async_track_time_interval(
            self._async_status_polling_task, timedelta(minutes=status_poll_interval)
        )

    # noinspection PyUnusedLocal
    async def _async_status_polling_task(self, now: datetime = None) -> None:
        """Get the latest device&channel status data from EFC-01.
        This method is called from HA task scheduler via async_track_time_interval"""

        # use Exta Life TCP communication class
        _LOGGER.debug(f"[{self._core.config_entry.title}] executing EFC-01 status polling task")

        # if connection error or other - will receive None
        # otherwise it contains a list of channels
        channels: list[dict[str, Any]] = await self._core.api.async_get_channels()
        if channels is None or len(channels) == 0:
            _LOGGER.warning(f"[{self._core.config_entry.title}] No Channels could be obtained from the controller")
            return

        # create indexed access: dict from list element
        # dict key = "data" section
        for channel in channels:
            self.channel_update_data(channel["id"], channel["data"])

        self._core.async_signal_send(SIGNAL_DATA_UPDATED)

        _LOGGER.debug(f"[{self._core.config_entry.title}] Status for {len(self._channels_data)} channel(s) updated")

        await self._async_discover_devices()

    async def _async_discover_devices(self) -> None:
        """Fetch / refresh device data & discover devices and register them in Home Assistant."""

        def device_register(_exta_app_id: int, _device_type: ExtaLifeDeviceModel, _serial_no: int) -> bool:

            device_data = self.device_register(_exta_app_id, _device_type, _serial_no)
            if device_data:
                restartable: bool = (_device_type == ExtaLifeDeviceModel.EFC01)

                updatable: bool = (_device_type not in DEVICE_ARR_ALL_TRANSMITTER and
                                   _device_type < ExtaLifeDeviceModel.EXTA_FREE_FIRST)
                _LOGGER.debug(f"[{self._core.config_entry.title}] new device: "
                              f"serial_no={_serial_no:06x}; type={_device_type.name}, "
                              f"update={"YES" if updatable else "NO"}")

                if updatable:
                    std_platforms_channels.setdefault(DOMAIN_UPDATE, []).append(device_data)
                if restartable:
                    std_platforms_channels.setdefault(DOMAIN_BUTTON, []).append(device_data)
                return True

            return False

        std_platforms_channels: dict[str, list[dict[str, Any]]] = {}
        usr_platforms_channels: dict[str, list[dict[str, Any]]] = {}

        entities: int = 0
        devices: int = 0
        if device_register(EFC01_EXTA_APP_ID, ExtaLifeDeviceModel.EFC01, self._core.api.serial_no):
            devices += 1

        light_icons_list: list[int] = self._config_entry.options.get(DOMAIN_LIGHT).get(OPTIONS_LIGHT_ICONS_LIST)

        # get data from the ChannelDataManager object stored in HA object data
        for channel_id, channel_data in self._channels_data.items():  # -> dict id:data

            # do discovery only for newly discovered devices and not known devices
            if self._channel_known(channel_id):
                continue

            channel: dict[str, Any] = {"id": channel_id, "data": channel_data}
            device_id: int = channel_data.get("id")
            device_type: ExtaLifeDeviceModel = ExtaLifeDeviceModel(channel_data.get("type"))
            serial_no: int = channel_data.get("serial")
            platform_name: str = ""

            # this channel is updatable add to list
            devices += 1 if device_register(device_id, device_type, serial_no) else 0

            # skip some devices that are not to be shown nor controlled by HA
            if device_type in DEVICE_ARR_ALL_IGNORE:
                continue

            if device_type in DEVICE_ARR_ALL_SWITCH:
                platform_name = DOMAIN_LIGHT if channel["data"]["icon"] in light_icons_list else DOMAIN_SWITCH

            elif device_type in DEVICE_ARR_ALL_LIGHT:
                platform_name = DOMAIN_LIGHT

            elif device_type in DEVICE_ARR_ALL_COVER:
                platform_name = DOMAIN_COVER

            elif device_type in DEVICE_ARR_ALL_SENSOR_MEAS:
                platform_name = DOMAIN_SENSOR

            elif device_type in DEVICE_ARR_ALL_SENSOR_BINARY:
                platform_name = DOMAIN_BINARY_SENSOR

            elif device_type in DEVICE_ARR_ALL_SENSOR_MULTI:
                platform_name = DOMAIN_SENSOR

            elif device_type in DEVICE_ARR_ALL_CLIMATE:
                platform_name = DOMAIN_CLIMATE

            elif device_type in DEVICE_ARR_ALL_TRANSMITTER:
                usr_platforms_channels.setdefault(DOMAIN_TRANSMITTER, []).append(channel)
                continue

            if not platform_name:
                _LOGGER.warning(f"Unsupported device type: {device_type}, channel id: {channel["id"]}")
                continue

            std_platforms_channels.setdefault(platform_name, []).append(channel)
            entities += 1

        _LOGGER.debug(f"Discovery found {entities} entities and {devices} device(s)")

        # can happen we don't have any sensors, so we need to put an empty list to trigger
        # creation of virtual sensors (if any) for
        std_platforms_channels.setdefault(DOMAIN_SENSOR, [])

        # sensors must be last as platforms will delegate their attributes to virtual sensors
        std_platforms_channels[DOMAIN_SENSOR] = std_platforms_channels.pop(DOMAIN_SENSOR)

        # this list will contain all platforms that require setup
        platforms: list[str] = []
        for platform_name, channels in std_platforms_channels.items():
            # store array of channels (variable 'channels') for each platform
            self._core.push_channels(platform_name, channels)
            # check if platform has been loaded. If not add to list if platform requiring
            # setup, otherwise load oper already added new channels for platform
            if not await self._core.platform_load(platform_name):
                platforms.append(platform_name)

        if platforms:
            # 'sync' call to synchronize channels' stack with platform setup
            _LOGGER.debug(f"Forward setup for {platforms}")
            await self._hass.config_entries.async_forward_entry_setups(self._config_entry, platforms)

        # setup pseudo-platforms
        for platform_name, channels in usr_platforms_channels.items():
            # store array of channels (variable 'channels') for each platform
            self._core.push_channels(platform_name, channels, True)
            self._hass.async_create_task(self._core.async_setup_custom_platform(platform_name))

    async def async_version_polling_task_setup(self, poll_now: bool = True, poll_periodic: bool = True) -> None:
        """Executes version polling triggered externally, not via periodic callback + resets next poll time"""

        self._version_polling_task_remove()

        if poll_now:
            await self._async_version_polling_task()

        if poll_periodic:
            self._version_polling_task_configure()

    async def async_version_polling_task_run(self) -> None:

        self._version_polling_task_remove(False)

        await self._async_version_polling_task()

        self._version_polling_task_configure(False)

    def _version_polling_task_configure(self, set_next_check: bool = True) -> None:
        """(Re)set periodic callback for version polling"""

        version_poll_interval: int = 10

        _LOGGER.debug(f"[{self._core.config_entry.title}] Periodic version poll task interval has "
                      f"been set to {version_poll_interval} minutes(s)")
        self._version_polling_task_stop = self._core.async_track_time_interval(
            self._async_version_polling_task, timedelta(minutes=version_poll_interval)
        )
        if set_next_check:
            self._core.ver_check_set(580)

    def _version_polling_task_remove(self, unset_next_check: bool = True) -> None:
        """Stop version polling task scheduler"""

        if self._version_polling_task_stop is not None:
            self._version_polling_task_stop()
            _LOGGER.debug(f"[{self._core.config_entry.title}] version polling task has been removed")
        if unset_next_check:
            self._core.ver_check_set(-1)
        self._version_polling_task_stop = None

    # noinspection PyUnusedLocal
    async def _async_version_polling_task(self, now: datetime = None) -> None:
        """Get the latest device config setup from EFC-01.
        This method is called from HA task scheduler via async_track_time_interval"""

        if now is not None and not self._core.ver_check_required():
            return

        try:
            _LOGGER.debug(f"[{self._core.config_entry.title}] Executing EFC-01 version polling task")

            for device_id, device_data in self.devices_get().items():

                if device_id == EFC01_EXTA_APP_ID:
                    config_data = await self._core.api.async_check_version(self._core.ver_check_web)
                else:
                    config_data = await self._core.api.async_get_dev_config_details(device_id)

                if config_data:
                    config_data.update({"command": ExtaLifeCmd.FETCH_RECEIVER_CONFIG_DETAILS})
                    self.device_on_notify(config_data)
        finally:
            version_poll_interval: int = self._config_entry.options.get(OPTIONS_GENERAL).get(
                OPTIONS_GENERAL_VER_INTERVAL, DEFAULT_VER_INTERVAL
            )
            next_check: int = version_poll_interval * 3600 if now is not None else 0
            self._core.ver_check_set(next_check, True)

        return None
