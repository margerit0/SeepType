"""Read PE architecture and import names without loading or executing a binary."""
from pathlib import Path
import struct


def inspect_pe(path: Path):
    raw = path.read_bytes()
    pe = struct.unpack_from("<I", raw, 0x3c)[0]
    if raw[:2] != b"MZ" or raw[pe:pe+4] != b"PE\0\0":
        raise ValueError(f"Not a PE image: {path}")
    machine, count = struct.unpack_from("<HH", raw, pe + 4)
    optional_size = struct.unpack_from("<H", raw, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", raw, optional)[0]
    directory = optional + (112 if magic == 0x20b else 96)
    sections = []
    for index in range(count):
        entry = optional + optional_size + index * 40
        virtual_size, address, size, offset = struct.unpack_from("<IIII", raw, entry + 8)
        sections.append((address, max(virtual_size, size), offset))

    def file_offset(rva):
        for address, size, offset in sections:
            if address <= rva < address + size:
                return offset + rva - address
        raise ValueError(f"Unmapped PE RVA {rva:x}")

    imports = []
    import_rva = struct.unpack_from("<I", raw, directory + 8)[0]
    if import_rva:
        position = file_offset(import_rva)
        while any(raw[position:position+20]):
            name_rva = struct.unpack_from("<I", raw, position + 12)[0]
            start = file_offset(name_rva)
            end = raw.index(b"\0", start)
            imports.append(raw[start:end].decode("ascii"))
            position += 20
    delay = []
    delay_rva = struct.unpack_from("<I", raw, directory + 13 * 8)[0]
    if delay_rva:
        position = file_offset(delay_rva)
        while any(raw[position:position+32]):
            attributes, name_rva = struct.unpack_from("<II", raw, position)
            if not attributes & 1:
                raise ValueError("VA-based delayed imports need an explicit audit")
            start = file_offset(name_rva)
            delay.append(raw[start:raw.index(b"\0", start)].decode("ascii"))
            position += 32
    return {"architecture": {0x8664: "x64", 0x14c: "x86", 0xaa64: "arm64"}.get(machine, hex(machine)),
            "imports": sorted(set(imports), key=str.casefold), "delay_imports": sorted(set(delay), key=str.casefold)}
