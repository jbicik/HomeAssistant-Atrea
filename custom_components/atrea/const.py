import logging
from datetime import timedelta

from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
)
from pyatrea import AtreaMode

DOMAIN = "atrea"
LOGGER = logging.getLogger(__name__)
UPDATE_DELAY = 1  # update delay disabled
MIN_TIME_BETWEEN_SCANS = timedelta(seconds=10)
SUPPORT_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.PRESET_MODE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)
DEFAULT_NAME = "Atrea"
STATE_MANUAL = "manual"
STATE_UNKNOWN = "unknown"
CONF_FAN_MODES = "fan_modes"
CONF_POWER_CONTROL_MODE = "power_control_mode"
POWER_CONTROL_PERCENT = "percent"
POWER_CONTROL_PRESET = "preset"
POWER_CONTROL_MODES = (POWER_CONTROL_PERCENT, POWER_CONTROL_PRESET)
PRESET_POWER_CODES = {
    "Off": 0,
    "Ventilation - Min": 10,
    "Ventilation - Norm": 11,
    "Ventilation - Max": 12,
    "Circulation - Min": 20,
    "Circulation - Norm": 21,
    "Circulation - Max": 22,
    "Circulation Min / Ventilation Min": 30,
    "Circulation Min / Ventilation Norm": 31,
    "Circulation Min / Ventilation Max": 32,
    "Circulation Norm / Ventilation Min": 33,
    "Circulation Norm / Ventilation Norm": 34,
    "Circulation Norm / Ventilation Max": 35,
    "Circulation Max / Ventilation Min": 36,
    "Circulation Max / Ventilation Norm": 37,
    "Circulation Max / Ventilation Max": 38,
}
# Match the controller's mode2Z() rules, using the requested operating mode.
PRESET_POWER_CODES_BY_MODE = {mode: (0, 10, 11, 12) for mode in AtreaMode}
PRESET_POWER_CODES_BY_MODE.update({
    AtreaMode.OFF: (0,),
    AtreaMode.AUTOMATIC: (0, 30, 31, 32, 33, 34, 35, 36, 37, 38),
    AtreaMode.CIRCULATION: (0, 20, 21, 22),
    AtreaMode.CIRCULATION_AND_VENTILATION: (0, 30, 31, 32, 33, 34, 35, 36, 37, 38),
})
CONF_PRESETS = "presets"
CONF_CO2_FORMULA = "co2_formula"
DEFAULT_CO2_FORMULA = "round(x * 200)"
CONF_SWING_MODE_POLICY = "swing_mode_policy"
DEFAULT_SWING_MODE_POLICY = "auto"
SWING_MODE_POLICIES = ("auto", "enabled", "disabled")
CONF_SWING_LABEL_ZONE_1 = "swing_label_zone_1"
CONF_SWING_LABEL_ZONE_2 = "swing_label_zone_2"
CONF_SWING_LABEL_BOTH_ZONES = "swing_label_both_zones"
DEFAULT_SWING_LABELS = ("SZ1", "SZ2", "SZ1 + SZ2")
DEFAULT_FAN_MODE_LIST = "12,20,30,40,50,60,70,80,90,100"
ALL_PRESET_LIST = [
    "Off",
    "Automatic",
    "Ventilation",
    "Circulation and Ventilation",
    "Circulation",
    "Night precooling",
    "Disbalance",
    "Overpressure",
    "Periodic ventilation",
    "Startup",
    "Rundown",
    "Defrosting",
    "External",
    "HP defrosting",
    "IN1",
    "IN2",
    "D1",
    "D2",
    "D3",
    "D4",
]

ICONS = {
    AtreaMode.OFF: "mdi:fan-off",
    AtreaMode.AUTOMATIC: "mdi:fan",
    AtreaMode.VENTILATION: "mdi:fan-chevron-up",
    AtreaMode.CIRCULATION_AND_VENTILATION: "mdi:fan",
    AtreaMode.CIRCULATION: "mdi:fan-chevron-down",
    AtreaMode.NIGHT_PRECOOLING: "mdi:fan-speed-1",
    AtreaMode.DISBALANCE: "mdi:fan-speed-2",
    AtreaMode.OVERPRESSURE: "mdi:fan-speed-3",
    AtreaMode.STARTUP: "mdi:chevron-up",
    AtreaMode.RUNDOWN: "mdi:chevron-down",
    AtreaMode.DEFROSTING: "mdi:car-defrost-rear",
    AtreaMode.EXTERNAL: "mdi:fan-alert",
    AtreaMode.HP_DEFROSTING: "mdi:car-defrost-front",
    AtreaMode.IN1: "mdi:fan-chevron-up",
    AtreaMode.IN2: "mdi:fan-chevron-up",
    AtreaMode.D1: "mdi:fan-chevron-up",
    AtreaMode.D2: "mdi:fan-chevron-up",
    AtreaMode.D3: "mdi:fan-chevron-up",
    AtreaMode.D4: "mdi:fan-chevron-up",
}

HVAC_MODES = [HVACMode.OFF, HVACMode.AUTO, HVACMode.FAN_ONLY]
