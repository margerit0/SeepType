"""Install/test only on the explicitly selected development emulator."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, write
from tools.android.device import adb

PACKAGE = "org.studyime.android.debug"


def install(serial):
    app = ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"
    tests = ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
    for path in (app, tests):
        print("Installing " + path.name, flush=True)
        result = adb("install", "-r", "-t", path, serial=serial)
        print(result.stdout.strip(), flush=True)
    adb("shell", "settings", "put", "secure", "show_ime_with_hard_keyboard", "1", serial=serial)
    json_write(CACHE / "evidence/installed-debug-apk.json", {"serial": serial, "apkSha256": digest(app),
        "testApkSha256": digest(tests), "fingerprint": adb("shell", "getprop", "ro.build.fingerprint", serial=serial).stdout.strip()})


def test(section, serial):
    test_class = "NativeEngineTest" if section == "native" else "ImeInteractionTest"
    report = "native-engine-report.json" if section == "native" else "ime-interaction-report.json"
    if section == "native":
        methods = adb("shell", "ime", "list", "-s", serial=serial).stdout.splitlines()
        other = next((method.strip() for method in methods if "inputmethod.latin" in method), None)
        if other: adb("shell", "ime", "set", other, serial=serial)
    else:
        component = PACKAGE + "/org.studyime.android.ime.StudyInputMethodService"
        adb("shell", "ime", "enable", component, serial=serial)
        adb("shell", "ime", "set", component, serial=serial)
    print("Running Android " + test_class, flush=True)
    result = adb("shell", "am", "instrument", "-w", "-r", "-e", "class", "org.studyime.android." + test_class,
        PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner", serial=serial, timeout=1200, check=False)
    write(CACHE / "logs" / ("instrumentation-" + section + ".log"), result.stdout + result.stderr)
    pulled = adb("exec-out", "run-as", PACKAGE, "cat", "files/" + report, serial=serial, check=False)
    if pulled.returncode == 0:
        value = json.loads(pulled.stdout)
        value["installedBuild"] = json.loads((CACHE / "evidence/installed-debug-apk.json").read_text())
        json_write(CACHE / "evidence" / report, value)
        print(json.dumps({"passed": value.get("passed", False), "checks": len(value.get("checks", [])),
                          "wordCases": len(value.get("wordRegressions", []))}), flush=True)
    print(result.stdout[-6000:], flush=True)
    if "OK (1 test)" not in result.stdout or result.returncode:
        raise SystemExit("Android instrumentation did not pass; see preserved log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["install", "native", "ime"])
    parser.add_argument("--serial", default="emulator-5554")
    args = parser.parse_args()
    if args.step == "install": install(args.serial)
    else: test(args.step, args.serial)
