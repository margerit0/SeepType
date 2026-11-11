"""Use the installed pinned compiler with worktree-local Android sysroots."""
import argparse
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.build_env import cargo, ndk, tool_env
from tools.android.common import CACHE, ROOT, digest, json_write, run


def build(abi):
    target = "aarch64-linux-android" if abi == "arm64-v8a" else "x86_64-linux-android"
    env = tool_env()
    bin_path = ndk() / "toolchains/llvm/prebuilt/windows-x86_64/bin"
    env["STUDY_RIME_LIB_DIR"] = str(ROOT / "android/app/src/main/jniLibs" / abi)
    key = "CARGO_TARGET_" + target.upper().replace("-", "_")
    env[key + "_LINKER"] = str(bin_path / (target + "29-clang.cmd"))
    env[key + "_RUSTFLAGS"] = "--sysroot " + (CACHE / "rust-sysroot").as_posix() + " -C link-arg=-Wl,-z,max-page-size=16384 -C link-arg=-Wl,-z,common-page-size=16384"
    run([cargo(), "build", "--locked", "--release", "--target", target, "-p", "study-android", "--jobs", "2"], "rust-" + abi, env=env)
    source = CACHE / "cargo-target" / target / "release/libstudy_android.so"
    destination = ROOT / "android/app/src/main/jniLibs" / abi / source.name
    shutil.copy2(source, destination)
    json_write(CACHE / "native" / abi / "rust-receipt.json", {"rust": "1.88.0", "target": target, "sha256": digest(destination), "bytes": destination.stat().st_size})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abi", choices=["arm64-v8a", "x86_64", "all"], default="all")
    args = parser.parse_args()
    for abi in (["x86_64", "arm64-v8a"] if args.abi == "all" else [args.abi]):
        build(abi)
