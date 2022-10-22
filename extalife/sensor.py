"""Support for Exta Life sensor devices"""
from dataclasses import dataclass
import logging
from pprint import pformat

from homeassistant.backports.enum import StrEnum

from homeassistant.components.sensor import (
    DOMAIN as DOMAIN_SENSOR,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry

from homeassistant.const import (
    PERCENTAGE,
    TEMP_CELSIUS,
    PRESSURE_HPA,
    DEGREE,
    ELECTRIC_POTENTIAL_VOLT,
    ELECTRIC_CURRENT_AMPERE,
    FREQUENCY_HERTZ,
    POWER_WATT,
    POWER_VOLT_AMPERE_REACTIVE,
    POWER_VOLT_AMPERE,
    ENERGY_KILO_WATT_HOUR,
    LIGHT_LUX,
)
from homeassistant.helpers.typing import HomeAssistantType

from . import ExtaLifeChannel
from .helpers.core import Core
from .helpers.const import (
    DOMAIN_VIRTUAL_SENSORS,
    DOMAIN_VIRTUAL_SENSOR,
    VIRT_SENSOR_CHN_FIELD,
    VIRT_SENSOR_DEV_CLS,
    VIRT_SENSOR_PATH,
    VIRT_SENSOR_ALLOWED_CHANNELS,
)
from .pyextalife import (           # pylint: disable=syntax-error
    DEVICE_ARR_SENS_ENERGY_METER,
    DEVICE_ARR_SENS_TEMP,
    DEVICE_ARR_SENS_LIGHT,
    DEVICE_ARR_SENS_HUMID,
    DEVICE_ARR_SENS_MULTI,
    DEVICE_ARR_SENS_PRESSURE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ELSensorEntityDescription(SensorEntityDescription):
    """Sensor entity config description"""

    key: str = ""
    factor: float = 1  # value scaling factor to have a value in normalized units like Watt, Volt etc
    value_path: str = "value_1"  # path to the value field in channel_data

class SensorEntityConfig():
    """ This class MUST correspond to class ELSensorEntityDescription.
    The task of this class is to have instance-based version of Entity Description/config,
    that can be manipulated / overwritten by Virtual sensors setup"""
    def __init__(self, descr: ELSensorEntityDescription) -> None:
        self.key: str = descr.key
        self.factor: float = descr.factor
        self.value_path: str = descr.value_path

        self.native_unit_of_measurement: str = descr.native_unit_of_measurement
        self.device_class: str = descr.device_class
        self.state_class: str = descr.state_class


class ExtaSensorDeviceClass(StrEnum):
    """ExtaLife custom device classes"""

    #TOTAL_ENERGY = "total_energy"
    APPARENT_ENERGY = "apparent_energy"  # kVAh
    REACTIVE_ENERGY = "reactive_energy"  # kvarh
    PHASE_SHIFT = "phase_shift"
    MANUAL_ENERGY = "manual_energy"


MAP_EXTA_DEV_TYPE_TO_DEV_CLASS = {}
MAP_EXTA_DEV_TYPE_TO_DEV_CLASS.update(
    {v: SensorDeviceClass.TEMPERATURE for v in DEVICE_ARR_SENS_TEMP}
)
MAP_EXTA_DEV_TYPE_TO_DEV_CLASS.update(
    {v: SensorDeviceClass.HUMIDITY for v in DEVICE_ARR_SENS_HUMID}
)
MAP_EXTA_DEV_TYPE_TO_DEV_CLASS.update(
    {v: SensorDeviceClass.ILLUMINANCE for v in DEVICE_ARR_SENS_LIGHT}
)
MAP_EXTA_DEV_TYPE_TO_DEV_CLASS.update(
    {v: SensorDeviceClass.PRESSURE for v in DEVICE_ARR_SENS_PRESSURE}
)
MAP_EXTA_DEV_TYPE_TO_DEV_CLASS.update(
    {v: SensorDeviceClass.ENERGY for v in DEVICE_ARR_SENS_ENERGY_METER}
)

MAP_EXTA_MULTI_CHN_TO_DEV_CLASS = {
    1: SensorDeviceClass.TEMPERATURE,
    2: SensorDeviceClass.HUMIDITY,
    3: SensorDeviceClass.PRESSURE,
    4: SensorDeviceClass.ILLUMINANCE,
}

MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS = {
    "battery_status": SensorDeviceClass.BATTERY,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
    "active_power": SensorDeviceClass.POWER,
    "reactive_power": SensorDeviceClass.REACTIVE_POWER,
    "apparent_power": SensorDeviceClass.APPARENT_POWER,
    "power_factor": SensorDeviceClass.POWER_FACTOR,
    "frequency": SensorDeviceClass.FREQUENCY,
    "phase_shift": ExtaSensorDeviceClass.PHASE_SHIFT,
    "phase_energy": SensorDeviceClass.ENERGY,
    "apparent_energy": ExtaSensorDeviceClass.APPARENT_ENERGY,
    "active_energy_solar": SensorDeviceClass.ENERGY,
    "reactive_energy_solar": ExtaSensorDeviceClass.REACTIVE_ENERGY,
    "manual_energy": ExtaSensorDeviceClass.MANUAL_ENERGY,
}

VIRTUAL_SENSOR_RESTRICTIONS = {
  "battery_status": {VIRT_SENSOR_ALLOWED_CHANNELS: (1,)}
}

# List of additional sensors which are created based on a property
# The key is the property name
SENSOR_TYPES: dict[str, ELSensorEntityDescription] = {
    SensorDeviceClass.ENERGY: ELSensorEntityDescription(
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_path='total_energy',
        factor=0.00001,
    ),
    ExtaSensorDeviceClass.MANUAL_ENERGY: ELSensorEntityDescription(
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_path='manual_energy',
        factor=0.00001,
    ),
    ExtaSensorDeviceClass.APPARENT_ENERGY: ELSensorEntityDescription(
        native_unit_of_measurement="kVAh",
        device_class=ExtaSensorDeviceClass.APPARENT_ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        factor=0.00001,
    ),
    ExtaSensorDeviceClass.REACTIVE_ENERGY: ELSensorEntityDescription(
        native_unit_of_measurement="kvarh",
        device_class=ExtaSensorDeviceClass.REACTIVE_ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        factor=0.00001,
    ),
    SensorDeviceClass.POWER: ELSensorEntityDescription(
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDeviceClass.REACTIVE_POWER: ELSensorEntityDescription(
        native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDeviceClass.APPARENT_POWER: ELSensorEntityDescription(
        native_unit_of_measurement=POWER_VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDeviceClass.VOLTAGE: ELSensorEntityDescription(
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        factor=0.01,
    ),
    SensorDeviceClass.POWER_FACTOR: ELSensorEntityDescription(
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        factor=0.001,
    ),
    SensorDeviceClass.CURRENT: ELSensorEntityDescription(
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        factor=0.001,
    ),
    SensorDeviceClass.FREQUENCY: ELSensorEntityDescription(
        native_unit_of_measurement=FREQUENCY_HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        factor=0.01,
    ),
    ExtaSensorDeviceClass.PHASE_SHIFT: ELSensorEntityDescription(
        native_unit_of_measurement=DEGREE,
        device_class=ExtaSensorDeviceClass.PHASE_SHIFT,
        state_class=SensorStateClass.MEASUREMENT,
        factor=0.1,
    ),
    SensorDeviceClass.PRESSURE: ELSensorEntityDescription(
        native_unit_of_measurement=PRESSURE_HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        factor=1,
    ),
    SensorDeviceClass.ILLUMINANCE: ELSensorEntityDescription(
        native_unit_of_measurement=LIGHT_LUX,
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        factor=1,
    ),
    SensorDeviceClass.HUMIDITY: ELSensorEntityDescription(
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        factor=1,
    ),
    SensorDeviceClass.BATTERY: ELSensorEntityDescription(
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        factor=100,
    ),
    SensorDeviceClass.TEMPERATURE: ELSensorEntityDescription(
        native_unit_of_measurement=TEMP_CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        factor=1,
    ),
}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """setup via configuration.yaml not supported anymore"""


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities
):
    """Set up Exta Life sensors based on existing config."""

    core = Core.get(config_entry.entry_id)
    channels = core.get_channels(DOMAIN_SENSOR)

    _LOGGER.debug("Discovery: %s", pformat(channels))
    if channels:
        async_add_entities(
            [ExtaLifeSensor(device, config_entry) for device in channels]
        )

    core.pop_channels(DOMAIN_SENSOR)

    # time for virtual, entity sensors
    for virtual_domain in DOMAIN_VIRTUAL_SENSORS:
        channels = core.get_channels(virtual_domain)
        _LOGGER.debug("Discovery (%s): %s", virtual_domain, pformat(channels))
        if channels:
            async_add_entities(
                [
                    ExtaLifeVirtualSensor(device, config_entry, virtual_domain)
                    for device in channels
                ]
            )

        core.pop_channels(virtual_domain)


class ExtaLifeSensorBase(ExtaLifeChannel, SensorEntity):
    """Representation of Exta Life Sensors"""

    def __init__(self, channel_data, config_entry):
        super().__init__(channel_data, config_entry)

        # self.channel_data = channel_data.get("data")
        self._config: SensorEntityConfig = None

    @property
    def device_class(self):
        return self._config.device_class

    @property
    def native_unit_of_measurement(self):
        return self._config.native_unit_of_measurement

    @property
    def state_class(self) -> SensorStateClass:
        return self._config.state_class

    @property
    def native_value(self):
        """Return state of the sensor"""

        value = self.get_value_from_attr_path(self._config.value_path)

        if value:
            value = value * self._config.factor

        return value

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        attr = super().extra_state_attributes

        data = self.channel_data
        if data.get("sync_time") is not None:
            attr.update({"sync_time": data.get("sync_time")})
        if data.get("last_sync") is not None:
            attr.update({"last_sync": data.get("last_sync")})

        self.format_state_attr(attr)

        return attr

    def on_state_notification(self, data):
        """React on state notification from controller"""

        self.channel_data.update(data)

        # synchronize DataManager data with processed update & entity data
        self.sync_data_update_ha()

    def get_value_from_attr_path(self, path: str):
        """Extract value from encoded path"""
        # Example path: 'phase[1].voltage   -> array phase, row 1, field voltage
        # attr.append({"dev_class": dev_class, "path": f"?phase[{c}]{k}", "unit": unit})
        def find_element(path: str, dictionary: dict):
            """Read field value by path e.g. test[1].value21.
            The path must lead to a single field, nit dict or list. The path is normalized to a '.' separated"""

            def _find_element(keys: list, dictionary: dict):
                rv = dictionary
                if isinstance(dictionary, dict):
                    rv = _find_element(keys[1:], rv[keys[0]])
                elif isinstance(dictionary, list):
                    if keys[0].isnumeric():
                        rv = _find_element(keys[1:], dictionary[int(keys[0])])
                else:
                    return rv
                return rv

            _keys = path.replace("[", ".")
            _keys = _keys.replace("]", "")

            return _find_element(_keys.split("."), dictionary)

        return find_element(path, self.channel_data)

class ExtaLifeSensor(ExtaLifeSensorBase):
    """Representation of Exta Life Sensors"""

    def __init__(self, channel_data, config_entry):
        super().__init__(channel_data, config_entry)

        data = self.channel_data
        dev_type = data.get("type")
        channel = data.get("channel")

        dev_class = None
        if dev_type in DEVICE_ARR_SENS_MULTI:
            dev_class = MAP_EXTA_MULTI_CHN_TO_DEV_CLASS[channel]
        else:
            dev_class = MAP_EXTA_DEV_TYPE_TO_DEV_CLASS[dev_type]

        self._config = SensorEntityConfig(SENSOR_TYPES[dev_class])

        # create virtual, attribute sensors
        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_SENSOR, channel_data)

    @property
    def virtual_sensors(self) -> list:
        """List of config dicts"""
        attr = []
        # return attribute + unit pairs
        data = self.channel_data
        phase = data.get("phase")
        if phase is not None:
            for p in phase:
                for k, v in p.items():      # pylint: disable=unused-variable
                    dev_class = MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS.get(k)
                    if dev_class:
                        attr.append(
                            {
                                VIRT_SENSOR_DEV_CLS: dev_class,
                                VIRT_SENSOR_PATH: f"phase[{phase.index(p)}].{k}",
                            }
                        )

        return attr


class ExtaLifeVirtualSensor(ExtaLifeSensorBase):
    """Representation of Exta Life Sensors"""

    def __init__(self, channel_data, config_entry, virtual_domain):
        super().__init__(channel_data, config_entry)

        self._virtual_domain = virtual_domain
        self._virtual_prop: dict = channel_data.get(VIRT_SENSOR_CHN_FIELD)

        self._config = SensorEntityConfig(SENSOR_TYPES[self._virtual_prop.get(VIRT_SENSOR_DEV_CLS)])

        self.override_config_from_dict(self._virtual_prop)


    def override_config_from_dict(self, override: dict):
        """Override sensor config from a dict"""
        for k, v in override.items():           # pylint: disable=unused-variable
            setattr(self._config, k, v)

    def get_unique_id(self) -> str:
        """Override return a unique ID.
        This will add channel attribute path to uniquely identify the entity"""

        super_id = super().get_unique_id()
        return f"{super_id}-{self._virtual_prop.get(VIRT_SENSOR_PATH)}"

    def get_name_suffix(self, path: str):
        """Derive name suffix for attribute (virtual) sensor entities
        Simply escape special characters with spaces"""

        from re import escape, sub
        from string import punctuation

        chars = escape(punctuation)
        escaped = sub(r"[" + chars + "]", " ", path)
        escaped = sub(' +', ' ', escaped)       # remove double spaces

        return escaped

    @property
    def name(self) -> str:
        """Entity name = default name + escaped name suffix (whitespaces)"""
        return f"{super().name} {self.get_name_suffix(self._virtual_prop.get(VIRT_SENSOR_PATH))}"
