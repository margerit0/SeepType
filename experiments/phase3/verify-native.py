"""Check only our isolated native host; no OS input injection or desktop capture."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results"
PREVIEWS = RESULTS / "previews"
PREVIEWS.mkdir(parents=True, exist_ok=True)
executable = HERE / "build/ui_probe.exe"


def run(mode):
    result = subprocess.run(
        [str(executable), str(ROOT), mode], cwd=ROOT, timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError(f"Native {mode} exited {result.returncode}; inspect results/native-ui.json and runtime/ui-error.txt")


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def export_frame(name):
    source = HERE / "runtime/frames"
    dimensions = json.loads((source / (name + ".json")).read_text(encoding="utf-8"))
    width, height = dimensions["width"], dimensions["height"]
    bgra = (source / (name + ".bgra")).read_bytes()
    if len(bgra) != width * height * 4:
        raise RuntimeError("Incomplete native frame: " + name)
    rows = bytearray()
    visible = 0
    colors = set()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            offset = (y * width + x) * 4
            blue, green, red, alpha = bgra[offset:offset + 4]
            if alpha:
                visible += 1
                # Layered windows use premultiplied BGRA; PNG uses straight RGBA.
                red, green, blue = (min(255, (v * 255 + alpha // 2) // alpha) for v in (red, green, blue))
            rows.extend((red, green, blue, alpha))
            colors.add((red, green, blue, alpha))
    if visible < width * height // 2 or len(colors) < 8:
        raise RuntimeError("Native frame is blank or incomplete: " + name)
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(rows)) + png_chunk(b"IEND", b"")
    destination = PREVIEWS / (name + ".png")
    destination.write_bytes(png)
    return {"file": str(destination.relative_to(HERE)), **dimensions,
            "sha256": hashlib.sha256(png).hexdigest()}


run("--smoke")
run("--measure")
run("--self-test")
frames = [export_frame(name) for name in (
    "native-light", "native-page-two", "native-long", "native-closed", "native-dark",
)]
report_path = RESULTS / "native-ui.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
report["executed_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
report["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
report["frames"] = frames
report["limitations"] = [
    "Frames come from Weasel's own paint buffer, not a desktop screenshot",
    "In-process button/key/candidate messages do not replace physical mouse and keyboard testing",
    "No TSF registration, application compatibility, system DPI switching, or installation test",
    "Animations, production settings and the final in-bar English menu are not implemented here",
]
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
for check in report["checks"]:
    print(("PASS " if check["passed"] else "FAIL ") + check["name"])
print(f"Saved {len(frames)} actual native paint-buffer previews")
