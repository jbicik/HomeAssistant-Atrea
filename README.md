# HomeAssistant-Atrea

Custom component - climate platform - for Atrea ventilation units for Home Assistant

## Installation using HACS

HACS is a community store for Home Assistant. You can install [HACS](https://github.com/custom-components/hacs) and then install Atrea from the HACS store.

## Installation:

1. In your Home Assistant instance, create directory `/custom_components/atrea` in your `/config` directory.
2. Copy all files from [/custom_components/atrea](https://github.com/JurajNyiri/HomeAssistant-Atrea/tree/master/custom_components/atrea) of this repository to the newly created directory in your Home Assistant.

## Usage:

Add climate unit via Integrations (search for Atrea) in Home Assistant UI. You can also simply click the button below if you have MyHomeAssistant redirects set up.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=atrea)

Active warnings and alerts are exposed as button entities on the Atrea device.
Each button includes the condition's parameter code, severity, and translated
message. The button becomes unavailable when the condition clears. The filter
replacement warning can be acknowledged from its button. Alert buttons use the
unit's global alarm reset command, matching the original web UI. Other warning
buttons report that their condition cannot be acknowledged because the web UI
does not provide an acknowledgement action for them.

IN1 and IN2 are exposed as voltage sensors and SA1 as a percentage sensor. The
CO₂ sensor uses a configurable formula in the integration options. In the
formula, `x` is the IN1 voltage in volts and the result is ppm. The default
`round(x * 200)` preserves the previous conversion; leave the formula empty to
disable the CO₂ sensor.

The integration also exposes airflow requirements and measurements, and
heat-pump defrost state when their registers are available. Airflow values are
only meaningful in constant-flow operation; ODA airflow applies to supported
R5 units.

Fan power control can be configured as percentage speeds or as preset levels.
Preset control is available when the unit reports `H10510 = 4` (R_5 constant
flow). It offers Off, Min/Norm/Max levels for ventilation (codes 10–12),
Min/Norm/Max levels for circulation (20–22), and paired circulation/ventilation
levels (30–38). Paired labels list circulation first and ventilation second.
The fan-mode dropdown follows the controller's requested operating preset:
Ventilation, Night precooling, Disbalance and Overpressure use ventilation levels;
Circulation uses circulation levels; Automatic and Circulation and Ventilation
use paired levels. Off is included in each list. The Off preset offers only Off.
Changing presets preserves the matching Min/Norm/Max level and updates the
power request when it belongs to a different family.
Units without that capability continue to expose the configured percentage
speeds.
Requested power is read from `H10714`, with effective power in `H10704`.
If an old request belongs to another preset, the dropdown displays the matching
effective level (or converts the request to the current family). Both raw codes
remain available for diagnostics. Power commands always write `H10708`, including
Temporary operation. Only the schedule flag for a changed parameter is overridden.

Outdoor, averaged outdoor, supply, extract, exhaust, and indoor air
temperatures are available as native sensors. D1–D4 inputs are exposed as
binary sensors.

Swing modes are enabled automatically when the unit's `H10511` register is
set to `1` (zone control). Their current state is read from `H10707`; `H10711`
is the last manually selected zone and may differ while a schedule is active.
The integration options allow overriding automatic detection and changing the
three displayed zone labels.

Requested/effective operating mode, forced operating mode, program, and season
are exposed as native status sensors. Heat-pump heating and cooling have binary
sensors. Entities are created only when their registers are present on the unit.

Optional diagnostic sensors are disabled by default: TU1/TU2/TEb/control-panel
temperatures, SA2 output voltage, requested/effective power codes, and bypass
SB+/SB- output codes. Enable the sensors you need from the device page. M1/M2/SC
output voltages are also available as native sensors. Physical temperature names
avoid assuming the unit's installation orientation. The raw power and bypass
codes intentionally have no percentage or duration unit; their interpretation
depends on unit configuration and special register values.

Rename entities for rooms in your own Home Assistant entity settings. Room names,
CO2 voltage calibration, and installation-specific airflow interpretations belong
in the installation configuration rather than in this integration.
