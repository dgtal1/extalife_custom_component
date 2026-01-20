from typing import TYPE_CHECKING

DeviceType = "Device"
DeviceManagerType = "DeviceManager"
TransmitterManagerType = "TransmitterManager"
ChannelDataManagerType = "ChannelDataManager"
CoreType = "Core"
ExtaLifeTransmitterEventProcessorType = "ExtaLifeTransmitterEventProcessor"
ExtaLifeControllerType = "ExtaLifeController"

if TYPE_CHECKING:
    from .core import Core
    from .device import Device, DeviceManager
    from ..transmitter import TransmitterManager
    from .. import (
        ChannelDataManager,
    )
    from .entities import (
        ExtaLifeController
    )

    DeviceType = Device
    DeviceManagerType = DeviceManager
    TransmitterManagerType = TransmitterManager
    ChannelDataManagerType = ChannelDataManager
    CoreType = Core
    ExtaLifeControllerType = ExtaLifeController
