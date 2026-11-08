"""Fetch pinned SDK/NDK and reuse installed build tools without changing PATH."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, DOWNLOADS, ROOT, digest, extract, fetch, json_write, write

GOOGLE = "https://dl.google.com/android/repository/"


def ndk_file(name):
    """NDK subset sufficient for API 29, arm64 and x86_64 release builds."""
    if name.startswith(("sources/", "shader-tools/", "simpleperf/", "prebuilt/")):
        return False
    if any(value in name for value in ("/i686-linux-android/", "/arm-linux-androideabi/", "/python", "/lldb", "/share/")):
        return False
    if "/bin/" in name and "toolchains/" in name:
        leaf = name.rsplit("/", 1)[-1]
        return leaf in {"clang.exe", "clang++.exe", "ld.lld.exe", "llvm-ar.exe", "llvm-ranlib.exe", "llvm-strip.exe", "llvm-readelf.exe", "llvm-nm.exe", "llvm-objcopy.exe"} or (leaf.endswith(".dll") and leaf != "liblldb.dll") or ("linux-android29-clang" in leaf)
    if "/sysroot/usr/lib/" in name:
        parts = name.split("/sysroot/usr/lib/", 1)[1].split("/")
        if parts[0] not in ("aarch64-linux-android", "x86_64-linux-android"):
            return False
        if len(parts) > 2 and parts[1].isdigit() and parts[1] != "29":
            return False
    return True


def repository(filename="repository2-3.xml", prefix=GOOGLE):
    path = fetch(prefix + filename, DOWNLOADS / filename)
    return ET.parse(path).getroot()


def packages(root, wanted, host="windows", prefix=GOOGLE):
    result = []
    for package in root.findall("remotePackage"):
        if package.get("path") not in wanted:
            continue
        channel = package.find("channelRef")
        if channel is not None and channel.get("ref") != "channel-0":
            continue
        for archive in package.findall("archives/archive"):
            if archive.findtext("host-os") not in (host, None):
                continue
            complete = archive.find("complete")
            result.append({"path": package.get("path"), "url": prefix + complete.findtext("url"),
                           "size": int(complete.findtext("size")),
                           "sha1": complete.findtext("checksum"), "host": host,
                           "revision": ".".join(package.findtext("revision/" + part, "0") for part in ("major", "minor", "micro"))})
    return result


def metadata():
    root = repository()
    records = packages(root, {"platforms;android-35", "build-tools;35.0.0", "ndk;27.2.12479018", "platform-tools"})
    records += packages(root, {"emulator"}, host="linux")
    image_prefix = GOOGLE + "sys-img/android/"
    images = repository("sys-img2-3.xml", image_prefix)
    records += packages(images, {"system-images;android-30;default;x86_64"}, host="linux", prefix=image_prefix)
    json_write(CACHE / "sdk-downloads.json", records)
    print(json.dumps(records, indent=2))


def install_sdk():
    records = json.loads((CACHE / "sdk-downloads.json").read_text())
    installed = []
    for item in records:
        if item["path"] in ("emulator", "system-images;android-30;default;x86_64"):
            continue
        destination = CACHE / "sdk" / item["path"].replace(";", "/")
        receipt = destination / ".study-receipt.json"
        if receipt.exists():
            installed.append(json.loads(receipt.read_text()))
            continue
        archive = fetch(item["url"], DOWNLOADS / item["url"].split("/")[-1], item["sha1"], "sha1")
        print("Extract " + item["path"], flush=True)
        # Keep complete toolchain for both supported 64-bit ABIs. Omit
        # unrelated 32-bit sysroots and debugging tools to fit small disks.
        def select(name):
            if not item["path"].startswith("ndk;"):
                return True
            return ndk_file(name)
        extract(archive, destination, select)
        record = {**item, "sha256": digest(archive), "selection": "64-bit toolchain; no clangd/lldb" if item["path"].startswith("ndk;") else "complete"}
        json_write(receipt, record)
        installed.append(record)
        # Receipts retain checksums; SDK archives are recoverable from Google.
        archive.unlink()
    licenses = CACHE / "sdk/licenses"
    write(licenses / "android-sdk-license", "8933bad161af4178b1185d1a37fbf41ea5269c55\nd56f5187479451eabf01fb78af6dfcb131a6481e\n24333f8a63b6825ea9c5514f83c2829b004d1fee\n")
    json_write(CACHE / "sdk-receipt.json", installed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["metadata", "sdk"])
    args = parser.parse_args()
    {"metadata": metadata, "sdk": install_sdk}[args.step]()
