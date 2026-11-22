"""Read-only host/WSL state, sampled outside the timed device work."""
# SPDX-License-Identifier: GPL-3.0-or-later
from datetime import datetime, timezone
import json
import os
import subprocess


WINDOWS = r"""
$ErrorActionPreference = 'Stop'
$osState = Get-CimInstance Win32_OperatingSystem
$cpuState = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor | Where-Object Name -eq '_Total'
$memoryState = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$processState = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(java|javaw|qemu.*|emulator|wsl|vmmemWSL|adb)\.exe$|^vmmemWSL$' } | ForEach-Object {
    [ordered]@{pid=$_.ProcessId; parentPid=$_.ParentProcessId; name=$_.Name; createdAt=$_.CreationDate;
        workingSetBytes=$_.WorkingSetSize; kernelTime100ns=$_.KernelModeTime; userTime100ns=$_.UserModeTime;
        emulatorCommand=$(if ($_.CommandLine -match 'sdk[/\\]emulator[/\\].*(-avd|qemu)') { $_.CommandLine } else { $null })}
}
[ordered]@{capturedAt=[DateTime]::UtcNow.ToString('o'); lastBoot=$osState.LastBootUpTime;
    totalMemoryKb=$osState.TotalVisibleMemorySize; freeMemoryKb=$osState.FreePhysicalMemory;
    availableBytes=$memoryState.AvailableBytes; committedBytes=$memoryState.CommittedBytes;
    commitLimitBytes=$memoryState.CommitLimit; cpuBusyPercent=$cpuState.PercentProcessorTime;
    processes=@($processState)} | ConvertTo-Json -Depth 5 -Compress
"""

LINUX = r"""
import glob, json, os, time
def read(path):
    try:
        with open(path) as stream: return stream.read().strip()
    except OSError as error: return {'unavailable':str(error)}
processes=[]
for directory in glob.glob('/proc/[0-9]*'):
    name=read(directory+'/comm')
    if not isinstance(name,str) or not name.startswith(('qemu','emulator','java')): continue
    command=read(directory+'/cmdline')
    processes.append({'pid':int(directory.rsplit('/',1)[-1]), 'name':name,
        'stat':read(directory+'/stat'), 'status':read(directory+'/status'),
        'emulatorCommand':command.replace('\0',' ') if name.startswith(('qemu','emulator')) and isinstance(command,str) else None})
print(json.dumps({'epochSeconds':time.time(),'kernel':os.uname().release,'clockTicksPerSecond':os.sysconf('SC_CLK_TCK'),
    'bootId':read('/proc/sys/kernel/random/boot_id'),'uptime':read('/proc/uptime'),
    'load':read('/proc/loadavg'),'memory':read('/proc/meminfo'),'cpu':read('/proc/stat'),
    'pressure':{name:read('/proc/pressure/'+name) for name in ['cpu','memory','io']},
    'processes':processes}))
"""


def host_snapshot():
    value = {"startedAt": datetime.now(timezone.utc).isoformat(), "errors": []}
    commands = {"windows": ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", WINDOWS],
                "wsl": ["wsl.exe", "--exec", "python3", "-c", LINUX]} if os.name == "nt" else {
                    "linux": ["python3", "-c", LINUX]}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=20,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or f"exit {result.returncode}")
            value[name] = json.loads(result.stdout.lstrip("\ufeff"))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            value["errors"].append(name + ": " + str(error))
    value["finishedAt"] = datetime.now(timezone.utc).isoformat()
    return value
