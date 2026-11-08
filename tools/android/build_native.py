"""Cross-compile the pinned Rime/Lua engine for Android, never a Windows DLL."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, run
from tools.android.build_env import cmake, ndk, ninja, tool_env


def build(abi):
    if not (ndk() / ".study-receipt.json").is_file():
        raise ValueError("NDK extraction has not completed; run bootstrap.py sdk first")
    sources = CACHE / "src"
    prefix = CACHE / "native" / abi / "install"
    env = tool_env()
    env["RIME_PLUGINS"] = "lua"
    for name in ("CMAKE_PREFIX_PATH", "CMAKE_TOOLCHAIN_FILE", "CMAKE_PROJECT_TOP_LEVEL_INCLUDES"):
        env.pop(name, None)
    common = ["-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={ninja().as_posix()}",
              f"-DCMAKE_TOOLCHAIN_FILE={(ndk() / 'build/cmake/android.toolchain.cmake').as_posix()}",
              f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-29", "-DANDROID_STL=c++_shared",
              "-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON", "-DCMAKE_BUILD_TYPE=Release",
              "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DBUILD_SHARED_LIBS=OFF", "-DBUILD_TESTING=OFF",
              "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", f"-DCMAKE_INSTALL_PREFIX={prefix.as_posix()}",
              f"-DCMAKE_PREFIX_PATH={prefix.as_posix()}", "-DCMAKE_INSTALL_LIBDIR=lib",
              "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
              "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384"]
    options = {
        "leveldb": ["-DLEVELDB_BUILD_TESTS=OFF", "-DLEVELDB_BUILD_BENCHMARKS=OFF", "-DHAVE_SNAPPY=OFF", "-DHAVE_CRC32C=OFF", "-DHAVE_TCMALLOC=OFF"],
        "yaml-cpp": ["-DYAML_CPP_BUILD_CONTRIB=OFF", "-DYAML_CPP_BUILD_TESTS=OFF", "-DYAML_CPP_BUILD_TOOLS=OFF", "-DYAML_CPP_FORMAT_SOURCE=OFF"],
        "marisa-trie": [],
        "opencc": ["-DENABLE_GTEST=OFF", "-DENABLE_BENCHMARK=OFF", "-DBUILD_PYTHON=OFF", "-DUSE_SYSTEM_MARISA=ON", f"-Dmarisa_DIR={(prefix / 'lib/cmake/marisa').as_posix()}"],
        "engine": ["-DBUILD_SHARED_LIBS=ON", "-DBUILD_STATIC=ON", "-DBUILD_TEST=OFF", "-DBUILD_DATA=OFF", "-DBUILD_SAMPLE=OFF",
                   "-DBUILD_SEPARATE_LIBS=OFF", "-DBUILD_MERGED_PLUGINS=ON", "-DENABLE_EXTERNAL_PLUGINS=OFF", "-DENABLE_TIMESTAMP=OFF",
                   "-DENABLE_LOGGING=OFF", f"-DBOOST_ROOT={(sources / 'boost').as_posix()}", "-DBoost_NO_SYSTEM_PATHS=ON",
                   "-DBoost_NO_BOOST_CMAKE=ON", f"-DBoost_INCLUDE_DIR={(sources / 'boost').as_posix()}",
                   f"-DYamlCpp_NEW_API={(prefix / 'include').as_posix()}",
                   *[f"-D{name}_INCLUDE_PATH={(prefix / 'include').as_posix()}" for name in ("YamlCpp", "LevelDb", "Marisa", "Opencc")],
                   *[f"-D{name}_LIBRARY={(prefix / ('lib/lib' + library + '.a')).as_posix()}" for name, library in (("YamlCpp", "yaml-cpp"), ("LevelDb", "leveldb"), ("Marisa", "marisa"), ("Opencc", "opencc"))],
                   f"-DSTUDY_SOURCES={sources.as_posix()}"],
    }
    for component, flags in options.items():
        source = ROOT / "android/native" if component == "engine" else sources / component
        build_dir = CACHE / "native" / abi / component
        run([cmake(), "-S", source, "-B", build_dir, *common, *flags], f"{abi}-configure-{component}", env=env)
        run([cmake(), "--build", build_dir, "--target", "install", "--parallel", "2"], f"{abi}-build-{component}", env=env)
    target = ROOT / "android/app/src/main/jniLibs" / abi
    target.mkdir(parents=True, exist_ok=True)
    runtime = "aarch64-linux-android" if abi == "arm64-v8a" else "x86_64-linux-android"
    outputs = [prefix / "lib/libstudy_rime.so", ndk() / "toolchains/llvm/prebuilt/windows-x86_64/sysroot/usr/lib" / runtime / "libc++_shared.so"]
    records = []
    for source in outputs:
        output = target / source.name
        shutil.copy2(source, output)
        run([ndk() / "toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-strip.exe", "--strip-unneeded", output], f"{abi}-strip-{source.stem}", env=env)
        records.append({"file": source.name, "sha256": digest(output), "bytes": output.stat().st_size})
    json_write(CACHE / "native" / abi / "receipt.json", {"abi": abi, "ndk": "27.2.12479018", "api": 29, "files": records,
                "sources": json.loads((CACHE / "native-sources.json").read_text()), "patchSha256": digest(ROOT / "android/native/patches/rime-android.patch")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abi", choices=["arm64-v8a", "x86_64", "all"], default="all")
    args = parser.parse_args()
    for abi in (["x86_64", "arm64-v8a"] if args.abi == "all" else [args.abi]):
        build(abi)
