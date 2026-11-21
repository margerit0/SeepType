"""One-click Windows acceptance of the actual APK on the owned Android emulator."""
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, extract, fetch, json_write, safe, write

WORK = CACHE / "acceptance"
RELEASE = "org.studyime.android"
HOST = RELEASE + ".debug"
AVD = "StudyIME_API30"
SERIALS = ("127.0.0.1:5555", "emulator-5554")
SCENARIOS = {
    "text": ("自由输入", "试试 gongyuan：点候选输入中文，按住候选查看释义。"),
    "multiline": ("多行文本", "试打几句，再试换行、移动光标和删除。"),
    "search": ("搜索", "右下角应显示搜索；点按后，输入页会记录收到的动作。"),
    "next": ("切换输入框", "在两个输入框之间切换，检查组合和候选是否跟随焦点。"),
    "password": ("密码", "使用虚构内容，检查英文释义是否关闭。"),
    "number": ("数字", "检查数字键盘、正负号、小数点与删除。"),
    "email": ("邮箱", "检查英文输入、@ 和标点。"),
    "url": ("网址", "检查英文输入、斜杠和网址标点。"),
    "phone": ("电话号码", "使用虚构号码，检查拨号布局。"),
    "private": ("暂停个性化", "此输入框要求暂停记录新的选词习惯。"),
    "send": ("发送动作", "按钮只记录编辑器动作，不会发送消息。"),
}
SYSTEM_SETTINGS = ("font_scale", "accelerometer_rotation", "user_rotation", "screen_off_timeout")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def mirror_ready(output):
    return re.search(r"INFO: Texture(?: \([^\r\n]*\))?: \d+x\d+", output) is not None


