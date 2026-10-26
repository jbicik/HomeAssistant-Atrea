import time
import re
import json
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import slugify
from homeassistant.components.climate.const import ClimateEntityFeature, HVACAction


from custom_components.atrea.utils import convert_temperature, processFanModes

try:
    from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
except ImportError:
    from homeassistant.components.climate import (
        ClimateDevice as ClimateEntity,
        PLATFORM_SCHEMA,
    )
from homeassistant.components.climate.const import (
    HVACMode
)
from homeassistant.const import (
    CONF_NAME,
    CONF_IP_ADDRESS,
    UnitOfTemperature,
    ATTR_TEMPERATURE,
)
from homeassistant.util import Throttle
from homeassistant.helpers import device_registry as dr
from typing import Callable
from pyatrea import AtreaProgram, AtreaMode

from .const import (
    DOMAIN,
    LOGGER,
    UPDATE_DELAY,
    MIN_TIME_BETWEEN_SCANS,
    SUPPORT_FLAGS,
    STATE_UNKNOWN,
    CONF_FAN_MODES,
    CONF_POWER_CONTROL_MODE,
    POWER_CONTROL_PERCENT,
    POWER_CONTROL_PRESET,
    PRESET_POWER_CODES,
    CONF_PRESETS,
    DEFAULT_FAN_MODE_LIST,
    ALL_PRESET_LIST,
    ICONS,
    HVAC_MODES,
    CONF_SWING_MODE_POLICY,
    DEFAULT_SWING_MODE_POLICY,
    CONF_SWING_LABEL_ZONE_1,
    CONF_SWING_LABEL_ZONE_2,
    CONF_SWING_LABEL_BOTH_ZONES,
    DEFAULT_SWING_LABELS,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Callable
):
    sensor_name = entry.data.get(CONF_NAME)
    if sensor_name is None:
        sensor_name = "atrea"

    fan_list = entry.data.get(CONF_FAN_MODES)
    if fan_list is None:
        fan_list = DEFAULT_FAN_MODE_LIST

    # todo: verify this works with options
    preset_list = entry.data.get(CONF_PRESETS)
    if preset_list is None:
        preset_list = {}
        for preset in ALL_PRESET_LIST:
            preset_list[preset] = True

    hass.data[DOMAIN][entry.entry_id]["climate"] = AtreaDevice(
        hass, entry, sensor_name, fan_list, preset_list
    )

    async_add_entities([hass.data[DOMAIN][entry.entry_id]["climate"]])


