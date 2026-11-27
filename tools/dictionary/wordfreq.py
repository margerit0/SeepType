"""Read fixed wordfreq cBpack data using only the Python standard library."""
from decimal import Decimal, localcontext
import gzip
import json
import tarfile

from tools.packaging.common import ROOT, file_hash, sha256


def unpack_cbpack(raw):
    # cBpack uses only MessagePack arrays, maps, strings and unsigned integers.
    # This is an independent format reader, not a copy of the msgpack library.
    position = 0

    def take(size):
        nonlocal position
        if size < 0 or position + size > len(raw): raise ValueError("Truncated cBpack")
        value = raw[position:position + size]
        position += size
        return value

    def length(tag, small, fixed, codes):
        if small <= tag <= fixed: return tag - small
        return int.from_bytes(take(codes[tag]), "big")

    def read(depth=0):
        if depth > 5: raise ValueError("Unexpected cBpack nesting")
        tag = take(1)[0]
        if tag < 0x80: return tag
        if 0xa0 <= tag <= 0xbf or tag in [0xd9, 0xda, 0xdb]:
            return take(length(tag, 0xa0, 0xbf, {0xd9: 1, 0xda: 2, 0xdb: 4})).decode("utf-8")
        if 0x90 <= tag <= 0x9f or tag in [0xdc, 0xdd]:
            size = length(tag, 0x90, 0x9f, {0xdc: 2, 0xdd: 4})
            if size > 1000000: raise ValueError("Unexpected cBpack array size")
            return [read(depth + 1) for _ in range(size)]
        if 0x80 <= tag <= 0x8f or tag in [0xde, 0xdf]:
            size = length(tag, 0x80, 0x8f, {0xde: 2, 0xdf: 4})
            if size > 16: raise ValueError("Unexpected cBpack metadata")
            result = {}
            for _ in range(size):
                key = read(depth + 1)
                result[key] = read(depth + 1)
            return result
        if tag in [0xcc, 0xcd, 0xce, 0xcf]:
            return int.from_bytes(take({0xcc: 1, 0xcd: 2, 0xce: 4, 0xcf: 8}[tag]), "big")
        raise ValueError("Unexpected MessagePack tag in fixed cBpack data: " + hex(tag))

    value = read()
    if position != len(raw) or not isinstance(value, list) or value[0] != {"format": "cB", "version": 1}:
        raise ValueError("Unexpected cBpack header or trailing data")
    return value[1:]


def frequency_groups(source):
    archive = ROOT / source["archive"]
    for path, expected in [(archive, source["archive_sha256"]), (ROOT / source["license_file"], source["license_sha256"]),
                           (ROOT / source["data_license_statement"], source["data_license_statement_sha256"])]:
        if file_hash(path) != expected: raise ValueError("Fixed wordfreq source or notice changed")
    with tarfile.open(archive) as bundle:
        compressed = bundle.extractfile(source["source_file"]).read()
    if sha256(compressed) != source["source_sha256"]: raise ValueError("wordfreq file changed")
    raw = gzip.decompress(compressed)
    if len(raw) > 40 * 1024 * 1024: raise ValueError("Unexpected wordfreq data size")
    groups = unpack_cbpack(raw)
    if not all(isinstance(words, list) and all(isinstance(word, str) for word in words) for words in groups):
        raise ValueError("Invalid wordfreq frequency group")
    return groups


def frequencies():
    source = json.loads((ROOT / "data/chinese/sources.lock.json").read_bytes())["wordfreq"]
    groups = frequency_groups(source)
    values = {}
    with localcontext() as context:
        context.prec = 40
        for index, words in enumerate(groups):
            weight = max(1, int(Decimal(10) ** (Decimal(900 - index) / 100)))
            for word in words:
                if word in values: raise ValueError("Duplicate wordfreq word")
                values[word] = weight
    return values, {**source, "frequency_groups": len(groups), "words": len(values)}
