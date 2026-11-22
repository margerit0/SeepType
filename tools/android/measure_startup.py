"""Measure fresh emulator IME processes without clearing dictionaries or app data."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, write
from tools.android.device import adb, require_emulator
from tools.android.run_device_checks import installed_apk


def measure(serial, samples=10, *, apks=None):
    if not 3 <= samples <= 20:
        raise ValueError("Use 3 to 20 fresh processes for this development baseline")
    require_emulator(serial)

    def command(*args, **kwargs):
        return adb(*args, serial=serial, **kwargs)

    if command("shell", "getprop", "ro.kernel.qemu").stdout.strip() != "1":
        raise ValueError("Only the dedicated development emulator is supported")
    package = "org.studyime.android"
    debug = package + ".debug"
    apks = apks or {
        package: ROOT / "android/app/build/outputs/apk/release/app-release.apk",
        debug: ROOT / "android/app/build/outputs/apk/debug/app-debug.apk",
        debug + ".test": ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
    }
    release_apk = apks[package]
    observed = [installed_apk(serial, debug, apks[debug]),
                installed_apk(serial, debug + ".test", apks[debug + ".test"]),
                installed_apk(serial, package, release_apk)]
    methods = command("shell", "ime", "list", "-a", "-s").stdout.splitlines()
    component = next(item.strip() for item in methods if item.strip().startswith(package + "/"))
    latin = next(item.strip() for item in methods if "inputmethod.latin" in item)
    output = CACHE / "evidence/startup"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "scope": "Fresh optimized IME processes on the development emulator with already deployed resources; OS file cache is not cleared. No personal data is removed.",
        "boundary": "First onStartInputView request to ready Compose draw in each fresh process; excludes process creation before that callback, GPU presentation and physical display latency.",
        "memoryBoundary": "RSS high-water mark, when readable, and PSS after the first ready draw; not a sampled PSS peak or a physical-device memory budget.",
        "startedAt": datetime.now(timezone.utc).isoformat(), "serial": serial,
        "imeApkSha256": digest(release_apk), "observedInstalledApks": observed,
        "installedBuild": {"serial": serial, "apkSha256": observed[0]["sha256"],
                           "testApkSha256": observed[1]["sha256"],
                           "fingerprint": command("shell", "getprop", "ro.build.fingerprint").stdout.strip()},
        "processes": [], "passed": False,
    }
    try:
        for index in range(samples):
            command("shell", "ime", "set", latin)
            command("shell", "am", "force-stop", package)
            command("shell", "am", "start", "-S", "-W", "-n", debug + "/org.studyime.android.ProbeActivity",
                    "--es", "field", "text")
            command("shell", "ime", "enable", component)
            command("shell", "ime", "set", component)
            deadline = time.monotonic() + 20
            metrics = None
            while time.monotonic() < deadline:
                time.sleep(.25)
                result = command("shell", "dumpsys", "activity", "service", component, "study-metrics")
                line = next((line.strip() for line in result.stdout.splitlines() if line.strip().startswith('{"boundary"')), None)
                if line:
                    value = json.loads(line)
                    if value["showInputViewToReadyDrawMs"]["samples"]:
                        metrics = value
                        break
            if metrics is None:
                raise RuntimeError("Fresh IME never produced a ready draw")
            pid = command("shell", "pidof", package).stdout.strip()
            if not pid.isdigit() or any(item["pid"] == pid for item in report["processes"]):
                raise RuntimeError("Expected a distinct optimized IME process")
            memory = command("shell", "dumpsys", "meminfo", package).stdout
            status = command("shell", "cat", "/proc/" + pid + "/status", check=False)
            write(output / f"process-{index + 1:02d}-meminfo.txt", memory)
            item = {"pid": pid, "timings": metrics,
                    "readyDrawMs": metrics["showInputViewToReadyDrawMs"]["max"],
                    "readyDrawSamples": metrics["showInputViewToReadyDrawMs"]["samples"]}
            if (item["readyDrawSamples"] != 1 or metrics.get("showRequests") != 1
                    or metrics.get("pendingShowDraw") is not False or metrics.get("pendingReadyDraw") is not False):
                report["failedProcess"] = item
                raise RuntimeError("A fresh process must contain exactly one complete first-show/ready-draw pair")
            total = re.search(r"TOTAL PSS:\s*(\d+)|^\s*TOTAL\s+(\d+)", memory, re.MULTILINE)
            if total:
                item["readyPssKb"] = int(next(group for group in total.groups() if group is not None))
            rss = {key: int(value) for key, value in re.findall(r"^(VmRSS|VmHWM):\s+(\d+)\s+kB", status.stdout, re.MULTILINE)}
            item["procMemoryKb"] = rss
            if not rss:
                item["procMemoryUnavailable"] = status.stderr.strip() or "Kernel did not expose RSS counters to shell"
            report["processes"].append(item)
            print(f"Fresh process {index + 1}/{samples}: ready draw {item['readyDrawMs']:.2f} ms", flush=True)
        values = sorted(item["readyDrawMs"] for item in report["processes"])
        report["readyDrawMs"] = {"samples": len(values), **{
            name: values[math.ceil(len(values) * percentile) - 1]
            for name, percentile in (("p50", .5), ("p95", .95), ("max", 1.0))}}
        report["callbackColdP95Target500Ms"] = report["readyDrawMs"]["p95"] <= 500
        apk_path = command("shell", "pm", "path", package).stdout.strip().removeprefix("package:")
        disk = command("shell", "du", "-k", apk_path, check=False)
        report["apkDiskUsage"] = {"scope": "Allocated base.apk blocks only; excludes compiled code and private resources/user dictionary",
                                  "output": disk.stdout.strip(), "error": disk.stderr.strip()}
        report["observedInstalledApksAfter"] = [installed_apk(serial, item["package"], sha256=item["sha256"]) for item in observed]
        report["passed"] = True
    except BaseException as error:
        report["failure"] = str(error)
        raise
    finally:
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        json_write(CACHE / "evidence/release-startup-report.json", report)
    print(json.dumps({"passed": report["passed"], "readyDrawMs": report["readyDrawMs"],
                      "callbackColdP95Target500Ms": report["callbackColdP95Target500Ms"]}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--samples", type=int, default=10)
    args = parser.parse_args()
    measure(args.serial, args.samples)
