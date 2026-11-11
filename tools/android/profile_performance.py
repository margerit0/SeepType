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
        "sdk": ("getprop", "ro.build.version.sdk"),
        "display": ("wm", "size"), "density": ("wm", "density"),
        "fontScale": ("settings", "get", "system", "font_scale"),
        "rotation": ("settings", "get", "system", "user_rotation"),
        "animatorScale": ("settings", "get", "global", "animator_duration_scale"),
        "accessibility": ("settings", "get", "secure", "enabled_accessibility_services"),
        "memory": ("cat", "/proc/meminfo"), "load": ("cat", "/proc/loadavg"),
        "bootId": ("cat", "/proc/sys/kernel/random/boot_id"),
        "jitEnabled": ("getprop", "dalvik.vm.usejit"),
        "renderer": ("getprop", "debug.hwui.renderer"),
        "cpu": ("cat", "/proc/cpuinfo"),
    }
    result = {name: adb("shell", *args, serial=serial).stdout.strip() for name, args in commands.items()}
    if not result["avd"]:
        result["avd"] = adb("shell", "getprop", "ro.boot.qemu.avd_name", serial=serial).stdout.strip()
    expected_sdk = {"StudyIME_API30": "30", "StudyIME_API35": "35"}.get(result["avd"])
    if serial not in ("127.0.0.1:5555", "emulator-5554") or result["emulator"] != "1" or expected_sdk != result["sdk"]:
        raise ValueError("Select a dedicated StudyIME_API30 or StudyIME_API35 development emulator")
    package = adb("shell", "dumpsys", "package", "org.studyime.android", serial=serial).stdout
    result["releaseDexopt"] = package.partition("Dexopt state:")[2].partition("Compiler stats:")[0].strip()
    if not result["releaseDexopt"]:
        raise RuntimeError("The Release compilation state is unavailable")
    return result


def archive_current(destination, report, evidence, artifact_names=None):
    destination.mkdir(parents=True, exist_ok=False)
    path = CACHE / "evidence" / report
    if path.is_file():
        shutil.copy2(path, destination / path.name)
    source = CACHE / "evidence" / evidence
    if source.is_dir():
        if artifact_names is None:
            shutil.copytree(source, destination / evidence)
        else:
            (destination / evidence).mkdir()
            for name in artifact_names:
                if name not in ("memory-before.txt", "memory-after.txt", "gfxinfo.txt", "failure.png", "failure.xml"):
                    raise ValueError("Unexpected performance artifact: " + name)
                shutil.copy2(source / name, destination / evidence / name)


def profile(label, serial, warm_runs=3, startup_runs=2, startup_samples=20, compilation="installed"):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}", label):
        raise ValueError("Use a short lowercase comparison label")
    if not 0 <= warm_runs <= 5 or not 0 <= startup_runs <= 3 or warm_runs + startup_runs == 0:
        raise ValueError("Use 0-5 warm runs and 0-3 startup batches")
    if not 3 <= startup_samples <= 20:
        raise ValueError("Use 3-20 fresh processes in each batch")
    if compilation not in ("installed", "verify", "speed"):
        raise ValueError("Use installed, verify or speed compilation")
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
    mapping = ROOT / "android/app/build/outputs/mapping/release/mapping.txt"
    if mapping.is_file():
        shutil.copy2(mapping, output / "mapping.txt")
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
              "requestedCompilation": compilation,
              "startup": [], "warm": [], "passed": False}
    json_write(CACHE / ("performance-" + label + "-latest.json"), {"directory": str(output)})
    json_write(output / "comparison.json", report)
    print("Comparison archive: " + str(output), flush=True)
    try:
        if compilation != "installed":
            compiled = adb("shell", "cmd", "package", "compile", "-m", compilation, "-f", "org.studyime.android", serial=serial)
            write(output / "compilation.txt", compiled.stdout + compiled.stderr)
            if compiled.stdout.strip() != "Success":
                raise RuntimeError("The requested compilation mode was not applied")
            adb("shell", "am", "force-stop", "org.studyime.android", serial=serial)
        report["environmentAtMeasurement"] = environment(serial)
        json_write(output / "comparison.json", report)
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
            archive_current(output / f"before-warm-{index + 1:02d}", "release-performance-report.json", "performance")
            attempt_started = datetime.now(timezone.utc)
            try:
                test("performance", serial, "org.studyime.android")
            except (Exception, SystemExit):
                failed = output / f"failed-warm-{index + 1:02d}"
                failed.mkdir()
                current = {}
                source = CACHE / "evidence/release-performance-report.json"
                try:
                    value = json.loads(source.read_text(encoding="utf-8"))
                    if datetime.fromisoformat(value["run"]["startedAt"]) >= attempt_started:
                        current = value
                        shutil.copy2(source, failed / source.name)
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                if not current:
                    write(failed / "unavailable-report.txt", "This attempt did not produce a fresh performance report; earlier evidence remains in before-warm.")
                log = CACHE / "logs/instrumentation-performance.log"
                if current and log.is_file():
                    shutil.copy2(log, failed / log.name)
                # Capture the original failure before a later APK install or
                # run replaces it. No fresh input or screenshots are injected.
                try:
                    crash = adb("logcat", "-d", "-b", "crash", "-v", "threadtime", serial=serial, check=False)
                    write(failed / "crash-logcat.txt", crash.stdout + crash.stderr)
                    for name in ("failure.png", "failure.xml"):
                        # A runner can die before PerformanceTest clears its
                        # files. Only collect attachments named by this run.
                        if name not in current.get("artifacts", []):
                            continue
                        artifact = adb("exec-out", "run-as", "org.studyime.android.debug", "cat", "files/performance/" + name,
                                       serial=serial, binary=True, check=False)
                        if artifact.returncode == 0:
                            write(failed / name, artifact.stdout)
                except Exception as error:
                    write(failed / "capture-error.txt", str(error))
                raise
            collect("performance", serial)
            destination = output / f"warm-{index + 1:02d}"
            current = json.loads((CACHE / "evidence/release-performance-report.json").read_text(encoding="utf-8"))
            archive_current(destination, "release-performance-report.json", "performance", current.get("artifacts"))
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
    parser.add_argument("--compilation", choices=("installed", "verify", "speed"), default="installed",
                        help="Keep the installed compiler state, or explicitly select a diagnostic compiler mode")
    args = parser.parse_args()
    profile(args.label, args.serial, args.warm_runs, args.startup_runs, args.startup_samples, args.compilation)
