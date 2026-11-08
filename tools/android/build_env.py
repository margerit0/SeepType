"""Worktree-local build environment; existing tools may be read, never updated."""
import os
from pathlib import Path
import subprocess
from functools import lru_cache
import urllib.request
import urllib.parse

from tools.android.common import CACHE, ROOT


@lru_cache(maxsize=1)
def tool_env():
    env = dict(os.environ)
    vcvars = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat")
    if vcvars.exists():
        output = subprocess.check_output(f'call "{vcvars}" >nul && set', shell=True)
        for line in output.decode("utf-8", errors="replace").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.upper() in ("PATH", "INCLUDE", "LIB", "LIBPATH"):
                env[name.upper()] = value
    jdk = env.get("STUDY_JAVA_HOME", str(CACHE / "jdk-21.0.7") if (CACHE / "jdk-21.0.7/bin/jlink.exe").is_file() else r"D:\Program Files\IntelliJ IDEA\jbr")
    rust = env.get("STUDY_RUST_BIN", str(Path.home() / ".rustup/toolchains/stable-x86_64-pc-windows-msvc/bin"))
    env.update({"JAVA_HOME": jdk, "RUSTC": str(Path(rust) / "rustc.exe"),
                "CARGO_HOME": str(CACHE / "cargo"), "CARGO_TARGET_DIR": str(CACHE / "cargo-target"),
                "GRADLE_USER_HOME": str(CACHE / "gradle-home"),
                "ANDROID_HOME": str(CACHE / "sdk"), "ANDROID_SDK_ROOT": str(CACHE / "sdk"),
                "ANDROID_USER_HOME": str(CACHE / "android-user"),
                "ANDROID_AVD_HOME": str(CACHE / "avd"),
                "PATH": str(Path(jdk) / "bin") + os.pathsep + rust + os.pathsep + env.get("PATH", "")})
    temporary = CACHE / "temp"
    temporary.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = env["TMP"] = str(temporary)
    proxy = urllib.parse.urlsplit(urllib.request.getproxies().get("https", ""))
    if proxy.hostname and not proxy.username:
        env["JAVA_TOOL_OPTIONS"] = " ".join(f"-D{scheme}.proxyHost={proxy.hostname} -D{scheme}.proxyPort={proxy.port or 80}" for scheme in ("http", "https"))
    env["JAVA_TOOL_OPTIONS"] = env.get("JAVA_TOOL_OPTIONS", "") + " -Djava.io.tmpdir=" + temporary.as_posix() + " -XX:ErrorFile=" + (CACHE / "logs/hs_err_pid%p.log").as_posix() + " -XX:ReplayDataFile=" + (CACHE / "logs/replay_pid%p.log").as_posix()
    return env


def cmake():
    return Path(os.environ.get("STUDY_CMAKE", r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"))


def ninja():
    return Path(os.environ.get("STUDY_NINJA", r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"))


def ndk():
    return CACHE / "sdk/ndk/27.2.12479018"


def cargo():
    return Path(tool_env()["RUSTC"]).with_name("cargo.exe")