class AtreaDevice(ClimateEntity):
    def __init__(
        self, hass, entry, sensor_name, fan_list, preset_list,
    ):
        super().__init__()
        self.data = hass.data[DOMAIN][entry.entry_id]
        self.atrea = self.data["atrea"]
        self._coordinator = self.data["coordinator"]
        self._userLabels = self.data["userLabels"]
        self.ip = entry.data.get(CONF_IP_ADDRESS)
        self.updatePending = False
        self._preset_list = []
        self._warnings = []
        self._name = sensor_name
        self._current_fan_mode = None
        self._power_control_mode = entry.options.get(
            CONF_POWER_CONTROL_MODE, POWER_CONTROL_PERCENT
        )
        self._alerts = []
        self._outside_temp = 0.0
        self._inside_temp = 0.0
        self._supply_air_temp = 0.0
        self._exhaust_temp = 0.0
        self._extract_temp = 0.0
        self._requested_temp = 0.0
        self._requested_power = None
        self._active_inputs = []
        self._forced_mode = None
        self._current_power = None
        self._in1 = None
        self._in2 = None
        self._sa1 = None
        self._current_preset = None
        self._current_hvac_mode = None
        self._unit = "Status"
        self.air_handling_control = None
        self._enabled = False
        self._cooling = -1
        self._heating = -1
        self._zone = -1
        self._swing_mode_policy = entry.options.get(
            CONF_SWING_MODE_POLICY, DEFAULT_SWING_MODE_POLICY
        )
        self._swing_labels = (
            entry.options.get(CONF_SWING_LABEL_ZONE_1, DEFAULT_SWING_LABELS[0]),
            entry.options.get(CONF_SWING_LABEL_ZONE_2, DEFAULT_SWING_LABELS[1]),
            entry.options.get(
                CONF_SWING_LABEL_BOTH_ZONES, DEFAULT_SWING_LABELS[2]
            ),
        )

        self.updatePresetList(preset_list, False)
        self.updateFanList(fan_list, False)
        self.manualUpdate(False)

    def updatePresetList(self, preset_list, updateState=True):
        self._preset_list = []
        for required_preset in preset_list:
            if preset_list[required_preset]:
                for i, preset_supported in self.data["supportedModes"]:
                    if preset_supported and ALL_PRESET_LIST[i] == required_preset:
                        self._preset_list.append(ALL_PRESET_LIST[i])
        if updateState:
            self.async_schedule_update_ha_state(True)

    def updateFanList(self, fan_list, updateState=True):
        self._fan_list = processFanModes(fan_list)
        if updateState:
            self.async_schedule_update_ha_state(True)

    def updatePowerControlMode(self, mode, updateState=True):
        self._power_control_mode = mode
        if updateState:
            self.async_schedule_update_ha_state(True)

    def updateName(self, name, updateState=True):
        self._name = name
        if updateState:
            self.async_schedule_update_ha_state(True)

    async def async_added_to_hass(self) -> None:
        self._enabled = True

    async def async_will_remove_from_hass(self) -> None:
        self._enabled = False

    def getUniqueID(self):
        return slugify(f"atrea_{self.ip}")

    @property
    def brand(self):
        return "ATREA s.r.o."

    @property
    def model(self):
        if self._model:
            return self._model["category"] + " " + self._model["model"]
        return False

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.getUniqueID())},
            "name": self.name,
            "manufacturer": self.brand,
            "model": self.model,
            "sw_version": self._swVersion,
            "hw_version": self._id,
            "connections": {},
        }

    @property
    def should_poll(self):
        return True

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def icon(self):
        if len(self._alerts) > 0:
            return "mdi:fan-alert"
        elif self.fan_mode == "0%":
            return "mdi:fan-off"
        elif self._current_preset in ICONS:
            return ICONS[self._current_preset]
        else:
            return "mdi:fan"

    @property
    def state(self):
        return self._current_hvac_mode

    @property
    def supported_features(self):
        features = SUPPORT_FLAGS
        if self._is_swing_mode_enabled():
            features |= ClimateEntityFeature.SWING_MODE
        return features

    def _is_swing_mode_enabled(self):
        """Respect the configured override or auto-detect configured zones."""
        policy = self._swing_mode_policy
        if policy == "enabled":
            return True
        if policy == "disabled":
            return False
        try:
            return int((self.data.get("status") or {}).get("H10511", 0)) == 1
        except (TypeError, ValueError):
            return False

    @property
    def unique_id(self) -> str:
        return self.getUniqueID()

    @property
    def name(self):
        return "{}".format(self._name)

    @property
    def extra_state_attributes(self):
        attributes = {}

        attributes["outside_temp"] = self._outside_temp
        attributes["inside_temp"] = self._inside_temp
        attributes["supply_air_temp"] = self._supply_air_temp
        attributes["requested_temp"] = self._requested_temp
        attributes["exhaust_temp"] = self._exhaust_temp
        attributes["extract_temp"]= self._extract_temp
        attributes["requested_power"] = self._requested_power
        attributes["warnings"] = self._warnings
        attributes["alerts"] = self._alerts
        attributes["program"] = self.air_handling_control
        attributes['zone'] = self._zone
        attributes["active_inputs"] = self._active_inputs
        attributes["forced_mode"] = self._forced_mode.name
        attributes["current_power"] = self._current_power

        if self._in1 is not None:
            attributes["in1"] = self._in1
        if self._in2 is not None:
            attributes["in2"] = self._in2
        if self._sa1 is not None:
            attributes["sa1"] = self._sa1

        if self._heating == 1:
            attributes["hvac_action"] = HVACAction.HEATING
        elif self._cooling == 1:
            attributes["hvac_action"] = HVACAction.COOLING
        elif self._current_hvac_mode == HVACMode.OFF:
            attributes["hvac_action"] = HVACAction.OFF
        elif "hvac_action" in attributes:
            del attributes["hvac_action"]
        return attributes

    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature(self):
        return float(self._requested_temp)

    @property
    def hvac_modes(self):
        return HVAC_MODES

    @property
    def hvac_mode(self):
        return self._current_hvac_mode

    @property
    def preset_mode(self):
        if self._current_preset.name and self._current_preset.name in self._userLabels:
            return self._userLabels[self._current_preset.name]
        elif self._current_preset < len(ALL_PRESET_LIST):
            return ALL_PRESET_LIST[self._current_preset]
        else:
            return STATE_UNKNOWN

    @property
    def preset_modes(self):
        return self._preset_list

    @property
    def current_temperature(self):
        return float(self._inside_temp)

    @property
    def min_temp(self):
        return 10

    @property
    def max_temp(self):
        return 40

    @property
    def fan_mode(self):
        return self._current_fan_mode

    @property
    def fan_modes(self):
        if self._power_control_mode == POWER_CONTROL_PRESET and self._supports_preset_power():
            return list(PRESET_POWER_CODES)
        return self._fan_list

    def _supports_preset_power(self):
        try:
            return int((self.data.get("status") or {}).get("H10510", -1)) == 4
        except (TypeError, ValueError):
            return False

    @property
    def program(self):
        return self.air_handling_control

    @property
    def hvac_action(self):
        if (self._heating == 1):
            return HVACAction.HEATING
        elif (self._cooling == 1):
            return HVACAction.COOLING
        elif (self._current_hvac_mode == HVACMode.OFF):
            return HVACAction.OFF
        else:
            return HVACAction.FAN

    @property
    def swing_modes(self):
        return list(self._swing_labels) if self._is_swing_mode_enabled() else []

    @property
    def swing_mode(self):
        if not self._is_swing_mode_enabled() or self._zone not in (0, 1, 2):
            return None
        return self._swing_labels[self._zone]

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    async def async_update(self):
        if not self.updatePending:
            self.updatePending = True
            await self._coordinator.async_request_refresh()
            await self.hass.async_add_executor_job(time.sleep, UPDATE_DELAY / 1000)
            self.manualUpdate()
            self.updatePending = False

    def manualUpdate(self, updateState=True):
        status = self.data["status"]
        self._id = self.atrea.getID()
        self._model = self.data["model"]
        self._swVersion = self.atrea.getVersion()
        self._warnings = []
        self._alerts = []
        self._active_inputs = []
        if status != False:

            if "I10211" in status:
                self._outside_temp = convert_temperature(status["I10211"])
            elif "I00202" in status:
                if self.atrea.getValue("I00202") == 126.0:
                    if self.atrea.getValue("H00511") == 1:
                        self._outside_temp = self.atrea.getValue("I00200")
                    elif self.atrea.getValue("H00511") == 1:
                        self._outside_temp = self.atrea.getValue("I00201")
                else:
                    self._outside_temp = self.atrea.getValue("I00202")

            # inside temperature is defined by T-IDA
            if "I10215" in status:
                self._inside_temp = convert_temperature(status["I10215"])

            if "I10212" in status:
                self._supply_air_temp = convert_temperature(status["I10212"])
            elif "I00200" in status:
                self._supply_air_temp = self.atrea.getValue("I00200")

            if "I10214" in status:
                self._exhaust_temp = convert_temperature(status["I10214"])

            if "I10213" in status:
                self._extract_temp = convert_temperature(status["I10213"])

            if "H10706" in status:
                self._requested_temp = float(status["H10706"]) / 10
            elif "H01006" in status:
                self._requested_temp = self.atrea.getValue("H01006")

            if "H10714" in status:
                self._requested_power = int(status["H10714"])
            elif "H01005" in status:
                self._requested_power = int(self.atrea.getValue("H01005"))

            preset_power = (
                self._power_control_mode == POWER_CONTROL_PRESET
                and self._supports_preset_power()
            )
            if preset_power:
                # Show the selected/requested code. H10704 is the effective
                # code and may differ from the selection made on the unit.
                if str(status.get("H10700")) == "0":
                    requested_code = status.get("H10708")
                else:
                    requested_code = status.get("H10714")
                if requested_code is None:
                    requested_code = status.get("H10704")
            else:
                requested_code = None

            if preset_power and requested_code is not None:
                power_code = int(requested_code)
                self._current_fan_mode = next(
                    (name for name, code in PRESET_POWER_CODES.items() if code == power_code),
                    str(power_code),
                )
            elif "H01001" in status:
                self._current_fan_mode = str(int(self.atrea.getValue("H01001"))) + "%"
            else:
                self._current_fan_mode = str(self._requested_power) + "%"

            if "C10215" in status:
                self._heating = int(status["C10215"])
            else:
                self._heating = -1

            if "C10216" in status:
                self._cooling = int(status["C10216"])
            else:
                self._cooling = -1

            if "H10707" in status:
                # H10707 is the currently requested zone. H10711 only stores
                # the last manually selected zone, which can differ in a schedule.
                self._zone = int(status["H10707"])
            else:
                self._zone = -1

            # Input IN1
            if "I10205" in status:
                self._in1 = int(status["I10205"])

            # Input IN2
            if "I10206" in status:
                self._in2 = int(status["I10206"])

            # Output SA1
            if "H10202" in status:
                self._sa1 = int(status["H10202"])

            # D1..D4 inputs are reported in D10200..D10203
            for inpt in range(4):
                entry = f"D1020{inpt}"
                if entry in status and int(status[entry]):
                    self._active_inputs.append(f"D{inpt + 1}")

            self._forced_mode = self.atrea.getForcedMode()

            if "H10704" in status:
                self._current_power = int(status["H10704"])

            self._current_preset = self.atrea.getMode()
            if self._current_preset == AtreaMode.OFF:
                self._current_hvac_mode = HVACMode.OFF

            program = self.atrea.getProgram()
            if program == AtreaProgram.MANUAL:
                self.air_handling_control = "Manual"
                if self.atrea.getValue("H10705") == 0:
                    self._current_hvac_mode = HVACMode.OFF
                else:
                    self._current_hvac_mode = HVACMode.FAN_ONLY
            elif program == AtreaProgram.WEEKLY:
                self.air_handling_control = "Schedule"
                self._current_hvac_mode = HVACMode.AUTO
            elif program == AtreaProgram.TEMPORARY:
                self.air_handling_control = "Temporary"
                if self.atrea.getValue("H10705") == 0:
                    self._current_hvac_mode = HVACMode.OFF
                else:
                    self._current_hvac_mode = HVACMode.FAN_ONLY
            else:
                self.air_handling_control = "Unknown (" + str(program) + ")"

            if self._current_fan_mode in ("0%", "Off"):
                self._current_hvac_mode = HVACMode.OFF

            # todo fix warning not translated
            params = self.atrea.getParams()
            for warning in params["warning"]:
                if status[warning] == "1":
                    self._warnings.append(self.atrea.getTranslation(warning))

            for alert in params["alert"]:
                if status[alert] == "1":
                    self._alerts.append(self.atrea.getTranslation(alert))

        else:
            self._current_hvac_mode = None
        if updateState:
            self.async_schedule_update_ha_state(True)

    async def async_set_fan_mode(self, fan_mode):
        preset_power = (
            self._power_control_mode == POWER_CONTROL_PRESET
            and self._supports_preset_power()
        )
        if preset_power:
            if fan_mode not in PRESET_POWER_CODES:
                LOGGER.warning("Unsupported preset power: %s", fan_mode)
                return
            program = await self.hass.async_add_executor_job(self.atrea.getProgram)
            if program == AtreaProgram.WEEKLY:
                self.atrea.setProgram(AtreaProgram.TEMPORARY)
                power_register = "H10714"
            elif program == AtreaProgram.TEMPORARY:
                power_register = "H10714"
            else:
                power_register = "H10708"
            self.atrea.setCommand(power_register, PRESET_POWER_CODES[fan_mode])
        else:
            try:
                fan_percent = int(re.sub("[^0-9]", "", fan_mode))
            except (TypeError, ValueError):
                LOGGER.warning("Invalid percentage fan mode: %s", fan_mode)
                return
            fan_percent = min(100, max(12, fan_percent))
            if (
                await self.hass.async_add_executor_job(self.atrea.getProgram)
                == AtreaProgram.WEEKLY
            ):
                self.atrea.setProgram(AtreaProgram.TEMPORARY)
            self.atrea.setPower(fan_percent)

        self.updatePending = True
        await self.hass.async_add_executor_job(self.atrea.exec)
        await self._coordinator.async_request_refresh()
        await self.hass.async_add_executor_job(time.sleep, UPDATE_DELAY / 1000)
        self.updatePending = False
        self.manualUpdate()

    async def async_turn_on(self):
        if self.air_handling_control == "Manual":
            self.atrea.setProgram(AtreaProgram.MANUAL)
            self._current_hvac_mode = HVACMode.FAN_ONLY
        elif self.air_handling_control == "Schedule":
            self.atrea.setProgram(AtreaProgram.WEEKLY)
            self._current_hvac_mode = HVACMode.AUTO
        elif self.air_handling_control == "Temporary":
            self.atrea.setProgram(AtreaProgram.TEMPORARY)
            self._current_hvac_mode = HVACMode.FAN_ONLY
        self.atrea.setMode(AtreaMode.VENTILATION)

        self.updatePending = True
        await self.hass.async_add_executor_job(self.atrea.exec)
        await self._coordinator.async_request_refresh()
        await self.hass.async_add_executor_job(time.sleep, UPDATE_DELAY / 1000)
        self.manualUpdate()
        self.updatePending = False

    async def async_turn_off(self):
        if self.air_handling_control == "Manual":
            self.atrea.setProgram(AtreaProgram.MANUAL)
        elif self.air_handling_control == "Temporary":
            self.atrea.setProgram(AtreaProgram.TEMPORARY)
        else:
            self.atrea.setProgram(AtreaProgram.WEEKLY)

        self._current_hvac_mode = HVACMode.OFF
        self.atrea.setMode(AtreaMode.OFF)

        self.updatePending = True
        await self.hass.async_add_executor_job(self.atrea.exec)
        await self._coordinator.async_request_refresh()
        await self.hass.async_add_executor_job(time.sleep, UPDATE_DELAY / 1000)
        self.manualUpdate()
        self.updatePending = False

    async def async_set_hvac_mode(self, hvac_mode):
        mode = None
        program = None
        if hvac_mode == HVACMode.AUTO:
            self._current_hvac_mode = HVACMode.AUTO
            program = AtreaProgram.WEEKLY
        elif hvac_mode == HVACMode.FAN_ONLY:
            mode = AtreaMode.VENTILATION
            program = AtreaProgram.MANUAL
            self._current_hvac_mode = HVACMode.FAN_ONLY
        elif hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            self._current_hvac_mode = HVACMode.OFF

        if program != None and program != await self.hass.async_add_executor_job(
            self.atrea.getProgram
        ):
            self.atrea.setProgram(program)

        if (
            mode != None and self._current_preset != mode
        ) or self.air_handling_control == "Schedule":
            self.atrea.setMode(mode)

        self.updatePending = True
        await self.hass.async_add_executor_job(self.atrea.exec)
        await self._coordinator.async_request_refresh()
        await self.hass.async_add_executor_job(time.sleep, UPDATE_DELAY / 1000)
        self.manualUpdate()
        self.updatePending = False

    async def async_set_preset_mode(self, preset_mode):
        mode = None
        try:
            mode = AtreaMode(ALL_PRESET_LIST.index(preset_mode))
        except ValueError:
            LOGGER.warn("Chosen preset=%s is incorrect preset.", str(preset_mode))
            return

        if mode == AtreaMode.OFF:
            await self.async_turn_off()
        if (
            await self.hass.async_add_executor_job(self.atrea.getProgram)
            == AtreaProgram.WEEKLY
        ):
            self.atrea.setProgram(AtreaProgram.TEMPORARY)
        if mode != await self.hass.async_add_executor_job(self.atrea.getMode):
            self.atrea.setMode(mode)

        self.updatePending = True
        await self.hass.async_add_executor_job(self.atrea.exec)
        await self._coordinator.async_request_refresh()
        await self.hass.async_add_executor_job(time.sleep, UPDATE_DELAY / 1000)
        self.manualUpdate()
        self.updatePending = False

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        elif temperature >= 10 and temperature <= 40:
            self.atrea.setTemperature(temperature)
            self.updatePending = True
            await self.hass.async_add_executor_job(self.atrea.exec)
            await self._coordinator.async_request_refresh()
            await self.hass.async_add_executor_job(time.sleep, UPDATE_DELAY / 1000)
            self.manualUpdate()
            self.updatePending = False
        else:
            LOGGER.warn(
                "Chosen temperature=%s is incorrect. It needs to be between 10 and 40.",
                str(temperature),
            )

    async def async_set_swing_mode(self, swing_mode):
        """Set new target swing operation."""
        LOGGER.debug("Setting swing mode to %s", str(swing_mode))
        if not self._is_swing_mode_enabled() or swing_mode not in self._swing_labels:
            LOGGER.warn(
                "Zone setting (%s) is not supported.", str(swing_mode))
            return
        zone = self._swing_labels.index(swing_mode)
        LOGGER.debug("Setting zone to %s", zone)
        self.updatePending = True
        try:
            # Transition H10703 from 1 to 2 before applying the zone.
            if self.atrea.getValue("H10703") == 1:
                self.atrea.setCommand("H10703", 2)
            self.atrea.setCommand("H10711", zone)

            result = await self.hass.async_add_executor_job(self.atrea.exec)
            if result is not False:
                LOGGER.error("Error setting zone to %s", zone)

            await self._coordinator.async_request_refresh()
            await self.hass.async_add_executor_job(
                time.sleep, UPDATE_DELAY / 1000
            )
            self.manualUpdate()
        finally:
            self.updatePending = False

