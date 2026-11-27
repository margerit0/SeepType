"""Generate all native identities and original icon resources from product.json."""
from pathlib import Path
import json
import math
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
    # Match the rounded artwork in packaging/artwork/StudyIME.svg.
    corner_radius = 21.6
    arc_radius = 14
    half_stroke = 5.5
    inner_radius_sq = (arc_radius - half_stroke) ** 2
    outer_radius_sq = (arc_radius + half_stroke) ** 2
    cap_radius_sq = half_stroke ** 2
    join = (48, 49)
    green_tip = (59.5, 27)
    purple_tip = (36.5, 71)
    green_end = math.atan2(-8, 11.5)
    purple_end = math.atan2(8, -11.5)

    def on_arc(x, y, center_y, start_angle, end_angle, tip):
        dx, dy = x - 48, y - center_y
        if inner_radius_sq <= dx * dx + dy * dy <= outer_radius_sq:
            angle = (math.atan2(dy, dx) - start_angle) % math.tau
            if angle <= (end_angle - start_angle) % math.tau:
                return True
        return any((x - cap_x) ** 2 + (y - cap_y) ** 2 <= cap_radius_sq
                   for cap_x, cap_y in (join, tip))

    scanlines = bytearray()
    samples = 4
    scale = 96 / size
    for row in range(size):
        scanlines.append(0)
        for col in range(size):
            red = green = blue = covered = 0
            for sy in range(samples):
                y = (row + (sy + .5) / samples) * scale
                corner_y = max(abs(y - 48) - (48 - corner_radius), 0)
                for sx in range(samples):
                    x = (col + (sx + .5) / samples) * scale
                    corner_x = max(abs(x - 48) - (48 - corner_radius), 0)
                    if corner_x ** 2 + corner_y ** 2 > corner_radius ** 2:
                        continue
                    # Test topmost artwork first: dot, purple arc, green arc, background.
                    if (x - 66) ** 2 + (y - 42) ** 2 <= 6 ** 2:
                        color = (255, 208, 79)
                    elif on_arc(x, y, 63, -math.pi / 2, purple_end, purple_tip):
                        color = (108, 99, 224)
                    elif on_arc(x, y, 35, math.pi / 2, green_end, green_tip):
                        color = (31, 200, 160)
                    else:
                        color = (247, 248, 251)
                    red += color[0]
                    green += color[1]
                    blue += color[2]
                    covered += 1
            # PNG stores straight alpha. Avoid dark fringes in transparent pixels.
            if covered:
                scanlines.extend((round(red / covered), round(green / covered), round(blue / covered),
                                  round(255 * covered / samples ** 2)))
            else:
                scanlines.extend((0, 0, 0, 0))
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
