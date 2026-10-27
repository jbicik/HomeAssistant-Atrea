import time
import re
import json
from homeassistant.core import HomeAssistant, callback
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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
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
    PRESET_POWER_CODES_BY_MODE,
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
        await super().async_added_to_hass()
        self._enabled = True
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self):
        """Publish every completed coordinator read without another device poll."""
        self.manualUpdate()

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
        return False

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
            valid_codes = PRESET_POWER_CODES_BY_MODE.get(self._current_preset)
            if valid_codes is not None:
                return [
                    name
                    for name, code in PRESET_POWER_CODES.items()
                    if code in valid_codes
                ]
            return list(PRESET_POWER_CODES)
        return self._fan_list

    @staticmethod
    def _matching_preset_power_code(power_code, mode):
        """Keep the selected min/norm/max level valid when its preset changes."""
        if mode not in PRESET_POWER_CODES_BY_MODE or power_code not in PRESET_POWER_CODES.values():
            return None
        if power_code == 0 or mode == AtreaMode.OFF:
            return 0
        if 30 <= power_code <= 38:
            circulation, ventilation = divmod(power_code - 30, 3)
        else:
            circulation = ventilation = power_code % 10
        if mode == AtreaMode.CIRCULATION:
            return 20 + circulation
        if mode in (AtreaMode.AUTOMATIC, AtreaMode.CIRCULATION_AND_VENTILATION):
            return 30 + circulation * 3 + ventilation
        return 10 + ventilation

    @staticmethod
    def _power_code(status, register):
        try:
            return int(status.get(register))
        except (TypeError, ValueError):
            return None

    def _uses_preset_power(self):
        return self._power_control_mode == POWER_CONTROL_PRESET and self._supports_preset_power()

    def _selected_power_code(self, status):
        """Report a selectable level while preserving raw power diagnostics."""
        requested = self._power_code(status, "H10714")
        effective = self._power_code(status, "H10704")
        valid = PRESET_POWER_CODES_BY_MODE.get(self._current_preset, ())
        if requested in valid:
            return requested
        if effective in valid:
            return effective
        return self._matching_preset_power_code(
            requested if requested is not None else effective, self._current_preset
        )

    def _queue_temporary_override(self, register):
        """Override only the scheduled parameter being changed, as the unit UI does."""
        pending = self.atrea.commands.get(register)
        control = int(pending) if pending is not None else self._power_code(
            self.data.get("status") or {}, register
        )
        if control == 1:
            self.atrea.setCommand(register, 2)

    def _queue_matching_power(self, mode):
        if not self._uses_preset_power():
            return None
        status = self.data.get("status") or {}
        requested = self._power_code(status, "H10714")
        if requested is None:
            requested = self._power_code(status, "H10704")
        matching = self._matching_preset_power_code(requested, mode)
        if matching is not None and matching != requested:
            self._queue_temporary_override("H10700")
            self.atrea.setCommand("H10708", matching)
            return matching
        return None

    async def _async_execute_control(self, expected_power=None):
        """Execute one command batch, refresh state and discard the queued commands."""
        self.updatePending = True
        try:
            if not await self.hass.async_add_executor_job(self.atrea.exec):
                raise HomeAssistantError("The Atrea unit did not accept the control command.")
            # Await a fresh read instead of returning while a debounced read is pending.
            await self._coordinator.async_refresh()
            if not self._coordinator.last_update_success or not self.data.get("status"):
                raise HomeAssistantError("Unable to read Atrea state after the control command.")
            self.manualUpdate()
            reported = self._power_code(self.data.get("status") or {}, "H10714")
            if expected_power is not None and reported is not None and reported != expected_power:
                raise HomeAssistantError(
                    f"The Atrea unit still reports requested power {reported}; "
                    f"expected {expected_power}."
                )
        finally:
            self.atrea.commands.clear()
            self.updatePending = False

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

            # H10715 is the requested mode, which determines the selectable power
            # family even when the effective mode is overridden by the unit.
            try:
                self._current_preset = AtreaMode(int(status["H10715"]))
            except (KeyError, TypeError, ValueError):
                self._current_preset = self.atrea.getMode()

            if "H10714" in status:
                self._requested_power = int(status["H10714"])
            elif "H01005" in status:
                self._requested_power = int(self.atrea.getValue("H01005"))

            preset_power = self._uses_preset_power()
            if preset_power:
                power_code = self._selected_power_code(status)
                self._current_fan_mode = next(
                    (name for name, code in PRESET_POWER_CODES.items() if code == power_code),
                    None,
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

            if self._current_preset == AtreaMode.OFF:
                self._current_hvac_mode = HVACMode.OFF

            program = self.atrea.getProgram()
            if any(self._power_code(status, f"H1070{i}") == 2 for i in range(4)):
                program = AtreaProgram.TEMPORARY
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
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        preset_power = self._uses_preset_power()
        expected_power = None
        if preset_power:
            if fan_mode not in self.fan_modes:
                raise ServiceValidationError(
                    f"Power mode {fan_mode!r} is not available for {self.preset_mode}."
                )
            self.atrea.commands.clear()
            self._queue_temporary_override("H10700")
            expected_power = PRESET_POWER_CODES[fan_mode]
            # H10714 is readback; the web control API always writes H10708.
            self.atrea.setCommand("H10708", expected_power)
        else:
            try:
                fan_percent = int(re.sub("[^0-9]", "", fan_mode))
            except (TypeError, ValueError):
                LOGGER.warning("Invalid percentage fan mode: %s", fan_mode)
                return
            fan_percent = min(100, max(12, fan_percent))
            self.atrea.commands.clear()
            if "H10700" in (self.data.get("status") or {}):
                self._queue_temporary_override("H10700")
            elif await self.hass.async_add_executor_job(self.atrea.getProgram) == AtreaProgram.WEEKLY:
                self.atrea.setProgram(AtreaProgram.TEMPORARY)
            self.atrea.setPower(fan_percent)

        await self._async_execute_control(expected_power)

    async def async_turn_on(self):
        self.atrea.commands.clear()
        if "H10701" in (self.data.get("status") or {}):
            self._queue_temporary_override("H10701")
        elif self.air_handling_control == "Manual":
            self.atrea.setProgram(AtreaProgram.MANUAL)
        elif self.air_handling_control == "Schedule":
            self.atrea.setProgram(AtreaProgram.WEEKLY)
        elif self.air_handling_control == "Temporary":
            self.atrea.setProgram(AtreaProgram.TEMPORARY)
        self.atrea.setMode(AtreaMode.VENTILATION)
        expected_power = self._queue_matching_power(AtreaMode.VENTILATION)
        await self._async_execute_control(expected_power)

    async def async_turn_off(self):
        self.atrea.commands.clear()
        if "H10701" in (self.data.get("status") or {}):
            self._queue_temporary_override("H10701")
        elif self.air_handling_control == "Manual":
            self.atrea.setProgram(AtreaProgram.MANUAL)
        elif self.air_handling_control == "Temporary":
            self.atrea.setProgram(AtreaProgram.TEMPORARY)
        else:
            self.atrea.setProgram(AtreaProgram.WEEKLY)
        self.atrea.setMode(AtreaMode.OFF)
        await self._async_execute_control()

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
            return

        self.atrea.commands.clear()

        if program is not None and (
            program != await self.hass.async_add_executor_job(self.atrea.getProgram)
            or any(
                self._power_code(self.data.get("status") or {}, f"H1070{i}")
                not in (None, int(program))
                for i in range(4)
            )
        ):
            self.atrea.setProgram(program)

        if mode is not None and self._current_preset != mode:
            self.atrea.setMode(mode)
        expected_power = self._queue_matching_power(mode) if mode is not None else None
        if self.atrea.commands:
            await self._async_execute_control(expected_power)

    async def async_set_preset_mode(self, preset_mode):
        mode = None
        try:
            mode = AtreaMode(ALL_PRESET_LIST.index(preset_mode))
        except ValueError:
            LOGGER.warn("Chosen preset=%s is incorrect preset.", str(preset_mode))
            return

        if mode == AtreaMode.OFF:
            await self.async_turn_off()
            return

        if preset_mode not in self.preset_modes:
            raise ServiceValidationError(f"Preset {preset_mode!r} is not available.")

        self.atrea.commands.clear()
        if "H10701" in (self.data.get("status") or {}):
            self._queue_temporary_override("H10701")
        elif await self.hass.async_add_executor_job(self.atrea.getProgram) == AtreaProgram.WEEKLY:
            self.atrea.setProgram(AtreaProgram.TEMPORARY)

        if mode != self._current_preset:
            self.atrea.setMode(mode)
        expected_power = self._queue_matching_power(mode)
        if self.atrea.commands:
            await self._async_execute_control(expected_power)

    async def async_set_temperature(self, **kwargs):
        """Set target temperature, temporarily overriding its weekly schedule."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        if not 10 <= temperature <= 40:
            LOGGER.warning(
                "Chosen temperature=%s is incorrect. It needs to be between 10 and 40.",
                str(temperature),
            )
            return

        self.atrea.commands.clear()
        self._queue_temporary_override("H10702")
        self.atrea.setTemperature(temperature)
        await self._async_execute_control()

    async def async_set_swing_mode(self, swing_mode):
        """Set the zone, temporarily overriding only scheduled zone control."""
        if not self._is_swing_mode_enabled() or swing_mode not in self._swing_labels:
            LOGGER.warning("Zone setting (%s) is not supported.", str(swing_mode))
            return
        zone = self._swing_labels.index(swing_mode)
        self.atrea.commands.clear()
        self._queue_temporary_override("H10703")
        self.atrea.setCommand("H10711", zone)
        await self._async_execute_control()

