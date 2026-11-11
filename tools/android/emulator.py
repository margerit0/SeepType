"""Install and run a headless AOSP emulator using existing WSL KVM support."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, DOWNLOADS, ROOT, digest, extract, fetch, json_write, safe, write


def install():
    records = json.loads((CACHE / "sdk-downloads.json").read_text())
    for item in records:
        if item["path"] not in ("emulator", "system-images;android-30;default;x86_64"):
            continue
        destination = CACHE / "sdk" / item["path"].replace(";", "/")
        if (destination / ".study-receipt.json").exists():
            continue
        archive = fetch(item["url"], DOWNLOADS / item["url"].split("/")[-1], item["sha1"], "sha1")
        print("Extract " + item["path"], flush=True)
        extract(archive, destination)
        # ZIP symlinks are replaced with checked hard links inside this isolated
        # SDK. This works on NTFS without enabling system-wide developer mode.
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if (member.external_attr >> 16) & 0o170000 != 0o120000:
                    continue
                relative = "/".join(member.filename.split("/")[1:])
                target = safe(destination / relative)
                source = safe(target.parent / bundle.read(member).decode("utf-8"))
                if not source.is_relative_to(destination.resolve()) or not source.is_file():
                    raise ValueError("Unsafe or unresolved emulator library link")
                if not target.exists():
                    os.link(source, target)
        json_write(destination / ".study-receipt.json", {**item, "sha256": digest(archive)})
        archive.unlink()
    print("AOSP API 30 x86_64 image and Linux emulator installed.")


def linux_path(path):
    path = Path(path).resolve()
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def configure():
    avd = CACHE / "avd/StudyIME_API30.avd"
    avd.mkdir(parents=True, exist_ok=True)
    write(CACHE / "avd/StudyIME_API30.ini", f"avd.ini.encoding=UTF-8\npath={linux_path(avd)}\ntarget=android-30\n")
    values = {"AvdId": "StudyIME_API30", "avd.ini.displayname": "StudyIME Android 11 (API 30)",
              "abi.type": "x86_64", "hw.cpu.arch": "x86_64", "hw.cpu.ncore": "2", "hw.ramSize": "1024",
              "hw.lcd.width": "1080", "hw.lcd.height": "2340", "hw.lcd.density": "440",
              "hw.keyboard": "yes", "hw.mainKeys": "no", "hw.gpu.enabled": "yes", "hw.gpu.mode": "swiftshader_indirect",
              "hw.audioInput": "no", "hw.camera.back": "none", "hw.camera.front": "none",
              "image.sysdir.1": linux_path(CACHE / "sdk/system-images/android-30/default/x86_64") + "/",
              "tag.id": "default", "tag.display": "Default", "PlayStore.enabled": "false",
              "disk.dataPartition.size": "1024M", "fastboot.forceColdBoot": "yes", "showDeviceFrame": "no"}
    write(avd / "config.ini", "".join(f"{key}={value}\n" for key, value in values.items()))


def start():
    configure()
    env_args = [f"ANDROID_HOME={linux_path(CACHE / 'sdk')}", f"ANDROID_SDK_ROOT={linux_path(CACHE / 'sdk')}",
                f"ANDROID_AVD_HOME={linux_path(CACHE / 'avd')}", f"ANDROID_USER_HOME={linux_path(CACHE / 'android-user')}",
                f"ANDROID_EMULATOR_HOME={linux_path(CACHE / 'emulator-user')}",
                f"XDG_CACHE_HOME={linux_path(CACHE / 'emulator-xdg')}", "QT_QPA_PLATFORM=offscreen"]
    log = CACHE / "logs/emulator.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    command = ["wsl.exe", "--user", "root", "--exec", "env", *env_args,
               linux_path(CACHE / "sdk/emulator/emulator"), "-avd", "StudyIME_API30", "-no-window", "-no-audio",
               "-no-boot-anim", "-no-snapshot", "-gpu", "swiftshader_indirect", "-accel", "on", "-port", "5554"]
    with log.open("wb") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    json_write(CACHE / "emulator-process.json", {"pid": process.pid, "avd": "StudyIME_API30", "log": str(log)})
    print(f"Started headless emulator launcher PID {process.pid}; see {log}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["install", "start"])
    args = parser.parse_args()
    {"install": install, "start": start}[args.step]()
