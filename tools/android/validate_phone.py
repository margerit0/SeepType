"""Bounded phone regression using only StudyIME reports and synthetic editors.

Never delegates to emulator collectors: no logcat, screenshots, hierarchy dumps,
clipboard reads, global package lists or personal-file access.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import ROOT, CACHE, digest, json_write, safe
from tools.android.build import input_hashes
from tools.android.performance_validation import assess_performance

PACKAGE = "org.studyime.android"
DEBUG = PACKAGE + ".debug"
COMPONENT = PACKAGE + "/.ime.StudyInputMethodService"
SUITES = {
    "lexicon": ("ReviewedLexiconTest", "reviewed-lexicon-smoke.json", 960),
    "native": ("NativeEngineTest", "native-engine-report.json", 960),
    "recovery": ("ResourceRecoveryTest", "resource-recovery-report.json", 180),
    "ime": ("ImeInteractionTest", "ime-interaction-report.json", 360),
    "input": ("PhoneInputTest", "phone-input-report.json", 360),
    "lifecycle": ("LifecycleTest", "lifecycle-report.json", 480),
    "performance": ("PerformanceTest", "performance-report.json", 360),
    "reopen": ("ReopenDrawingTest", "reopen-drawing-report.json", 240),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--debug", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sections", nargs="+", choices=SUITES, default=list(SUITES))
    parser.add_argument("--performance-runs", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--install-helpers", action="store_true")
    parser.add_argument("--exclude-system-routed-password", action="store_true",
                        help="Verify a different system keyboard owns our password field; record two blocked UI checks and continue other fields")
    args = parser.parse_args()
    output = safe(args.output)
    output.mkdir(parents=True, exist_ok=False)
    command_log = []

    def adb(*parts, timeout=40, check=True):
        command_log.append([str(p) for p in parts])
        json_write(output / "commands.json", command_log)
        result = subprocess.run([str(args.adb), "-s", args.serial, *map(str, parts)],
                                capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        if check and result.returncode:
            raise RuntimeError("Scoped ADB failure: " + " ".join(map(str, parts[:5])) + ": " + result.stderr.strip())
        return result

    def shell(*parts, **kwargs):
        return adb("shell", *parts, **kwargs).stdout.strip()

    def installed(package):
        path = shell("pm", "path", package)
        if not re.fullmatch(r"package:/[A-Za-z0-9_./=+~\-]+/base\.apk", path):
            raise ValueError("Expected a single installed APK: " + package)
        return shell("sha256sum", path.removeprefix("package:")).split()[0]

    apks = {PACKAGE: args.release, DEBUG: args.debug, DEBUG + ".test": args.test}
    frozen = output / "apks"
    frozen.mkdir()
    identities = {}
    for package, path in apks.items():
        target = frozen / (package + ".apk")
        shutil.copy2(path, target)
        identities[package] = {"sha256": digest(target), "path": str(target), "bytes": target.stat().st_size}
    with zipfile.ZipFile(args.release) as bundle:
        manifest = json.loads(bundle.read("assets/generated/manifest.json"))
    for path in (args.release, args.debug):
        with zipfile.ZipFile(path) as bundle:
            actual = json.loads(bundle.read("assets/generated/manifest.json"))
            assert actual == manifest, "Editors must carry exactly the same product resources"
            names = {n.removeprefix("assets/generated/") for n in bundle.namelist() if n.startswith("assets/generated/") and not n.endswith("/")}
            assert names == set(manifest["files"]) | {"manifest.json"}
            import hashlib
            for name, expected in manifest["files"].items():
                assert hashlib.sha256(bundle.read("assets/generated/" + name)).hexdigest() == expected, name
    with zipfile.ZipFile(args.test) as bundle:
        full_cases = json.loads(bundle.read("assets/generated/reviewed-full.json"))
        case_manifest = json.loads(bundle.read("assets/generated/reviewed-cases-manifest.json"))
        assert len(full_cases) == case_manifest["files"]["reviewed-full.json"]["cases"]
        assert hashlib.sha256(bundle.read("assets/generated/reviewed-full.json")).hexdigest() == case_manifest["files"]["reviewed-full.json"]["sha256"]
    assert installed(PACKAGE) == identities[PACKAGE]["sha256"], "Do not replace the pinned Release during validation"
    if args.install_helpers:
        for package in (DEBUG, DEBUG + ".test"):
            if installed(package) != identities[package]["sha256"]:
                print("Installing " + package, flush=True)
                result = adb("install", "-r", "-t", identities[package]["path"], timeout=180)
                assert "Success" in result.stdout, result.stdout + result.stderr
    for package in apks:
        assert installed(package) == identities[package]["sha256"], "Installed APK mismatch: " + package

    original = shell("settings", "get", "secure", "default_input_method")
    if not re.fullmatch(r"[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+", original) or original.startswith(PACKAGE):
        raise ValueError("Use a preexisting non-StudyIME keyboard for this bounded test")
    enabled = shell("settings", "get", "secure", "enabled_input_methods")
    was_enabled = any(x.split(";")[0].startswith(PACKAGE + "/") for x in enabled.split(":"))
    rotation = {key: shell("settings", "get", "system", key) for key in ("accelerometer_rotation", "user_rotation")}
    json_write(output / "restore.json", {"originalIme": original, "releaseEnabled": was_enabled, "rotation": rotation})
    report = {"startedAt": datetime.now(timezone.utc).isoformat(), "apks": identities,
              "resourceVersion": manifest["version"], "caseManifest": case_manifest,
              "sourceInputs": input_hashes(), "sections": args.sections, "runs": [], "passed": False,
              "privacy": "Own-package reports and memory only; no logcat, screenshot, window dump, clipboard or personal-file collection.",
              "device": {key: shell("getprop", prop) for key, prop in (("model", "ro.product.model"), ("sdk", "ro.build.version.sdk"), ("abi", "ro.product.cpu.abi"))}}
    def save(): json_write(output / "report.json", report)
    save()
    ui_sections = set(args.sections) & {"ime", "input", "lifecycle", "performance", "reopen"}
    prepared = False
    password_route = None

    def instrument(name, test_class, filename, timeout, extra=()):
        destination = output / name
        destination.mkdir()
        shell("run-as", DEBUG, "rm", "-f", "files/" + filename)
        command = ["am", "instrument", "-w", "-r", "-e", "class", "org.studyime.android." + test_class,
                   "-e", "imePackage", PACKAGE, "-e", "privateDevice", "true", "-e", "fallbackIme", original,
                   "-e", "evidenceRunId", uuid.uuid4().hex, *extra, DEBUG + ".test/androidx.test.runner.AndroidJUnitRunner"]
        print("Running " + name, flush=True)
        started = time.monotonic()
        try:
            result = adb("shell", *command, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            # Only the dedicated runner is stopped; no personal app is affected.
            shell("am", "force-stop", DEBUG)
            result = subprocess.CompletedProcess(command, 124, "", "Scoped instrumentation timeout")
        (destination / "instrumentation.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        raw = adb("shell", "run-as", DEBUG, "cat", "files/" + filename, check=False)
        value = json.loads(raw.stdout) if raw.returncode == 0 else {"passed": False, "reportUnavailable": True}
        json_write(destination / "report.json", value)
        ok = result.returncode == 0 and "OK (1 test)" in result.stdout and value.get("passed") is True
        row = {"name": name, "passed": ok, "elapsedSeconds": time.monotonic() - started}
        if name.startswith("performance"):
            row.update(assess_performance(value))
            row["passed"] = ok and row["coverageComplete"]
            for artifact in ("memory-before.txt", "memory-after.txt", "gfxinfo.txt"):
                if artifact in value.get("artifacts", []):
                    content = shell("run-as", DEBUG, "cat", "files/performance/" + artifact)
                    (destination / artifact).write_text(content, encoding="utf-8")
        if name == "lexicon":
            row["passed"] = ok and value.get("checks") == len(full_cases) and value.get("failures") == 0 and value.get("resourceVersion") == manifest["version"]
        if name == "ime":
            row["coverageComplete"] = value.get("coverageComplete", True)
            row["blockedChecks"] = value.get("blockedChecks", [])
            row["blockedReason"] = value.get("blockedReason")
        report["runs"].append(row)
        save()
        print(json.dumps(row), flush=True)
        if not row["passed"]:
            for owned in (DEBUG, PACKAGE):
                detail = shell("dumpsys", "activity", "exit-info", owned, check=False)
                (destination / (owned + "-exit-info.txt")).write_text(detail, encoding="utf-8")
            raise RuntimeError("Test failed; retained own-package evidence: " + name)
        return value

    try:
        for section in args.sections:
            if section in ui_sections and not prepared:
                shell("run-as", DEBUG, "rm", "-f", "files/phone-preferences-original.json")
                prepared = True  # Also try restoration after a partial preparation failure.
                instrument("settings-prepare", "PhoneSettingsTest", "phone-settings-report.json", 90)
            if section == "ime" and args.exclude_system_routed_password:
                routing = instrument("password-routing", "PhonePasswordRoutingTest#inspectSyntheticPasswordRouting", "phone-password-routing.json", 90)
                routes = [line.removeprefix("mCurId=") for line in routing.get("routing", []) if line.startswith("mCurId=")]
                assert routing.get("studyKeyboardAvailable") is False and routing.get("defaultIme") == COMPONENT
                assert len(routes) == 1 and re.fullmatch(r"[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+", routes[0])
                assert not routes[0].startswith(PACKAGE), "Do not exclude password coverage when StudyIME owns the field"
                password_route = routes[0]
            test_class, filename, timeout = SUITES[section]
            if section in ("performance", "reopen") and "stabilityStartedAt" not in report:
                report["stabilityStartedAt"] = datetime.now(timezone.utc).isoformat()
                stability_deadline = time.monotonic() + 1800
            count = args.performance_runs if section == "performance" else 1
            for index in range(count):
                if section in ("performance", "reopen"):
                    timeout = min(timeout, int(stability_deadline - time.monotonic()))
                    if timeout <= 0: raise TimeoutError("30-minute bounded stability window ended")
                extra = ("-e", "lexiconMatrix", "full") if section == "lexicon" else ()
                if section == "ime" and password_route:
                    extra += ("-e", "systemPasswordIme", password_route)
                instrument(f"performance-{index+1:02d}" if count > 1 else section, test_class, filename, timeout, extra)
        report["passed"] = True
        report["coverageComplete"] = all(row.get("coverageComplete", True) for row in report["runs"])
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            if prepared:
                exists = adb("shell", "run-as", DEBUG, "test", "-f", "files/phone-preferences-original.json", check=False).returncode == 0
                if exists:
                    instrument("settings-restore", "PhoneSettingsTest", "phone-settings-report.json", 90, ("-e", "phoneSettings", "restore"))
                    report["productPreferencesRestored"] = True
                else:
                    report["productPreferencesRestored"] = "No preference mutation: preparation did not save a record"
        except Exception as error:
            report["preferenceRestoreError"] = str(error)
            report["passed"] = False
        try:
            shell("ime", "set", original)
            if not was_enabled: shell("ime", "disable", COMPONENT)
            shell("am", "force-stop", DEBUG)
            shell("am", "force-stop", PACKAGE)
            for key, value in rotation.items():
                if value == "null": shell("settings", "delete", "system", key)
                elif re.fullmatch(r"[0-3]", value): shell("settings", "put", "system", key, value)
                else: raise ValueError("Unexpected rotation restoration value")
            report["originalKeyboardRestored"] = shell("settings", "get", "secure", "default_input_method") == original
            report["rotationRestored"] = all(shell("settings", "get", "system", key) == value for key,value in rotation.items())
            final_enabled = shell("settings", "get", "secure", "enabled_input_methods")
            report["enabledStateRestored"] = any(x.split(";")[0].startswith(PACKAGE + "/") for x in final_enabled.split(":")) == was_enabled
            report["installedApksAfter"] = {package: installed(package) for package in apks}
            assert all(report["installedApksAfter"][p] == identities[p]["sha256"] for p in apks)
            assert report["originalKeyboardRestored"] and report["rotationRestored"] and report["enabledStateRestored"]
        except Exception as error:
            report["restoreError"] = str(error)
            report["passed"] = False
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        save()
    if not report["passed"]: raise RuntimeError("Run/restoration incomplete; see report")
    print("Complete: " + str(output), flush=True)


if __name__ == "__main__": main()
