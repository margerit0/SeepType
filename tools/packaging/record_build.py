"""Record actual compiler inputs and native artifact hashes after a product build."""
from pathlib import Path
import json
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, write_changed, product, sha256
from tools.packaging.pe import inspect_pe
from tools.packaging.native_inputs import snapshot


def record():
    actual = snapshot()
    tsf = json.loads((CACHE / "build/tsf-x64/native-inputs.json").read_text(encoding="utf-8"))
    service = json.loads((CACHE / "build/service-x64/native-inputs.json").read_text(encoding="utf-8"))
    if tsf["inputs"] != service["inputs"] or tsf["toolchain"] != service["toolchain"] or tsf["inputs"] != actual:
        raise ValueError("Native source/dependency/toolchain inputs changed during the product build")
    headers = sorted(set(tsf["included_headers"]) | set(service["included_headers"]))
    if not headers or any("/wtl/" in path.casefold() for path in headers):
        raise ValueError("Missing or unexpected WTL native header trace")
    trace = json_bytes({name: file_hash(ROOT / name) for name in headers})
    write_changed(CACHE / "build/include-trace.json", trace)
    binaries = {}
    for name in ["StudyIME.TSF.x64.dll", "StudyIME.Service.exe", "StudyIME.Settings.exe", "StudyIME.Registrar.exe"]:
        file = CACHE / "build/bin" / name
        image = inspect_pe(file)
        if image["architecture"] != "x64": raise ValueError(f"Unexpected product architecture: {name}")
        binaries[name] = {"sha256": file_hash(file), "bytes": file.stat().st_size, **image}
    compiler = subprocess.run(["cl"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
    version = re.search(rb'\b(19\.\d+\.\d+(?:\.\d+)?)\b', compiler)
    if not version: raise ValueError("Cannot record the actual MSVC compiler version")
    compiler_version = "MSVC " + version[1].decode("ascii") + " (x64)"
    result = {"schema_version": 1, "product_version": product()["version"], "compiler": compiler_version,
              "runtime": "/MT", "reproducible_flags": ["cl /Brepro /experimental:deterministic /pathmap:<project>=.", "link /Brepro", "lib /Brepro"],
              "relative_project_paths": True,
              "cache_fingerprint": (CACHE / "build/tsf-x64/compile-inputs.sha256").read_text(encoding="ascii"),
              "inputs": actual["project"], "generated_inputs": actual["generated"],
              "dependency_inputs": actual["dependencies"], "toolchain": tsf["toolchain"], "binaries": binaries,
              "include_trace_sha256": sha256(trace), "included_header_count": len(headers), "wtl_compiled": False,
              "boost_library_sha256": file_hash(CACHE / "build/boost_study.lib")}
    write_changed(CACHE / "build/native-build.json", json_bytes(result))
    print("Recorded native build inputs and x64 binary hashes.")


if __name__ == "__main__": record()
