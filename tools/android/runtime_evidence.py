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
from tools.android.device import adb, require_emulator
from tools.android.host_evidence import host_snapshot
from tools.android.runtime_artifacts import (attribute_record, exit_key, exit_snapshot,
                                             freeze_tombstones, tombstone_inventory)

SYSTEM_PROCESSES = ("zygote64", "system_server", "com.android.systemui")
LINE = re.compile(r"^\s*(\d+\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+(\S+)\s*:\s?(.*)$")


def classify_process(name, ime_package):
    if name == ime_package or name.startswith(ime_package + ":"):
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
    interval = {}
    for line in text.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        epoch, pid, tid, level, tag, message = match.groups()
        if tag == "StudyIMEValidation" and message == start:
            if not saw_start:
                interval["beginEpoch"] = float(epoch)
            active = saw_start = True
            continue
        if tag == "StudyIMEValidation" and message == end and active:
            saw_end = True
            interval["endEpoch"] = float(epoch)
            break
        if active:
            rows.append((epoch, pid, tid, level, tag, message))
            java = re.search(r"Process: ([\w.:/]+), PID: (\d+)", message)
            native = re.search(r"pid: (\d+),.*>>> (.+?) <<<", message)
            if java:
                names[java[2]] = java[1]
            if native:
                names[native[1]] = native[2]
    crashes = []
    deaths = []
    for epoch, pid, tid, level, tag, message in rows:
        if (tag == "AndroidRuntime" and "FATAL EXCEPTION" in message) or (tag == "libc" and "Fatal signal " in message):
            # SI_USER includes the signal sender's PID earlier in the message.
            # The trailing pid (...) identifies the process that actually died.
            native_pid = re.search(r"\bpid (\d+) \([^)]*\)\s*$", message) if tag == "libc" else None
            process_pid = native_pid[1] if native_pid else pid
            name = names.get(process_pid, "unknown")
            crashes.append({"epoch": epoch, "pid": process_pid, "tid": tid, "process": name,
                            "category": classify_process(name, ime_package), "message": message})
        if tag in ("am_proc_died", "am_kill"):
            deaths.append({"epoch": epoch, "tag": tag, "message": message})
    return {"markersComplete": saw_start and saw_end, "interval": interval,
            "crashes": crashes, "processExitEvents": deaths}


def process_snapshot(serial, ime_package="org.studyime.android"):
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
    for name in (*SYSTEM_PROCESSES, ime_package, "org.studyime.android.debug", "com.android.phone"):
        for pid in processes.get(name, []):
            result = adb("shell", "cat", f"/proc/{pid}/stat", serial=serial, check=False, timeout=10)
            fields = result.stdout.rpartition(")")[2].split()
            birth[pid] = fields[19] if result.returncode == 0 and len(fields) >= 20 else None
    clock = adb("shell", "date '+%s.%N %z'; cat /proc/uptime", serial=serial, timeout=15).stdout.split()
    if len(clock) != 4 or not re.fullmatch(r"[+-]\d{4}", clock[1]):
        raise RuntimeError("Device clock/uptime correlation is unavailable")
    return {"bootId": boot, "processes": processes, "processStartTicks": birth,
            "epochSeconds": float(clock[0]), "timezoneOffset": clock[1], "uptimeSeconds": float(clock[2])}


