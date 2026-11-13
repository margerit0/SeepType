"""Capture one instrumentation attempt without clearing or reusing crash buffers."""
# SPDX-License-Identifier: GPL-3.0-or-later
from datetime import datetime, timezone
import os
import re
import subprocess
import time
import uuid

from tools.android.build_env import tool_env
from tools.android.common import CACHE, json_write, write
from tools.android.device import adb

SYSTEM_PROCESSES = ("zygote64", "system_server", "com.android.systemui")
LINE = re.compile(r"^\s*(\d+\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+(\S+)\s*:\s?(.*)$")


def classify_process(name, ime_package):
    if name == ime_package:
        return "ime"
    if name.startswith("org.studyime.android.debug"):
        return "test/editor"
    if name in (*SYSTEM_PROCESSES, "com.android.phone") or name.startswith("/system/"):
        return "system"
    return "other/unknown"


def parse_runtime_log(text, token, ime_package, known_processes=None):
    """Markers separate this run from stale entries in each logcat buffer."""
    start, end = "begin-" + token, "end-" + token
    names = dict(known_processes or {})
    rows = []
    active = False
    saw_start = saw_end = False
    for line in text.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        epoch, pid, tid, level, tag, message = match.groups()
        if tag == "StudyIMEValidation" and message == start:
            active = saw_start = True
            continue
        if tag == "StudyIMEValidation" and message == end and active:
            saw_end = True
            break
        if active:
            rows.append((epoch, pid, tid, level, tag, message))
            java = re.search(r"Process: ([\w.:/]+), PID: (\d+)", message)
            native = re.search(r"pid: (\d+),.*>>> ([\w.:/]+) <<<", message)
            if java:
                names[java[2]] = java[1]
            if native:
                names[native[1]] = native[2]
    crashes = []
    deaths = []
    for epoch, pid, tid, level, tag, message in rows:
        if (tag == "AndroidRuntime" and "FATAL EXCEPTION" in message) or (tag == "libc" and "Fatal signal " in message):
            native_pid = re.search(r"\bpid (\d+)\b", message) if tag == "libc" else None
            process_pid = native_pid[1] if native_pid else pid
            name = names.get(process_pid, "unknown")
            crashes.append({"epoch": epoch, "pid": process_pid, "tid": tid, "process": name,
                            "category": classify_process(name, ime_package), "message": message})
        if tag in ("am_proc_died", "am_kill"):
            deaths.append({"epoch": epoch, "tag": tag, "message": message})
    return {"markersComplete": saw_start and saw_end, "crashes": crashes, "processExitEvents": deaths}


def process_snapshot(serial):
    boot = adb("shell", "cat", "/proc/sys/kernel/random/boot_id", serial=serial, timeout=15).stdout.strip()
    if not boot:
        raise RuntimeError("Device boot identity is unavailable")
    process_list = adb("shell", "ps", "-A", "-o", "PID,NAME", serial=serial, timeout=15).stdout
    processes = {}
    for line in process_list.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            processes.setdefault(parts[1], []).append(parts[0])
    birth = {}
    for name in (*SYSTEM_PROCESSES, "org.studyime.android"):
        for pid in processes.get(name, []):
            result = adb("shell", "cat", f"/proc/{pid}/stat", serial=serial, check=False, timeout=10)
            fields = result.stdout.rpartition(")")[2].split()
            birth[pid] = fields[19] if result.returncode == 0 and len(fields) >= 20 else None
    return {"bootId": boot, "processes": processes, "processStartTicks": birth}


