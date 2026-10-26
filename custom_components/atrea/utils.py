import ast
import math

from pyatrea import Atrea
from .const import (
    LOGGER,
    DOMAIN,
    CONF_PRESETS,
    ALL_PRESET_LIST,
    CONF_FAN_MODES,
    DEFAULT_FAN_MODE_LIST,
)
from homeassistant.const import CONF_NAME


def convert_temperature(value):
    """Convert a signed 16-bit ATREA temperature register to Celsius."""
    value = int(value)
    if value > 32767:
        value -= 65536
    return value / 10


_FORMULA_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.Pow: lambda left, right: left**right,
}
_FORMULA_FUNCTIONS = {
    "abs": abs,
    "max": max,
    "min": min,
    "round": round,
}


def validate_co2_formula(formula):
    """Validate a safe arithmetic formula using x as the voltage in volts."""
    if not isinstance(formula, str) or not formula.strip():
        return True
    try:
        tree = ast.parse(formula, mode="eval")
        _validate_formula_node(tree.body)
    except (SyntaxError, TypeError, ValueError):
        return False
    return True


def convert_co2_voltage(formula, voltage):
    """Convert voltage to ppm using a validated user-provided formula."""
    try:
        result = _evaluate_formula_node(
            ast.parse(formula, mode="eval").body, float(voltage)
        )
        return result if math.isfinite(result) else None
    except (ArithmeticError, SyntaxError, TypeError, ValueError):
        return None


def _evaluate_formula_node(node, voltage):
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id == "x":
        return voltage
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_formula_node(node.operand, voltage)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _FORMULA_OPERATORS:
        left = _evaluate_formula_node(node.left, voltage)
        right = _evaluate_formula_node(node.right, voltage)
        if isinstance(node.op, ast.Pow) and (abs(right) > 10 or abs(left) > 1_000_000):
            raise ValueError("Formula exponent is outside the supported range")
        result = _FORMULA_OPERATORS[type(node.op)](left, right)
        if not math.isfinite(result):
            raise ValueError("Formula result must be finite")
        return result
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FORMULA_FUNCTIONS
        and not node.keywords
    ):
        arguments = [_evaluate_formula_node(arg, voltage) for arg in node.args]
        if node.func.id in ("abs", "round") and len(arguments) not in (1, 2):
            raise ValueError("Invalid function arguments")
        if node.func.id in ("min", "max") and not arguments:
            raise ValueError("Invalid function arguments")
        return float(_FORMULA_FUNCTIONS[node.func.id](*arguments))
    raise ValueError("Unsupported expression in CO2 formula")


def _validate_formula_node(node):
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return
    if isinstance(node, ast.Name) and node.id == "x":
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        _validate_formula_node(node.operand)
        return
    if isinstance(node, ast.BinOp) and type(node.op) in _FORMULA_OPERATORS:
        _validate_formula_node(node.left)
        _validate_formula_node(node.right)
        return
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FORMULA_FUNCTIONS
        and not node.keywords
    ):
        if node.func.id in ("abs", "round") and len(node.args) not in (1, 2):
            raise ValueError("Invalid function arguments")
        if node.func.id in ("min", "max") and not node.args:
            raise ValueError("Invalid function arguments")
        for argument in node.args:
            _validate_formula_node(argument)
        return
    raise ValueError("Unsupported expression in CO2 formula")


def isAtreaUnit(host, port):
    atrea = Atrea(host, port)
    return atrea.isAtreaUnit()


def processFanModes(fan_modes):
    fanModesArr = fan_modes.split(",")
    numericArr = []
    convertedFanMode = []
    for fan_mode in fanModesArr:
        fan_mode = fan_mode.strip().rstrip("%")
        if not fan_mode.isnumeric() or int(fan_mode) < 12 or int(fan_mode) > 100:
            return False
        numericArr.append(int(fan_mode.strip().rstrip("%")))

    numericArr.sort()
    for fan_mode in numericArr:
        fan_mode = str(fan_mode) + "%"
        convertedFanMode.append(fan_mode)
    return convertedFanMode


async def update_listener(hass, entry):
    preset_list = entry.data.get(CONF_PRESETS)
    if preset_list is None:
        preset_list = ALL_PRESET_LIST
    fan_list = entry.data.get(CONF_FAN_MODES)
    if fan_list is None:
        fan_list = DEFAULT_FAN_MODE_LIST
    sensor_name = entry.data.get(CONF_NAME)
    if sensor_name is None:
        sensor_name = "atrea"
    hass.data[DOMAIN][entry.entry_id]["climate"].updatePresetList(preset_list)
    hass.data[DOMAIN][entry.entry_id]["climate"].updateFanList(fan_list)
    hass.data[DOMAIN][entry.entry_id]["climate"].updateName(sensor_name)
    hass.data[DOMAIN][entry.entry_id]["update"].updateName(sensor_name)
