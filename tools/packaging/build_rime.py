"""Build the product's Rime/Lua engine from fixed local source archives.

All source preparation, CMake install prefixes and output stay in .cache.
The original official Rime DLL is neither an input nor a build dependency.
"""
from pathlib import Path
import argparse
import ctypes
import difflib
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.build_tools import cmake
from tools.packaging.collect_licenses import source_files
from tools.packaging.common import ROOT, file_hash, json_bytes, package_path, sha256, write_changed
from tools.packaging.pe import inspect_pe
from tools.packaging.product_sources import locked_sources

WORK = ROOT / ".cache/rime-build"
COMPONENTS = ["librime", "librime-lua", "lua-thirdparty", "glog", "leveldb", "marisa-trie", "opencc", "yaml-cpp"]


def command_arguments(command):
    count = ctypes.c_int()
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer: raise OSError("Cannot parse the compiler command")
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        kernel = ctypes.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))


def normalized(value):
    value = str(value)
    if value.startswith(("-DCMAKE_C_FLAGS=", "-DCMAKE_CXX_FLAGS=")):
        key, flags = value.split("=", 1)
        # Spaces in a relocated checkout require different command quoting,
        # while the actual compiler arguments remain equivalent.
        return key + "=" + subprocess.list2cmdline([normalized(arg) for arg in command_arguments("cl " + flags)[1:]])
    return value.replace(str(ROOT), "<project>").replace(ROOT.as_posix(), "<project>")


def relative(path):
    # Input hashing needs a canonical spelling, not thousands of filesystem
    # handle lookups. Workspace safety is checked at each mutation boundary.
    path = Path(os.path.abspath(path))
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def prepare_sources():
    lock = locked_sources()
    inputs, originals, files = {}, {}, {}
    for component in COMPONENTS:
        item = next(item for item in lock["sources"] if item["id"] == component)
        archive = ROOT / item["archive"]
        if file_hash(archive) != item["archive_sha256"]:
            raise ValueError("Rime source archive changed: " + component)
        inputs[component] = {key: item[key] for key in ["commit", "archive", "archive_sha256", "url",
            "materials_kind", "upstream_archive_sha256", "selection"] if key in item}
        destination = {"librime-lua": "librime/plugins/lua", "lua-thirdparty": "librime/plugins/lua/thirdparty"}.get(component, component)
        for name, data in source_files(archive):
            package_path(name)
            # Only the fixed Lua 5.4 source is needed by the Lua plugin.
            if component == "lua-thirdparty" and not name.startswith("lua5.4/"):
                continue
            files[destination + "/" + name] = data

    def replace(name, before, after):
        raw = files[name]
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if text.count(before) != 1:
            raise ValueError("Rime source overlay context changed: " + name)
        originals.setdefault(name, text)
        files[name] = text.replace(before, after).encode("utf-8")

    replace("librime/CMakeLists.txt", '  set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /Zi")\n',
            '  # StudyIME: reproducible release build without a PDB.\n')
    replace("librime/CMakeLists.txt", '${CMAKE_SHARED_LINKER_FLAGS_RELEASE} /DEBUG /OPT:REF /OPT:ICF',
            '${CMAKE_SHARED_LINKER_FLAGS_RELEASE} /OPT:REF /OPT:ICF')
    replace("librime/CMakeLists.txt", '  add_subdirectory(tools)\n',
            '  # StudyIME uses the C API; standalone tools and their historical preset data are omitted.\n')
    # Keep Rime's scoring, dictionary storage and deletion behavior. This
    # session property only pauses new learning; existing entries still rank.
    # Checking at the native commit hook covers keys, clicks and segmented input.
    replace("librime/src/rime/gear/memory.cc",
            'void Memory::OnCommit(Context* ctx) {\n',
            'void Memory::OnCommit(Context* ctx) {\n'
            '  // StudyIME: do not learn new words while the user pauses learning.\n'
            '  if (ctx->get_property("study_user_learning") == "0")\n'
            '    return;\n')
    rc = files["librime/cmake/AddRCInfo.cmake"].decode("utf-8").replace("\r\n", "\n")
    replace("librime/cmake/AddRCInfo.cmake", rc[:rc.index('set(original_filename')],
            '# StudyIME: sources come from the fixed archive, never a parent Git checkout.\nset(build_release ON)\n')
    # The same upstream adaptation is used in librime's own Windows build.bat.
    replace("opencc/CMakeLists.txt", '  find_library(LIBMARISA NAMES marisa)',
            '  find_package(marisa CONFIG REQUIRED)\n  set(LIBMARISA marisa)')
    # The product passes absolute paths to its packaged conversion config.
    # Never compile a fallback path into the developer's private build cache.
    replace("opencc/CMakeLists.txt", '  -DPKGDATADIR="${DIR_SHARE_OPENCC}"\n', '')
    replace("opencc/CMakeLists.txt", '  -DLOCALEDIR="${DIR_SHARE_LOCALE}"', '  -DLOCALEDIR="locale"')
    # Only the OpenCC library is a product dependency. Its standalone converter
    # uses narrow argv paths and is not needed for our directly sourced Chinese
    # dictionary; do not build its CLI programs or their compiled data files.
    replace("opencc/CMakeLists.txt", 'add_subdirectory(data)\n', '# StudyIME: no standalone conversion data.\n')
    replace("opencc/src/CMakeLists.txt", 'add_subdirectory(tools)\n', '# StudyIME: library and headers only.\n')
    replace("glog/src/config.h.cmake.in", '#cmakedefine TEST_SRC_DIR ${TEST_SRC_DIR}',
            '#define TEST_SRC_DIR "." /* StudyIME: tests are disabled; no checkout path in generated headers. */')
    patches = []
    for name, original in sorted(originals.items()):
        patches.extend(difflib.unified_diff(original.splitlines(True), files[name].decode("utf-8").splitlines(True),
                                          fromfile="a/" + name, tofile="b/" + name))
    write_changed(ROOT / "packaging/patches/rime-source-build.patch", "".join(patches))
    destination = WORK / "src"
    if WORK.is_symlink() or WORK.is_junction() or destination.is_symlink() or destination.is_junction():
        raise ValueError("Reparse point in Rime source workspace")
    for path in destination.rglob("*"):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Unsafe generated Rime source path")
        if path.is_file() and path.relative_to(destination).as_posix() not in files:
            path.unlink()
    for name, data in sorted(files.items()):
        write_changed(destination / name, data)
    return inputs, {relative(destination / name): sha256(data) for name, data in sorted(files.items())}


