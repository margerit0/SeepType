"""Reproducible Android entry point. Outputs follow the configured cache path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, run
from tools.android.build_env import tool_env


def input_hashes():
    """Bind APK assembly to source and prepared bytes, including dirty inputs."""
    source_roots = ["android", "crates", "tools/android", "data/lexicon-expansion/android-runtime",
                    "data/lexicon-expansion/android-names", "src/study/lua/study_core.lua", "Cargo.toml", "Cargo.lock", "rust-toolchain.toml"]
    source_roots.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / "packaging/data").glob("study*.schema.yaml"))
    if (ROOT / ".git").exists():
        names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *source_roots],
                                        cwd=ROOT).decode("utf-8").split("\0")
    else:
        # Source archives intentionally have no .git directory. Prune outputs
        # before walking so an extracted archive remains a buildable input.
        names = []
        for name in source_roots:
            path = ROOT / name
            if path.is_file():
                names.append(name)
            elif path.is_dir():
                for directory, dirs, files in os.walk(path):
                    dirs[:] = [part for part in dirs if part not in ("build", ".gradle", ".kotlin", ".cxx", "jniLibs", "generated", "__pycache__")]
                    names.extend((Path(directory) / file).relative_to(ROOT).as_posix() for file in files if file != "local.properties")
    result = {}
    for name in sorted(set(names)):
        path = ROOT / name
        if not name or not path.is_file() or path.suffix == ".md":
            continue
        data = path.read_bytes()
        try:
            data.decode("utf-8")
            data = data.replace(b"\r\n", b"\n")
        except UnicodeDecodeError:
            pass
        result[name] = hashlib.sha256(data).hexdigest()
    prepared = list((ROOT / "android/app/src/main/jniLibs").glob("*/*.so"))
    prepared.append(ROOT / "android/app/src/main/assets/generated/manifest.json")
    prepared.extend((ROOT / "android/app/src/androidTest/assets/generated").glob("*.json"))
    for path in prepared:
        if path.is_file():
            result[path.relative_to(ROOT).as_posix()] = digest(path)
    return result


def apk_version(apk):
    """Read the installable package's version, not the Rime resource version."""
    aapt = CACHE / "sdk/build-tools/35.0.0/aapt.exe"
    badging = subprocess.check_output([str(aapt), "dump", "badging", str(apk)]).decode("utf-8", errors="replace")
    match = re.search(r"^package: .*?versionCode='([0-9]+)' versionName='([A-Za-z0-9][A-Za-z0-9.+-]*)'",
                      badging, re.MULTILINE)
    if not match:
        raise ValueError(f"Cannot read versionName and versionCode from APK: {apk}")
    return {"versionName": match[2], "versionCode": int(match[1])}


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
    before = input_hashes()
    executable = ROOT / "android/gradlew.bat" if wrapper else CACHE / "gradle-8.11.1/bin/gradle.bat"
    command = [executable, *tasks, "--no-daemon", "--console=plain"]
    if locks: command.append("--write-locks")
    run(command, log, env=tool_env(), cwd=ROOT / "android")
    after = input_hashes()
    for variant in ("Debug", "Release", "DebugAndroidTest"):
        if not any(task.split(":")[-1] == "assemble" + variant for task in tasks):
            continue
        apk = (ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk" if variant == "DebugAndroidTest"
               else ROOT / f"android/app/build/outputs/apk/{variant.lower()}/app-{variant.lower()}.apk")
        json_write(CACHE / ("assembly-" + variant.lower() + ".json"), {
            "variant": variant, "apkSha256": digest(apk), "bytes": apk.stat().st_size,
            "inputHashing": "SHA-256; UTF-8 source CRLF normalized to LF; prepared binaries hashed verbatim",
            "inputHashes": after, "inputsUnchangedDuringBuild": before == after,
            "tasks": tasks, "log": log + ".log", "logSha256": digest(CACHE / "logs" / (log + ".log")),
            "scope": "Successful Gradle assembly of these sources and prepared native libraries/assets; not a fresh native source rebuild",
        })


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
        # Resolve managed dependencies before collecting their original
        # notices, then regenerate the versioned, complete asset payload.
        gradle([":app:compileDebugKotlin"], log="gradle-prepare-dependencies", locks=True)
        prepare_data.prepare(args.source_cache)
    elif args.step == "compile":
        gradle([":app:compileDebugKotlin"], log="gradle-compile", wrapper=False, locks=True)
    elif args.step == "apk":
        from tools.android.prepare_data import prepare, refresh_if_needed
        variant = "Debug" if args.debug else "Release"
        if not (ROOT / "android/app/src/main/assets/generated/notices/THIRD-PARTY.txt").is_file():
            gradle([":app:compile" + variant + "Kotlin"], log="gradle-prepare-notices", locks=True)
            prepare(args.source_cache)
        else:
            refresh_if_needed(args.source_cache)
        gradle([":app:assemble" + variant], log="gradle-apk-" + variant.lower(), locks=True)
        output = ROOT / "android/app/build/outputs/apk" / variant.lower() / ("app-" + variant.lower() + ".apk")
        version = apk_version(output)
        sha = digest(output)
        print(f"APK: {output.resolve()}\nVersion: {version['versionName']} ({version['versionCode']})\nSHA256: {sha}")
        json_write(CACHE / ("apk-" + variant.lower() + ".json"), {"variant": variant, "path": str(output.resolve()),
                    **version, "sha256": sha, "bytes": output.stat().st_size, "gitHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() if (ROOT / ".git").exists() else None,
                    "sourceState": "worktree build; see delivery manifest for final source hashes"})
    elif args.step == "tests":
        from tools.android.prepare_data import refresh_if_needed
        refresh_if_needed(args.source_cache)
        gradle([":app:testDebugUnitTest", ":app:assembleDebugAndroidTest"], log="gradle-tests", locks=True)
    else:
        gradle([":app:lintDebug", ":app:lintRelease"], log="gradle-lint")


if __name__ == "__main__":
    main()
