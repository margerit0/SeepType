"""Explicit-device startup timings only: no logcat, screenshots or personal files."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time

PACKAGE = "org.studyime.android"
DEBUG = PACKAGE + ".debug"
COMPONENT = PACKAGE + "/.ime.StudyInputMethodService"
PROBE = DEBUG + "/org.studyime.android.ProbeActivity"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(values):
    values = sorted(values)
    return {"samples": len(values), **{name: values[math.ceil(len(values) * p) - 1]
            for name, p in (("p50", .5), ("p95", .95), ("max", 1))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--debug", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    if not 3 <= args.samples <= 20:
        raise ValueError("Use 3 through 20 bounded samples")
    args.output.mkdir(parents=True, exist_ok=True)

    def adb(*command, timeout=40, check=True):
        result = subprocess.run([str(args.adb), "-s", args.serial, *map(str, command)],
                                capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        if check and result.returncode:
            raise RuntimeError("Scoped ADB command failed: " + " ".join(map(str, command[:4]))
                               + ": " + result.stderr.strip())
        return result.stdout.strip()

    def installed(package, path):
        value = adb("shell", "pm", "path", package)
        if not re.fullmatch(r"package:/[A-Za-z0-9_./=+~\-]+/base\.apk", value):
            raise ValueError("Expected exactly one installed APK for " + package)
        actual = adb("shell", "sha256sum", value.removeprefix("package:")).split()[0]
        if actual != digest(path):
            raise ValueError("Installed APK mismatch: " + package)
        return actual

    def metrics(timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = adb("shell", "dumpsys", "activity", "service", COMPONENT, "study-metrics")
            for line in raw.splitlines():
                if line.strip().startswith('{"boundary"'):
                    value = json.loads(line.strip())
                    if value["showInputViewToReadyDrawMs"]["samples"]:
                        return value
            time.sleep(.25)
        raise RuntimeError("No ready draw in the dedicated synthetic editor; keep phone unlocked")

    report = {"startedAt": datetime.now(timezone.utc).isoformat(),
              "privacy": "Only own-service timing counters and own-package identity; no global logcat, screenshots, clipboard or personal file reads.",
              "boundary": "First onStartInputView request to ready Compose draw. Excludes earlier process creation, GPU presentation and physical display latency.",
              "coldScope": "Fresh IME process, already deployed resources; OS file cache retained; no forced compilation or app-data clearing.",
              "warmScope": "Fresh synthetic editor, same ready IME process, one show per sample.",
              "device": {key: adb("shell", "getprop", prop) for key, prop in
                         (("model", "ro.product.model"), ("android", "ro.build.version.release"),
                          ("sdk", "ro.build.version.sdk"), ("abi", "ro.product.cpu.abi"))},
              "releaseSha256": installed(PACKAGE, args.release), "debugSha256": installed(DEBUG, args.debug),
              "cold": [], "warm": [], "passed": False}
    original = adb("shell", "settings", "get", "secure", "default_input_method")
    enabled = adb("shell", "settings", "get", "secure", "enabled_input_methods")
    if not re.fullmatch(r"[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+", original) or original.startswith(PACKAGE):
        raise ValueError("A preexisting non-StudyIME keyboard is required for restoration")
    already_enabled = any(item.split(";")[0].startswith(PACKAGE + "/") for item in enabled.split(":"))
    # Recovery state is local and contains keyboard component names only.
    state_path = args.output / "restore-keyboard.json"
    state_path.write_text(json.dumps({"original": original, "releaseAlreadyEnabled": already_enabled}), encoding="utf-8")

    def save():
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def open_probe():
        result = adb("shell", "am", "start", "-S", "-W", "-n", PROBE, "--es", "field", "private")
        if "Status: ok" not in result:
            raise RuntimeError("Synthetic editor did not start normally")

    def fresh():
        adb("shell", "ime", "set", original)
        adb("shell", "am", "force-stop", PACKAGE)
        open_probe()
        adb("shell", "ime", "enable", COMPONENT)
        adb("shell", "ime", "set", COMPONENT)
        value = metrics()
        pid = adb("shell", "pidof", PACKAGE)
        if not pid.isdigit():
            raise ValueError("Expected one IME process")
        valid(value)
        return {"pid": pid, "readyDrawMs": value["showInputViewToReadyDrawMs"]["max"], "metrics": value}

    def valid(value):
        if (value["showInputViewToReadyDrawMs"]["samples"] != 1 or value["showRequests"] != 1
                or value["pendingShowDraw"] or value["pendingReadyDraw"]
                or value["drawnShowEpoch"] != value["showDrawEpoch"]):
            report["invalidTiming"] = value
            raise ValueError("Expected exactly one complete show-to-ready pair")

    try:
        # This first sample is kept separate: on a new install it includes deployment.
        report["initialLaunch"] = fresh()
        print("Initial launch: %.3f ms" % report["initialLaunch"]["readyDrawMs"], flush=True)
        save()
        seen = {report["initialLaunch"]["pid"]}
        for index in range(args.samples):
            row = fresh()
            if row["pid"] in seen:
                raise ValueError("Cold sample reused an IME process")
            seen.add(row["pid"])
            report["cold"].append(row)
            save()
            print("Cold %d/%d: %.3f ms" % (index + 1, args.samples, row["readyDrawMs"]), flush=True)
        report["coldSummaryMs"] = summarize([row["readyDrawMs"] for row in report["cold"]])
        last_pid = report["cold"][-1]["pid"]
        for index in range(args.samples):
            adb("shell", "am", "force-stop", DEBUG)
            time.sleep(.25)
            adb("shell", "dumpsys", "activity", "service", COMPONENT, "study-metrics-reset")
            open_probe()
            value = metrics(20)
            valid(value)
            if adb("shell", "pidof", PACKAGE) != last_pid:
                raise ValueError("Warm sample restarted the IME")
            row = {"readyDrawMs": value["showInputViewToReadyDrawMs"]["max"], "metrics": value}
            report["warm"].append(row)
            save()
            print("Warm %d/%d: %.3f ms" % (index + 1, args.samples, row["readyDrawMs"]), flush=True)
        report["warmSummaryMs"] = summarize([row["readyDrawMs"] for row in report["warm"]])
        installed(PACKAGE, args.release)
        installed(DEBUG, args.debug)
        report["coldP95Under500Ms"] = report["coldSummaryMs"]["p95"] <= 500
        report["warmP95Under100Ms"] = report["warmSummaryMs"]["p95"] <= 100
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            adb("shell", "ime", "set", original)
            if not already_enabled:
                adb("shell", "ime", "disable", COMPONENT)
            adb("shell", "am", "force-stop", DEBUG)
            adb("shell", "am", "force-stop", PACKAGE)
            report["originalKeyboardRestored"] = adb("shell", "settings", "get", "secure", "default_input_method") == original
        except Exception as error:
            report["restoreError"] = str(error)
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({key: report[key] for key in ("passed", "coldSummaryMs", "warmSummaryMs", "originalKeyboardRestored")}), flush=True)


if __name__ == "__main__":
    main()
