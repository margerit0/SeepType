"""ADB helper restricted by default to the development emulator."""
import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE
from tools.android.build_env import tool_env


def adb(*arguments, serial="emulator-5554", binary=False, check=True, timeout=120):
    command = [str(CACHE / "sdk/platform-tools/adb.exe")]
    if serial: command += ["-s", serial]
    command += [str(arg) for arg in arguments]
    return subprocess.run(command, env=tool_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=not binary, encoding=None if binary else "utf-8", check=check, timeout=timeout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    result = adb(*args.arguments, serial=None if args.arguments[0] in ("devices", "connect", "start-server") else args.serial, check=False)
    print(result.stdout, end="")
    if result.stderr: print(result.stderr, file=sys.stderr, end="")
    raise SystemExit(result.returncode)
