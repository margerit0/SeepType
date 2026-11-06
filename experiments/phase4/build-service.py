"""Build only the new isolated IPC path with the installed VS2019 toolchain."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TSF = "--tsf" in sys.argv
SERVICE_X64 = "--service-x64" in sys.argv
if TSF and SERVICE_X64:
    raise SystemExit("Choose either the TSF DLL or the x64 service build")
BUILD = HERE / ("build/tsf-x64" if TSF else "build/service-x64" if SERVICE_X64 else "build/service")
UPSTREAM = ROOT / ".cache/src/weasel"
OVERLAY = ROOT / ".cache/study-weasel"
BOOST = ROOT / ".cache/src/boost_1_84_0"
BUILD.mkdir(parents=True, exist_ok=True)


def run(args, name):
    print(name, flush=True)
    with (BUILD / f"{name}.log").open("w", encoding="utf-8") as output:
        result = subprocess.run([str(arg) for arg in args], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                env={**os.environ, "VSLANG": "1033"})
    if result.returncode:
        raw = (BUILD / f"{name}.log").read_bytes()
        try:
            detail = raw.decode("utf-8")
        except UnicodeDecodeError:
            detail = raw.decode("gb18030", errors="replace")
        print(detail[-12000:])
        raise SystemExit(result.returncode)


run([sys.executable, HERE / "prepare-weasel.py"], "prepare-weasel")
run([sys.executable, HERE / "prepare-service-deps.py"], "prepare-deps")
common = ["/nologo", "/std:c++17", "/EHsc", "/O2", "/MT", "/utf-8", "/DBOOST_ALL_NO_LIB", "/DBOOST_THREAD_USE_LIB", "/DUNICODE", "/D_UNICODE"]
boostlib = BUILD / "boost_study.lib"
if SERVICE_X64 and (HERE / 'build/tsf-x64/boost_study.lib').exists():
    boostlib = HERE / 'build/tsf-x64/boost_study.lib'
if not boostlib.exists():
    boost_objects = []
    groups = {
        "serialization": sorted((BOOST / "libs/serialization/src").glob("*.cpp")),
        "thread": [BOOST / "libs/thread/src" / name for name in ["win32/thread.cpp", "win32/tss_dll.cpp", "win32/tss_pe.cpp", "win32/thread_primitives.cpp", "future.cpp"]],
        "chrono": [BOOST / "libs/chrono/src" / name for name in ["chrono.cpp", "process_cpu_clocks.cpp", "thread_clock.cpp"]],
    }
    for group, sources in groups.items():
        directory = BUILD / ("boost-" + group)
        directory.mkdir(exist_ok=True)
        flags = ["/DBOOST_THREAD_BUILD_LIB", "/DBOOST_USE_WINDOWS_H", "/DWIN32_LEAN_AND_MEAN"] if group == "thread" else []
        run(["cl", *common, *flags, "/c", "/I", BOOST, *sources, "/Fo" + str(directory) + "\\"], "build-boost-" + group)
        boost_objects.extend(sorted(directory.glob("*.obj")))
    run(["lib", "/nologo", "/OUT:" + str(boostlib), *boost_objects], "link-boost")

includes = [OVERLAY / "include", ROOT / "src", UPSTREAM / "include", BOOST, ROOT / ".cache/rime-1.13.1/dist/include", UPSTREAM / "WeaselServer", OVERLAY / "WeaselUI", UPSTREAM / "WeaselUI", UPSTREAM / "WeaselIPC", UPSTREAM / "WeaselIPCServer", UPSTREAM / "RimeWithWeasel", OVERLAY / "WeaselTSF", UPSTREAM / "WeaselTSF"]
flags = [*common, "/DWEASEL_STUDY_ISOLATED"]
if TSF: flags += ["/DWEASEL_STUDY_TSF"]
for include in includes:
    flags.extend(["/I", str(include)])
headers = list(OVERLAY.rglob("*.h")) + list((ROOT / "src/study").rglob("*.h")) + list((ROOT / "src/study").rglob("*.inc"))
header_time = max(path.stat().st_mtime for path in headers)


def compile_source(source, group):
    source = Path(source)
    directory = BUILD / group
    directory.mkdir(exist_ok=True)
    obj = directory / (source.stem + ".obj")
    dependency_time = max(source.stat().st_mtime, header_time)
    if source.name == "tsf_text_host.cpp":
        dependency_time = max(dependency_time, (HERE / "text_store.h").stat().st_mtime)
    if not obj.exists() or obj.stat().st_mtime < dependency_time:
        run(["cl", *flags, "/c", source, "/Fo" + str(obj)], "compile-" + group + "-" + source.stem)
    return obj


study_objects = [compile_source(path, "study") for path in (ROOT / "src/study").glob("*.cpp")]
ipc_objects = []
for path in UPSTREAM.glob("WeaselIPC/*.cpp"):
    if path.name == "stdafx.cpp": continue
    overlay = OVERLAY / "WeaselIPC" / path.name
    ipc_objects.append(compile_source(overlay if overlay.exists() else path, "ipc"))
if TSF:
    server_objects = []
else:
    dispatch_object = compile_source(ROOT / "src/study/windows/WindowDispatcher.cpp", "study")
    server_objects = [dispatch_object, compile_source(OVERLAY / "WeaselIPCServer/WeaselServerImpl.cpp", "server"), compile_source(UPSTREAM / "WeaselIPCServer/SecurityAttribute.cpp", "server"), compile_source(OVERLAY / "RimeWithWeasel/RimeWithWeasel.cpp", "rime")]
ui_objects = []
for path in UPSTREAM.glob("WeaselUI/*.cpp"):
    if path.name == "stdafx.cpp": continue
    overlay = OVERLAY / "WeaselUI" / path.name
    ui_objects.append(compile_source(overlay if TSF and overlay.exists() else path, "ui"))
libraries = [boostlib, "user32.lib", "gdi32.lib", "comctl32.lib", "ole32.lib", "oleacc.lib", "advapi32.lib", "shell32.lib", "imm32.lib"]


def link(name, sources, objects):
    objects = objects + [compile_source(HERE / path, "test") for path in sources]
    output = HERE / "build" / (name + ".exe")
    if not output.exists() or output.stat().st_mtime < max(path.stat().st_mtime for path in objects + [boostlib, Path(__file__)]):
        run(["link", "/nologo", "/INCREMENTAL:NO", "/SUBSYSTEM:CONSOLE", "/MANIFEST:EMBED", "/MANIFESTUAC:level='asInvoker' uiAccess='false'", "/OUT:" + str(output), *objects, *libraries], "link-" + name)


if TSF:
    tsf_objects = []
    for path in UPSTREAM.glob("WeaselTSF/*.cpp"):
        if path.name == "stdafx.cpp": continue
        overlay = OVERLAY / "WeaselTSF" / path.name
        tsf_objects.append(compile_source(overlay if overlay.exists() else path, "tsf"))
    for name in ["WeaselResponse", "EnglishMenu", "UiPreferences", "StudyMotion", "StudyLayout", "CandidateUi", "CandidateAccessibility"]:
        tsf_objects.append(compile_source(ROOT / "src/study/windows" / (name + ".cpp"), "study"))
    resource = BUILD / "WeaselTSF.res"
    run(["rc", "/nologo", "/c65001", "/d", "WIN64", "/i", UPSTREAM / "include", "/i", UPSTREAM / "WeaselTSF",
         "/fo", resource, OVERLAY / "WeaselTSF/WeaselTSF.rc"], "compile-resource")
    run(["link", "/nologo", "/DLL", "/MACHINE:X64", "/INCREMENTAL:NO", "/MANIFEST:EMBED",
         "/DEF:" + str(UPSTREAM / "WeaselTSF/WeaselTSF.def"),
         "/OUT:" + str(BUILD / "study_weasel_x64.dll"), *tsf_objects, *ipc_objects, *ui_objects,
         *[o for o in study_objects if o.stem == "StudyProtocol"], resource,
         *libraries, "oleaut32.lib", "uuid.lib", "usp10.lib"], "link-tsf")
    if (HERE / "frontend_test.cpp").exists():
        link("frontend_test_x64", ["frontend_test.cpp"], ipc_objects +
             [o for o in study_objects + tsf_objects if o.stem in ["StudyProtocol", "WeaselResponse"]])
    if (HERE / "selection_test.cpp").exists():
        link("selection_test_x64", ["selection_test.cpp"], ipc_objects +
             [o for o in study_objects + tsf_objects if o.stem in ["StudyProtocol", "WeaselResponse"]])
    libraries += ["uuid.lib", "oleaut32.lib"]
    link("tsf_text_host_x64", ["tsf_text_host.cpp"], ipc_objects +
         [o for o in study_objects + tsf_objects if o.stem in ["StudyProtocol", "UiPreferences"]])
    if (HERE / "native_ui_test.cpp").exists():
        link("native_ui_test_x64", ["native_ui_test.cpp"], ui_objects +
             [o for o in tsf_objects if o.stem in ["UiPreferences", "StudyMotion", "StudyLayout", "CandidateUi", "CandidateAccessibility", "EnglishMenu"]])
    if (HERE / "settings_main.cpp").exists():
        link("study_settings_x64", ["settings_main.cpp"], [o for o in tsf_objects if o.stem == "UiPreferences"])
else:
    link("study_service_x64" if SERVICE_X64 else "study_service", ["service_host.cpp", "service_rime.cpp"], server_objects + ipc_objects + ui_objects + study_objects)
    if (HERE / "service_client_test.cpp").exists():
        link("service_client_test_x64" if SERVICE_X64 else "service_client_test", ["service_client_test.cpp"], ipc_objects + [obj for obj in study_objects if obj.stem == "StudyProtocol"])
    link("dispatch_test_x64" if SERVICE_X64 else "dispatch_test", ["dispatch_test.cpp"], [obj for obj in server_objects if obj.stem != "RimeWithWeasel"] + ipc_objects + [obj for obj in study_objects if obj.stem == "StudyProtocol"])
    print("New Weasel IPC build complete; no installer or registered input method was run.")
