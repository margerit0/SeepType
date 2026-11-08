"""Verify ABI, shared-library closure, ELF page alignment and APK zip layout."""
import argparse
import json
from pathlib import Path
import struct
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write


def elf(data):
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected a little-endian 64-bit ELF")
    machine = struct.unpack_from("<H", data, 18)[0]
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 54)
    headers = [struct.unpack_from("<IIQQQQQQ", data, phoff + index * phentsize) for index in range(phnum)]
    loads = [header for header in headers if header[0] == 1]
    if not loads or not all(header[7] >= 16384 and (header[2] - header[3]) % 16384 == 0 for header in loads):
        raise ValueError("ELF is not 16 KB page compatible")
    dynamic = next(header for header in headers if header[0] == 2)
    entries = [struct.unpack_from("<QQ", data, offset) for offset in range(dynamic[2], dynamic[2] + dynamic[5], 16)]
    strings_address = next(value for tag, value in entries if tag == 5)
    strings_segment = next(header for header in loads if header[3] <= strings_address < header[3] + header[5])
    strings = strings_segment[2] + strings_address - strings_segment[3]
    needed = []
    for tag, value in entries:
        if tag == 1:
            end = data.index(0, strings + value)
            needed.append(data[strings + value:end].decode("utf-8"))
    return {"machine": machine, "loadAlignments": [header[7] for header in loads], "needed": needed}


def verify(apk=None):
    allowed = {"libc.so", "libm.so", "libdl.so", "liblog.so", "libc++_shared.so", "libstudy_rime.so"}
    records = []
    for abi, machine in (("arm64-v8a", 183), ("x86_64", 62)):
        directory = ROOT / "android/app/src/main/jniLibs" / abi
        for name in ("libstudy_android.so", "libstudy_rime.so", "libc++_shared.so"):
            path = directory / name
            result = elf(path.read_bytes())
            if result["machine"] != machine or set(result["needed"]) - allowed:
                raise ValueError(f"Wrong ABI or unresolved runtime dependency in {abi}/{name}: {result}")
            records.append({"abi": abi, "file": name, "sha256": digest(path), **result})
    output = {"scope": "Static ELF ABI/alignment verification; actual 16 KB-device execution remains a separate check", "passed": True, "libraries": records}
    if apk:
        apk = Path(apk)
        binary = apk.read_bytes()
        entries = []
        with zipfile.ZipFile(apk) as bundle:
            for item in bundle.infolist():
                if not item.filename.endswith(".so"):
                    continue
                name_length, extra_length = struct.unpack_from("<HH", binary, item.header_offset + 26)
                offset = item.header_offset + 30 + name_length + extra_length
                if item.compress_type != zipfile.ZIP_STORED or offset % 16384:
                    raise ValueError("Native APK entry is not uncompressed/16 KB aligned: " + item.filename)
                native = elf(bundle.read(item))
                entries.append({"file": item.filename, "dataOffset": offset, "alignment": 16384, **native})
        expected = {f"lib/{record['abi']}/{record['file']}" for record in records}
        if not expected.issubset({entry["file"] for entry in entries}):
            raise ValueError("APK is missing a verified StudyIME native library")
        output["apk"] = {"path": str(apk.resolve()), "sha256": digest(apk), "bytes": apk.stat().st_size, "nativeEntries": entries}
    json_write(CACHE / "evidence" / ("apk-native-layout.json" if apk else "native-abi.json"), output)
    print(json.dumps({"passed": True, "libraries": len(records), "apkChecked": bool(apk)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path)
    args = parser.parse_args()
    verify(args.apk)
