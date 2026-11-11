"""Focused tests for device isolation, evidence identity, and recovery semantics."""
# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.android import acceptance as app


class AcceptanceTest(unittest.TestCase):
    def setUp(self):
        # Temporary outputs stay in the project-owned cache, including on Windows.
        app.safe(app.WORK).mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=app.WORK)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.scope = patch.object(app, "WORK", self.work)
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.controller = app.Acceptance(notify=lambda _: None)
        self.controller.serial = app.SERIALS[0]

    def test_mirror_readiness_accepts_gpu_and_software_texture_logs(self):
        self.assertTrue(app.mirror_ready("INFO: Texture (D3D11VA): 672x1440\n"))
        self.assertTrue(app.mirror_ready("INFO: Texture: 664x1440\n"))
        self.assertFalse(app.mirror_ready("INFO: Renderer: direct3d11\n"))
        self.assertFalse(app.mirror_ready("ERROR: Could not create texture\n"))

    def test_rejects_physical_or_remote_serial(self):
        for serial in ("0123456789ABCDEF", "192.168.1.4:5555", "emulator-5556"):
            with self.subTest(serial=serial), self.assertRaises(ValueError):
                app.Acceptance(serial=serial)

    def test_wrong_avd_cannot_open_activity(self):
        self.controller.shell = Mock(side_effect=["1", "OtherProject"])
        with self.assertRaisesRegex(RuntimeError, "已停止操作"):
            self.controller.open_scenario("text")
        self.assertTrue(all(call.args[0] == "getprop" for call in self.controller.shell.call_args_list))

    def test_phone_at_same_loopback_address_is_rejected(self):
        self.controller.shell = Mock(side_effect=["0", app.AVD])
        with self.assertRaisesRegex(RuntimeError, "已停止操作"):
            self.controller.open_app("settings")
        self.assertEqual(self.controller.shell.call_count, 2)

    def test_remote_shell_values_are_quoted(self):
        self.controller.adb = Mock(return_value=Mock(stdout="ok"))
        self.controller.shell("settings", "put", "system", "example", "a; echo unexpected")
        self.controller.adb.assert_called_once_with("shell", "settings put system example 'a; echo unexpected'")

    def test_rejects_unknown_scenario_without_device_access(self):
        self.controller.verify_device = Mock()
        with self.assertRaises(ValueError):
            self.controller.open_scenario("custom;command")
        self.controller.verify_device.assert_not_called()

    def test_existing_exact_apks_are_not_reinstalled(self):
        self.controller.installed_hash = Mock(return_value="same")
        self.controller.shell = Mock(return_value="versionName=0.1.0-preview.1")
        self.controller.adb = Mock()
        with patch.object(app, "digest", return_value="same"):
            self.controller.install_apks()
        self.controller.adb.assert_not_called()
        self.assertEqual([item["package"] for item in self.controller.installed], [app.RELEASE, app.HOST])

    def test_reinstall_preserves_data_and_verifies_bytes(self):
        self.controller.installed_hash = Mock(side_effect=[None, "same", "same", "same"])
        self.controller.shell = Mock(return_value="versionName=0.1.0-preview.1")
        self.controller.adb = Mock()
        with patch.object(app, "digest", return_value="same"):
            self.controller.install_apks()
        self.assertEqual(self.controller.adb.call_args.args[:3], ("install", "-r", "-t"))
        self.assertEqual(self.controller.adb.call_count, 1)

    def test_changed_apk_cannot_be_labeled_with_previous_identity(self):
        self.controller.verify_device = Mock()
        self.controller.installed = [{"package": app.RELEASE, "sha256": "original"}]
        self.controller.installed_hash = Mock(return_value="replaced")
        self.controller.adb = Mock()
        with self.assertRaisesRegex(RuntimeError, "APK 已变化"):
            self.controller.screenshot()
        self.controller.adb.assert_not_called()
        self.assertFalse((self.work / "captures").exists())

    def test_invalid_screenshot_is_not_saved(self):
        self.controller.capture_metadata = Mock(return_value={})
        self.controller.adb = Mock(return_value=Mock(stdout=b"error: disconnected"))
        with self.assertRaisesRegex(RuntimeError, "有效的原生截图"):
            self.controller.screenshot()
        self.assertFalse((self.work / "captures").exists())

    def test_rotation_change_during_recording_is_rejected(self):
        self.controller.recording = {"pid": "123"}
        self.controller.verify_device = Mock()
        with self.assertRaisesRegex(RuntimeError, "先结束录像"):
            self.controller.display("landscape")
        self.controller.verify_device.assert_not_called()

    def test_restore_uses_original_overrides_and_deletes_absent_settings(self):
        self.controller.baseline = {"size": "800x1800", "density": "reset", "font_scale": "1.2",
            "accelerometer_rotation": "1", "user_rotation": "null", "screen_off_timeout": "30000",
            "default_input_method": "test/.Ime", "show_ime_with_hard_keyboard": "null", "night": "auto"}
        self.controller.verify_device = Mock()
        self.controller.shell = Mock()
        self.controller.restore()
        self.controller.shell.assert_any_call("wm", "size", "800x1800")
        self.controller.shell.assert_any_call("wm", "density", "reset")
        self.controller.shell.assert_any_call("settings", "put", "system", "font_scale", "1.2")
        self.controller.shell.assert_any_call("settings", "delete", "system", "user_rotation")
        self.controller.shell.assert_any_call("settings", "delete", "secure", "show_ime_with_hard_keyboard")
        self.controller.shell.assert_any_call("ime", "set", "test/.Ime")
        self.assertTrue(json.loads(self.controller.journal.read_text())["restored"])

    def test_failed_restore_remains_pending_for_next_launch(self):
        self.controller.baseline = {"size": "reset", "density": "reset"}
        app.json_write(self.controller.journal, {"restored": False})
        self.controller.verify_device = Mock(side_effect=RuntimeError("disconnected"))
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            self.controller.restore()
        self.assertFalse(json.loads(self.controller.journal.read_text())["restored"])
        self.assertIsNotNone(self.controller.baseline)

    def test_single_instance_lock_releases_after_exit(self):
        with app.InstanceLock():
            with self.assertRaisesRegex(RuntimeError, "已经打开"):
                with app.InstanceLock():
                    self.fail("Second launcher acquired the lock")
        with app.InstanceLock():
            pass


if __name__ == "__main__":
    unittest.main()