def process(argv, *, timeout=30, binary=False, check=True, env=None):
    result = subprocess.run([str(arg) for arg in argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=not binary, encoding=None if binary else "utf-8", errors=None if binary else "replace",
                            timeout=timeout, env=env, creationflags=NO_WINDOW, cwd=ROOT)
    if check and result.returncode:
        detail = result.stderr or result.stdout
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        raise RuntimeError(f"命令未成功（{result.returncode}）：{detail.strip()[-1800:]}")
    return result


class InstanceLock:
    """An OS lock, not a stale PID check; releases even after a crashed launcher."""
    def __enter__(self):
        import msvcrt
        self.path = safe(WORK / "launcher.lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        try:
            if os.fstat(self.stream.fileno()).st_size == 0:
                self.stream.write(b"0")
                self.stream.flush()
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.stream.close()
            raise RuntimeError("验收面板已经打开，请使用现有窗口。") from None
        return self

    def __exit__(self, *_):
        self.stream.close()


def prepare_scrcpy(notify):
    entry = json.loads((ROOT / "android/acceptance-tools.lock.json").read_text(encoding="utf-8"))["scrcpy"]
    archive = WORK / "downloads" / f"scrcpy-win64-v{entry['version']}.zip"
    # Reuse a previously verified download from the project's shared download cache.
    previous = CACHE / "downloads" / archive.name
    if not archive.exists() and previous.is_file() and digest(previous) == entry["sha256"]:
        safe(archive).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(previous, archive)
    if not archive.is_file() or digest(archive) != entry["sha256"]:
        notify("首次准备操作窗口：下载并校验 scrcpy…")
        try:
            fetch(entry["url"], archive, entry["sha256"])
        except (OSError, ValueError):
            # Some networks cannot reach github.com release redirects. The official
            # GitHub asset API serves the same bytes, with the same pinned digest.
            partial = safe(archive.with_suffix(".zip.part"))
            request = urllib.request.Request(entry["apiUrl"], headers={
                "User-Agent": "StudyIME-Android-acceptance", "Accept": "application/octet-stream"})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
                if not response.url.startswith("https://"):
                    raise ValueError("scrcpy 下载离开了 HTTPS")
                shutil.copyfileobj(response, output, 1024 * 1024)
            if digest(partial) != entry["sha256"]:
                raise ValueError("scrcpy 下载校验失败，请重试；未运行下载内容。")
            partial.replace(archive)
    if archive.stat().st_size != entry["bytes"]:
        raise ValueError("scrcpy 下载长度与锁定版本不一致")
    destination = WORK / "tools" / ("scrcpy-" + entry["version"])
    # Compare extracted bytes with the trusted archive, including DLLs and server.
    # A receipt alone must not allow executing an incomplete/modified extraction.
    with zipfile.ZipFile(archive) as bundle:
        valid = all((destination / "/".join(item.filename.split("/")[1:])).is_file()
                    and (destination / "/".join(item.filename.split("/")[1:])).read_bytes() == bundle.read(item)
                    for item in bundle.infolist() if not item.is_dir())
    if not valid:
        extract(archive, destination)
    json_write(destination / "study-receipt.json", entry)
    return destination / "scrcpy.exe"


RECORD_HELPER = r"""#!/system/bin/sh
case "$1" in
  start)
    if [ -n "$(pidof screenrecord)" ]; then echo another-recording-is-active; exit 1; fi
    screenrecord --time-limit 120 --size "$3" --bit-rate 4000000 "$2" </dev/null >"$2.log" 2>&1 &
    echo "$!"
    ;;
  stop)
    case "$2" in ''|*[!0-9]*) exit 1;; esac
    if [ -d "/proc/$2" ]; then
      [ "$(cat /proc/$2/comm)" = "screenrecord" ] || exit 1
      tr '\000' '\n' <"/proc/$2/cmdline" | grep -F -x -- "$3" >/dev/null || exit 1
      kill -INT "$2" || exit 1
    fi
    attempts=0
    while [ -d "/proc/$2" ] && [ "$attempts" -lt 100 ]; do
      sleep 0.1
      attempts=$((attempts + 1))
    done
    [ ! -d "/proc/$2" ] || exit 1
    ;;
  *) exit 1;;
esac
"""


class Acceptance:
    def __init__(self, notify=print, serial=None):
        if serial is not None and serial not in SERIALS:
            raise ValueError("只支持本项目的本机开发模拟器。")
        safe(WORK).mkdir(parents=True, exist_ok=True)
        self.notify = notify
        self.requested_serial = serial
        self.serial = None
        self.adb_path = CACHE / "sdk/platform-tools/adb.exe"
        self.session = WORK / "sessions" / (timestamp() + "-" + uuid.uuid4().hex[:8])
        self.session.mkdir(parents=True)
        self.journal = WORK / "restore-state.json"
        self.baseline = None
        self.initial_state = None
        self.installed = []
        self.scrcpy = None
        self.mirror = None
        self.recording = None
        self.scenario = "text"
        self.version = ""
        self.events = []

    def adb(self, *args, select=True, **kwargs):
        if not self.adb_path.is_file():
            raise RuntimeError("未找到本工程的 Android SDK。请先按 android/README.md 准备开发环境。")
        if select and self.serial is None:
            raise RuntimeError("尚未连接开发模拟器")
        selection = ["-s", self.serial] if select else []
        return process([self.adb_path, *selection, *args], **kwargs)

    def shell(self, *args, **kwargs):
        # adb shell joins arguments again on Android; quote for that second shell.
        return self.adb("shell", shlex.join([str(arg) for arg in args]), **kwargs).stdout.strip()

    def verify_device(self):
        if self.serial not in SERIALS:
            raise RuntimeError("设备不在开发模拟器列表中")
        qemu = self.shell("getprop", "ro.kernel.qemu")
        name = self.shell("getprop", "ro.kernel.qemu.avd_name") or self.shell("getprop", "ro.boot.qemu.avd_name")
        if qemu != "1" or name != AVD:
            raise RuntimeError(f"目标不是 {AVD} 开发模拟器，已停止操作。")

    def connect(self):
        self.notify("正在连接开发模拟器…")
        candidates = (self.requested_serial,) if self.requested_serial else SERIALS

        def find_ready():
            rows = self.adb("devices", select=False).stdout.splitlines()[1:]
            ready = {row.split()[0] for row in rows if len(row.split()) >= 2 and row.split()[1] == "device"}
            for candidate in candidates:
                if candidate in ready:
                    self.serial = candidate
                    self.verify_device()
                    if self.shell("getprop", "sys.boot_completed") == "1":
                        return True
            return False

        if find_ready():
            return
        self.adb("connect", "127.0.0.1:5555", select=False, check=False, timeout=12)
        if find_ready():
            return
        if self.serial is None:
            if not (CACHE / "sdk/emulator/emulator").is_file():
                raise RuntimeError("未找到开发模拟器。请先运行 tools/android/emulator.py install。")
            self.notify("正在启动 Android；首次启动通常需要约一分钟…")
            from tools.android.emulator import start
            start()
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            self.adb("connect", "127.0.0.1:5555", select=False, check=False, timeout=8)
            if find_ready():
                return
            time.sleep(2)
        raise RuntimeError("模拟器未在限定时间内就绪。请查看 .cache/android/logs/emulator.log 后重试。")

    def ensure_apks(self):
        from tools.android.build import input_hashes, gradle
        from tools.android.prepare_data import refresh_if_needed
        refresh_if_needed()
        current = input_hashes()
        variants = []
        changed = set()
        for variant in ("release", "debug"):
            apk = ROOT / f"android/app/build/outputs/apk/{variant}/app-{variant}.apk"
            receipt = CACHE / f"assembly-{variant}.json"
            observed = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else {}
            previous = observed.get("inputHashes", {})
            changed.update(name for name in previous.keys() | current.keys() if previous.get(name) != current.get(name))
            if (not apk.is_file() or observed.get("apkSha256") != digest(apk)
                    or previous != current or not observed.get("inputsUnchangedDuringBuild")):
                variants.append(variant)
        if not variants:
            return
        # Gradle does not rebuild JNI inputs. Refuse a stale native-source build,
        # rather than silently labeling old .so files as the current Rust/C++ code.
        native_changes = [name for name in changed if name.startswith(("crates/", "android/native/"))
                          or name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")]
        if native_changes:
            raise RuntimeError("原生代码或工具链有变化，请先按 android/README.md 重新构建 Rust / Rime，再生成 APK。")
        if not (ROOT / "android/app/src/main/assets/generated/manifest.json").is_file():
            raise RuntimeError("词库资源尚未准备，请先运行 tools/android/build.py prepare。")
        self.notify("正在更新验收用 APK，构建进度保存在本机日志…")
        # Keep incremental acceptance builds usable alongside an already-running
        # emulator. This override affects this build only, not global Gradle/JDK.
        memory = "-Dorg.gradle.jvmargs=-Xmx448m -XX:+UseSerialGC -XX:ActiveProcessorCount=2 -XX:CICompilerCount=2 -XX:ReservedCodeCacheSize=96m -Dfile.encoding=UTF-8"
        gradle([*(":app:assemble" + variant.title() for variant in variants), memory], log="gradle-acceptance")
        for variant in variants:
            result = json.loads((CACHE / f"assembly-{variant}.json").read_text(encoding="utf-8"))
            if not result["inputsUnchangedDuringBuild"]:
                raise RuntimeError("构建时源码发生变化，请待编辑完成后重新启动验收。")

    def installed_hash(self, package):
        result = self.shell("pm", "path", package, check=False)
        paths = result.splitlines()
        if not paths:
            return None
        if len(paths) != 1 or not re.fullmatch(r"package:/[A-Za-z0-9_./=+~\-]+/base\.apk", paths[0]):
            raise RuntimeError("预期为单个开发 APK：" + package)
        return self.shell("sha256sum", paths[0][8:]).split()[0]

    def install_apks(self):
        self.notify("正在核对并安装验收版本…")
        self.installed = []
        for variant, package in (("release", RELEASE), ("debug", HOST)):
            path = ROOT / f"android/app/build/outputs/apk/{variant}/app-{variant}.apk"
            expected = digest(path)
            if self.installed_hash(package) != expected:
                self.adb("install", "-r", "-t", path, timeout=120)
            if self.installed_hash(package) != expected:
                raise RuntimeError("安装后 APK 校验不一致：" + package)
            self.installed.append({"package": package, "sha256": expected, "file": str(path.resolve())})
        details = self.shell("dumpsys", "package", RELEASE)
        match = re.search(r"versionName=([^\s]+)", details)
        self.version = match.group(1) if match else "开发预览"

    def device_state(self):
        state = {key: self.shell("settings", "get", "system", key) for key in SYSTEM_SETTINGS}
        for key in ("default_input_method", "show_ime_with_hard_keyboard"):
            state[key] = self.shell("settings", "get", "secure", key)
        for key in ("size", "density"):
            raw = self.shell("wm", key)
            override = re.search(r"Override (?:size|density): (\S+)", raw)
            state[key] = override.group(1) if override else "reset"
        state["night"] = self.shell("cmd", "uimode", "night").removeprefix("Night mode: ").strip()
        return state

    def restore(self):
        if not self.baseline:
            return
        self.verify_device()
        self.notify("正在恢复模拟器显示设置…")
        for key in ("size", "density"):
            self.shell("wm", key, self.baseline[key])
        for key in SYSTEM_SETTINGS:
            value = self.baseline[key]
            self.shell("settings", "delete" if value == "null" else "put", "system", key,
                       *([] if value == "null" else [value]))
        value = self.baseline["show_ime_with_hard_keyboard"]
        self.shell("settings", "delete" if value == "null" else "put", "secure", "show_ime_with_hard_keyboard",
                   *([] if value == "null" else [value]))
        previous = self.baseline["default_input_method"]
        if previous and previous != "null":
            self.shell("ime", "set", previous)
        if self.baseline["night"] in ("yes", "no", "auto"):
            self.shell("cmd", "uimode", "night", self.baseline["night"])
        json_write(self.journal, {"restored": True, "workspace": str(ROOT), "serial": self.serial})
        self.baseline = None

    def prepare(self, geometry=None):
        self.scrcpy = prepare_scrcpy(self.notify)
        self.ensure_apks()
        self.connect()
        if self.journal.is_file():
            previous = json.loads(self.journal.read_text(encoding="utf-8"))
            if not previous.get("restored", True):
                if previous.get("workspace") != str(ROOT) or previous.get("serial") != self.serial:
                    raise RuntimeError("上次验收有待恢复的设备状态，且与当前设备不一致。请查看 restore-state.json。")
                self.baseline = previous["state"]
                self.restore()
        self.baseline = self.device_state()
        self.initial_state = dict(self.baseline)
        json_write(self.journal, {"workspace": str(ROOT), "serial": self.serial, "restored": False,
                                  "state": self.baseline, "session": str(self.session)})
        self.install_apks()
        component = RELEASE + "/.ime.StudyInputMethodService"
        self.shell("ime", "enable", component)
        self.shell("ime", "set", component)
        self.shell("settings", "put", "secure", "show_ime_with_hard_keyboard", "1")
        self.shell("settings", "put", "system", "screen_off_timeout", "2147483647")
        self.shell("input", "keyevent", "KEYCODE_WAKEUP")
        self.open_scenario("text")
        self.open_mirror(geometry)
        self.save_session()
        self.notify("已就绪 · 在手机窗口点按键盘开始体验")

    def save_session(self):
        json_write(self.session / "session.json", {"workspace": str(ROOT), "serial": self.serial,
            "version": self.version, "installedApks": self.installed, "initialDeviceState": self.initial_state,
            "events": self.events, "scope": "Manual interaction with real Release IME; not an automated pass or physical-device performance result"})

    def note(self, action):
        self.events.append({"at": datetime.now(timezone.utc).isoformat(), "action": action})
        self.save_session()

    def open_scenario(self, kind):
        if kind not in SCENARIOS:
            raise ValueError("未知验收场景")
        self.verify_device()
        self.shell("am", "start", "-W", "-n", HOST + "/org.studyime.android.ProbeActivity", "-f", "0x10008000",
                   "--es", "field", kind, "--ez", "manual", "true", timeout=30)
        self.scenario = kind
        self.note("scenario:" + kind)
        self.notify(SCENARIOS[kind][0] + " · " + SCENARIOS[kind][1])

    def open_app(self, screen):
        if screen not in ("home", "practice", "settings", "about"):
            raise ValueError("未知页面")
        self.verify_device()
        self.shell("am", "start", "-W", "-n", RELEASE + "/.MainActivity", "-f", "0x10008000",
                   "--es", "screen", screen, timeout=30)
        self.note("app:" + screen)

    def open_mirror(self, geometry=None):
        if self.mirror and self.mirror.poll() is None:
            return
        self.verify_device()
        env = dict(os.environ, ADB=str(self.adb_path.resolve()))
        options = [self.scrcpy, "--serial=" + self.serial, "--no-audio", "--no-clipboard-autosync",
                   "--no-power-on", "--shortcut-mod=lalt", "--force-adb-forward", "--max-size=1440",
                   "--max-fps=60", "--video-bit-rate=4M", "--window-title=拾词 · Android 交互验收 · " + self.version]
        if geometry:
            x, y, height = geometry
            options += [f"--window-x={x}", f"--window-y={y}", f"--window-height={height}"]
        else:
            options += ["--window-height=800"]
        log_path = self.session / "scrcpy.log"
        offset = log_path.stat().st_size if log_path.exists() else 0
        with log_path.open("ab") as log:
            self.mirror = subprocess.Popen([str(item) for item in options], stdout=log, stderr=subprocess.STDOUT,
                                           cwd=self.scrcpy.parent, env=env, creationflags=NO_WINDOW)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with log_path.open("rb") as log:
                log.seek(offset)
                output = log.read().decode("utf-8", errors="replace")
            if self.mirror.poll() is not None:
                raise RuntimeError("操作窗口启动失败：\n" + output[-1800:])
            if mirror_ready(output):
                return
            time.sleep(.3)
        raise RuntimeError("操作窗口未及时显示画面，请查看本次会话的 scrcpy.log。")

    def display(self, preset):
        if self.recording:
            raise RuntimeError("请先结束录像，再调整屏幕布局。")
        self.verify_device()
        if preset in ("portrait", "narrow", "landscape"):
            self.shell("settings", "put", "system", "accelerometer_rotation", "0")
            self.shell("settings", "put", "system", "user_rotation", "1" if preset == "landscape" else "0")
            self.shell("wm", "size", "880x1904" if preset == "narrow" else "1080x2340")
            self.shell("wm", "density", "440")
        elif preset in ("font100", "font130"):
            self.shell("settings", "put", "system", "font_scale", "1.3" if preset == "font130" else "1.0")
        elif preset in ("light", "dark"):
            self.shell("cmd", "uimode", "night", "yes" if preset == "dark" else "no")
        else:
            raise ValueError("未知显示预设")
        self.note("display:" + preset)

    def capture_metadata(self):
        self.verify_device()
        for apk in self.installed:
            if self.installed_hash(apk["package"]) != apk["sha256"]:
                raise RuntimeError("设备中的 APK 已变化，请重新启动验收后再保存证据。")
        return {"at": datetime.now(timezone.utc).isoformat(), "serial": self.serial, "version": self.version,
                "installedApks": self.installed, "scenario": self.scenario, "deviceState": self.device_state(),
                "scope": "User-triggered capture; does not claim acceptance passed"}

    def screenshot(self):
        metadata = self.capture_metadata()
        data = self.adb("exec-out", "screencap", "-p", binary=True).stdout
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("未收到有效的原生截图")
        path = WORK / "captures" / (timestamp() + "-" + self.scenario + ".png")
        write(path, data)
        json_write(path.with_suffix(".json"), {**metadata, "sha256": digest(path)})
        self.note("screenshot:" + path.name)
        return path.resolve()

    def start_recording(self):
        if self.recording:
            raise RuntimeError("正在录像")
        metadata = self.capture_metadata()
        identifier = timestamp() + "-" + uuid.uuid4().hex[:8]
        remote = "/data/local/tmp/studyime-acceptance-" + identifier + ".mp4"
        script = "/data/local/tmp/studyime-acceptance-" + identifier + ".sh"
        local_script = self.session / (identifier + ".sh")
        write(local_script, RECORD_HELPER)
        self.adb("push", local_script, script)
        png = self.adb("exec-out", "screencap", "-p", binary=True).stdout
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("无法读取屏幕尺寸")
        width, height = struct.unpack(">II", png[16:24])
        scale = min(1, 1280 / max(width, height))
        size = f"{max(2, int(width * scale) // 2 * 2)}x{max(2, int(height * scale) // 2 * 2)}"
        pid = self.shell("sh", script, "start", remote, size)
        if not pid.isdecimal():
            raise RuntimeError("录像启动失败：" + pid)
        self.recording = {"pid": pid, "remote": remote, "script": script, "identifier": identifier,
                          "started": time.monotonic(), "metadata": metadata}
        self.note("recording:start")

    def stop_recording(self):
        if not self.recording:
            return None
        self.verify_device()
        record = self.recording
        self.shell("sh", record["script"], "stop", record["pid"], record["remote"], timeout=20)
        path = WORK / "captures" / (record["identifier"] + ".mp4")
        safe(path).parent.mkdir(parents=True, exist_ok=True)
        self.adb("pull", record["remote"], path, timeout=90)
        with path.open("rb") as stream:
            valid = stream.read(12)[4:8] == b"ftyp"
        if not valid or path.stat().st_size < 1024:
            self.recording = None
            raise RuntimeError("录像未成功生成；诊断保留在模拟器的同名 .log 文件。")
        json_write(path.with_suffix(".json"), {**record["metadata"], "sha256": digest(path),
            "finishedAt": datetime.now(timezone.utc).isoformat(), "maximumSeconds": 120,
            "end": self.capture_metadata()})
        self.recording = None
        self.shell("rm", "-f", record["remote"], record["remote"] + ".log", record["script"])
        self.note("recording:saved:" + path.name)
        return path.resolve()

    def close(self):
        errors = []
        if self.recording:
            try:
                self.stop_recording()
            except Exception as error:
                errors.append(str(error))
        if self.mirror and self.mirror.poll() is None:
            self.mirror.terminate()
            self.mirror.wait(timeout=8)
        try:
            self.restore()
        except Exception as error:
            errors.append(str(error))
        self.note("closed" if not errors else "close:recovery-needed")
        if errors:
            raise RuntimeError("\n".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", choices=SERIALS)
    args = parser.parse_args()
    from tools.android.acceptance_ui import run
    run(args.serial)


if __name__ == "__main__":
    main()
