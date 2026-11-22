"""Regression cases for incomplete, stale and incorrectly attributed evidence."""
# SPDX-License-Identifier: GPL-3.0-or-later
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.android.performance_validation import PHASES, assess_performance
from tools.android.profile_performance import validate_device_identity
from tools.android.run_device_checks import installed_apk
from tools.android.runtime_evidence import RuntimeCapture, parse_runtime_log
from tools.android.common import CACHE


def completed_report():
    # A fixed synthetic contract: 180 independent keys, ten 1 ms phases each.
    def summary(samples, duration):
        return {"samples": samples, "p50": duration, "p95": duration, "p99": duration, "max": duration}
    return {"passed": True, "initialImePid": "123", "finalImePid": "123",
            "syntheticFinalText": "nihao" * 31,
            "syntheticWordObservations": [{"iteration": i + 1, "syntheticEditorText": "nihao" * (i + 2)} for i in range(30)],
            "reopeningObservations": [{"iteration": i + 1, "showRequests": i + 1, "readyDraws": i + 1, "pendingReadyDraw": False} for i in range(20)],
            "warmTimings": {"keyToDeliveryMs": summary(180, 6), "keyToComposeDrawMs": summary(180, 10),
                            "showInputViewToDrawMs": summary(20, 20), "showInputViewToReadyDrawMs": summary(20, 20),
                            "showRequests": 20, "pendingShowDraw": False, "pendingReadyDraw": False,
                            "coalescedKeysBeforeDraw": 0, "discardedBeforeDraw": 0, "pendingDraws": 0, "invalidPhasePairs": 0,
                            "phaseOrder": list(PHASES), "pairedKeySamplesMs": [[1] * 10 for _ in range(180)]}}


class PerformanceEvidenceTest(unittest.TestCase):
    def test_complete_input_and_reopens_are_accepted(self):
        result = assess_performance(completed_report())
        self.assertTrue(result["coverageComplete"], result)
        self.assertTrue(result["timingTargetsMet"])

    def test_old_170_draw_tolerance_cannot_pass(self):
        report = completed_report()
        report["warmTimings"]["keyToComposeDrawMs"]["samples"] = 170
        report["warmTimings"]["pairedKeySamplesMs"] = [[1] * 10 for _ in range(170)]
        self.assertFalse(assess_performance(report)["coverageComplete"])

    def test_nineteen_ready_reopens_cannot_pass(self):
        report = completed_report()
        report["warmTimings"]["showInputViewToReadyDrawMs"]["samples"] = 19
        report["reopeningObservations"].pop()
        self.assertFalse(assess_performance(report)["coverageComplete"])

    def test_pending_coalesced_discarded_or_unpaired_inputs_cannot_pass(self):
        for key in ("pendingDraws", "coalescedKeysBeforeDraw", "discardedBeforeDraw", "invalidPhasePairs"):
            with self.subTest(key=key):
                report = completed_report()
                report["warmTimings"][key] = 1
                self.assertFalse(assess_performance(report)["coverageComplete"])

    def test_a_missing_then_duplicate_word_is_not_hidden_by_final_text(self):
        report = completed_report()
        report["syntheticWordObservations"][8]["syntheticEditorText"] = "nihao" * 9
        self.assertFalse(assess_performance(report)["coverageComplete"])

    def test_stale_percentiles_cannot_override_raw_phases(self):
        report = completed_report()
        report["warmTimings"]["pairedKeySamplesMs"][0][-1] = 500
        self.assertFalse(assess_performance(report)["coverageComplete"])

    def test_slow_complete_report_is_not_a_timing_pass(self):
        report = completed_report()
        report["warmTimings"]["showInputViewToReadyDrawMs"]["p95"] = 100.01
        report["warmReadyP95Target100Ms"] = True
        result = assess_performance(report)
        self.assertTrue(result["coverageComplete"])
        self.assertFalse(result["timingTargetsMet"])

    def test_missing_malformed_and_nonfinite_reports_fail(self):
        cases = [{}, {"warmTimings": None}, {"warmTimings": []}]
        for value in (math.nan, math.inf, -1, True):
            report = completed_report()
            report["warmTimings"]["pairedKeySamplesMs"][0][0] = value
            cases.append(report)
        for report in cases:
            with self.subTest(report=report.get("warmTimings", {}).__class__.__name__):
                self.assertFalse(assess_performance(report)["coverageComplete"])

    def test_ime_restart_is_not_a_pass(self):
        report = completed_report()
        report["finalImePid"] = "456"
        self.assertFalse(assess_performance(report)["coverageComplete"])

    def test_apk_replaced_with_a_new_local_build_is_rejected_against_pinned_hash(self):
        from subprocess import CompletedProcess
        with patch("tools.android.run_device_checks.adb", side_effect=[
            CompletedProcess([], 0, "package:/data/app/example/base.apk\n"),
            CompletedProcess([], 0, "b" * 64 + "  /data/app/example/base.apk\n"),
        ]), self.assertRaisesRegex(ValueError, "differs"):
            installed_apk("127.0.0.1:5581", "org.studyime.android", sha256="a" * 64)


