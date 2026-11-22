"""Evidence must fail closed without replacing the original test failure."""
# SPDX-License-Identifier: GPL-3.0-or-later
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.android.common import CACHE
from tools.android.runtime_artifacts import attribute_record, parse_exit_info, parse_tombstone
from tools.android.runtime_evidence import RuntimeCapture, parse_runtime_log


class ArtifactAttributionTest(unittest.TestCase):
    def setUp(self):
        self.before = {"bootId": "boot-a", "timezoneOffset": "+0800", "epochSeconds": 100., "uptimeSeconds": 50.}
        self.after = {**self.before, "epochSeconds": 110., "uptimeSeconds": 60.}
        self.interval = {"beginEpoch": 102., "endEpoch": 108.}
        self.record = {"epoch": 105., "pid": "20", "process": "org.studyime.android"}

    def test_new_event_needs_same_boot_and_marked_time(self):
        self.assertEqual("current", attribute_record(self.record, self.before, self.after, self.interval))
        self.assertEqual("outside-run", attribute_record(dict(self.record, epoch=101.), self.before, self.after, self.interval))
        self.assertEqual("unresolved-boot", attribute_record(self.record, self.before, dict(self.after, bootId="boot-b"), self.interval))

    def test_preexisting_record_is_historical_even_when_pid_is_reused(self):
        self.assertEqual("historical", attribute_record(self.record, self.before, self.after, self.interval, existed=True))

    def test_clock_jump_or_missing_identity_cannot_attribute_a_crash(self):
        self.assertEqual("unresolved-clock", attribute_record(self.record, self.before, dict(self.after, uptimeSeconds=55.), self.interval))
        self.assertEqual("unresolved-identity", attribute_record(dict(self.record, pid=None), self.before, self.after, self.interval))
        self.assertEqual("unresolved-identity", attribute_record(self.record, self.before, self.after, {}))

    def test_android_exit_time_uses_device_offset_not_host_timezone(self):
        text = """ApplicationExitInfo #0:
          timestamp=2026-11-13 21:59:49.598 pid=17505 realUid=10148
          process=org.studyime.android reason=10 (USER REQUESTED) subreason=21 (FORCE STOP) status=0
          description=stop org.studyime.android"""
        record, = parse_exit_info(text, "+0800")
        self.assertEqual(datetime(2026, 11, 13, 13, 59, 49, 598000, tzinfo=timezone.utc).timestamp(), record["epoch"])
        self.assertEqual(10, record["reason"])

    def test_unrecognized_exit_record_is_a_capture_failure(self):
        with self.assertRaises(ValueError):
            parse_exit_info("ApplicationExitInfo #0: truncated", "+0800")

    def test_native_metadata_preserves_time_pid_name_and_fault(self):
        value = parse_tombstone("""Timestamp: 2026-11-13 21:59:49.598123456+0800
Cmdline: org.studyime.android
pid: 17505, tid: 17505, name: main  >>> org.studyime.android <<<
signal 11 (SIGSEGV), code 1, fault addr 0x3f800007
""")
        self.assertEqual("17505", value["pid"])
        self.assertEqual("org.studyime.android", value["process"])
        self.assertIn("0x3f800007", value["signal"])


class CaptureFailureTest(unittest.TestCase):
    def test_si_user_sender_is_not_the_native_crash_pid(self):
        text = "\n".join([
            "101.000 1 1 I StudyIMEValidation: begin-probe",
            "102.000 2136 2136 F libc: Fatal signal 11 (SIGSEGV), code 0 (SI_USER from pid 2143, uid 2000) in tid 2136 (sleep), pid 2136 (sleep)",
            "102.100 2150 2150 F DEBUG: pid: 2136, tid: 2136, name: sleep >>> /system/bin/sleep 40 <<<",
            "103.000 1 1 I StudyIMEValidation: end-probe",
        ])
        crash, = parse_runtime_log(text, "probe", "org.studyime.android")["crashes"]
        self.assertEqual("2136", crash["pid"])
        self.assertEqual("system", crash["category"])

    def test_collection_failure_cannot_mask_original_assertion_or_leave_pass_true(self):
        temporary = CACHE / "temp"
        temporary.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            capture = RuntimeCapture("127.0.0.1:5581", Path(directory), "org.studyime.android")
            snapshot = {"bootId": "a", "processes": {"zygote64": ["1"], "system_server": ["2"], "com.android.systemui": ["3"]},
                        "processStartTicks": {}}
            capture.summary["before"] = snapshot
            (Path(directory) / "logcat.txt").write_text(
                f"101.000 1 1 I StudyIMEValidation: begin-{capture.token}\n102.000 1 1 I StudyIMEValidation: end-{capture.token}", encoding="utf-8")
            with patch.object(capture, "marker"), patch.object(capture, "stop_logger"), \
                 patch("tools.android.runtime_evidence.process_snapshot", return_value=snapshot), \
                 patch.object(capture, "checkpoint", side_effect=RuntimeError("exit-info unavailable")), \
                 patch.object(capture, "freeze_failure", side_effect=lambda: capture.summary["captureErrors"].append("screenshot failed")):
                result = capture.__exit__(AssertionError, AssertionError("missing ready draw"), None)
            self.assertFalse(result)
            self.assertEqual("missing ready draw", capture.summary["triggerFailure"])
            self.assertFalse(capture.summary["complete"])
            self.assertFalse(capture.summary["passed"])
            self.assertEqual(2, len(capture.summary["captureErrors"]))


if __name__ == "__main__":
    unittest.main()
