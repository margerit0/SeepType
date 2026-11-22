"""Freeze and conservatively attribute emulator exit records and tombstones."""
# SPDX-License-Identifier: GPL-3.0-or-later
from datetime import datetime
import re
import shlex

from tools.android.common import digest, json_write, write
from tools.android.device import adb

EXIT_PACKAGES = ("org.studyime.android.debug", "com.android.systemui", "com.android.phone", "android")
TOMBSTONE = re.compile(r"^/data/tombstones/tombstone_[0-9]+(?:\.pb)?$")


def parse_exit_info(text, offset):
    records = []
    for block in re.split(r"ApplicationExitInfo #\d+:", text)[1:]:
        match = re.search(r"timestamp=(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) pid=(\d+)", block)
        process = re.search(r"process=(\S+) reason=(\d+) \(([^)]+)\).*?status=(\d+)", block)
        if not match or not process:
            raise ValueError("Unrecognized ApplicationExitInfo record; preserve the raw dump")
        timestamp, pid = match.groups()
        records.append({"epoch": datetime.fromisoformat(timestamp + offset).timestamp(),
                        "pid": pid, "process": process[1], "reason": int(process[2]),
                        "reasonName": process[3], "status": int(process[4]), "raw": block.strip()})
    return records


def exit_key(record):
    return tuple(record.get(name) for name in ("epoch", "pid", "process", "reason", "status"))


def attribute_record(record, before, after, interval, *, existed=False):
    """A new file/PID alone never proves an event belongs to this attempt."""
    if existed:
        return "historical"
    if before.get("bootId") != after.get("bootId") or not after.get("bootId"):
        return "unresolved-boot"
    if before.get("timezoneOffset") != after.get("timezoneOffset"):
        return "unresolved-clock"
    # Detect wall-clock jumps instead of mapping old wall timestamps to a new boot.
    elapsed = after.get("uptimeSeconds", 0) - before.get("uptimeSeconds", 0)
    wall = after.get("epochSeconds", 0) - before.get("epochSeconds", 0)
    if abs(elapsed - wall) > 1:
        return "unresolved-clock"
    begin, end = interval.get("beginEpoch"), interval.get("endEpoch")
    if begin is None or end is None or record.get("epoch") is None or not record.get("pid") or not record.get("process"):
        return "unresolved-identity"
    return "current" if float(begin) <= record["epoch"] <= float(end) else "outside-run"


def parse_tombstone(text):
    timestamp = re.search(r"^Timestamp:\s*(.+)$", text, re.MULTILINE)
    process = re.search(r"^pid:\s*(\d+),.*?>>> (.+?) <<<", text, re.MULTILINE)
    command = re.search(r"^Cmdline:\s*(.+)$", text, re.MULTILINE)
    signal = re.search(r"^signal .+$", text, re.MULTILINE)
    return {"epoch": datetime.fromisoformat(timestamp[1]).timestamp() if timestamp else None,
            "pid": process[1] if process else None,
            "process": command[1] if command else process[2] if process else None,
            "signal": signal[0] if signal else None}


def tombstone_inventory(serial):
    # userdebug su reads the files without restarting adbd, changing SELinux or
    # installing a helper. The command and file names are fixed/validated.
    script = 'test -r /data/tombstones && for f in /data/tombstones/tombstone_*; do if [ -f "$f" ]; then stat -c "%n|%s|%Y|%i" "$f"; sha256sum "$f"; fi; done'
    result = adb("shell", "su 0 sh -c " + shlex.quote(script), serial=serial, check=False, timeout=20)
    if result.returncode:
        raise RuntimeError("Tombstone inventory unavailable: " + result.stderr.strip())
    lines, value = result.stdout.splitlines(), {}
    if len(lines) % 2:
        raise ValueError("Incomplete tombstone inventory")
    for index in range(0, len(lines), 2):
        path, size, modified, inode = lines[index].split("|")
        sha256 = lines[index + 1].split()[0]
        if not TOMBSTONE.fullmatch(path) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("Unexpected tombstone inventory entry")
        value[path] = {"bytes": int(size), "modifiedEpoch": int(modified), "inode": inode, "sha256": sha256}
    return value


def exit_snapshot(serial, directory, ime_package, offset):
    records = []
    for package in dict.fromkeys((ime_package, *EXIT_PACKAGES)):
        result = adb("shell", "dumpsys", "activity", "exit-info", package, serial=serial, timeout=15)
        write(directory / (package + "-exit-info.txt"), result.stdout + result.stderr)
        records.extend(parse_exit_info(result.stdout, offset))
    # The same system record can be returned under more than one package.
    return list({exit_key(record): record for record in records}.values())


def freeze_tombstones(serial, directory, previous, current, before, after, interval):
    records = []
    for path, metadata in current.items():
        if previous.get(path) == metadata:
            continue
        result = adb("exec-out", "su", "0", "cat", path, serial=serial, binary=True, timeout=20)
        destination = directory / path.rsplit("/", 1)[-1]
        write(destination, result.stdout)
        if digest(destination) != metadata["sha256"]:
            raise RuntimeError("Tombstone changed while being frozen: " + path)
        if path.endswith(".pb"):
            continue  # Preserve the proto; attribute its matching text file once.
        record = {**metadata, **parse_tombstone(result.stdout.decode("utf-8", errors="replace")), "file": destination.name}
        record["attribution"] = attribute_record(record, before, after, interval)
        records.append(record)
    json_write(directory / "attribution.json", records)
    return records