class RuntimeAttributionTest(unittest.TestCase):
    def test_marker_waits_until_logcat_is_subscribed(self):
        temporary = CACHE / "temp"
        temporary.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            capture = RuntimeCapture("127.0.0.1:5581", Path(directory), "org.studyime.android")
            capture.logger = Mock()
            capture.logger.poll.return_value = None
            log = Path(directory) / "logcat.txt"
            log.write_text("", encoding="utf-8")
            calls = []
            def emit(*args, **kwargs):
                calls.append(args)
                if len(calls) == 2:
                    log.write_text("101.000 1 1 I StudyIMEValidation: begin-" + capture.token, encoding="utf-8")
            with patch("tools.android.runtime_evidence.adb", side_effect=emit):
                capture.marker("begin")
            self.assertEqual(2, len(calls))

    def test_old_buffer_crash_and_later_crash_are_excluded(self):
        text = "\n".join([
            "100.000 10 10 E AndroidRuntime: FATAL EXCEPTION: main",
            "101.000 1 1 I StudyIMEValidation: begin-attempt",
            "102.000 1 1 I StudyIMEValidation: end-attempt",
            "103.000 10 10 E AndroidRuntime: FATAL EXCEPTION: main",
        ])
        result = parse_runtime_log(text, "attempt", "org.studyime.android")
        self.assertTrue(result["markersComplete"])
        self.assertEqual([], result["crashes"])

    def test_ime_runner_and_system_are_distinguished(self):
        text = "\n".join([
            "101.000 1 1 I StudyIMEValidation: begin-attempt",
            "102.000 10 10 E AndroidRuntime: FATAL EXCEPTION: main",
            "102.001 10 10 E AndroidRuntime: Process: org.studyime.android, PID: 10",
            "103.000 20 21 E AndroidRuntime: FATAL EXCEPTION: FinalizerDaemon",
            "103.001 20 21 E AndroidRuntime: Process: org.studyime.android.debug, PID: 20",
            "104.000 30 30 F libc    : Fatal signal 11 (SIGSEGV), code 1, fault addr 0x3f800007 in tid 30 (ndroid.systemui), pid 30 (ndroid.systemui)",
            "104.100 40 40 F DEBUG   : pid: 30, tid: 30, name: ndroid.systemui >>> com.android.systemui <<<",
            "105.000 1 1 I StudyIMEValidation: end-attempt",
        ])
        events = parse_runtime_log(text, "attempt", "org.studyime.android")["crashes"]
        self.assertEqual([("10", "ime"), ("20", "test/editor"), ("30", "system")],
                         [(item["pid"], item["category"]) for item in events])

    def test_java_system_server_crash_is_detected(self):
        text = "\n".join([
            "101.000 1 1 I StudyIMEValidation: begin-attempt",
            "102.000 50 51 E AndroidRuntime: *** FATAL EXCEPTION IN SYSTEM PROCESS: main",
            "103.000 1 1 I StudyIMEValidation: end-attempt",
        ])
        events = parse_runtime_log(text, "attempt", "org.studyime.android", {"50": "system_server"})["crashes"]
        self.assertEqual("system", events[0]["category"])

    def test_missing_end_marker_is_not_complete_evidence(self):
        result = parse_runtime_log("101.000 1 1 I StudyIMEValidation: begin-attempt", "attempt", "org.studyime.android")
        self.assertFalse(result["markersComplete"])


class IsolatedDeviceTest(unittest.TestCase):
    def test_explicit_owned_emulator_is_accepted(self):
        validate_device_identity("127.0.0.1:5581", "StudyIME_Stability_API35_20261113", "1", "35", "StudyIME_Stability_API35_20261113")

    def test_wrong_device_at_the_same_port_is_rejected(self):
        for name, emulator, sdk in (("StudyIME_Skins_API30", "1", "30"),
                                    ("StudyIME_Stability_API35_20261113", "0", "35"),
                                    ("StudyIME_Stability_API35_20261113", "1", "30")):
            with self.subTest(name=name, emulator=emulator, sdk=sdk), self.assertRaises(ValueError):
                validate_device_identity("127.0.0.1:5581", name, emulator, sdk, "StudyIME_Stability_API35_20261113")

    def test_an_isolated_port_requires_explicit_selection(self):
        with self.assertRaises(ValueError):
            validate_device_identity("127.0.0.1:5581", "StudyIME_API35", "1", "35")


if __name__ == "__main__":
    unittest.main()
