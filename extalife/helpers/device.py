"""Provides device automations for Exta Life."""

import logging
from typing import Any
from homeassistant.helpers.device_registry import (
    DeviceRegistry,
    DeviceEntry
)
from homeassistant.helpers import device_registry
from homeassistant.config_entries import ConfigEntry
from .typing import CoreType

from ..pyextalife import (
    ExtaLifeDeviceModel,
    ExtaLifeDeviceModelName,
    DEVICE_ARR_ALL_TRANSMITTER,
)

from .const import (
    CONF_EXTALIFE_EVENT_TRANSMITTER,
    TRIGGER_BUTTON_UP,
    TRIGGER_BUTTON_DOWN,
    TRIGGER_BUTTON_DOUBLE_CLICK,
    TRIGGER_BUTTON_TRIPLE_CLICK,
    TRIGGER_BUTTON_SINGLE_CLICK,
    TRIGGER_BUTTON_LONG_PRESS,
    TRIGGER_TYPE,
    TRIGGER_SUBTYPE,
    TRIGGER_SUBTYPE_BUTTON_TEMPLATE,
    CONF_PROCESSOR_EVENT_STAT_NOTIFICATION,
)

_LOGGER = logging.getLogger(__name__)


class DeviceEvent:
    def __init__(self, event, unique_id) -> None:
        """
        event - event in HA
        unique_id - unique identifier of the event source e.g. unique device id
        """
        self._event = event
        self._unique_id = unique_id

    @property
    def event(self):
        return self._event

    @property
    def unique_id(self):
        return self._unique_id


class Device:
    def __init__(self, device: DeviceEntry, device_type: ExtaLifeDeviceModel):
        """dev_info - device info - the same passed to Device Registry
        type  - Exta Life module type e.g. 10 = ROP-21"""
        self._type: ExtaLifeDeviceModel = device_type
        self._device: DeviceEntry = device
        self._event_processor = None

    @property
    def model(self) -> ExtaLifeDeviceModelName:
        return ExtaLifeDeviceModelName(self._device.model)

    @property
    def type(self):
        return self._type

    @property
    def identifiers(self) -> set:
        return self._device.identifiers

    @property
    def unique_id(self):

        # unpack tuple from set and return unique_id by list generator and list index 0
        return [value for value in self.identifiers][0][1]

    @property
    def registry_id(self) -> str:
        return self._device.id

    @property
    def triggers(self) -> list:
        return []

    def controller_event(self, dataa):
        _LOGGER.debug("Device.controller_event")
        pass

    @property
    def config_entry_id(self):
        return [t for t in self._device.config_entries][
            0
        ]  # the same device can exist only in 1 Config Entry

    @property
    def event(self) -> DeviceEvent:
        return DeviceEvent(CONF_EXTALIFE_EVENT_TRANSMITTER, self.unique_id)


class DeviceFactory:
    @staticmethod
    def get_device(device: DeviceEntry, device_type) -> Device:  # subclass
        if device_type in DEVICE_ARR_ALL_TRANSMITTER:
            return TransmitterDevice(device, device_type)
        else:
            raise NotImplementedError


class TransmitterDevice(Device):
    def __init__(self, device: DeviceEntry, device_type: ExtaLifeDeviceModel):
        from .event import ExtaLifeTransmitterEventProcessor

        super().__init__(device, device_type)
        self._event_processor = ExtaLifeTransmitterEventProcessor(self)

    @property
    def triggers(self) -> list:
        triggers = []

        trigger_types = (
            TRIGGER_BUTTON_UP,
            TRIGGER_BUTTON_DOWN,
            TRIGGER_BUTTON_SINGLE_CLICK,
            TRIGGER_BUTTON_DOUBLE_CLICK,
            TRIGGER_BUTTON_TRIPLE_CLICK,
            TRIGGER_BUTTON_LONG_PRESS,
        )
        buttons = 0
        if self.type in (ExtaLifeDeviceModel.RNK22, ExtaLifeDeviceModel.P4572):
            buttons = 2
        elif self.type in (ExtaLifeDeviceModel.RNK24, ExtaLifeDeviceModel.P4574, ExtaLifeDeviceModel.RNM24,
                           ExtaLifeDeviceModel.RNP21, ExtaLifeDeviceModel.RNP22):
            buttons = 4
        elif self.type in ExtaLifeDeviceModel.P4578:
            buttons = 8
        elif self.type in ExtaLifeDeviceModel.P45736:
            buttons = 36

        for button in range(1, buttons + 1):
            for trigger_type in trigger_types:
                triggers.append(
                    {
                        TRIGGER_TYPE: trigger_type,
                        TRIGGER_SUBTYPE: TRIGGER_SUBTYPE_BUTTON_TEMPLATE.format(button),
                    }
                )

        return triggers

    def controller_event(self, data):
        _LOGGER.debug("TransmitterDevice.controller_event")
        super().controller_event(data)
        self._event_processor.process_event(
            data, event_type=CONF_PROCESSOR_EVENT_STAT_NOTIFICATION
        )


class DeviceManager:
    def __init__(self, config_entry: ConfigEntry, core: CoreType):

        self._core: CoreType = core
        self._config_entry: ConfigEntry = config_entry

        self._devices = dict()

    async def register_in_ha_device_registry(self, dev_info: dict[str, Any]) -> DeviceEntry:

        ha_device_registry: DeviceRegistry = device_registry.async_get(self._core.hass)

        device_entry = ha_device_registry.async_get_or_create(
            config_entry_id=self._config_entry.entry_id, **dev_info
        )

        return device_entry

    async def async_add(self, device_type: ExtaLifeDeviceModel,
                        device_info: dict[str, Any] = None,
                        ha_device: DeviceEntry = None) -> Device:
        """
        dev_info - device info data in HA device registry format. To be passed to HA Device Registry
        type  - Exta Life module type e.g. 10 = ROP-21
        ha_device: DeviceEntry - boolean whether to register device in HA Device Registry or not
        """

        device_entry = ha_device if ha_device else await self.register_in_ha_device_registry(device_info)
        device = DeviceFactory.get_device(device_entry, device_type)

        self._devices.update({device_entry.id: device})
        return device

    async def async_get_by_registry_id(self, device_id) -> Device:
        """Get device by HA Device Registry id"""
        return self._devices.get(device_id)
