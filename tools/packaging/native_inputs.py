"""Hash the actual project, generated headers and dependency trees used by MSVC."""
from pathlib import Path

from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, sha256


def file_tree(directory):
    return {path.relative_to(ROOT).as_posix(): file_hash(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def snapshot():
    project = {}
    for folder in ["src/study", "packaging/artwork"]:
        project.update(file_tree(ROOT / folder))
    for relative in [
        "packaging/product.json", "packaging/StudyIME.def", "tools/packaging/build.cmd",
        "tools/packaging/identity.py", "tools/packaging/prepare_product.py",
        "tools/packaging/native_inputs.py", "tools/packaging/record_build.py",
        "tools/packaging/runtime_probe.cpp", "tools/packaging/render_probe.cpp",
        "tools/packaging/frequency_probe.cpp",
        "experiments/phase4/build-service.py", "experiments/phase4/prepare-weasel.py",
        "experiments/phase4/prepare-tsf.py", "experiments/phase4/prepare-service-deps.py",
        "experiments/phase4/native-host.manifest", "experiments/phase3/vs-env.cmd",
        "experiments/phase3/dependencies.lock.json",
        "experiments/phase3/engine_probe.cpp",
    ]:
        project[relative] = file_hash(ROOT / relative)
    generated = file_tree(CACHE / "weasel")
    for name in ["ProductIdentity.h", "StudyIME.ico", "StudyIME.TSF.x64.dll.rc",
                 "StudyIME.Service.exe.rc", "StudyIME.Settings.exe.rc", "StudyIME.Registrar.exe.rc"]:
        path = CACHE / "generated" / name
        generated[path.relative_to(ROOT).as_posix()] = file_hash(path)
    dependencies = {}
    for relative in [
        ".cache/src/boost_1_84_0/boost", ".cache/src/boost_1_84_0/libs/serialization/src",
        ".cache/src/boost_1_84_0/libs/thread/src", ".cache/src/boost_1_84_0/libs/chrono/src",
        ".cache/rime-build/dist/include",
    ]:
        files = file_tree(ROOT / relative)
        if not files:
            raise ValueError("Missing native input tree: " + relative)
        dependencies[relative] = {"files": len(files), "sha256": sha256(json_bytes(files))}
    return {"project": project, "generated": generated, "dependencies": dependencies}