class RuntimeCapture:
    def __init__(self, serial, directory, ime_package, require_ime_continuity=False):
        self.serial, self.directory, self.ime_package = serial, directory, ime_package
        self.require_ime_continuity = require_ime_continuity
        self.token = uuid.uuid4().hex
        self.summary = {"runId": self.token, "startedAt": datetime.now(timezone.utc).isoformat(),
                        "serial": serial, "complete": False, "passed": False, "captureErrors": []}
        self.logger = self.stream = None

    def marker(self, phase):
        message = phase + "-" + self.token
        deadline = time.monotonic() + 5
        next_emit = 0
        while time.monotonic() < deadline:
            if message in (self.directory / "logcat.txt").read_text(encoding="utf-8", errors="replace"):
                return
            if self.logger.poll() is not None:
                break
            # Popen returns before logcat has attached to every buffer. The
            # first marker can otherwise precede its -T 1 subscription.
            if time.monotonic() >= next_emit:
                adb("shell", "log", "-p", "i", "-t", "StudyIMEValidation", message, serial=self.serial, timeout=15)
                next_emit = time.monotonic() + .2
            time.sleep(.05)
        raise RuntimeError("The runtime log did not capture its " + phase + " marker")

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=False)
        try:
            self.summary["before"] = process_snapshot(self.serial)
            self.stream = (self.directory / "logcat.txt").open("wb")
            self.logger = subprocess.Popen(
                [str(CACHE / "sdk/platform-tools/adb.exe"), "-s", self.serial, "logcat", "-b", "all", "-v", "epoch", "-T", "1"],
                env=tool_env(), stdout=self.stream, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.marker("begin")
            json_write(self.directory / "runtime.json", self.summary)
            return self
        except BaseException as error:
            self.stop_logger()
            self.summary["captureErrors"].append(str(error))
            self.summary["finishedAt"] = datetime.now(timezone.utc).isoformat()
            json_write(self.directory / "runtime.json", self.summary)
            raise

    def stop_logger(self):
        if self.logger and self.logger.poll() is None:
            self.logger.terminate()
            try:
                self.logger.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.logger.kill()
                self.logger.wait(timeout=5)
        if self.stream:
            self.stream.close()

    def __exit__(self, *exception):
        try:
            self.summary["after"] = process_snapshot(self.serial)
            self.marker("end")
        except Exception as error:
            self.summary["captureErrors"].append(str(error))
        finally:
            self.stop_logger()
        before, after = self.summary["before"], self.summary.get("after", {})
        names = {pid: name for name, pids in before["processes"].items() for pid in pids}
        text = (self.directory / "logcat.txt").read_text(encoding="utf-8", errors="replace")
        self.summary.update(parse_runtime_log(text, self.token, self.ime_package, names))
        changes = []
        if before["bootId"] != after.get("bootId"):
            changes.append("Device rebooted or became unavailable")
        monitored = (*SYSTEM_PROCESSES, self.ime_package) if self.require_ime_continuity else SYSTEM_PROCESSES
        for name in monitored:
            old = before["processes"].get(name, [])
            new = after.get("processes", {}).get(name, [])
            if (old and old != new) or (name in SYSTEM_PROCESSES and not old):
                changes.append(name + ": " + str(old) + " -> " + str(new))
            for pid in set(old) & set(new):
                start = before["processStartTicks"].get(pid)
                finish = after.get("processStartTicks", {}).get(pid)
                if start is not None and finish is not None and start != finish:
                    changes.append(name + ": PID reused " + pid)
        self.summary["processChanges"] = changes
        self.summary["complete"] = self.summary["markersComplete"] and not self.summary["captureErrors"]
        self.summary["passed"] = self.summary["complete"] and not self.summary["crashes"] and not changes
        self.summary["finishedAt"] = datetime.now(timezone.utc).isoformat()
        # Exit-info retains historical records and is diagnostic only; unlike the
        # marked log interval it must not be treated as this attempt's crashes.
        if not self.summary["passed"]:
            for package in (self.ime_package, "org.studyime.android.debug"):
                try:
                    result = adb("shell", "dumpsys", "activity", "exit-info", package, serial=self.serial, check=False, timeout=15)
                    write(self.directory / (package + "-exit-info.txt"), result.stdout + result.stderr)
                except Exception as error:
                    self.summary["captureErrors"].append(str(error))
        json_write(self.directory / "runtime.json", self.summary)
        return False
