from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, CONF_PASSWORD, CONF_NAME
from homeassistant.core import callback
from .utils import isAtreaUnit, processFanModes
import voluptuous as vol
from .const import (
    CONF_FAN_MODES,
    CONF_POWER_CONTROL_MODE,
    POWER_CONTROL_PERCENT,
    POWER_CONTROL_PRESET,
    POWER_CONTROL_MODES,
    CONF_CO2_FORMULA,
    DEFAULT_CO2_FORMULA,
    CONF_SWING_MODE_POLICY,
    DEFAULT_SWING_MODE_POLICY,
    SWING_MODE_POLICIES,
    CONF_SWING_LABEL_ZONE_1,
    CONF_SWING_LABEL_ZONE_2,
    CONF_SWING_LABEL_BOTH_ZONES,
    DEFAULT_SWING_LABELS,
    DOMAIN,
    LOGGER,
    CONF_PRESETS,
    ALL_PRESET_LIST,
    DEFAULT_FAN_MODE_LIST,
)
from .utils import validate_co2_formula
from pyatrea import Atrea


@config_entries.HANDLERS.register(DOMAIN)
class FlowHandler(config_entries.ConfigFlow):
    VERSION = 2

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AtreaOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        LOGGER.debug("[ADD DEVICE] Setup process for tapo initiated by user.")
        return await self.async_step_ip()

    async def async_step_dhcp(self, dhcp_discovery):
        return await self.async_step_auth()

    @callback
    def _async_host_already_configured(self, host):
        """See if we already have an entry matching the host."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_IP_ADDRESS) == host:
                return True
        return False

    async def async_step_ip(self, user_input=None):
        """Enter IP Address and verify Tapo device"""
        errors = {}
        host = ""
        port = 80
        if user_input is not None:
            LOGGER.debug("[ADD DEVICE] Verifying IP address")
            try:
                host = user_input[CONF_IP_ADDRESS]
                port = user_input[CONF_PORT]

                if self._async_host_already_configured(host + ":" + str(port)):
                    LOGGER.debug(
                        "[ADD DEVICE][%s:%d] IP:Port already configured.", host, port
                    )
                    raise Exception("already_configured")

                LOGGER.debug(
                    "[ADD DEVICE][%s:%d] Verifying IP address being atrea unit",
                    host,
                    port,
                )
                if not (
                    await self.hass.async_add_executor_job(isAtreaUnit, host, port)
                ):
                    raise Exception("not_atrea_unit")

                self.atreaHost = host
                self.atreaPort = port
                return await self.async_step_auth()

            except Exception as e:
                LOGGER.debug(e)
                if "Failed to establish a new connection" in str(e):
                    errors["base"] = "connection_failed"
                elif "already_configured" in str(e):
                    errors["base"] = "already_configured"
                elif "not_atrea_unit" in str(e):
                    errors["base"] = "not_atrea_unit"
                else:
                    errors["base"] = "unknown"
                    LOGGER.error(e)

        LOGGER.debug("[ADD DEVICE] Showing config flow for IP.")
        return self.async_show_form(
            step_id="ip",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IP_ADDRESS, description={"suggested_value": host}
                    ): str,
                    vol.Required(CONF_PORT, description={"suggested_value": port}): int,
                }
            ),
            errors=errors,
        )

    async def async_step_auth(self, user_input=None):
        """Provide authentication data."""
        errors = {}
        name = "Atrea"
        password = ""
        host = self.atreaHost
        port = self.atreaPort
        if user_input is not None:
            try:
                LOGGER.debug("[ADD DEVICE][%s:%d] Verifying password.", host, port)
                name = user_input[CONF_NAME]
                if CONF_PASSWORD in user_input:
                    password = user_input[CONF_PASSWORD]

                self.atreaPassword = password

                atrea = Atrea(self.atreaHost, self.atreaPort, self.atreaPassword)
                status = await self.hass.async_add_executor_job(atrea.getStatus)
                if not status:
                    raise Exception("Invalid authentication data")

                LOGGER.debug("[ADD DEVICE][%s:%d] Creating new entry.", host, port)
                return self.async_create_entry(
                    title=host + ":" + str(port),
                    data={
                        CONF_IP_ADDRESS: host,
                        CONF_PORT: port,
                        CONF_PASSWORD: password,
                        CONF_NAME: name,
                    },
                )

            except Exception as e:
                LOGGER.debug(e)
                if "Failed to establish a new connection" in str(e):
                    errors["base"] = "connection_failed"
                elif str(e) == "Invalid authentication data":
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "unknown"
                    LOGGER.error(e)

        LOGGER.debug(
            "[ADD DEVICE][%s] Showing config flow for password.", host,
        )
        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, description={"suggested_value": name}): str,
                    vol.Optional(
                        CONF_PASSWORD, description={"suggested_value": password}
                    ): str,
                }
            ),
            errors=errors,
        )


class AtreaOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        #haze 500 - HA 2024.11+ read only atribut
        #self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        errors = {}
        host = self.config_entry.data[CONF_IP_ADDRESS]
        port = self.config_entry.data[CONF_PORT]

        name = ""
        if CONF_NAME in self.config_entry.data:
            name = self.config_entry.data[CONF_NAME]

        password = ""
        if CONF_PASSWORD in self.config_entry.data:
            password = self.config_entry.data[CONF_PASSWORD]

        presets = []
        if CONF_PRESETS in self.config_entry.data:
            presets = self.config_entry.data[CONF_PRESETS]

        fan_modes = DEFAULT_FAN_MODE_LIST
        try:
            if CONF_FAN_MODES in self.config_entry.data and processFanModes(
                self.config_entry.data[CONF_FAN_MODES]
            ):
                fan_modes = self.config_entry.data[CONF_FAN_MODES]
        except Exception as e:
            LOGGER.debug("Incorrect fan modes: " + e)
            # pass

        co2_formula = self.config_entry.options.get(
            CONF_CO2_FORMULA,
            self.config_entry.data.get(CONF_CO2_FORMULA, DEFAULT_CO2_FORMULA),
        )
        swing_mode_policy = self.config_entry.options.get(
            CONF_SWING_MODE_POLICY, DEFAULT_SWING_MODE_POLICY
        )
        power_control_mode = self.config_entry.options.get(
            CONF_POWER_CONTROL_MODE, POWER_CONTROL_PERCENT
        )
        swing_labels = (
            self.config_entry.options.get(
                CONF_SWING_LABEL_ZONE_1, DEFAULT_SWING_LABELS[0]
            ),
            self.config_entry.options.get(
                CONF_SWING_LABEL_ZONE_2, DEFAULT_SWING_LABELS[1]
            ),
            self.config_entry.options.get(
                CONF_SWING_LABEL_BOTH_ZONES, DEFAULT_SWING_LABELS[2]
            ),
        )

        LOGGER.debug(
            "[%s] Opened Atrea options.", self.config_entry.data[CONF_IP_ADDRESS]
        )
        if user_input is not None:
            LOGGER.debug("Verifying user input...")
            try:
                LOGGER.debug("Loading name...")
                if CONF_NAME in user_input:
                    name = user_input[CONF_NAME]

                LOGGER.debug("Loading password...")
                if CONF_PASSWORD in user_input:
                    password = user_input[CONF_PASSWORD]
                else:
                    password = ""

                LOGGER.debug("Loading fan_modes...")
                if CONF_FAN_MODES in user_input:
                    fan_modes = user_input[CONF_FAN_MODES]

                power_control_mode = user_input.get(
                    CONF_POWER_CONTROL_MODE, power_control_mode
                )
                if power_control_mode not in POWER_CONTROL_MODES:
                    raise Exception("Invalid power control mode")

                co2_formula = user_input.get(CONF_CO2_FORMULA, co2_formula).strip()
                if not validate_co2_formula(co2_formula):
                    raise Exception("Invalid CO2 formula")

                swing_mode_policy = user_input.get(
                    CONF_SWING_MODE_POLICY, swing_mode_policy
                )
                swing_labels = (
                    user_input.get(CONF_SWING_LABEL_ZONE_1, swing_labels[0]).strip(),
                    user_input.get(CONF_SWING_LABEL_ZONE_2, swing_labels[1]).strip(),
                    user_input.get(
                        CONF_SWING_LABEL_BOTH_ZONES, swing_labels[2]
                    ).strip(),
                )
                if (
                    swing_mode_policy not in SWING_MODE_POLICIES
                    or (
                        swing_mode_policy != "disabled"
                        and (
                            any(not label for label in swing_labels)
                            or len(set(swing_labels)) != len(swing_labels)
                        )
                    )
                ):
                    raise Exception("Invalid swing mode configuration")

                LOGGER.debug("Verifying format of fan modes...")
                if not processFanModes(fan_modes):
                    raise Exception("Invalid fan mode format")

                LOGGER.debug("Preparing save object: ip, password, name")
                data = {
                    CONF_IP_ADDRESS: host,
                    CONF_PORT: port,
                    CONF_PASSWORD: password,
                    CONF_NAME: name,
                }
                LOGGER.debug("Preparing save object: fan_modes")
                data[CONF_FAN_MODES] = fan_modes
                LOGGER.debug("Preparing save object: presets")
                data[CONF_PRESETS] = {}
                for preset in ALL_PRESET_LIST:
                    if preset in user_input:
                        data[CONF_PRESETS][preset] = user_input[preset]

                LOGGER.debug("Verifying password...")
                if password != self.config_entry.data[CONF_PASSWORD]:
                    atrea = Atrea(host, port, password)
                    status = await self.hass.async_add_executor_job(atrea.getStatus)
                    if not status:
                        raise Exception("Invalid authentication data")

                LOGGER.debug("Saving entity...")
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data,
                )
                options = dict(self.config_entry.options)
                options[CONF_POWER_CONTROL_MODE] = power_control_mode
                options[CONF_CO2_FORMULA] = co2_formula
                options[CONF_SWING_MODE_POLICY] = swing_mode_policy
                options[CONF_SWING_LABEL_ZONE_1] = swing_labels[0]
                options[CONF_SWING_LABEL_ZONE_2] = swing_labels[1]
                options[CONF_SWING_LABEL_BOTH_ZONES] = swing_labels[2]
                return self.async_create_entry(title="", data=options)
            except Exception as e:
                LOGGER.debug(e)
                if "Failed to establish a new connection" in str(e):
                    errors["base"] = "connection_failed"
                elif str(e) == "Invalid authentication data":
                    errors["base"] = "invalid_auth"
                elif str(e) == "Invalid fan mode format":
                    errors["base"] = "invalid_fan_mode"
                elif str(e) == "Invalid CO2 formula":
                    errors["base"] = "invalid_co2_formula"
                elif str(e) == "Invalid swing mode configuration":
                    errors["base"] = "invalid_swing_configuration"
                elif str(e) == "Invalid power control mode":
                    errors["base"] = "invalid_power_control_mode"
                else:
                    errors["base"] = "unknown"
                    LOGGER.error(e)

        LOGGER.debug("Preparing form... password, name, fan_modes, presets header")
        spec = {
            vol.Optional(CONF_PASSWORD, description={"suggested_value": password}): str,
            vol.Optional(CONF_NAME, description={"suggested_value": name}): str,
            vol.Optional(
                CONF_FAN_MODES, description={"suggested_value": fan_modes}
            ): str,
            vol.Optional(
                CONF_POWER_CONTROL_MODE, default=power_control_mode
            ): vol.In(
                {
                    POWER_CONTROL_PERCENT: "Percentage fan speeds",
                    POWER_CONTROL_PRESET: "Preset power levels (R_5 constant flow)",
                }
            ),
            vol.Optional(CONF_CO2_FORMULA, default=co2_formula): str,
            vol.Optional(
                CONF_SWING_MODE_POLICY, default=swing_mode_policy
            ): vol.In(
                {
                    "auto": "Auto (detect from H10511)",
                    "enabled": "Enabled",
                    "disabled": "Disabled",
                }
            ),
            vol.Optional(
                CONF_SWING_LABEL_ZONE_1, default=swing_labels[0]
            ): str,
            vol.Optional(
                CONF_SWING_LABEL_ZONE_2, default=swing_labels[1]
            ): str,
            vol.Optional(
                CONF_SWING_LABEL_BOTH_ZONES, default=swing_labels[2]
            ): str,
        }

        LOGGER.debug("Preparing form... presets")
        for preset in ALL_PRESET_LIST:
            if preset in presets:
                spec[
                    vol.Required(
                        preset, description={"suggested_value": presets[preset]}
                    )
                ] = bool
            else:
                spec[vol.Required(preset, description={"suggested_value": True})] = bool

        LOGGER.debug("Returning form.")

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(spec), errors=errors,
        )
