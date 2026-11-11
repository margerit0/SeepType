"""Install/test only on the explicitly selected development emulator."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, write
from tools.android.device import adb

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


def installed_apk(serial, package, expected):
    paths = adb("shell", "pm", "path", package, serial=serial).stdout.splitlines()
    if len(paths) != 1 or not paths[0].startswith("package:"):
        raise ValueError("Expected one installed development APK: " + package)
    path = paths[0].removeprefix("package:").strip()
    if not re.fullmatch(r"/[A-Za-z0-9_./=+~\-]+/base\.apk", path):
        raise ValueError("Unexpected installed APK path")
    actual = adb("shell", "sha256sum", path, serial=serial).stdout.split()[0]
    if actual != digest(expected):
        raise ValueError("Installed APK differs from the local build; install it before testing: " + package)
    return {"package": package, "sha256": actual}


def install(serial):
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


def test(section, serial, ime_package=None):
    if ime_package not in (None, PACKAGE, "org.studyime.android"):
        raise ValueError("Only the StudyIME development builds are supported")
    test_class, report = {
        "native": ("NativeEngineTest", "native-engine-report.json"),
        "ime": ("ImeInteractionTest", "ime-interaction-report.json"),
        "recovery": ("ResourceRecoveryTest", "resource-recovery-report.json"),
        "visual": ("VisualMatrixTest", "visual-matrix-report.json"),
        "lifecycle": ("LifecycleTest", "lifecycle-report.json"),
        "scenarios": ("ScenarioTest", "scenario-report.json"),
        "performance": ("PerformanceTest", "performance-report.json"),
        "apps": ("AppEditorTest", "app-editor-report.json"),
        "recording": ("PreviewRecordingTest", "preview-recording-report.json"),
    }[section]
    observed = [installed_apk(serial, PACKAGE, ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"),
                installed_apk(serial, PACKAGE + ".test", ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk")]
    if ime_package and ime_package != PACKAGE:
        observed.append(installed_apk(serial, ime_package, ROOT / "android/app/build/outputs/apk/release/app-release.apk"))
    archived_report = ("release-" if ime_package and ime_package != PACKAGE else "") + report
    old_report = CACHE / "evidence" / archived_report
    old_log = CACHE / "logs" / ("instrumentation-" + section + ".log")
    if old_report.is_file():
        archive = CACHE / "evidence/history" / (Path(archived_report).stem + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        archive.mkdir(parents=True, exist_ok=False)
        shutil.copy2(old_report, archive / old_report.name)
        if old_log.is_file():
            shutil.copy2(old_log, archive / old_log.name)
    # A crashed runner must never reuse a report left by an earlier successful run.
    adb("shell", "run-as", PACKAGE, "rm", "-f", "files/" + report, serial=serial)
    started = datetime.now(timezone.utc).isoformat()
    if section == "apps":
        # Use a fresh process for the dedicated AOSP test browser as well as
        # a fresh page; long matrix runs can leave an obsolete renderer alive.
        # This preserves its data and does not touch a user's normal browser.
        adb("shell", "am", "force-stop", "org.chromium.webview_shell", serial=serial)
    if section == "recording":
        helper = CACHE / "temp/studyime-recording.sh"
        write(helper, RECORDING_SCRIPT)
        adb("push", helper, "/data/local/tmp/studyime-recording.sh", serial=serial)
    if section == "native":
        methods = adb("shell", "ime", "list", "-s", serial=serial).stdout.splitlines()
        other = next((method.strip() for method in methods if "inputmethod.latin" in method), None)
        if other: adb("shell", "ime", "set", other, serial=serial)
    elif section != "recovery":
        package = ime_package or PACKAGE
        component = next(method.strip() for method in adb("shell", "ime", "list", "-a", "-s", serial=serial).stdout.splitlines()
                         if method.strip().startswith(package + "/"))
        adb("shell", "ime", "enable", component, serial=serial)
        adb("shell", "ime", "set", component, serial=serial)
    print("Running Android " + test_class, flush=True)
    extra = ["-e", "imePackage", ime_package] if ime_package else []
    result = adb("shell", "am", "instrument", "-w", "-r", "-e", "class", "org.studyime.android." + test_class, *extra,
        PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner", serial=serial, timeout=1200, check=False)
    write(CACHE / "logs" / ("instrumentation-" + section + ".log"), result.stdout + result.stderr)
    passed = "OK (1 test)" in result.stdout and result.returncode == 0
    pulled = adb("exec-out", "run-as", PACKAGE, "cat", "files/" + report, serial=serial, check=False)
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
    value["run"] = {"startedAt": started, "finishedAt": datetime.now(timezone.utc).isoformat(),
                    "serial": serial, "class": test_class, "instrumentationPassed": passed}
    value["observedInstalledApks"] = observed
    value["installedBuild"] = {"serial": serial, "apkSha256": observed[0]["sha256"],
        "testApkSha256": observed[1]["sha256"],
        "fingerprint": adb("shell", "getprop", "ro.build.fingerprint", serial=serial).stdout.strip()}
    if ime_package and ime_package != PACKAGE:
        release = ROOT / "android/app/build/outputs/apk/release/app-release.apk"
        value["imeApkSha256"] = digest(release)
        report = "release-" + report
    if section == "recording" and value["passed"]:
        video = CACHE / "evidence/recording/preview-interactions.mp4"
        video.parent.mkdir(parents=True, exist_ok=True)
        adb("pull", "/data/local/tmp/studyime-preview-interactions.mp4", video, serial=serial)
        if video.stat().st_size < 1024 or video.read_bytes()[4:8] != b"ftyp":
            raise ValueError("Screen recording is missing or incomplete")
        value["video"] = {"file": "recording/preview-interactions.mp4", "bytes": video.stat().st_size, "sha256": digest(video)}
    json_write(CACHE / "evidence" / report, value)
    print(json.dumps({"passed": value.get("passed", False), "checks": len(value.get("checks", [])),
                      "wordCases": len(value.get("wordRegressions", []))}), flush=True)
    passed = value["passed"]
    print(result.stdout[-6000:], flush=True)
    if not passed:
        raise SystemExit("Android instrumentation did not pass; see preserved log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["install", "native", "ime", "recovery", "visual", "lifecycle", "scenarios", "performance", "apps", "recording"])
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--ime-package", help="Test the installed optimized IME from the separate debug editor/runner")
    args = parser.parse_args()
    if args.step == "install": install(args.serial)
    else: test(args.step, args.serial, args.ime_package)
