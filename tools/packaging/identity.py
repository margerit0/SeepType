"""Generate all native identities and original icon resources from product.json."""
from pathlib import Path
import json
import struct
import sys
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, product, write_changed


def guid(value):
    fields = uuid.UUID(value).fields
    tail = uuid.UUID(value).bytes[8:]
    return "{0x%x,0x%x,0x%x,{%s}}" % (*fields[:3], ",".join(f"0x{x:02x}" for x in tail))


def png(size):
    def inside(x, y, a, b, width, height, radius):
        qx = abs(x - (a + width / 2)) - (width / 2 - radius)
        qy = abs(y - (b + height / 2)) - (height / 2 - radius)
        return max(qx, 0) ** 2 + max(qy, 0) ** 2 <= radius ** 2

    scanlines = bytearray()
    samples = 4
    for row in range(size):
        scanlines.append(0)
        for col in range(size):
            total = [0, 0, 0, 0]
            for sy in range(samples):
                for sx in range(samples):
                    x, y = (col + (sx + .5) / samples) * 64 / size, (row + (sy + .5) / samples) * 64 / size
                    color = (0, 0, 0, 0)
                    if inside(x, y, 3, 3, 58, 58, 15): color = (21, 61, 67, 255)
                    if any(inside(x, y, 15, top, width, 7, 3.5) for top, width in [(16, 34), (29, 26), (42, 18)]):
                        color = (245, 251, 247, 255)
                    if (x - 46) ** 2 + (y - 46) ** 2 <= 64: color = (227, 185, 96, 255)
                    for i in range(4): total[i] += color[i]
            # PNG stores straight alpha. Avoid dark fringes in transparent pixels.
            alpha = total[3] / samples ** 2
            rgba = [round(total[i] * 255 / total[3]) if total[3] else 0 for i in range(3)] + [round(alpha)]
            scanlines.extend(rgba)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(scanlines), 9)) + chunk(b"IEND", b"")


def generate():
    data = product()
    output = CACHE / "generated"
    constants = {
        "kProductName": data["name"], "kProductNameEn": data["name_en"],
        "kProductId": data["id"], "kProductFolder": data["user_data_folder"],
        "kProductRegistryKey": data["registry_key"], "kProductPipePrefix": data["pipe_prefix"],
        "kTextServiceGuidText": "{" + data["guids"]["text_service"] + "}",
    }
    header = '#pragma once\n#include <windows.h>\nnamespace study {\n'
    for name, value in constants.items():
        header += f"inline constexpr wchar_t {name}[] = L{json.dumps(value, ensure_ascii=False)};\n"
    for name, key in [("kTextServiceGuid", "text_service"), ("kProfileGuid", "language_profile")]:
        header += f"inline constexpr GUID {name} = {guid(data['guids'][key])};\n"
    header += f"inline constexpr LANGID kProductLanguageId = {data['language_id']};\n"
    identity = json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    header += f"inline constexpr char kProductIdentityJson[] = {json.dumps(identity)};\n"
    header += f"inline constexpr char kProductVersion[] = {json.dumps(data['version'])};\n"
    header += '}\n'
    write_changed(output / "ProductIdentity.h", header)
    icon = output / "StudyIME.ico"
    # Artwork changes invalidate cached raster output without running a tool/UI.
    art = (ROOT / "packaging/artwork/StudyIME.svg").read_bytes()
    from tools.packaging.common import sha256
    signature = sha256(art + Path(__file__).read_bytes())
    marker = output / "icon-source.sha256"
    if not icon.exists() or not marker.exists() or marker.read_text() != signature:
        images = [(size, png(size)) for size in [16, 20, 24, 32, 40, 48, 64, 128, 256]]
        content = bytearray(struct.pack("<HHH", 0, 1, len(images)))
        offset = 6 + 16 * len(images)
        for size, raw in images:
            content += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(raw), offset)
            offset += len(raw)
        for _, raw in images: content += raw
        write_changed(icon, bytes(content))
        write_changed(output / "StudyIME.png", images[-1][1])
        write_changed(marker, signature)
    for filename, kind, description in [
        ("StudyIME.TSF.x64.dll", 2, "拾词输入法 TSF"),
        ("StudyIME.Service.exe", 1, "拾词输入法服务"),
        ("StudyIME.Settings.exe", 1, "拾词输入法设置"),
        ("StudyIME.Registrar.exe", 1, "拾词输入法注册工具"),
    ]:
        resource = '#include <winres.h>\nLANGUAGE LANG_CHINESE, SUBLANG_CHINESE_SIMPLIFIED\n'
        for item in [100, 101, 102, 103]:
            resource += f'{item} ICON "{icon.relative_to(ROOT).as_posix()}"\n'
        version = ",".join(map(str, data["file_version"]))
        resource += f'''1 VERSIONINFO
 FILEVERSION {version}
 PRODUCTVERSION {version}
 FILEFLAGSMASK 0x3fL
 FILEFLAGS 0x2L
 FILEOS 0x40004L
 FILETYPE {kind}
 FILESUBTYPE 0
BEGIN
 BLOCK "StringFileInfo"
 BEGIN
  BLOCK "080404b0"
  BEGIN
   VALUE "CompanyName", "StudyIME contributors"
   VALUE "FileDescription", "{description}"
   VALUE "FileVersion", "{data['version']}"
   VALUE "InternalName", "{filename}"
   VALUE "LegalCopyright", "Copyright (C) 2026 StudyIME contributors; includes modified Weasel"
   VALUE "OriginalFilename", "{filename}"
   VALUE "ProductName", "{data['name']} (StudyIME)"
   VALUE "ProductVersion", "{data['version']}"
   VALUE "Comments", "Developer preview; third-party notices and sources accompany the package"
  END
 END
 BLOCK "VarFileInfo"
 BEGIN
  VALUE "Translation", 0x804, 1200
 END
END
'''
        write_changed(output / (filename + ".rc"), resource)
    return output


if __name__ == "__main__":
    print(generate())
