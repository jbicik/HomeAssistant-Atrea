"""Sensors for ATREA analog inputs and outputs."""

from collections.abc import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_NAME,
    PERCENTAGE,
    UnitOfRatio,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .const import CONF_CO2_FORMULA, DEFAULT_CO2_FORMULA
from .utils import convert_co2_voltage, convert_temperature

VOLT = "V"
VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR = "m³/h"


def convert_millivolts_to_volts(value) -> float:
    """Convert an ATREA voltage register from millivolts to volts."""
    return int(value) / 1000


SENSOR_REGISTERS = {
    "I10211": {
        "key": "outdoor_air_temperature",
        "name": "Outdoor air temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "display_precision": 1,
        "convert": convert_temperature,
    },
    "I10212": {
        "key": "supply_air_temperature",
        "name": "Supply air temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "display_precision": 1,
        "convert": convert_temperature,
    },
    "I10213": {
        "key": "extract_air_temperature",
        "name": "Extract air temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "display_precision": 1,
        "convert": convert_temperature,
    },
    "I10214": {
        "key": "exhaust_air_temperature",
        "name": "Exhaust air temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "display_precision": 1,
        "convert": convert_temperature,
    },
    "I10215": {
        "key": "indoor_air_temperature",
        "name": "Indoor air temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "display_precision": 1,
        "convert": convert_temperature,
    },
    "I11420": {
        "key": "average_outdoor_air_temperature",
        "name": "Average outdoor air temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "display_precision": 1,
        "convert": convert_temperature,
    },
    "I10205": {
        "key": "in1_voltage",
        "name": "IN1 voltage",
        "unit": VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "display_precision": 3,
        "convert": lambda value: int(value) / 1000,
    },
    "I10206": {
        "key": "in2_voltage",
        "name": "IN2 voltage",
        "unit": VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "display_precision": 3,
        "convert": lambda value: int(value) / 1000,
    },
    "H10202": {
        "key": "sa1_output",
        "name": "SA1 output",
        "unit": PERCENTAGE,
        "device_class": None,
        "convert": lambda value: int(value) * 10,
    },
    "H10200": {
        "key": "supply_fan_voltage",
        "name": "Supply fan voltage",
        "unit": VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "display_precision": 3,
        "convert": convert_millivolts_to_volts,
    },
    "H10201": {
        "key": "extract_fan_voltage",
        "name": "Extract fan voltage",
        "unit": VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "display_precision": 3,
        "convert": convert_millivolts_to_volts,
    },
    "H10204": {
        "key": "sc_voltage",
        "name": "SC voltage",
        "unit": VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "display_precision": 3,
        "convert": convert_millivolts_to_volts,
    },
    "I11600": {
        "key": "supply_requested_airflow",
        "name": "Supply requested airflow",
        "unit": VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
        "device_class": None,
        "convert": int,
        "constant_flow_only": True,
    },
    "I11602": {
        "key": "supply_actual_airflow",
        "name": "Supply actual airflow",
        "unit": VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
        "device_class": None,
        "convert": int,
        "constant_flow_only": True,
    },
    "I11601": {
        "key": "extract_requested_airflow",
        "name": "Extract requested airflow",
        "unit": VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
        "device_class": None,
        "convert": int,
        "constant_flow_only": True,
    },
    "I11603": {
        "key": "extract_actual_airflow",
        "name": "Extract actual airflow",
        "unit": VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
        "device_class": None,
        "convert": int,
        "constant_flow_only": True,
    },
    "I11604": {
        "key": "outdoor_requested_airflow",
        "name": "Outdoor requested airflow",
        "unit": VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
        "device_class": None,
        "convert": int,
        "constant_flow_only": True,
    },
    "I11605": {
        "key": "outdoor_actual_airflow",
        "name": "Outdoor actual airflow",
        "unit": VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
        "device_class": None,
        "convert": int,
        "constant_flow_only": True,
    },
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Create sensors for registers supported by the unit."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    known_sensor_keys: set[str] = set()
    co2_formula = entry.options.get(
        CONF_CO2_FORMULA,
        entry.data.get(CONF_CO2_FORMULA, DEFAULT_CO2_FORMULA),
    )
    sensor_definitions = list(SENSOR_REGISTERS.items())
    if co2_formula.strip():
        sensor_definitions.append(
            (
                "I10205",
                {
                    "key": "co2",
                    "name": "CO₂ concentration",
                    "unit": UnitOfRatio.PARTS_PER_MILLION,
                    "device_class": SensorDeviceClass.CO2,
                    "display_precision": 0,
                    "convert": lambda value: convert_co2_voltage(
                        co2_formula, int(value) / 1000
                    ),
                },
            )
        )

    def async_discover_sensors() -> None:
        status = data.get("status") or {}
        entities = []

        for register, description in sensor_definitions:
            sensor_key = description["key"]
            if (
                register not in status
                or sensor_key in known_sensor_keys
                or (
                    description.get("constant_flow_only")
                    and str(status.get("H10510")) != "1"
                )
            ):
                continue
            known_sensor_keys.add(sensor_key)
            entities.append(
                AtreaRegisterSensor(entry, data, register, description)
            )

        if entities:
            async_add_entities(entities)

    async_discover_sensors()
    entry.async_on_unload(coordinator.async_add_listener(async_discover_sensors))


class AtreaRegisterSensor(CoordinatorEntity, SensorEntity):
    """A sensor backed by one ATREA status register."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        entry: ConfigEntry,
        data: dict,
        register: str,
        description: dict,
    ) -> None:
        super().__init__(data["coordinator"])
        self._data = data
        self._register = register
        self._convert = description["convert"]
        self._display_precision = description.get("display_precision")
        self._constant_flow_only = description.get("constant_flow_only", False)

        ip_address = entry.data.get(CONF_IP_ADDRESS)
        device_unique_id = slugify(f"atrea_{ip_address}")
        self._attr_unique_id = slugify(
            f"{device_unique_id}_{description['key']}"
        )
        self._attr_name = description["name"]
        self._attr_native_unit_of_measurement = description["unit"]
        self._attr_device_class = description["device_class"]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_unique_id)},
            "name": entry.data.get(CONF_NAME) or "atrea",
        }

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the preferred number of decimal places."""
        return self._display_precision

    @property
    def available(self) -> bool:
        """Report whether the register is present in the latest status."""
        register_available = (
            super().available
            and self._register in (self._data.get("status") or {})
        )
        if not register_available:
            return False
        return (
            not self._constant_flow_only
            or str((self._data.get("status") or {}).get("H10510")) == "1"
        )

    @property
    def native_value(self):
        """Return the converted register value."""
        value = (self._data.get("status") or {}).get(self._register)
        return None if value is None else self._convert(value)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the source register for diagnostics."""
        return {
            "register": self._register,
            "constant_flow_only": self._constant_flow_only,
        }
