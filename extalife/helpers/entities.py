"""Support for ExtaLife devices."""
import logging
from typing import (
    Any,
    Mapping,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.helpers import (
    device_registry as dr,
    entity_platform,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import DEFAULT_SCAN_INTERVAL

from .const import (
    DOMAIN,
    SIGNAL_DATA_UPDATED,
    SIGNAL_CHANNEL_NOTIF_STATE_UPDATED,
    SIGNAL_DEVICE_NOTIF_CONFIG_UPDATED,
    OPTIONS_GENERAL_DISABLE_NOT_RESPONDING,
    URL_FIRMWARE_HTML,
    VIRTUAL_SENSOR_CHN_FIELD,
    VIRTUAL_SENSOR_DEV_CLS,
    VIRTUAL_SENSOR_PATH,
    VIRTUAL_SENSOR_ALLOWED_CHANNELS
)
from .core import Core
from .typing import (
    ChannelDataManagerType
)
from ..pyextalife import (
    ExtaLifeAPI,
    ExtaLifeConnParams,
    ExtaLifeDeviceModel,
    ExtaLifeDeviceModelName,
    ExtaLifeMap,
    PRODUCT_MANUFACTURER,
    PRODUCT_SERIES_EXTA_LIFE,
    PRODUCT_SERIES_EXTA_FREE,
    DEVICE_ARR_ALL_TRANSMITTER,
)

_LOGGER = logging.getLogger(__name__)


class ExtaLifeEntity(Entity):
    _attr_has_entity_name = True
    _attr_translation_key = DOMAIN

    def __init__(self, config_entry: ConfigEntry, data: dict[str, Any]):
        """Channel data -- channel information from PyExtaLife."""

        self._config_entry: ConfigEntry = config_entry
        self._core: Core = Core.get(config_entry.entry_id)
        self._data: dict[str, Any] = data
        self._data_available = True
        self._device_id: int = data.get("id", 0)
        self._device_model: ExtaLifeDeviceModel = ExtaLifeDeviceModel(data.get("type"))
        self._serial_no: int = data.get("serial")

        self._assumed_on: bool = False
        self._attr_has_entity_name = True
        self._attr_translation_key = DOMAIN

    def _set_data(self, data: dict[str, Any] | None) -> None:
        """store new data to entity"""

        _LOGGER.debug(f"async_update() for entity: {self.entity_id}, data to be updated: {data}")
        if data is None:
            self._data_available = False
            return

        self._data_available = True
        self._data.update(data)

    @staticmethod
    def _extra_state_attribute_update(src: dict[str, Any], dst: dict[str, Any], key: str):
        if src.get(key) is not None:
            dst.update({key: src.get(key)})

    @staticmethod
    def _mapping_to_dict(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(mapping) if mapping is not None else {}

    async def async_update(self) -> None:
        """Call to update state."""

    def _get_unique_id(self) -> str:
        """Provide unique id for HA entity registry"""
        return f"{DOMAIN}-{self.data.get("serial")}"

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """must be overridden in entity subclasses"""

    def get_placeholder(self) -> dict[str, str]:
        return {}

    @property
    def channel_manager(self) -> ChannelDataManagerType:
        """Return ChannelDataManager object"""
        return self.core.channel_manager

    @property
    def config_entry(self) -> ConfigEntry:
        return self._config_entry

    @property
    def controller(self) -> ExtaLifeAPI:
        """Return PyExtaLife's controller component associated with entity."""
        return self.core.api

    @property
    def core(self) -> Core:
        return self._core

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def data_available(self) -> bool:
        return self._data_available

    @property
    def device_id(self) -> int:
        return self._device_id

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device specific attributes."""

        prod_series = (PRODUCT_SERIES_EXTA_FREE if self.is_exta_free else PRODUCT_SERIES_EXTA_LIFE)
        serial_no = self.data.get("serial", 0)
        if self.device_model == ExtaLifeDeviceModel.EFC01:
            identify = self.controller.mac
        else:
            identify = str(serial_no)

        device_info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, identify)},
            name=f"{PRODUCT_MANUFACTURER} {prod_series} {self.device_model_name}",
            manufacturer=PRODUCT_MANUFACTURER,
            model=self.device_model_name,
            serial_number=f"{serial_no:06X} ({serial_no})"
        )
        if not self.is_exta_free and self.device_model not in DEVICE_ARR_ALL_TRANSMITTER:
            device_info.setdefault("configuration_url", f"{URL_FIRMWARE_HTML}?device={self.device_model.name}")

        return device_info

    @property
    def device_model(self) -> ExtaLifeDeviceModel:
        """Return device type"""
        return self._device_model

    @property
    def device_model_name(self) -> ExtaLifeDeviceModelName:
        """Return model"""
        return ExtaLifeMap.type_to_model_name(self._device_model)

    @property
    def is_exta_free(self) -> bool:
        return self._device_model >= ExtaLifeDeviceModel.EXTA_FREE_FIRST

    @property
    def should_poll(self) -> bool:
        """
        Turn off HA polling in favour of update-when-needed status changes.
        Updates will be passed to HA by calling async_schedule_update_ha_state() for each entity
        """
        return False

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._get_unique_id()


class ExtaLifeDevice(ExtaLifeEntity):

    def __init__(self, config_entry: ConfigEntry, device: dict[str, Any]):
        # TODO: missing one-liner

        super().__init__(config_entry, device)

    def _get_unique_id(self) -> str:
        """Provide unique id for HA entity registry"""

        super_id = super()._get_unique_id()
        return f"{super_id}-{self.device_id}"

    async def async_update(self) -> None:
        """Call to update state."""

        await super().async_update()

        # read "data" section/dict by channel id
        data = self.channel_manager.device_get_data(self.device_id)

        self._set_data(data)

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """must be overridden in entity subclasses"""

    @staticmethod
    def signal_get_device_notification_id(device_id: int) -> str:
        return f"{SIGNAL_DEVICE_NOTIF_CONFIG_UPDATED}-{device_id}"

    def sync_data_update_ha(self) -> None:
        """Performs update of Channel Data Manager with Device data and calls HA state update.
        This is useful e.g. when Entity receives notification update, processes it and
        then must update its state. For consistency reasons - Channel Data Manager is updated and then
        HA status update is scheduled"""

        self.channel_manager.device_update_data(self.device_id, self.data)
        self.async_schedule_update_ha_state(True)

    @property
    def device_info(self) -> DeviceInfo | None:
        """Register device in Device Registry"""
        device_info = super().device_info
        if self.device_model != ExtaLifeDeviceModel.EFC01:
            device_info.setdefault("via_device", (DOMAIN, self.controller.mac))
        return device_info


class ExtaLifeChannel(ExtaLifeEntity):
    """Base class of a ExtaLife Channel (an equivalent of HA's Entity).
    ParentEntity - instance of Parent Entity which instantiates this entity
    add_entity_cb - HA callback for adding entity in entity registry
    """

    def __init__(self, config_entry: ConfigEntry, channel: dict[str, Any]):
        """Channel data -- channel information from PyExtaLife."""

        super().__init__(config_entry, channel.get("data"))

        self._channel_id: str = channel.get("id")

    @staticmethod
    def _format_state_attr(attr: dict[str, Any]) -> dict[str, Any]:
        """Format state attributes based on name and other criteria.
        Can be overridden in dedicated subclasses to refine formatting"""
        from re import search

        for k, v in attr.items():
            val = v
            if search("voltage", k):
                v = v / 100
            elif search("current", k):
                v = v / 1000
            elif search("energy_consumption", k):
                v = v / 100000
            elif search("frequency", k):
                v = v / 100
            elif search("phase_shift", k):
                v = v / 10
            elif search("phase_energy", k):
                v = v / 100000
            if val != v:
                attr.update({k: v})
        return attr

    @staticmethod
    def signal_get_channel_notification_id(channel_id: str) -> str:
        return f"{SIGNAL_CHANNEL_NOTIF_STATE_UPDATED}-{channel_id}"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        await super().async_added_to_hass()

    async def async_update(self) -> None:
        """Call to update state."""

        await super().async_update()

        # read "data" section/dict by channel id
        data = self.channel_manager.channel_get_data(self.channel_id)

        self._set_data(data)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()

    def _get_unique_id(self) -> str:
        """Provide unique id for HA entity registry"""

        super_id = super()._get_unique_id()
        return f"{super_id}-{self.channel_id}"

    def sync_data_update_ha(self) -> None:
        """Performs update of Channel Data Manager with Entity data and calls HA state update.
        This is useful e.g. when Entity receives notification update, processes it and
        then must update its state. For consistency reasons - Channel Data Manager is updated and then
        HA status update is scheduled"""

        self.channel_manager.channel_update_data(self.channel_id, self.channel_data)
        self.async_schedule_update_ha_state(True)

    @property
    def assumed_state(self) -> bool:
        """Returns boolean if entity status is assumed status"""
        ret = self.is_exta_free
        _LOGGER.debug(f"Assumed state for entity: {self.entity_id}, {ret}")
        return ret

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_timeout = (
            self.channel_data.get("is_timeout")
            if self.config_entry.options.get(OPTIONS_GENERAL_DISABLE_NOT_RESPONDING)
            else False
        )
        _LOGGER.debug(f"available() for entity: {self.entity_id}. "
                      f"self.data_available: {self.data_available}; 'is_timeout': {is_timeout}")

        return self.data_available is True and is_timeout is False

    @property
    def channel_data(self) -> dict[str, Any]:
        return self.data

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def device_info(self) -> DeviceInfo | None:
        """Register device in Device Registry"""
        device_info = super().device_info
        device_info.setdefault("via_device", (DOMAIN, self.controller.mac))
        return device_info

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return state attributes"""
        es_attr: dict[str, Any] = self._mapping_to_dict(super().extra_state_attributes)
        es_attr.update(
            {
                "channel_id": self.channel_id,
                "not_responding": self.channel_data.get("is_timeout")
            }
        )
        return es_attr

    @property
    def is_exta_free(self) -> bool:
        """Returns boolean if entity represents Exta Free device"""
        exta_free_device = self.channel_data.get("exta_free_device")
        if exta_free_device is None or not bool(exta_free_device):
            return False
        return True


class ExtaLifeChannelNamed(ExtaLifeChannel):

    def __init__(self, config_entry: ConfigEntry, channel: dict[str, Any]):
        super().__init__(config_entry, channel)

    async def _async_state_notif_update_callback(self, *args: Any) -> None:
        """Inform HA of state change received from controller status notification"""
        data = args[0]
        _LOGGER.debug(f"State update notification callback for entity id: {self.entity_id}, data: {data}")

        self.on_state_notification(data)

    async def _async_update_callback(self) -> None:
        """Inform HA of state update when receiving signal from channel data manager"""

        _LOGGER.debug(f"Update callback for entity id: {self.entity_id}")
        self.async_schedule_update_ha_state(True)

    def _get_virtual_sensors(self) -> list[dict[str, Any]]:
        """By default, check all entity attributes and return virtual sensor config"""
        from ..sensor import MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS

        attr: list[dict[str, Any]] = []
        for k, v in self.channel_data.items():  # pylint: disable=unused-variable
            dev_class = MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS.get(k)
            if dev_class:

                if not self.is_virtual_sensor_allowed(k):
                    continue

                attr.append(
                    {
                        VIRTUAL_SENSOR_DEV_CLS: dev_class,
                        VIRTUAL_SENSOR_PATH: k
                    }
                )

        # get additional sensors returned by specific platform
        platform_sensors = self.virtual_sensors
        if platform_sensors:
            attr.extend(platform_sensors)

        return attr

    async def async_action(self, action, **add_pars: Any) -> dict[str, Any] | None:
        """Run controller command/action. Actions are currently hardcoded in platforms"""

        _LOGGER.debug(f"Executing action '{action}' on channel {self.channel_id}, params: {add_pars}")

        return await self.controller.async_execute_action(action, self.channel_id, **add_pars)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        await super().async_added_to_hass()

        _LOGGER.debug(f"async_added_to_hass: entity: {self.entity_id}")
        # register entity in Core for receiving all data updated notification
        self.core.async_signal_register(SIGNAL_DATA_UPDATED, self._async_update_callback)

        # register entity in Core for receiving entity own data updated notification
        self.core.async_signal_register(
            self.signal_get_channel_notification_id(self.channel_id),
            self._async_state_notif_update_callback,
        )

    def is_virtual_sensor_allowed(self, attr_name: str) -> bool:
        """Check if virtual sensor should be created for an attribute based on settings"""
        from ..sensor import VIRTUAL_SENSOR_RESTRICTIONS

        channel = self.channel_data.get("channel")
        restr = VIRTUAL_SENSOR_RESTRICTIONS.get(attr_name)

        if restr:
            if not (channel in restr.get(VIRTUAL_SENSOR_ALLOWED_CHANNELS)):
                return False

        return True

    def push_virtual_sensor_channels(self, virtual_sensor_domain: str, channel_data: dict[str, Any]):
        """Push additional, virtual sensor channels for entity attributes. These should be
        processed by all platforms during platform setup and ultimately sensor entities
        shouldbe created by the sensor platform"""

        virtual_sensors = self._get_virtual_sensors()
        if len(virtual_sensors):
            _LOGGER.debug(f"Virtual sensors: {virtual_sensors}")
            for virtual in virtual_sensors:
                v_channel_data = channel_data.copy()
                v_channel_data.update({VIRTUAL_SENSOR_CHN_FIELD: virtual})
                self.core.push_channels(virtual_sensor_domain, [v_channel_data], append=True, custom=True)

    @property
    def name(self) -> str | None:
        """Return name of the entity"""
        return self.channel_data["alias"]

    @property
    def virtual_sensors(self) -> list[dict[str, Any]]:
        """Return channel attributes which will serve as the basis for virtual sensors.
        Platforms should implement this property and return additional sensors if needed"""
        return []


class ExtaLifeController(ExtaLifeEntity):
    """Base class of a ExtaLife Channel (an equivalent of HA's Entity)."""

    def __init__(self, config_entry: ConfigEntry, serial_no: int):
        super().__init__(config_entry, {"id": 0, "type": int(ExtaLifeDeviceModel.EFC01), "serial": serial_no})

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "controller"

    async def async_added_to_hass(self) -> None:
        """When entity added to HA"""
        await super().async_added_to_hass()

        # let the Core know about the controller entity
        self._core.controller_entity_added_to_hass(self)

    def _get_unique_id(self) -> str:
        super_id = super()._get_unique_id()
        return f"{super_id}-conn"

    @staticmethod
    async def register_controller(config_entry: ConfigEntry, serial_no: int) -> None:
        """Create Controller entity and create device for it in Dev. Registry
        :param config_entry: Config entry
        :param serial_no: Serial number
        :type config_entry: ConfigEntry
        :type serial_no: int
        :return: None
        """

        core: Core = Core.get(config_entry.entry_id)

        platform = entity_platform.EntityPlatform(
            hass=core.get_hass(),
            logger=_LOGGER,
            platform_name=DOMAIN,
            domain=DOMAIN,
            platform=None,
            entity_namespace=None,
            scan_interval=DEFAULT_SCAN_INTERVAL
        )
        platform.config_entry = core.config_entry

        async def async_load_entities() -> None:
            exta_life_controller = ExtaLifeController(config_entry, serial_no)
            await platform.async_add_entities([exta_life_controller])
            return

        await core.platform_register(DOMAIN, async_load_entities)

    async def unregister_controller(self) -> None:
        if self.platform:
            await self.platform.async_remove_entity(self.entity_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # for lost api connection this should return False, so entity status changes to 'unavailable'
        return self.controller is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Register controller in Device Registry"""

        device_info = super().device_info
        device_info.setdefault("connections", {(dr.CONNECTION_NETWORK_MAC, self.mac)})
        # device_info.setdefault("entry_type", DeviceEntryType.SERVICE)
        device_info.update({"sw_version": self.controller.version_installed})

        return device_info

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""

        es_attr = self._mapping_to_dict(super().extra_state_attributes)
        es_attr.update(
            {
                "name": self.controller.name,
                "type": "gateway",
                "mac_address": self.controller.mac,
                "hostname": ExtaLifeConnParams.get_addr(self.controller.host, self.controller.port),
                "username": self.controller.username,
                "ipv4_address": self.controller.network["ip_address"],
                "ipv4_netmask": self.controller.network["netmask"],
                "ipv4_gateway": self.controller.network["gateway"],
                "ipv4_dns": self.controller.network["dns"],
                "software_version": self.controller.version_installed,
                "ver_check_last": self.controller.ver_check_last,
                "ver_check_next": self.controller.ver_check_next,
            }
        )
        return es_attr

    @property
    def name(self) -> str | None:
        """Return name of the entity"""
        return self.controller.name

    @property
    def mac(self) -> str | None:
        """controller's MAC address"""
        return self.controller.mac

    @property
    def state(self) -> str:
        """Return the controller state. it will be either 'ready' or 'unavailable'"""
        return "connected" if self.controller.is_connected else "disconnected"
