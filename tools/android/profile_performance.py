"""Archive comparable Release timing runs and their exact APK/source inputs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.build import input_hashes
from tools.android.common import CACHE, ROOT, digest, json_write, safe, write
from tools.android.collect_device_evidence import collect
from tools.android.device import adb
from tools.android.measure_startup import measure
from tools.android.run_device_checks import installed_apk, test


def environment(serial):
    commands = {
        "avd": ("getprop", "ro.kernel.qemu.avd_name"),
        "emulator": ("getprop", "ro.kernel.qemu"),
        "fingerprint": ("getprop", "ro.build.fingerprint"),
        "display": ("wm", "size"), "density": ("wm", "density"),
        "fontScale": ("settings", "get", "system", "font_scale"),
        "rotation": ("settings", "get", "system", "user_rotation"),
        "animatorScale": ("settings", "get", "global", "animator_duration_scale"),
        "accessibility": ("settings", "get", "secure", "enabled_accessibility_services"),
        "memory": ("cat", "/proc/meminfo"), "load": ("cat", "/proc/loadavg"),
    }
    result = {name: adb("shell", *args, serial=serial).stdout.strip() for name, args in commands.items()}
    if not result["avd"]:
        result["avd"] = adb("shell", "getprop", "ro.boot.qemu.avd_name", serial=serial).stdout.strip()
    if serial not in ("127.0.0.1:5555", "emulator-5554") or result["emulator"] != "1" or result["avd"] != "StudyIME_API30":
        raise ValueError("Select the dedicated StudyIME_API30 development emulator")
    return result


def archive_current(destination, report, evidence):
    destination.mkdir(parents=True, exist_ok=False)
    path = CACHE / "evidence" / report
    if path.is_file():
        shutil.copy2(path, destination / path.name)
    source = CACHE / "evidence" / evidence
    if source.is_dir():
        shutil.copytree(source, destination / evidence)


def profile(label, serial, warm_runs=3, startup_runs=2, startup_samples=20):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", label):
        raise ValueError("Use a short lowercase comparison label")
    if not 0 <= warm_runs <= 5 or not 0 <= startup_runs <= 3 or warm_runs + startup_runs == 0:
        raise ValueError("Use 0-5 warm runs and 0-3 startup batches")
    if not 3 <= startup_samples <= 20:
        raise ValueError("Use 3-20 fresh processes in each batch")
    initial = environment(serial)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = safe(CACHE / "evidence/performance-investigation" / (stamp + "-" + label))
    output.mkdir(parents=True, exist_ok=False)
    apks = {
        "org.studyime.android": ROOT / "android/app/build/outputs/apk/release/app-release.apk",
        "org.studyime.android.debug": ROOT / "android/app/build/outputs/apk/debug/app-debug.apk",
        "org.studyime.android.debug.test": ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
    }
    observed = [installed_apk(serial, package, path) for package, path in apks.items()]
    inputs = input_hashes()
    for package, path in apks.items():
        shutil.copy2(path, output / (package + ".apk"))
    for variant in ("release", "debug"):
        assembly_path = CACHE / ("assembly-" + variant + ".json")
        assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
        package = "org.studyime.android" + (".debug" if variant == "debug" else "")
        if (not assembly["inputsUnchangedDuringBuild"] or assembly["inputHashes"] != inputs
                or assembly["apkSha256"] != digest(apks[package])):
            raise ValueError("Rebuild the current sources before profiling: " + variant)
        shutil.copy2(assembly_path, output / assembly_path.name)
    # Save changed and new source files as well as hashes while the worktree is dirty.
    changed = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, text=True).splitlines()
    added = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    for name in set(changed + added):
        source = ROOT / name
        if name in inputs and source.is_file():
            destination = output / "sources" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    report = {"label": label, "serial": serial, "startedAt": datetime.now(timezone.utc).isoformat(),
              "gitHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "inputHashes": inputs, "installedApks": observed, "environmentBefore": initial,
              "startup": [], "warm": [], "passed": False}
    json_write(CACHE / ("performance-" + label + "-latest.json"), {"directory": str(output)})
    json_write(output / "comparison.json", report)
    print("Comparison archive: " + str(output), flush=True)
    try:
        for index in range(startup_runs):
            archive_current(output / f"before-startup-{index + 1:02d}", "release-startup-report.json", "startup")
            destination = output / f"startup-{index + 1:02d}"
            try:
                measure(serial, startup_samples)
            finally:
                archive_current(destination, "release-startup-report.json", "startup")
            value = json.loads((destination / "release-startup-report.json").read_text(encoding="utf-8"))
            report["startup"].append({"directory": destination.name, "readyDrawMs": value["readyDrawMs"]})
            json_write(output / "comparison.json", report)
        for index in range(warm_runs):
            try:
                test("performance", serial, "org.studyime.android")
            except (Exception, SystemExit):
                failed = output / f"failed-warm-{index + 1:02d}"
                failed.mkdir()
                for source in (CACHE / "evidence/release-performance-report.json", CACHE / "logs/instrumentation-performance.log"):
                    if source.is_file():
                        shutil.copy2(source, failed / source.name)
                raise
            collect("performance", serial)
            destination = output / f"warm-{index + 1:02d}"
            archive_current(destination, "release-performance-report.json", "performance")
            shutil.copy2(CACHE / "logs/instrumentation-performance.log", destination / "instrumentation.log")
            value = json.loads((destination / "release-performance-report.json").read_text(encoding="utf-8"))
            timings = value["warmTimings"]
            report["warm"].append({"directory": destination.name, "draw": timings["keyToComposeDrawMs"],
                                   "delivery": timings["keyToDeliveryMs"], "phases": timings.get("keyPhasesMs"),
                                   "ready": timings["showInputViewToReadyDrawMs"]})
            json_write(output / "comparison.json", report)
            print(json.dumps(report["warm"][-1]), flush=True)
        report["environmentAfter"] = environment(serial)
        if inputs != input_hashes():
            raise RuntimeError("Sources changed during measurement; this comparison is incomplete")
        for package, path in apks.items():
            installed_apk(serial, package, path)
        report["passed"] = True
    finally:
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        json_write(output / "comparison.json", report)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--warm-runs", type=int, default=3)
    parser.add_argument("--startup-runs", type=int, default=2)
    parser.add_argument("--startup-samples", type=int, default=20)
    args = parser.parse_args()
    profile(args.label, args.serial, args.warm_runs, args.startup_runs, args.startup_samples)
