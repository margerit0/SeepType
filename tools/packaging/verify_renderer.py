"""Compare the WTL-free product renderer with the approved v0.5 PNG pixels."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, write_changed
from tools.packaging.package import native_build


def verify():
    native = native_build()
    work = CACHE / "verification" / ("renderer-" + uuid.uuid4().hex)
    work.mkdir(parents=True)
    frames = work / "frames"
    check_file = work / "checks.json"
    executable = CACHE / "build/bin/StudyIME.RenderProbe.exe"
    env = {**os.environ, "STUDYIME_DEV_SESSION": uuid.uuid4().hex,
           "STUDYIME_DEV_DATA_ROOT": str(work / "user")}
    result = subprocess.run([str(executable), str(check_file), str(frames)], cwd=work,
                            env=env, capture_output=True, timeout=45,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    (work / "probe.log").write_bytes(result.stdout + result.stderr)
    checks = json.loads(check_file.read_bytes())["checks"] if check_file.exists() else []
    print((result.stdout + result.stderr).decode("utf-8", errors="replace"), end="")
    comparisons = []
    names = ["light", "dpi-96", "dpi-120", "dpi-144", "dpi-192", "closed", "narrow", "dark", "large"]
    for name in names:
        metadata = frames / (name + ".json")
        if not metadata.exists():
            comparisons.append({"name": name, "identical_pixels": False, "error": "missing frame"})
            continue
        size = json.loads(metadata.read_bytes())
        pixels = (frames / (name + ".bgra")).read_bytes()
        rgba = bytearray(Image.frombytes("RGBA", (size["width"], size["height"]), pixels, "raw", "BGRA").tobytes())
        # Match the original golden exporter: Direct2D uses premultiplied alpha.
        for i in range(0, len(rgba), 4):
            alpha = rgba[i + 3]
            if alpha:
                for c in range(3):
                    rgba[i + c] = min(255, round(rgba[i + c] * 255 / alpha))
        actual = Image.frombytes("RGBA", (size["width"], size["height"]), bytes(rgba))
        actual.save(work / (name + ".png"))
        golden_path = ROOT / "experiments/phase4/results/previews-v05" / (name + ".png")
        with Image.open(golden_path) as golden:
            same_size = actual.size == golden.size
            expected = golden.convert("RGBA").tobytes()
            different = sum(a != b for a, b in zip(rgba, expected)) if same_size else None
        comparisons.append({"name": name, **size, "identical_pixels": same_size and different == 0,
                            "different_channels": different, "golden_sha256": file_hash(golden_path)})
        print(("PASS " if comparisons[-1]["identical_pixels"] else "FAIL ") + name + " pixels")
    passed = result.returncode == 0 and bool(checks) and all(item["passed"] for item in checks) and all(item["identical_pixels"] for item in comparisons)
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "passed": passed,
              "scope": "Product objects, offscreen rendering and callback dispatch; no desktop UI or installation",
              "native_build_sha256": file_hash(CACHE / "build/native-build.json"),
              "include_trace_sha256": native["include_trace_sha256"], "wtl_compiled": native["wtl_compiled"],
              "probe_sha256": file_hash(executable), "checks": checks, "comparisons": comparisons,
              "exit_code": result.returncode, "work_directory": work.relative_to(ROOT).as_posix()}
    write_changed(ROOT / "experiments/phase6/results/product-renderer.json", json_bytes(report))
    if not passed: raise SystemExit("Product renderer regression")


if __name__ == "__main__":
    verify()
