"""Reproducible Android entry point. Outputs follow the configured cache path."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, run
from tools.android.build_env import tool_env


def signing_key():
    key = CACHE / "keystore/studyime-debug.keystore"
    if key.exists():
        return
    key.parent.mkdir(parents=True, exist_ok=True)
    run([Path(tool_env()["JAVA_HOME"]) / "bin/keytool.exe", "-genkeypair", "-keystore", key,
         "-storepass", "android", "-keypass", "android", "-alias", "androiddebugkey", "-keyalg", "RSA",
         "-keysize", "2048", "-validity", "10000", "-dname", "CN=StudyIME Android Development,O=StudyIME,C=CN"],
        "development-signing-key", env=tool_env())


def gradle(tasks, *, log="gradle-build", wrapper=True, locks=False):
    signing_key()
    executable = ROOT / "android/gradlew.bat" if wrapper else CACHE / "gradle-8.11.1/bin/gradle.bat"
    command = [executable, *tasks, "--no-daemon", "--console=plain"]
    if locks: command.append("--write-locks")
    run(command, log, env=tool_env(), cwd=ROOT / "android")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["prepare", "compile", "apk", "tests", "lint"])
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--source-cache", type=Path)
    args = parser.parse_args()
    if args.step == "prepare":
        from tools.android import bootstrap, prepare_sources, prepare_build_tools, prepare_data, build_native, build_rust
        if not (CACHE / "sdk-downloads.json").exists(): bootstrap.metadata()
        bootstrap.install_sdk()
        prepare_build_tools.prepare()
        prepare_sources.prepare()
        prepare_data.prepare(args.source_cache)
        for abi in ("x86_64", "arm64-v8a"):
            build_native.build(abi)
            build_rust.build(abi)
    elif args.step == "compile":
        gradle([":app:compileDebugKotlin"], log="gradle-compile", wrapper=False, locks=True)
    elif args.step == "apk":
        variant = "Debug" if args.debug else "Release"
        gradle([":app:assemble" + variant], log="gradle-apk-" + variant.lower(), locks=True)
        output = ROOT / "android/app/build/outputs/apk" / variant.lower() / ("app-" + variant.lower() + ".apk")
        print(f"APK: {output.resolve()}\nSHA256: {digest(output)}")
        json_write(CACHE / ("apk-" + variant.lower() + ".json"), {"variant": variant, "path": str(output.resolve()),
                    "sha256": digest(output), "bytes": output.stat().st_size, "gitHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    "sourceState": "worktree build; see delivery manifest for final source hashes"})
    elif args.step == "tests":
        gradle([":app:testDebugUnitTest", ":app:assembleDebugAndroidTest"], log="gradle-tests", locks=True)
    else:
        gradle([":app:lintDebug", ":app:lintRelease"], log="gradle-lint")


if __name__ == "__main__":
    main()
