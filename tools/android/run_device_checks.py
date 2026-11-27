"""Install/test only on the explicitly selected development emulator."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, write
from tools.android.device import adb, require_emulator
from tools.android.performance_validation import assess_performance
from tools.android.runtime_evidence import RuntimeCapture

PACKAGE = "org.studyime.android.debug"

RECORDING_SCRIPT = """#!/system/bin/sh
case "$1" in
    start)
        if [ -n "$(pidof screenrecord)" ]; then echo already-recording; exit 1; fi
        screenrecord --time-limit 120 --bit-rate 4000000 /data/local/tmp/studyime-preview-interactions.mp4 </dev/null >/data/local/tmp/studyime-recording.log 2>&1 &
        echo "$!"
        ;;
    stop)
        case "$2" in ''|*[!0-9]*) echo invalid-pid; exit 1;; esac
        if [ -d "/proc/$2" ]; then
            if [ "$(cat /proc/$2/comm)" != "screenrecord" ]; then echo unexpected-process; exit 1; fi
            kill -INT "$2"
        fi
        attempts=0
        while [ -d "/proc/$2" ] && [ "$attempts" -lt 80 ]; do
            sleep 0.1
            attempts=$((attempts + 1))
        done
        if [ -d "/proc/$2" ]; then echo recorder-stop-timeout; exit 1; fi
        echo stopped
        ;;
    *) echo unsupported-action; exit 1;;
