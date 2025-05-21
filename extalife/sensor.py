"""Support for Exta Life sensor devices"""
import logging
from dataclasses import dataclass
from datetime import (
    date,
    datetime,
)
from decimal import Decimal
from enum import StrEnum
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
    UnitOfTemperature,
    UnitOfPressure,
    DEGREE,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfReactivePower,
    UnitOfApparentPower,
    UnitOfEnergy,
    LIGHT_LUX,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import (
    StateType,
)
from typing import (
    Any,
    Mapping,
)

from .helpers.const import (
    DOMAIN_VIRTUAL_SENSORS,
    DOMAIN_VIRTUAL_SENSOR,
    VIRTUAL_SENSOR_CHN_FIELD,
    VIRTUAL_SENSOR_DEV_CLS,
    VIRTUAL_SENSOR_PATH,
    VIRTUAL_SENSOR_ALLOWED_CHANNELS,
)
from .helpers.core import Core
from .helpers.entities import ExtaLifeChannelNamed
from .pyextalife import (  # pylint: disable=syntax-error
    ExtaLifeDeviceModel,
    DEVICE_ARR_SENS_ENERGY_METER,
    DEVICE_ARR_SENS_TEMP,
    DEVICE_ARR_SENS_LIGHT,
    DEVICE_ARR_SENS_HUMID,
    DEVICE_ARR_SENS_PRESSURE,
    DEVICE_ARR_ALL_SENSOR_MULTI,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ELSensorEntityDescription(SensorEntityDescription):
    """Sensor entity config description"""

    key: str = ""
    factor: float = 1  # value scaling factor to have a value in normalized units like Watt, Volt etc
    value_path: str | dict[ExtaLifeDeviceModel, str] = "value_1"  # path to the value field in channel


class SensorEntityConfig:
    """ This class MUST correspond to class ELSensorEntityDescription.
    The task of this class is to have instance-based version of Entity Description/config,
    that can be manipulated / overwritten by Virtual sensors setup"""
    def __init__(self, descr: ELSensorEntityDescription) -> None:
        self.key: str = descr.key
        self.factor: float = descr.factor
        self.value_path: str | dict[ExtaLifeDeviceModel, str] = descr.value_path

        self.native_unit_of_measurement = descr.native_unit_of_measurement
        self.device_class = descr.device_class
        self.state_class: SensorStateClass | str | None = descr.state_class
        self.suggested_display_precision: int | None = descr.suggested_display_precision


class ExtaSensorDeviceClass(StrEnum):
    """ExtaLife custom device classes"""

    # TOTAL_ENERGY = "total_energy"
    APPARENT_ENERGY = "apparent_energy"  # kVAh
    REACTIVE_ENERGY = "reactive_energy"  # kVArh
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

MAP_EXTA_MULTI_CHN_TO_DEV_CLASS: dict[ExtaLifeDeviceModel, dict[int, SensorDeviceClass]] = {
    ExtaLifeDeviceModel.RCM21: {
        1: SensorDeviceClass.TEMPERATURE,
        2: SensorDeviceClass.HUMIDITY,
        3: SensorDeviceClass.PRESSURE,
        4: SensorDeviceClass.ILLUMINANCE,
    },
    ExtaLifeDeviceModel.RCW21: {
        1: SensorDeviceClass.WIND_SPEED,
        2: SensorDeviceClass.ILLUMINANCE,
    }
}

MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS: dict[str, SensorDeviceClass] = {
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
  "battery_status": {VIRTUAL_SENSOR_ALLOWED_CHANNELS: (1,)}
}

# List of additional sensors which are created based on a property
# The key is the property name
# noinspection PyArgumentList
SENSOR_TYPES: dict[SensorDeviceClass | ExtaSensorDeviceClass, ELSensorEntityDescription] = {
    SensorDeviceClass.WIND_SPEED: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_path="value",
        factor=0.277777778,
    ),
    SensorDeviceClass.ENERGY: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_path='total_energy',
        factor=0.00001,
    ),
    ExtaSensorDeviceClass.MANUAL_ENERGY: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
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
        native_unit_of_measurement="kVArh",
        device_class=ExtaSensorDeviceClass.REACTIVE_ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        factor=0.00001,
    ),
    SensorDeviceClass.POWER: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDeviceClass.REACTIVE_POWER: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDeviceClass.APPARENT_POWER: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDeviceClass.VOLTAGE: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
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
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        factor=0.001,
    ),
    SensorDeviceClass.FREQUENCY: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
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
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        factor=1,
    ),
    SensorDeviceClass.ILLUMINANCE: ELSensorEntityDescription(
        native_unit_of_measurement=LIGHT_LUX,
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_path={ExtaLifeDeviceModel.RCW21: "value", },
        factor=1,
    ),
    SensorDeviceClass.HUMIDITY: ELSensorEntityDescription(
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        factor=1,
    ),
    SensorDeviceClass.BATTERY: ELSensorEntityDescription(
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        factor=100,
    ),
    SensorDeviceClass.TEMPERATURE: ELSensorEntityDescription(
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        factor=1,
    ),
}


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up Exta Life sensors based on existing config."""

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:

        channels: list[dict[str, Any]] = core.get_channels(DOMAIN_SENSOR)
        _LOGGER.debug(f"Discovery ({DOMAIN_SENSOR}): {channels}")
        if channels:
            async_add_entities([ExtaLifeSensor(channel_data, config_entry) for channel_data in channels])

        core.pop_channels(DOMAIN_SENSOR)

        # time for virtual, entity sensors
        for virtual_domain in DOMAIN_VIRTUAL_SENSORS:
            channels = core.get_channels(virtual_domain)
            _LOGGER.debug(f"Discovery ({virtual_domain}): {channels}")
            if channels:
                async_add_entities(
                    [ExtaLifeVirtualSensor(channel, config_entry, virtual_domain) for channel in channels]
                )

            core.pop_channels(virtual_domain)

        return None

    await core.platform_register(DOMAIN_SENSOR, async_load_entities)


class ExtaLifeSensorBaseNamed(ExtaLifeChannelNamed, SensorEntity):
    """Representation of Exta Life Sensors"""

    def __init__(self, channel: dict[str, Any],
                 config_entry: ConfigEntry, device_class: SensorDeviceClass | ExtaSensorDeviceClass):
        super().__init__(config_entry, channel)

        self._config: SensorEntityConfig = SensorEntityConfig(SENSOR_TYPES[device_class])

        if isinstance(self._config.value_path, dict):
            self._config.value_path = self._config.value_path.get(self.device_model, "value_1")

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the class of this device, from component SENSOR_CLASSES."""
        return self._config.device_class

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor, if any."""
        return self._config.native_unit_of_measurement

    @property
    def state_class(self) -> SensorStateClass | str | None:
        """Return the state class of this entity, if any."""
        return self._config.state_class

    @property
    def name(self) -> str | None:
        """Return name of the entity"""
        result = super().name
        return result

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the value reported by the sensor."""

        try:
            value = self.get_value_from_attr_path(self._config.value_path)
        except Exception as err:
            _LOGGER.error(f"failed to read sensor native value, device_type={self.device_model.name}, {err}")
            value = 0

        if value:
            if isinstance(value, str) or isinstance(value, int):
                value = float(value)
            value = value * self._config.factor

        return value

    @property
    def suggested_display_precision(self) -> int | None:        
        """Return the suggested number of decimal digits for display."""
        if self._config.suggested_display_precision is None:
            return super().suggested_display_precision
        return self._config.suggested_display_precision

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return device specific state attributes."""

        es_attrs = self._mapping_to_dict(super().extra_state_attributes)

        self._extra_state_attribute_update(self.channel_data, es_attrs, "sync_time")
        self._extra_state_attribute_update(self.channel_data, es_attrs, "last_sync")

        return self._format_state_attr(es_attrs)

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """React on state notification from controller"""
        super().on_state_notification(data)

        self.channel_data.update(data)

        # synchronize DataManager data with processed update & entity data
        self.sync_data_update_ha()

    def get_value_from_attr_path(self, attr_path: str):
        """Extract value from encoded path"""
        # Example path: 'phase[1].voltage'   -> array phase, row 1, field voltage
        # attr.append({"dev_class": dev_class, "path": f"?phase[{c}]{k}", "unit": unit})

        def find_element(path: str, dictionary: dict):
            """Read field value by path e.g. test[1].value21.
            The path must lead to a single field, nit dict or list. The path is normalized to a '.' separated"""

            def _find_element(keys: list, _dictionary: dict):
                rv = _dictionary
                if isinstance(_dictionary, dict):
                    rv = _find_element(keys[1:], rv[keys[0]])
                elif isinstance(_dictionary, list):
                    if keys[0].isnumeric():
                        rv = _find_element(keys[1:], _dictionary[int(keys[0])])
                else:
                    return rv
                return rv

            _keys = path.replace("[", ".")
            _keys = _keys.replace("]", "")

            return _find_element(_keys.split("."), dictionary)

        return find_element(attr_path, self.channel_data)


class ExtaLifeSensor(ExtaLifeSensorBaseNamed):
    """Representation of Exta Life Sensors"""

    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry):

        ch_data: dict[str, Any] = channel.get("data")
        device_type: ExtaLifeDeviceModel = ExtaLifeDeviceModel(ch_data.get("type"))
        channel_no: int = ch_data.get("channel")

        if device_type in DEVICE_ARR_ALL_SENSOR_MULTI:
            device_class = MAP_EXTA_MULTI_CHN_TO_DEV_CLASS[device_type][channel_no]
        else:
            device_class = MAP_EXTA_DEV_TYPE_TO_DEV_CLASS[device_type]

        super().__init__(channel, config_entry, device_class)

        # create virtual, attribute sensors
        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_SENSOR, channel)

    @property
    def virtual_sensors(self) -> list[dict[str, Any]]:
        """List of config dicts"""

        attr = []
        # return attribute + unit pairs
        data = self.channel_data
        phase = data.get("phase")  # this is for MEM-21
        if phase is not None:
            for p in phase:
                for k, v in p.items():      # pylint: disable=unused-variable
                    dev_class = MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS.get(k)
                    if dev_class:
                        attr.append(
                            {
                                VIRTUAL_SENSOR_DEV_CLS: dev_class,
                                VIRTUAL_SENSOR_PATH: f"phase[{phase.index(p)}].{k}",
                            }
                        )

        return attr


class ExtaLifeVirtualSensor(ExtaLifeSensorBaseNamed):
    """Representation of Exta Life Sensors"""

    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry, virtual_domain):

        self._virtual_domain = virtual_domain
        self._virtual_prop: dict[str, Any] = channel.get(VIRTUAL_SENSOR_CHN_FIELD)

        # base constructor must be called here after _virtual_prop assignment
        super().__init__(channel, config_entry, self._virtual_prop.get(VIRTUAL_SENSOR_DEV_CLS))

        self.override_config_from_dict(self._virtual_prop)

    def override_config_from_dict(self, override: dict[str, Any]) -> None:
        """Override sensor config from a dict"""
        for k, v in override.items():           # pylint: disable=unused-variable
            setattr(self._config, k, v)

    def _get_unique_id(self) -> str:
        """Override return a unique ID.
        This will add channel attribute path to uniquely identify the entity"""

        super_id = super()._get_unique_id()
        return f"{super_id}-{self._virtual_prop.get(VIRTUAL_SENSOR_PATH)}"

    @staticmethod
    def get_name_suffix(path: str) -> str:
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
        return f"{super().name} {self.get_name_suffix(self._virtual_prop.get(VIRTUAL_SENSOR_PATH))}"
