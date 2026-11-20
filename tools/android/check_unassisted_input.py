"""Regress input with no accessibility service, using only synthetic editors."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import struct
import sys
import time
import uuid
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, write
from tools.android.device import adb
from tools.android.run_device_checks import installed_apk


def check(serial):
    def command(*args, **kwargs):
        return adb(*args, serial=serial, **kwargs)

    if command("shell", "getprop", "ro.kernel.qemu").stdout.strip() != "1":
        raise ValueError("This geometry-controlled regression is only for the development emulator")
    if command("shell", "settings", "get", "secure", "accessibility_enabled").stdout.strip() != "0":
        raise ValueError("Run after instrumentation disconnects, with accessibility already disabled")
    package = "org.studyime.android"
    debug = "org.studyime.android.debug"
    apk = ROOT / "android/app/build/outputs/apk/release/app-release.apk"
    observed = [installed_apk(serial, package, apk), installed_apk(serial, debug,
                ROOT / "android/app/build/outputs/apk/debug/app-debug.apk")]
    evidence = CACHE / "evidence/recording"
    tree = ET.parse(evidence / "release-light.xml").getroot()
    with (evidence / "release-light.png").open("rb") as image:
        header = image.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (780, 1688):
        raise ValueError("Run the 390 dp recording before this regression")
    keys = {}
    first_candidate = None
    for node in tree.iter("node"):
        name = node.get("resource-id", "")
        if not name.startswith("key_") and name != "candidate_0":
            continue
        left, top, right, bottom = map(int, re.findall(r"\d+", node.get("bounds", "")))
        center = ((left + right) // 2, (top + bottom) // 2)
        if name == "candidate_0":
            first_candidate = center
        else:
            keys[name.removeprefix("key_")] = center
    if not set("gongyuanihao").issubset(keys) or "space" not in keys or first_candidate is None:
        raise ValueError("Recorded keyboard geometry is incomplete")
    component = next(value.strip() for value in command("shell", "ime", "list", "-a", "-s").stdout.splitlines()
                     if value.strip().startswith(package + "/"))
    activity = debug + "/org.studyime.android.ProbeActivity"
    old_font = command("shell", "settings", "get", "system", "font_scale").stdout.strip()
    report = {"scope": "Real touch input with AccessibilityManager disabled; host ADB and debug-only text snapshot, no UiAutomation",
              "startedAt": datetime.now(timezone.utc).isoformat(), "serial": serial,
              "observedInstalledApks": observed, "imeApkSha256": digest(apk), "checks": [], "passed": False}

    def assert_check(name, passed):
        report["checks"].append({"name": name, "passed": passed})
        if not passed:
            raise AssertionError(name)

    def snapshot():
        token = uuid.uuid4().hex
        command("shell", "am", "start", "-W", "-f", "0x20000000", "-n", activity, "--es", "snapshotToken", token)
        value = json.loads(command("exec-out", "run-as", debug, "cat", "files/unassisted-editor.json").stdout)
        if value["token"] != token:
            raise ValueError("Synthetic editor snapshot is stale")
        return value

    try:
        command("shell", "wm", "density", "320")
        command("shell", "wm", "size", "780x1688")
        command("shell", "settings", "put", "system", "font_scale", "1.0")
        command("shell", "am", "force-stop", package)
        command("shell", "ime", "enable", component)
        command("shell", "ime", "set", component)
        command("shell", "am", "start", "-S", "-W", "-n", activity, "--es", "field", "text")
        time.sleep(2)
        process = command("shell", "pidof", package).stdout.strip()
        assert_check("Optimized IME starts without an accessibility service", bool(process))
        for key in "gongyuan":
            command("shell", "input", "tap", *keys[key])
        command("shell", "input", "tap", *first_candidate)
        first = snapshot()
        assert_check("Chinese commit works with accessibility disabled", first["text"] == "公园" and not first["accessibilityEnabled"])
        command("shell", "input", "keyevent", "4")
        # The synthetic activity requests its own keyboard on launch, so no
        # accessibility service is needed to refocus or inspect the editor.
        command("shell", "am", "start", "-S", "-W", "-n", activity, "--es", "field", "text")
        time.sleep(1)
        for key in "nihao":
            command("shell", "input", "tap", *keys[key])
        command("shell", "input", "tap", *keys["space"])
        second = snapshot()
        assert_check("Space commits raw pinyin after hiding and reopening the keyboard", second["text"] == "nihao" and not second["accessibilityEnabled"])
        assert_check("The optimized IME process did not crash or restart", command("shell", "pidof", package).stdout.strip() == process)
        report["syntheticEditorSnapshots"] = [first, second]
        write(CACHE / "evidence/unassisted-input.png", command("exec-out", "screencap", "-p", binary=True).stdout)
        report["passed"] = True
    finally:
        command("shell", "wm", "size", "reset")
        command("shell", "wm", "density", "reset")
        command("shell", "settings", "put", "system", "font_scale", old_font if old_font != "null" else "1.0")
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        json_write(CACHE / "evidence/release-unassisted-input-report.json", report)
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    check(parser.parse_args().serial)
