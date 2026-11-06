"""Build only the new isolated IPC path with the installed VS2019 toolchain."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TSF = "--tsf" in sys.argv
SERVICE_X64 = "--service-x64" in sys.argv
PRODUCT = "--product" in sys.argv
if PRODUCT and not (TSF or SERVICE_X64):
    raise SystemExit("The StudyIME product currently targets x64 only")
if TSF and SERVICE_X64:
    raise SystemExit("Choose either the TSF DLL or the x64 service build")
BUILD = HERE / ("build/tsf-x64" if TSF else "build/service-x64" if SERVICE_X64 else "build/service")
PRODUCT_ROOT = ROOT / ".cache/packaging"
if PRODUCT:
    BUILD = PRODUCT_ROOT / "build" / ("tsf-x64" if TSF else "service-x64")
OUTPUT = PRODUCT_ROOT / "build/bin" if PRODUCT else HERE / "build"
UPSTREAM = ROOT / ".cache/src/weasel"
OVERLAY = ROOT / ".cache/study-weasel"
if PRODUCT:
    OVERLAY = PRODUCT_ROOT / "weasel"
    UPSTREAM = OVERLAY
BOOST = ROOT / ".cache/src/boost_1_84_0"
BUILD.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)


def run(args, name):
    print(name, flush=True)
    def argument(arg):
        value = str(arg)
        if not PRODUCT:
            return value
        # __FILE__ and COFF member names must not encode the checkout location.
        # Keep output/manifest paths relative as well, while the process cwd is
        # always ROOT. Paths belonging to the installed toolchain stay intact.
        prefix = ""
        for option in ["/MANIFESTINPUT:", "/OUT:", "/DEF:", "/Fo", "/fo"]:
            if value.startswith(option):
                prefix, value = option, value[len(option):]
                break
        root_prefix = str(ROOT) + os.sep
        if value.casefold().startswith(root_prefix.casefold()):
            value = value[len(root_prefix):]
        return prefix + value
    with (BUILD / f"{name}.log").open("w", encoding="utf-8") as output:
        result = subprocess.run([argument(arg) for arg in args], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                env={**os.environ, "VSLANG": "1033"})
    if result.returncode:
        raw = (BUILD / f"{name}.log").read_bytes()
        try:
            detail = raw.decode("utf-8")
        except UnicodeDecodeError:
            detail = raw.decode("gb18030", errors="replace")
        print(detail[-12000:])
        raise SystemExit(result.returncode)


if not PRODUCT:
    run([sys.executable, HERE / "prepare-weasel.py"], "prepare-weasel")
run([sys.executable, HERE / "prepare-service-deps.py"], "prepare-deps")
if PRODUCT:
    run([sys.executable, ROOT / "tools/packaging/prepare_product.py"], "prepare-product")
common = ["/nologo", "/std:c++17", "/EHsc", "/O2", "/MT", "/utf-8", "/DBOOST_ALL_NO_LIB", "/DBOOST_THREAD_USE_LIB", "/DUNICODE", "/D_UNICODE"]
if PRODUCT:
    # VS2019 requires experimental:deterministic for pathmap. Brepro alone
    # leaves absolute assert paths and anonymous-namespace hashes in objects.
    common += ["/Brepro", "/experimental:deterministic", "/pathmap:" + str(ROOT) + "=."]
    sys.path.insert(0, str(ROOT))
    from tools.packaging.native_inputs import snapshot
    native_inputs = snapshot()
    toolchain = {
        "tools": {name: hashlib.sha256(Path(shutil.which(name)).read_bytes()).hexdigest()
                  for name in ["cl", "link", "lib", "rc"]},
        "toolset": os.environ.get("VCToolsVersion"),
        "sdk": os.environ.get("WindowsSDKVersion"),
        "architecture": os.environ.get("VSCMD_ARG_TGT_ARCH"),
    }
    if any(os.environ.get(name) for name in ["CL", "_CL_", "LINK", "_LINK_"]):
        raise SystemExit("Product builds require unset CL/_CL_/LINK/_LINK_ override variables")
    signature_inputs = {
        "build_script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "toolchain": toolchain,
        "common_flags": [arg.replace(str(ROOT), "<project>") for arg in common],
    }
    build_signature = hashlib.sha256(json.dumps({**signature_inputs, "inputs": native_inputs}, sort_keys=True).encode()).hexdigest()
    boost_signature = hashlib.sha256(json.dumps({**signature_inputs, "dependencies": native_inputs["dependencies"]}, sort_keys=True).encode()).hexdigest()
    build_stamp = BUILD / "compile-inputs.sha256"
    force_compile = not build_stamp.exists() or build_stamp.read_text() != build_signature
    boost_stamp = PRODUCT_ROOT / "build/boost-inputs.sha256"
    force_boost = not boost_stamp.exists() or boost_stamp.read_text() != boost_signature
else:
    force_compile = force_boost = False
boostlib = BUILD / "boost_study.lib"
if PRODUCT:
    boostlib = PRODUCT_ROOT / "build/boost_study.lib"
elif SERVICE_X64 and (HERE / 'build/tsf-x64/boost_study.lib').exists():
    boostlib = HERE / 'build/tsf-x64/boost_study.lib'
if not boostlib.exists() or force_boost:
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
    run(["lib", "/nologo", *(["/Brepro"] if PRODUCT else []), "/OUT:" + str(boostlib), *boost_objects], "link-boost")
    if PRODUCT:
        boost_stamp.write_text(boost_signature, encoding="ascii")

includes = [OVERLAY / "include", ROOT / "src", UPSTREAM / "include", BOOST, ROOT / ".cache/rime-1.13.1/dist/include", UPSTREAM / "WeaselServer", OVERLAY / "WeaselUI", UPSTREAM / "WeaselUI", UPSTREAM / "WeaselIPC", UPSTREAM / "WeaselIPCServer", UPSTREAM / "RimeWithWeasel", OVERLAY / "WeaselTSF", UPSTREAM / "WeaselTSF"]
if PRODUCT:
    includes.insert(0, PRODUCT_ROOT / "generated")
flags = [*common, "/DWEASEL_STUDY_ISOLATED"]
if PRODUCT: flags += ["/DWEASEL_STUDY_PRODUCT"]
if TSF: flags += ["/DWEASEL_STUDY_TSF"]
for include in includes:
    flags.extend(["/I", str(include)])
headers = list(OVERLAY.rglob("*.h")) + list((ROOT / "src/study").rglob("*.h")) + list((ROOT / "src/study").rglob("*.inc"))
if PRODUCT:
    headers += list((PRODUCT_ROOT / "generated").glob("*.h"))
header_time = max(path.stat().st_mtime for path in headers)


def compile_source(source, group):
    source = Path(source)
    directory = BUILD / group
    directory.mkdir(exist_ok=True)
    obj = directory / (source.stem + ".obj")
    dependency_time = max(source.stat().st_mtime, header_time)
    if source.name == "tsf_text_host.cpp":
        dependency_time = max(dependency_time, (HERE / "text_store.h").stat().st_mtime)
    if force_compile or not obj.exists() or obj.stat().st_mtime < dependency_time:
        run(["cl", *flags, "/c", source, "/Fo" + str(obj)], "compile-" + group + "-" + source.stem)
    return obj


study_objects = [compile_source(path, "study") for path in sorted((ROOT / "src/study").glob("*.cpp"))]
ipc_objects = []
for path in sorted(UPSTREAM.glob("WeaselIPC/*.cpp")):
    if path.name == "stdafx.cpp": continue
    overlay = OVERLAY / "WeaselIPC" / path.name
    ipc_objects.append(compile_source(overlay if overlay.exists() else path, "ipc"))
if TSF:
    server_objects = []
else:
    dispatch_object = compile_source(ROOT / "src/study/windows/WindowDispatcher.cpp", "study")
    server_objects = [dispatch_object, compile_source(OVERLAY / "WeaselIPCServer/WeaselServerImpl.cpp", "server"), compile_source((OVERLAY if PRODUCT else UPSTREAM) / "WeaselIPCServer/SecurityAttribute.cpp", "server"), compile_source(OVERLAY / "RimeWithWeasel/RimeWithWeasel.cpp", "rime")]
ui_objects = []
for path in sorted(UPSTREAM.glob("WeaselUI/*.cpp")):
    if path.name == "stdafx.cpp": continue
    overlay = OVERLAY / "WeaselUI" / path.name
    ui_objects.append(compile_source(overlay if TSF and overlay.exists() else path, "ui"))
libraries = [boostlib, "user32.lib", "gdi32.lib", "comctl32.lib", "ole32.lib", "oleacc.lib", "advapi32.lib", "shell32.lib", "imm32.lib"]
if PRODUCT:
    libraries += ["uuid.lib", "oleaut32.lib"]
    product_runtime = compile_source(ROOT / "src/study/windows/ProductRuntime.cpp", "study")


def link(name, sources, objects):
    objects = objects + [compile_source(HERE / path, "test") for path in sources]
    output = OUTPUT / (name + ".exe")
    # Declare awareness before Windows/COM can create any windows. A TSF DLL
    # must never change the DPI awareness of the application loading it.
    manifest = HERE / "native-host.manifest" if PRODUCT or name in {
        "tsf_text_host_x64", "native_ui_test_x64", "study_settings_x64"} else None
    dependencies = objects + [boostlib, Path(__file__)] + ([manifest] if manifest else [])
    if PRODUCT and (PRODUCT_ROOT / "generated" / (name + ".exe.rc")).exists():
        resource = BUILD / (name + ".res")
        resource_source = PRODUCT_ROOT / "generated" / (name + ".exe.rc")
        run(["rc", "/nologo", "/c65001", "/fo", resource, resource_source], "resource-" + name)
        objects += [resource]
        dependencies += [resource_source, resource]
    manifest_flags = ["/MANIFESTINPUT:" + str(manifest)] if manifest else []
    if not output.exists() or output.stat().st_mtime < max(path.stat().st_mtime for path in dependencies):
        subsystem = ["/SUBSYSTEM:WINDOWS", "/ENTRY:wmainCRTStartup", "/Brepro"] if PRODUCT else ["/SUBSYSTEM:CONSOLE"]
        run(["link", "/nologo", "/INCREMENTAL:NO", *subsystem, "/MANIFEST:EMBED", "/MANIFESTUAC:level='asInvoker' uiAccess='false'", *manifest_flags, "/OUT:" + str(output), *objects, *libraries], "link-" + name)


if TSF:
    tsf_objects = []
    for path in sorted(UPSTREAM.glob("WeaselTSF/*.cpp")):
        if path.name == "stdafx.cpp": continue
        if PRODUCT and path.name == "Register.cpp": continue
        overlay = OVERLAY / "WeaselTSF" / path.name
        tsf_objects.append(compile_source(overlay if overlay.exists() else path, "tsf"))
    for name in ["WeaselResponse", "EnglishMenu", "UiPreferences", "StudyMotion", "StudyLayout", "CandidateUi", "CandidateAccessibility"]:
        tsf_objects.append(compile_source(ROOT / "src/study/windows" / (name + ".cpp"), "study"))
    if PRODUCT:
        tsf_objects += [product_runtime, compile_source(ROOT / "src/study/windows/ProductRegistration.cpp", "study")]
    resource = BUILD / "WeaselTSF.res"
    run(["rc", "/nologo", "/c65001", "/d", "WIN64", "/i", UPSTREAM / "include", "/i", UPSTREAM / "WeaselTSF",
         "/fo", resource, (PRODUCT_ROOT / "generated/StudyIME.TSF.x64.dll.rc") if PRODUCT else (OVERLAY / "WeaselTSF/WeaselTSF.rc")], "compile-resource")
    run(["link", "/nologo", "/DLL", "/MACHINE:X64", "/INCREMENTAL:NO", "/MANIFEST:EMBED",
         *(["/Brepro"] if PRODUCT else []),
         "/DEF:" + str((ROOT / "packaging/StudyIME.def") if PRODUCT else (UPSTREAM / "WeaselTSF/WeaselTSF.def")),
         "/OUT:" + str((OUTPUT / "StudyIME.TSF.x64.dll") if PRODUCT else (BUILD / "study_weasel_x64.dll")), *tsf_objects, *ipc_objects, *ui_objects,
         *[o for o in study_objects if o.stem == "StudyProtocol"], resource,
         *libraries, "oleaut32.lib", "uuid.lib", "usp10.lib"], "link-tsf")
    if PRODUCT:
        link("StudyIME.Settings", [ROOT / "src/study/windows/ProductSettingsMain.cpp"], [product_runtime] + [o for o in tsf_objects if o.stem == "UiPreferences"])
        link("StudyIME.Registrar", [ROOT / "src/study/windows/ProductRegistrarMain.cpp"], [product_runtime])
        probe = ROOT / "tools/packaging/runtime_probe.cpp"
        if probe.exists():
            link("StudyIME.PackageProbe", [probe], [product_runtime] + ipc_objects + [o for o in study_objects + tsf_objects if o.stem in ["StudyProtocol", "WeaselResponse"]])
    if not PRODUCT and (HERE / "frontend_test.cpp").exists():
        link("frontend_test_x64", ["frontend_test.cpp"], ipc_objects +
             [o for o in study_objects + tsf_objects if o.stem in ["StudyProtocol", "WeaselResponse"]])
    if not PRODUCT and (HERE / "selection_test.cpp").exists():
        link("selection_test_x64", ["selection_test.cpp"], ipc_objects +
             [o for o in study_objects + tsf_objects if o.stem in ["StudyProtocol", "WeaselResponse"]])
    libraries += ["uuid.lib", "oleaut32.lib"]
    if not PRODUCT:
        link("tsf_text_host_x64", ["tsf_text_host.cpp"], ipc_objects +
             [o for o in study_objects + tsf_objects if o.stem in ["StudyProtocol", "UiPreferences"]])
    if not PRODUCT and (HERE / "native_ui_test.cpp").exists():
        link("native_ui_test_x64", ["native_ui_test.cpp"], ui_objects +
             [o for o in tsf_objects if o.stem in ["UiPreferences", "StudyMotion", "StudyLayout", "CandidateUi", "CandidateAccessibility", "EnglishMenu"]])
    if not PRODUCT and (HERE / "settings_main.cpp").exists():
        link("study_settings_x64", ["settings_main.cpp"], [o for o in tsf_objects if o.stem == "UiPreferences"])
else:
    if PRODUCT:
        link("StudyIME.Service", [ROOT / "src/study/windows/ProductServiceMain.cpp", ROOT / "src/study/windows/ProductRime.cpp"], [product_runtime] + server_objects + ipc_objects + ui_objects + study_objects)
    else:
        link("study_service_x64" if SERVICE_X64 else "study_service", ["service_host.cpp", "service_rime.cpp"], server_objects + ipc_objects + ui_objects + study_objects)
    if not PRODUCT and (HERE / "service_client_test.cpp").exists():
        link("service_client_test_x64" if SERVICE_X64 else "service_client_test", ["service_client_test.cpp"], ipc_objects + [obj for obj in study_objects if obj.stem == "StudyProtocol"])
    if not PRODUCT:
        link("dispatch_test_x64" if SERVICE_X64 else "dispatch_test", ["dispatch_test.cpp"], [obj for obj in server_objects if obj.stem != "RimeWithWeasel"] + ipc_objects + [obj for obj in study_objects if obj.stem == "StudyProtocol"])
    print("New Weasel IPC build complete; no installer or registered input method was run.")

if PRODUCT:
    build_stamp.write_text(build_signature, encoding="ascii")
    (BUILD / "native-inputs.json").write_text(json.dumps({"inputs": native_inputs, "toolchain": toolchain}, sort_keys=True), encoding="utf-8")
