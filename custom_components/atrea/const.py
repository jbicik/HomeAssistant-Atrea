import logging
from datetime import timedelta

from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
    SWING_VERTICAL,
    SWING_HORIZONTAL,
    SWING_BOTH
)
from pyatrea import AtreaMode

DOMAIN = "atrea"
LOGGER = logging.getLogger(__name__)
UPDATE_DELAY = 1  # update delay disabled
MIN_TIME_BETWEEN_SCANS = timedelta(seconds=10)
SUPPORT_FLAGS = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.SWING_MODE
DEFAULT_NAME = "Atrea"
STATE_MANUAL = "manual"
STATE_UNKNOWN = "unknown"
CONF_FAN_MODES = "fan_modes"
CONF_PRESETS = "presets"
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
# SWING_VERTICAL = Zone 0, SWING_HORIZONTAL = Zone 1, SWING_BOTH = Zone 2
SWING_MODES = [SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH]

FAN_MODE_LABELS = {
    0: "Off",
    10: "Min-Vent",
    11: "Norm-Vent",
    12: "Max-Vent",
    20: "Min-Circ",
    21: "Norm-Circ",
    22: "Max-Circ",
    30: "Min/Min",
    31: "Min/Norm",
    32: "Min/Max",
    33: "Norm/Min",
    34: "Norm/Norm",
    35: "Norm/Max",
    36: "Max/Min",
    37: "Max/Norm",
    38: "Max/Max",
}
