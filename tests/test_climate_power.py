"""Power control regressions using pyatrea and an offline RD5 HTTP transport."""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from homeassistant.components.climate.const import HVACMode
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pyatrea import Atrea, AtreaMode

from custom_components.atrea.climate import AtreaDevice
from custom_components.atrea.const import ALL_PRESET_LIST, PRESET_POWER_CODES


def device(program=2, mode=4, requested=33, effective=21):
    atrea = Atrea("192.0.2.1")
    status = {
        "H10510": "4", "H10700": str(program), "H10701": str(program),
        "H10702": str(program), "H10703": str(program),
        "H10704": str(effective), "H10705": str(mode),
        "H10714": str(requested), "H10715": str(mode),
        "I00020": "2", "I00021": "3", "I00022": "41",
    }
    atrea.status = status.copy()
    atrea.params = {
        "ids": [f"H1070{i}" for i in range(10)] + ["H10714", "H10715"],
        "coefs": {}, "offsets": {}, "warning": [], "alert": [],
    }
    atrea.writable_modes = {mode: True for mode in AtreaMode}
    data = {
        "atrea": atrea, "status": atrea.status, "userLabels": {}, "model": None,
        "supportedModes": list(atrea.writable_modes.items()),
    }
    writes = []
    accept_power = [True]

    def transport(url, **kwargs):
        path = urlsplit(url).path
        if path == "/config/xml.cgi":
            commands = {}
            for part in urlsplit(url).query.split("&"):
                match = re.fullmatch(r"([A-Z]\d{5})(\d{5})", part)
                if match:
                    commands[match[1]] = int(match[2])
            writes.append(commands)
            for register in ("H10700", "H10701", "H10702", "H10703"):
                if register in commands:
                    status[register] = str(commands[register])
            if "H10709" in commands:
                status["H10715"] = status["H10705"] = str(commands["H10709"])
            # H10708 is the command register. Writing readback H10714 is ignored.
            if "H10708" in commands and accept_power[0]:
                status["H10714"] = status["H10704"] = str(commands["H10708"])
            return SimpleNamespace(status_code=200, text="OK")
        if path == "/config/xml.xml":
            root = ET.Element("RD5WEB")
            group = ET.SubElement(ET.SubElement(root, "RD5"), "group")
            for register, value in status.items():
                ET.SubElement(group, "O", I=register, V=value)
            content = ET.tostring(root)
            return SimpleNamespace(status_code=200, text=content.decode(), content=content)
        raise AssertionError(f"Unexpected request to {path}")

    async def executor(func, *args):
        return func(*args)

    async def refresh():
        data["status"] = atrea.getStatus(False)

    data["coordinator"] = SimpleNamespace(async_request_refresh=refresh)
    hass = SimpleNamespace(
        data={"atrea": {"test": data}}, async_add_executor_job=executor,
    )
    entry = SimpleNamespace(
        entry_id="test", data={"ip_address": "192.0.2.1"},
        options={"power_control_mode": "preset"},
    )
    entity = AtreaDevice(hass, entry, "Atrea", "12,20,50,100", dict.fromkeys(ALL_PRESET_LIST, True))
    entity.hass = hass
    entity.async_schedule_update_ha_state = Mock()
    return entity, status, writes, transport, accept_power


class PowerStateTests(unittest.TestCase):
    def test_stale_request_uses_valid_effective_level_and_keeps_raw_codes(self):
        entity, *_ = device()
        self.assertEqual(entity.fan_mode, "Circulation - Norm")
        self.assertIn(entity.fan_mode, entity.fan_modes)
        self.assertEqual(entity.extra_state_attributes["requested_power"], 33)
        self.assertEqual(entity.extra_state_attributes["current_power"], 21)

    def test_valid_request_takes_precedence_over_effective_power(self):
        entity, *_ = device(requested=20, effective=21)
        self.assertEqual(entity.fan_mode, "Circulation - Min")

    def test_requested_mode_controls_choices_during_effective_override(self):
        entity, *_ = device(mode=2, requested=11, effective=21)
        entity.atrea.status["H10705"] = "4"
        entity.manualUpdate(False)
        self.assertEqual(entity.preset_mode, "Ventilation")
        self.assertEqual(entity.fan_mode, "Ventilation - Norm")
        self.assertNotIn("Circulation - Norm", entity.fan_modes)

    def test_firmware_power_families_for_all_user_presets(self):
        for mode, codes in {
            0: [0], 1: [0, *range(30, 39)], 2: [0, 10, 11, 12],
            3: [0, *range(30, 39)], 4: [0, 20, 21, 22],
            5: [0, 10, 11, 12], 6: [0, 10, 11, 12], 7: [0, 10, 11, 12],
        }.items():
            with self.subTest(mode=mode):
                entity, *_ = device(mode=mode)
                self.assertEqual([PRESET_POWER_CODES[name] for name in entity.fan_modes], codes)
                self.assertIn(entity.fan_mode, entity.fan_modes)

    def test_family_conversion_preserves_each_component(self):
        for code, mode, expected in [
            (33, 4, 21), (33, 2, 10), (35, 4, 21), (35, 2, 12),
            (21, 1, 34), (21, 3, 34), (12, 4, 22), (22, 5, 12),
            (33, 6, 10), (33, 7, 10), (0, 4, 0), (99, 4, None),
        ]:
            with self.subTest(code=code, mode=mode):
                self.assertEqual(AtreaDevice._matching_preset_power_code(code, AtreaMode(mode)), expected)


class PowerCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_power_writes_command_register_in_every_program(self):
        for program in (0, 1, 2):
            with self.subTest(program=program):
                entity, status, writes, transport, _ = device(program=program)
                with patch("pyatrea.requests.get", side_effect=transport):
                    await entity.async_set_fan_mode("Circulation - Norm")
                expected = {"H10708": 21}
                if program == 1:
                    expected["H10700"] = 2
                self.assertEqual(writes, [expected])
                self.assertEqual(status["H10714"], "21")
                self.assertEqual(entity.fan_mode, "Circulation - Norm")
                self.assertEqual(status["H10701"], str(program))
                self.assertEqual(status["H10702"], str(program))
                self.assertEqual(status["H10703"], str(program))
                self.assertFalse(entity.atrea.commands)
                self.assertFalse(entity.updatePending)

    async def test_every_preset_transition_selects_matching_power(self):
        for mode, expected in [(1, 33), (2, 10), (4, 21), (5, 10), (6, 10), (7, 10)]:
            with self.subTest(mode=mode):
                entity, status, writes, transport, _ = device(mode=3, effective=33)
                with patch("pyatrea.requests.get", side_effect=transport):
                    await entity.async_set_preset_mode(ALL_PRESET_LIST[mode])
                self.assertEqual(status["H10715"], str(mode))
                self.assertEqual(status["H10714"], str(expected))
                self.assertIn(entity.fan_mode, entity.fan_modes)
                self.assertNotIn("H10714", writes[0])

    async def test_reselecting_circulation_repairs_old_combined_request(self):
        entity, status, writes, transport, _ = device()
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_set_preset_mode("Circulation")
        self.assertEqual(writes, [{"H10708": 21}])
        self.assertEqual(status["H10714"], "21")

    async def test_scheduled_preset_change_overrides_only_mode_and_power(self):
        entity, status, writes, transport, _ = device(program=1, requested=21)
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_set_preset_mode("Ventilation")
        self.assertEqual(writes, [{"H10701": 2, "H10709": 2, "H10700": 2, "H10708": 11}])
        self.assertEqual(status["H10702"], "1")
        self.assertEqual(status["H10703"], "1")
        self.assertEqual(entity.program, "Temporary")

    async def test_wrong_family_is_rejected_without_device_write(self):
        entity, _, writes, transport, _ = device()
        with patch("pyatrea.requests.get", side_effect=transport):
            with self.assertRaises(ServiceValidationError):
                await entity.async_set_fan_mode("Ventilation - Norm")
        self.assertFalse(writes)

    async def test_rejected_write_surfaces_error_and_clears_pending_state(self):
        entity, _, writes, transport, accept = device()
        accept[0] = False
        with patch("pyatrea.requests.get", side_effect=transport):
            with self.assertRaisesRegex(HomeAssistantError, "still reports requested power 33"):
                await entity.async_set_fan_mode("Circulation - Norm")
        self.assertFalse(entity.atrea.commands)
        self.assertFalse(entity.updatePending)

    async def test_old_queued_commands_are_not_replayed(self):
        entity, _, writes, transport, _ = device()
        entity.atrea.commands["H10709"] = "00002"
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_set_fan_mode("Circulation - Norm")
        self.assertEqual(writes, [{"H10708": 21}])

    async def test_hvac_manual_normalizes_power_without_leaving_manual(self):
        entity, status, writes, transport, _ = device(program=1)
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_set_hvac_mode(HVACMode.FAN_ONLY)
        self.assertEqual(status["H10714"], "10")
        self.assertEqual(status["H10715"], "2")
        self.assertEqual(status["H10700"], "0")
        self.assertNotIn("H10714", writes[0])

    async def test_hvac_auto_does_not_send_a_none_operating_mode(self):
        entity, _, writes, transport, _ = device()
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_set_hvac_mode(HVACMode.AUTO)
        self.assertNotIn("H10709", writes[0])

    async def test_turn_on_matches_ventilation_power(self):
        entity, status, writes, transport, _ = device()
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_turn_on()
        self.assertEqual(status["H10715"], "2")
        self.assertEqual(status["H10714"], "10")
        self.assertNotIn("H10714", writes[0])

    async def test_percentage_fallback_keeps_pyatrea_percentage_limits(self):
        entity, status, writes, transport, _ = device()
        entity.atrea.status["H10510"] = "0"
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_set_fan_mode("10%")
        self.assertEqual(writes, [{"H10708": 12}])
        self.assertEqual(status["H10714"], "12")

    async def test_network_failure_does_not_leave_polling_suspended(self):
        entity, _, _, _, _ = device()
        with patch("pyatrea.requests.get", side_effect=ConnectionError("offline")):
            with self.assertRaises(ConnectionError):
                await entity.async_set_fan_mode("Circulation - Norm")
        self.assertFalse(entity.atrea.commands)
        self.assertFalse(entity.updatePending)

    async def test_off_executes_one_command_batch(self):
        entity, status, writes, transport, _ = device()
        with patch("pyatrea.requests.get", side_effect=transport):
            await entity.async_set_hvac_mode(HVACMode.OFF)
        self.assertEqual(len(writes), 1)
        self.assertEqual(status["H10715"], "0")


if __name__ == "__main__":
    unittest.main()