esac
"""


def installed_apk(serial, package, expected=None, *, sha256=None):
    if (expected is None) == (sha256 is None):
        raise ValueError("Specify an APK file or a pinned SHA-256")
    expected_hash = sha256 if sha256 is not None else digest(expected)
    paths = adb("shell", "pm", "path", package, serial=serial).stdout.splitlines()
    if len(paths) != 1 or not paths[0].startswith("package:"):
        raise ValueError("Expected one installed development APK: " + package)
    path = paths[0].removeprefix("package:").strip()
    if not re.fullmatch(r"/[A-Za-z0-9_./=+~\-]+/base\.apk", path):
        raise ValueError("Unexpected installed APK path")
    actual = adb("shell", "sha256sum", path, serial=serial).stdout.split()[0]
    if actual != expected_hash:
        raise ValueError("Installed APK differs from the local build; install it before testing: " + package)
    return {"package": package, "sha256": actual}


def install(serial):
    require_emulator(serial)
    app = ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"
    tests = ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
    for path in (app, tests):
        print("Installing " + path.name, flush=True)
        result = adb("install", "-r", "-t", path, serial=serial)
        print(result.stdout.strip(), flush=True)
    adb("shell", "settings", "put", "secure", "show_ime_with_hard_keyboard", "1", serial=serial)
    json_write(CACHE / "evidence/installed-debug-apk.json", {"serial": serial,
        "apkSha256": installed_apk(serial, PACKAGE, app)["sha256"],
        "testApkSha256": installed_apk(serial, PACKAGE + ".test", tests)["sha256"],
        "fingerprint": adb("shell", "getprop", "ro.build.fingerprint", serial=serial).stdout.strip()})


def apk_inputs(release=None):
    return {
        PACKAGE: ROOT / "android/app/build/outputs/apk/debug/app-debug.apk",
        PACKAGE + ".test": ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
        "org.studyime.android": release or ROOT / "android/app/build/outputs/apk/release/app-release.apk",
    }


def test(section, serial, ime_package=None, *, names_baseline=False, apks=None, timeout=1200, capture_runtime=False):
    if ime_package not in (None, PACKAGE, "org.studyime.android"):
        raise ValueError("Only the StudyIME development builds are supported")
    require_emulator(serial)
    if section in ("preview-input", "clipboard-privacy") and ime_package != "org.studyime.android":
        raise ValueError(section + " requires the optimized Release IME")
    name_check = section.startswith("offline-names-")
    if names_baseline and section not in ("offline-names-engine", "offline-names-ui"):
        raise ValueError("--names-baseline is for the offline names checks only")
    if name_check and ime_package not in (None, PACKAGE):
        raise ValueError("Offline name comparisons use the same debug APK and test editor")
    test_class, report = {
        "offline-names-engine": ("OfflineNamesTest#nativeCandidates", "offline-names-engine.json"),
        "offline-names-ui": ("OfflineNamesTest#foldedCandidates", "offline-names-ui.json"),
        "offline-names-coverage": ("OfflineNamesTest#allPackagedNames", "offline-names-coverage.json"),
        "offline-names-work-titles": ("OfflineNamesTest#workTitleCandidates", "offline-names-work-titles.json"),
        "curated-phrases-engine": ("OfflineNamesTest#curatedPhraseCandidates", "curated-phrases-engine.json"),
        "curated-phrases-coverage": ("OfflineNamesTest#allCuratedPhrases", "curated-phrases-coverage.json"),
        "native": ("NativeEngineTest", "native-engine-report.json"),
        "ime": ("ImeInteractionTest", "ime-interaction-report.json"),
        "preview-input": ("PhoneInputTest", "phone-input-report.json"),
        "emoji": ("EmojiPickerTest", "emoji-picker-report.json"),
        "recovery": ("ResourceRecoveryTest", "resource-recovery-report.json"),
        "visual": ("VisualMatrixTest", "visual-matrix-report.json"),
        "skins": ("SkinSwitchTest", "skin-switch-report.json"),
        "number-pad": ("NumberPadTest", "number-pad-report.json"),
        "word-details": ("WordDetailTest", "word-detail-report.json"),
        "clipboard": ("ClipboardHistoryTest", "clipboard-history-report.json"),
        "clipboard-persistence": ("ClipboardPersistenceTest", "clipboard-persistence-report.json"),
        "clipboard-privacy": ("ClipboardPrivacyTest", "clipboard-privacy-report.json"),
        "lifecycle": ("LifecycleTest", "lifecycle-report.json"),
        "scenarios": ("ScenarioTest", "scenario-report.json"),
        "performance": ("PerformanceTest", "performance-report.json"),
        "reopen": ("ReopenDrawingTest", "reopen-drawing-report.json"),
        "draw": ("DrawRequestTest", "draw-request-report.json"),
        "apps": ("AppEditorTest", "app-editor-report.json"),
        "recording": ("PreviewRecordingTest", "preview-recording-report.json"),
    }[section]
    apks = apks or apk_inputs()
    observed = [installed_apk(serial, package, apks[package]) for package in (PACKAGE, PACKAGE + ".test")]
    if ime_package and ime_package != PACKAGE:
        observed.append(installed_apk(serial, ime_package, apks[ime_package]))
    fingerprint = adb("shell", "getprop", "ro.build.fingerprint", serial=serial).stdout.strip()
    archived_report = ("release-" if ime_package and ime_package != PACKAGE else "") + report
    old_report = CACHE / "evidence" / archived_report
    old_log = CACHE / "logs" / ("instrumentation-" + section + ".log")
    if old_report.is_file():
        archive = CACHE / "evidence/history" / (Path(archived_report).stem + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        archive.mkdir(parents=True, exist_ok=False)
        shutil.copy2(old_report, archive / old_report.name)
        if old_log.is_file():
            shutil.copy2(old_log, archive / old_log.name)
    started = datetime.now(timezone.utc).isoformat()
    print("Running Android " + test_class, flush=True)
    extra = ["-e", "imePackage", ime_package] if ime_package else []
    if names_baseline:
        extra += ["-e", "namesBaseline", "true"]
    attempt = CACHE / "evidence/runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + section)
    runtime = (RuntimeCapture(serial, attempt, ime_package or PACKAGE,
                              require_ime_continuity=section in ("performance", "reopen") and ime_package == "org.studyime.android")
               if capture_runtime else None)
    run_id = runtime.token if runtime else uuid4().hex
    if not runtime:
        attempt.mkdir(parents=True, exist_ok=False)
    instrumentation_started = False
    timed_out = False
    try:
        with (runtime if runtime else nullcontext()):
            # Capture IME startup and every setup command before instrumentation
            # so an early service failure cannot fall in an unlogged gap.
            setup_commands = []
            def setup(*args):
                setup_commands.append([str(arg) for arg in args])
                json_write(attempt / "setup.json", {"serial": serial, "commands": setup_commands})
                return adb(*args, serial=serial)
            # Never reuse a report left by a previous crashed/successful runner.
            setup("shell", "run-as", PACKAGE, "rm", "-f", "files/" + report)
            if section == "apps":
                setup("shell", "am", "force-stop", "org.chromium.webview_shell")
            if section == "recording":
                helper = CACHE / "temp/studyime-recording.sh"
                write(helper, RECORDING_SCRIPT)
                setup("push", helper, "/data/local/tmp/studyime-recording.sh")
            # Standalone Compose tests must not share InputMetrics with a live
            # debug IME in the same process.
            if section in ("native", "draw", "offline-names-engine", "offline-names-coverage", "offline-names-work-titles",
                           "curated-phrases-engine", "curated-phrases-coverage"):
                methods = setup("shell", "ime", "list", "-s").stdout.splitlines()
                other = next((method.strip() for method in methods if "inputmethod.latin" in method), None)
                if other: setup("shell", "ime", "set", other)
            elif section != "recovery":
                package = ime_package or PACKAGE
                component = next(method.strip() for method in setup("shell", "ime", "list", "-a", "-s").stdout.splitlines()
                                 if method.strip().startswith(package + "/"))
                setup("shell", "ime", "enable", component)
                setup("shell", "ime", "set", component)
            command = ["shell", "am", "instrument", "-w", "-r", "-e", "class", "org.studyime.android." + test_class,
                       "-e", "evidenceRunId", run_id, *extra,
                       PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner"]
            json_write(attempt / "invocation.json", {"command": command, "serial": serial, "timeoutSeconds": timeout, "installedApks": observed,
                       "apkInputs": {package: {"path": str(path.resolve()), "sha256": digest(path)} for package, path in apks.items()}})
            instrumentation_started = True
            try:
                result = adb(*command, serial=serial, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as error:
                timed_out = True
                def decoded(value):
                    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
                result = subprocess.CompletedProcess(error.cmd, 124, decoded(error.stdout), decoded(error.stderr) + "\nInstrumentation timed out")
            write(attempt / "instrumentation.log", result.stdout + result.stderr)
            if runtime and ("OK (1 test)" not in result.stdout or result.returncode != 0):
                runtime.note_failure(result.stdout + result.stderr)
                for item in observed:
                    def freeze_apk(item=item):
                        path = apks[item["package"]]
                        if digest(path) != item["sha256"]:
                            raise ValueError("APK changed before failure freeze: " + item["package"])
                        destination = attempt / (item["package"] + ".apk")
                        shutil.copy2(path, destination)
                        if digest(destination) != item["sha256"]:
                            raise ValueError("APK changed during failure freeze: " + item["package"])
                    runtime.capture_step("freeze-apk", freeze_apk)
    except Exception as error:
        result = subprocess.CompletedProcess([], 1, "", str(error))
    if timed_out:
        # Losing the adb client does not reliably end remote instrumentation.
        # Preserve collected evidence before stopping this dedicated test runner.
        def stop_timed_out_runner():
            stopped = adb("shell", "am", "force-stop", PACKAGE, serial=serial, timeout=15)
            json_write(attempt / "timeout-cleanup.json", {"recordedAt": datetime.now(timezone.utc).isoformat(),
                       "command": ["am", "force-stop", PACKAGE], "afterFailureFreeze": True,
                       "output": stopped.stdout + stopped.stderr})
        if runtime:
            runtime.capture_step("stop-timed-out-runner", stop_timed_out_runner)
            if runtime.summary["captureErrors"]:
                runtime.summary["complete"] = runtime.summary["passed"] = False
            json_write(attempt / "runtime.json", runtime.summary)
        else:
            stop_timed_out_runner()
    write(CACHE / "logs" / ("instrumentation-" + section + ".log"), result.stdout + result.stderr)
    passed = "OK (1 test)" in result.stdout and result.returncode == 0
    try:
        pulled = adb("exec-out", "run-as", PACKAGE, "cat", "files/" + report, serial=serial, check=False, timeout=30)
    except Exception as error:
        pulled = subprocess.CompletedProcess([], 1, "", str(error))
    value = None
    if pulled.returncode == 0:
        try:
            parsed = json.loads(pulled.stdout)
            if isinstance(parsed, dict):
                value = parsed
        except json.JSONDecodeError:
            pass
    if value is None:
        # A runner can die while its report file is still empty or partial.
        # Write a fresh, APK-bound failure instead of leaving the previous
        # local report in place for an evidence collector to mistake as current.
        write(CACHE / "logs" / ("instrumentation-" + section + "-invalid-report.txt"), pulled.stdout + pulled.stderr)
        value = {"passed": False, "failure": "Instrumentation did not produce a valid JSON object report"}
    value["passed"] = passed and value.get("passed", False)
    if name_check:
        value["passed"] = value["passed"] and value.get("baseline") == names_baseline
    value["run"] = {"startedAt": started, "finishedAt": datetime.now(timezone.utc).isoformat(),
                    "serial": serial, "class": test_class, "instrumentationStarted": instrumentation_started,
                    "instrumentationPassed": passed, "instrumentationTimedOut": timed_out,
                    "timeoutSeconds": timeout, "returnCode": result.returncode}
    if timed_out:
        value["reportFailure"] = value.get("failure")
        value["failure"] = f"Instrumentation exceeded its {timeout:.3f} second time limit"
    value["observedInstalledApks"] = observed
    if runtime:
        value["runtimeEvidence"] = {"directory": str(attempt.resolve()), **runtime.summary}
        value["passed"] = value["passed"] and runtime.summary["passed"]
    try:
        value["observedInstalledApksAfter"] = [installed_apk(serial, item["package"], sha256=item["sha256"]) for item in observed]
    except Exception as error:
        value["artifactIdentityError"] = str(error)
        value["passed"] = False
    if section == "performance" and value.get("runId") != run_id:
        value["passed"] = False
        value["reportIdentityError"] = "Report does not belong to this attempt"
    if section == "performance":
        value["performanceAssessment"] = assess_performance(value)
        value["passed"] = value["passed"] and value["performanceAssessment"]["coverageComplete"]
    value["installedBuild"] = {"serial": serial, "apkSha256": observed[0]["sha256"],
        "testApkSha256": observed[1]["sha256"],
        "fingerprint": fingerprint}
    if ime_package and ime_package != PACKAGE:
        value["imeApkSha256"] = next(item["sha256"] for item in observed if item["package"] == ime_package)
        report = "release-" + report
    if section == "recording" and value["passed"]:
        video = CACHE / "evidence/recording/preview-interactions.mp4"
        video.parent.mkdir(parents=True, exist_ok=True)
        adb("pull", "/data/local/tmp/studyime-preview-interactions.mp4", video, serial=serial)
        if video.stat().st_size < 1024 or video.read_bytes()[4:8] != b"ftyp":
            raise ValueError("Screen recording is missing or incomplete")
        value["video"] = {"file": "recording/preview-interactions.mp4", "bytes": video.stat().st_size, "sha256": digest(video)}
    json_write(CACHE / "evidence" / report, value)
    json_write(attempt / report, value)
    write(attempt / "instrumentation.log", result.stdout + result.stderr)
    print(json.dumps({"passed": value.get("passed", False), "checks": len(value.get("checks", [])),
                      "wordCases": len(value.get("wordRegressions", []))}), flush=True)
    passed = value["passed"]
    print(result.stdout[-6000:], flush=True)
    if not passed:
        raise SystemExit("Android instrumentation did not pass; see preserved log")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["install", "native", "offline-names-engine", "offline-names-ui", "offline-names-coverage", "offline-names-work-titles", "curated-phrases-engine", "curated-phrases-coverage", "ime", "preview-input", "emoji", "recovery", "visual", "skins", "number-pad", "word-details", "clipboard", "clipboard-persistence", "clipboard-privacy", "lifecycle", "scenarios", "performance", "reopen", "draw", "apps", "recording"])
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--ime-package", help="Test the installed optimized IME from the separate debug editor/runner")
    parser.add_argument("--release-apk", type=Path, help="Pin the installed optimized IME to a different APK, such as the final signed release")
    parser.add_argument("--names-baseline", action="store_true", help="Record candidates from an APK without the names table")
    parser.add_argument("--runtime-evidence", action="store_true", help="Collect system logs from the dedicated test emulator only")
    args = parser.parse_args()
    if args.release_apk and (args.step == "install" or args.ime_package != "org.studyime.android"):
        parser.error("--release-apk requires a test with --ime-package org.studyime.android")
    if args.step == "install": install(args.serial)
    else: test(args.step, args.serial, args.ime_package, names_baseline=args.names_baseline,
               apks=apk_inputs(args.release_apk), capture_runtime=args.runtime_evidence)
