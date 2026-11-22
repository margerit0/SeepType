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
from tools.android.device import adb, require_emulator
from tools.android.run_device_checks import installed_apk


def check(serial, release_apk=None):
    def command(*args, **kwargs):
        return adb(*args, serial=serial, **kwargs)

    require_emulator(serial)
    if command("shell", "settings", "get", "secure", "accessibility_enabled").stdout.strip() != "0":
        raise ValueError("Run after instrumentation disconnects, with accessibility already disabled")
    package = "org.studyime.android"
    debug = "org.studyime.android.debug"
    apk = release_apk or ROOT / "android/app/build/outputs/apk/release/app-release.apk"
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
    old_ime = command("shell", "settings", "get", "secure", "default_input_method").stdout.strip()
    old_show = command("shell", "settings", "get", "secure", "show_ime_with_hard_keyboard").stdout.strip()
    old_methods = set(command("shell", "ime", "list", "-s").stdout.splitlines())
    old_size = re.search(r"Override size: (\d+x\d+)", command("shell", "wm", "size").stdout)
    old_density = re.search(r"Override density: (\d+)", command("shell", "wm", "density").stdout)
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

    def open_editor():
        # NEW_TASK | CLEAR_TASK, rather than reopening an editor that Android
        # might restore with text/view state from an earlier test.
        command("shell", "am", "start", "-W", "-f", "0x10008000", "-n", activity, "--es", "field", "text")
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            pid = command("shell", "pidof", package, check=False).stdout.strip()
            if pid and re.search(r"(?m)^\s*mInputShown=true\s*$", command("shell", "dumpsys", "input_method").stdout):
                lines = command("shell", "dumpsys", "activity", "service", component, "study-metrics").stdout.splitlines()
                metrics = next((json.loads(line) for line in lines if line.lstrip().startswith('{"boundary"')), {})
                if (metrics.get("showInputViewToReadyDrawMs", {}).get("samples", 0) and
                        metrics.get("pendingReadyDraw") is False and
                        metrics.get("showDrawEpoch") == metrics.get("drawnShowEpoch")):
                    return pid
            time.sleep(.25)
        return ""

    try:
        command("shell", "wm", "density", "320")
        command("shell", "wm", "size", "780x1688")
        command("shell", "settings", "put", "system", "font_scale", "1.0")
        command("shell", "settings", "put", "secure", "show_ime_with_hard_keyboard", "1")
        command("shell", "am", "force-stop", package)
        # A force-stopped package is not eligible to bind as an IME until it
        # is explicitly started. Start our own app, not an unrelated editor.
        command("shell", "am", "start", "-W", "-n", package + "/org.studyime.android.MainActivity", "--es", "screen", "home")
        command("shell", "ime", "enable", component)
        command("shell", "ime", "set", component)
        process = open_editor()
        assert_check("Optimized IME starts without an accessibility service", bool(process))
        baseline = snapshot()
        report["initialEditor"] = baseline
        assert_check("The first editor starts empty without accessibility", baseline["text"] == "" and not baseline["accessibilityEnabled"])
        for key in "gongyuan":
            command("shell", "input", "tap", *keys[key])
        command("shell", "input", "tap", *first_candidate)
        first = snapshot()
        report["syntheticEditorSnapshots"] = [first]
        # This test taps the first candidate by geometry. A restored user
        # dictionary can reorder these homophones; preview-input separately
        # selects exactly 公园 by label. Neither raw pinyin nor extra text passes.
        assert_check("A gongyuan candidate commits with accessibility disabled",
                     first["text"] in ("公园", "公元") and not first["accessibilityEnabled"])
        command("shell", "input", "keyevent", "4")
        # The synthetic activity requests its own keyboard on launch, so no
        # accessibility service is needed to refocus or inspect the editor.
        assert_check("A visible keyboard returns in the same process", open_editor() == process)
        baseline = snapshot()
        report["reopenedEditor"] = baseline
        assert_check("The reopened editor starts empty without accessibility", baseline["text"] == "" and not baseline["accessibilityEnabled"])
        for key in "nihao":
            command("shell", "input", "tap", *keys[key])
        command("shell", "input", "tap", *keys["space"])
        second = snapshot()
        assert_check("Space commits raw pinyin after hiding and reopening the keyboard", second["text"] == "nihao" and not second["accessibilityEnabled"])
        assert_check("The optimized IME process did not crash or restart", command("shell", "pidof", package).stdout.strip() == process)
        report["syntheticEditorSnapshots"].append(second)
        write(CACHE / "evidence/unassisted-input.png", command("exec-out", "screencap", "-p", binary=True).stdout)
        report["passed"] = True
    except Exception as failure:
        report["failure"] = str(failure)
        raise
    finally:
        command("shell", "wm", "size", old_size[1] if old_size else "reset")
        command("shell", "wm", "density", old_density[1] if old_density else "reset")
        if old_font == "null": command("shell", "settings", "delete", "system", "font_scale")
        else: command("shell", "settings", "put", "system", "font_scale", old_font)
        if old_show == "null": command("shell", "settings", "delete", "secure", "show_ime_with_hard_keyboard")
        else: command("shell", "settings", "put", "secure", "show_ime_with_hard_keyboard", old_show)
        if re.fullmatch(r"[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+", old_ime): command("shell", "ime", "set", old_ime)
        if component not in old_methods: command("shell", "ime", "disable", component)
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        json_write(CACHE / "evidence/release-unassisted-input-report.json", report)
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--release-apk", type=Path, help="Verify the bytes of a signed build outside the Gradle output directory")
    args = parser.parse_args()
    check(args.serial, args.release_apk)