def build():
    if os.environ.get("VSCMD_ARG_TGT_ARCH") != "x64":
        raise ValueError("Run build-rime.cmd with the VS2019 x64 toolchain")
    if any(os.environ.get(name) for name in ["CL", "_CL_", "LINK", "_LINK_"]):
        raise ValueError("Rime source builds require unset compiler/linker override variables")
    sources, source_tree = prepare_sources()
    cmake_exe = cmake()
    vsroot = Path(os.environ["VSINSTALLDIR"])
    ninja = vsroot / "Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe"
    if not ninja.is_file(): raise ValueError("The existing VS Ninja tool is missing")
    tools = {name: Path(shutil.which(name)) for name in ["cl", "link", "lib", "rc"]}
    tools.update({"cmake": cmake_exe, "ninja": ninja})
    toolchain = {"tools": {name: file_hash(path) for name, path in tools.items()},
                 "toolset": os.environ["VCToolsVersion"], "sdk": os.environ["WindowsSDKVersion"],
                 "architecture": "x64"}
    project = {name: file_hash(ROOT / name) for name in [
        "tools/packaging/build_rime.py", "tools/packaging/build-rime.cmd", "tools/packaging/build_tools.py",
        "tools/packaging/rime-project.cmake",
        "tools/packaging/collect_licenses.py", "tools/packaging/product_sources.py", "licensing/product-sources.lock.json",
        "licensing/build-tools.lock.json", "packaging/patches/rime-source-build.patch"]}
    boost = ROOT / ".cache/src/boost_1_84_0"
    boost_headers = {relative(path): file_hash(path) for path in sorted((boost / "boost").rglob("*")) if path.is_file()}
    if not boost_headers: raise ValueError("Missing fixed Boost headers")
    logs = WORK / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    commands = []
    env = {**os.environ, "RIME_PLUGINS": "lua", "VSLANG": "1033"}
    # Do not let an unrelated CMake package registry or optional dependency enter.
    for name in ["CMAKE_PREFIX_PATH", "CMAKE_TOOLCHAIN_FILE", "CMAKE_PROJECT_TOP_LEVEL_INCLUDES"]:
        env.pop(name, None)

    def run(command, name, cwd=ROOT, record=True):
        print(name, flush=True)
        if record:
            commands.append({"cwd": normalized(cwd), "argv": [normalized(arg) for arg in command]})
        with (logs / (name + ".log")).open("wb") as output:
            result = subprocess.run([str(arg) for arg in command], cwd=cwd, env=env,
                                    stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            detail = (logs / (name + ".log")).read_bytes().decode("utf-8", errors="replace")
            print(detail[-10000:])
            raise SystemExit(result.returncode)

    # CMake 3.x can decode UTF-8 Chinese /showIncludes as the active ACP.
    # Discover the compiler's actual UTF-8 prefix and override that detection.
    prefix_source = logs / "include-prefix.cpp"
    write_changed(prefix_source, '#include <stddef.h>\n')
    probe = subprocess.run([str(tools["cl"]), "/nologo", "/c", "/utf-8", "/showIncludes",
                            str(prefix_source), "/Fo" + str(logs / "include-prefix.obj")],
                           cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    write_changed(logs / "include-prefix.log", probe.stdout)
    match = re.search(r"^(.+?:[ \t]+)([A-Za-z]:[\\/].+)$", probe.stdout.decode("utf-8"), re.M)
    if probe.returncode or not match:
        raise ValueError("Cannot determine the actual MSVC include prefix")
    include_prefix = match[1].rstrip() + " "
    flags = subprocess.list2cmdline(["/nologo", "/utf-8", "/Brepro", "/experimental:deterministic", "/pathmap:" + str(ROOT) + "=."])
    prefix = WORK / "deps"
    common = ["-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + str(ninja), "-DCMAKE_BUILD_TYPE=Release",
              "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded",
              "-DCMAKE_C_FLAGS=" + flags, "-DCMAKE_CXX_FLAGS=" + flags + " /EHsc",
              "-DCMAKE_C_FLAGS_RELEASE=/O2 /Ob2 /DNDEBUG", "-DCMAKE_CXX_FLAGS_RELEASE=/O2 /Ob2 /DNDEBUG",
              "-DCMAKE_EXE_LINKER_FLAGS=/Brepro /INCREMENTAL:NO", "-DCMAKE_SHARED_LINKER_FLAGS=/Brepro /INCREMENTAL:NO",
              "-DCMAKE_STATIC_LINKER_FLAGS=/Brepro", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
              "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
              "-DCMAKE_PROJECT_INCLUDE=" + str(ROOT / "tools/packaging/rime-project.cmake"),
              "-DSTUDY_MSVC_INCLUDE_PREFIX=" + include_prefix,
              "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DCMAKE_INSTALL_LIBDIR=lib"]
    options = {
        "glog": ["-DBUILD_TESTING=OFF", "-DWITH_GFLAGS=OFF", "-DWITH_GTEST=OFF", "-DWITH_UNWIND=none"],
        "leveldb": ["-DLEVELDB_BUILD_TESTS=OFF", "-DLEVELDB_BUILD_BENCHMARKS=OFF", "-DHAVE_SNAPPY=OFF", "-DHAVE_CRC32C=OFF", "-DHAVE_TCMALLOC=OFF"],
        "yaml-cpp": ["-DYAML_MSVC_SHARED_RT=OFF", "-DYAML_CPP_BUILD_CONTRIB=OFF", "-DYAML_CPP_BUILD_TESTS=OFF", "-DYAML_CPP_BUILD_TOOLS=OFF", "-DYAML_CPP_FORMAT_SOURCE=OFF"],
        "marisa-trie": [],
        "opencc": ["-DENABLE_GTEST=OFF", "-DENABLE_BENCHMARK=OFF", "-DBUILD_PYTHON=OFF", "-DUSE_SYSTEM_MARISA=ON", "-Dmarisa_DIR=" + str(prefix / "lib/cmake/marisa")],
        "librime": ["-DBUILD_STATIC=ON", "-DBUILD_TEST=OFF", "-DBUILD_DATA=OFF", "-DBUILD_SAMPLE=OFF", "-DBUILD_SEPARATE_LIBS=OFF", "-DBUILD_MERGED_PLUGINS=ON",
                    "-DENABLE_EXTERNAL_PLUGINS=OFF", "-DENABLE_TIMESTAMP=OFF", "-DENABLE_LOGGING=ON", "-DCMAKE_DISABLE_FIND_PACKAGE_Gflags=ON",
                    "-DBOOST_ROOT=" + str(boost), "-DBoost_NO_SYSTEM_PATHS=ON", "-DBoost_NO_BOOST_CMAKE=ON"],
    }
    for component, arguments in options.items():
        directory = WORK / "build" / component
        if directory.is_symlink() or directory.is_junction() or not directory.resolve().is_relative_to(WORK.resolve()):
            raise ValueError("Unsafe Rime build directory")
        install = WORK / "dist" if component == "librime" else prefix
        run([cmake_exe, "-S", WORK / "src" / component, "-B", directory, *common,
             "-DCMAKE_INSTALL_PREFIX=" + str(install), "-DBUILD_SHARED_LIBS=" + ("ON" if component == "librime" else "OFF"), *arguments],
            "configure-" + component)
        prefix_stamp = directory / "study-include-prefix.txt"
        if not prefix_stamp.exists() or prefix_stamp.read_text(encoding="utf-8") != include_prefix:
            run([cmake_exe, "--build", directory, "--target", "clean"], "reset-dependencies-" + component, record=False)
        run([cmake_exe, "--build", directory, "--target", "install", "--parallel", "4"], "build-" + component)
        write_changed(prefix_stamp, include_prefix)

    includes, compiled = {}, {}
    for component in options:
        directory = WORK / "build" / component
        compile_commands = json.loads((directory / "compile_commands.json").read_bytes())
        outputs = [item["output"] for item in compile_commands if not item["file"].lower().endswith(".rc")]
        # An incremental Ninja database can retain objects removed from the
        # current build graph. Query only the actual current translation units.
        dependencies = ""
        for offset in range(0, len(outputs), 64):
            dependencies += subprocess.check_output([str(ninja), "-t", "deps", *outputs[offset:offset + 64]],
                cwd=directory, env=env).decode("utf-8", errors="strict")
        paths = []
        for name in re.findall(r"^    (.+)$", dependencies, re.M):
            path = Path(os.path.abspath(directory / name.strip()))
            if path.is_file():
                paths.append(path)
        if not paths: raise ValueError("Ninja did not record compiler dependencies: " + component)
        for path in paths: includes[relative(path)] = file_hash(path)
        for item in compile_commands:
            path = Path(item["file"])
            arguments = command_arguments(item["command"])
            if path.suffix.lower() == ".rc":
                # Ninja/cmcldeps can omit RC dependencies on a fresh Windows
                # build. Trace the same RC preprocessor inputs explicitly,
                # with RC_INVOKED and the actual recorded defines/includes.
                resource_flags = []
                index = 1
                while index < len(arguments):
                    arg = arguments[index]
                    if arg in ["-I", "/I", "-D", "/D"]:
                        resource_flags += arguments[index:index + 2]
                        index += 2
                        continue
                    if arg.startswith(("-I", "/I", "-D", "/D")):
                        resource_flags.append(arg)
                    index += 1
                name = "resource-headers-" + component
                run([tools["cl"], "/nologo", "/TC", "/EP", "/showIncludes", "/utf-8", "/DRC_INVOKED",
                     *resource_flags, path], name)
                resource_log = (logs / (name + ".log")).read_text(encoding="utf-8")
                resource_headers = re.findall(r"^" + re.escape(include_prefix) + r"\s*(.+)$", resource_log, re.M)
                if not resource_headers: raise ValueError("Missing explicit resource header trace")
                for header in resource_headers:
                    header_path = Path(header.strip())
                    includes[relative(header_path)] = file_hash(header_path)
            compiled[relative(path)] = {"sha256": file_hash(path),
                "arguments": [normalized(arg) for arg in arguments]}
    if any("/wtl/" in name.casefold() for name in includes):
        raise ValueError("Unexpected WTL header in Rime build")
    for name, digest in source_tree.items():
        if file_hash(ROOT / name) != digest: raise ValueError("Rime source changed during compilation")
    for name, digest in project.items():
        if file_hash(ROOT / name) != digest: raise ValueError("Rime build script changed during compilation")
    dll = WORK / "dist/lib/rime.dll"
    image = inspect_pe(dll)
    if image["architecture"] != "x64": raise ValueError("Unexpected Rime architecture")
    include_trace = json_bytes(dict(sorted(includes.items())))
    compile_trace = json_bytes(dict(sorted(compiled.items())))
    write_changed(WORK / "include-trace.json", include_trace)
    write_changed(WORK / "compile-commands.json", compile_trace)
    record = {"schema_version": 1, "version": "1.13.1", "build_kind": "StudyIME source build", "plugins": ["lua"],
              "network_used": False, "runtime": "/MT", "toolchain": toolchain, "project_inputs": project,
              "compiler_include_prefix": include_prefix,
              "source_archives": sources, "source_tree_sha256": sha256(json_bytes(source_tree)),
              "boost_headers_sha256": sha256(json_bytes(boost_headers)), "compiled_source_count": len(compiled),
              "include_trace_sha256": sha256(include_trace), "compile_commands_sha256": sha256(compile_trace),
              "commands": commands, "binary": {"path": relative(dll), "sha256": file_hash(dll), "bytes": dll.stat().st_size, **image},
              "static_libraries": {relative(path): file_hash(path) for path in sorted(prefix.glob("lib/*.lib"))}}
    write_changed(WORK / "source-tree.json", json_bytes(source_tree))
    write_changed(WORK / "rime-build.json", json_bytes(record))
    print("Built and recorded the x64 Rime engine with only the Lua plugin; no system installation.", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        sources, tree = prepare_sources()
        print(f"Prepared {len(sources)} fixed source archives, {len(tree)} files.")
    else:
        build()