class RuntimeCapture:
    def __init__(self, serial, directory, ime_package, require_ime_continuity=False):
        self.serial, self.directory, self.ime_package = serial, directory, ime_package
        self.require_ime_continuity = require_ime_continuity
        self.token = uuid.uuid4().hex
        self.summary = {"runId": self.token, "startedAt": datetime.now(timezone.utc).isoformat(),
                        "serial": serial, "complete": False, "passed": False, "captureErrors": []}
        self.logger = self.stream = None
        self.previous_tombstones = {}
        self.previous_exits = []
        self.failure = None

    def capture_step(self, name, work):
        try:
            return work()
        except Exception as error:
            self.summary["captureErrors"].append(name + ": " + str(error))
            return None

    def checkpoint(self, phase):
        host = host_snapshot()
        json_write(self.directory / ("host-" + phase + ".json"), host)
        self.summary["captureErrors"].extend("host-" + phase + ": " + value for value in host["errors"])
        snapshot = self.summary[phase]
        exits = exit_snapshot(self.serial, self.directory / phase, self.ime_package, snapshot["timezoneOffset"])
        inventory = tombstone_inventory(self.serial)
        json_write(self.directory / phase / "tombstones.json", inventory)
        package = adb("shell", "dumpsys", "package", self.ime_package, serial=self.serial, timeout=15).stdout
        write(self.directory / phase / "package.txt", package)
        self.summary[phase + "Compilation"] = package.partition("Dexopt state:")[2].partition("Compiler stats:")[0].strip()
        return exits, inventory

    def note_failure(self, message):
        # The trigger is independent of capture errors and is never overwritten
        # by a failed dumpsys or a missing attachment.
        if self.failure is None:
            self.failure = str(message)
            self.summary["triggerFailure"] = self.failure

    def freeze_failure(self):
        for name, command in {
            "activity-processes.txt": ("shell", "dumpsys", "activity", "processes"),
            "input-method.txt": ("shell", "dumpsys", "input_method"),
            "ime-memory.txt": ("shell", "dumpsys", "meminfo", self.ime_package),
            "ime-metrics.txt": ("shell", "dumpsys", "activity", "service",
                                self.ime_package + "/org.studyime.android.ime.StudyInputMethodService", "study-metrics"),
        }.items():
            def collect(name=name, command=command):
                result = adb(*command, serial=self.serial, check=False, timeout=15)
                write(self.directory / "failure" / name, result.stdout + result.stderr)
                if result.returncode:
                    raise RuntimeError(f"exit {result.returncode}")
            self.capture_step(name, collect)
        def screenshot():
            result = adb("exec-out", "screencap", "-p", serial=self.serial, binary=True, timeout=15)
            write(self.directory / "failure/screen.png", result.stdout)
            if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Invalid failure screenshot")
        self.capture_step("screenshot", screenshot)

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
        require_emulator(self.serial)
        self.directory.mkdir(parents=True, exist_ok=False)
        try:
            self.summary["before"] = process_snapshot(self.serial, self.ime_package)
            self.previous_exits, self.previous_tombstones = self.checkpoint("before")
            if self.summary["captureErrors"]:
                raise RuntimeError("Runtime evidence preflight is incomplete")
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
        if len(exception) > 1 and exception[1] is not None:
            self.note_failure(exception[1])
        try:
            self.marker("end")
        except Exception as error:
            self.summary["captureErrors"].append(str(error))
        finally:
            self.stop_logger()
        self.summary["after"] = self.capture_step("process-after", lambda: process_snapshot(self.serial, self.ime_package)) or {}
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
        checkpoint = self.capture_step("checkpoint-after", lambda: self.checkpoint("after"))
        self.summary["artifactCrashes"] = []
        if checkpoint is not None:
            exits, inventory = checkpoint
            prior = {exit_key(record) for record in self.previous_exits}
            for record in exits:
                record["attribution"] = attribute_record(record, before, after, self.summary["interval"], existed=exit_key(record) in prior)
                record["category"] = classify_process(record["process"], self.ime_package)
            json_write(self.directory / "exit-attribution.json", exits)
            tombstones = self.capture_step("freeze-tombstones", lambda: freeze_tombstones(
                self.serial, self.directory / "tombstones", self.previous_tombstones, inventory,
                before, after, self.summary["interval"])) or []
            self.summary["exitRecords"] = [{key: value for key, value in record.items() if key != "raw"} for record in exits]
            self.summary["tombstones"] = tombstones
            self.summary["artifactCrashes"] = [record for record in exits if record["attribution"] == "current" and record["reason"] in (4, 5, 6)]
            self.summary["artifactCrashes"] += [dict(record, category=classify_process(record["process"], self.ime_package))
                                                for record in tombstones if record["attribution"] == "current"]
        if self.failure or self.summary["crashes"] or self.summary["artifactCrashes"] or changes or self.summary["captureErrors"]:
            self.freeze_failure()
        # Compute these last: an attachment failure must not leave complete=true.
        self.summary["complete"] = self.summary["markersComplete"] and not self.summary["captureErrors"]
        self.summary["passed"] = (self.summary["complete"] and not self.failure and not self.summary["crashes"]
                                  and not self.summary["artifactCrashes"] and not changes)
        self.summary["finishedAt"] = datetime.now(timezone.utc).isoformat()
        json_write(self.directory / "runtime.json", self.summary)
        return False
