"""Install the Wrapper distribution and Android Rust stdlib in this checkout."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, DOWNLOADS, ROOT, digest, extract, fetch, json_write, write


def prepare():
    receipts = []
    jdk_url = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.7%2B6/OpenJDK21U-jdk_x64_windows_hotspot_21.0.7_6.zip"
    jdk_checksum = fetch(jdk_url + ".sha256.txt", DOWNLOADS / "jdk-21.0.7.sha256.txt").read_text().split()[0]
    jdk = CACHE / "jdk-21.0.7"
    if not (jdk / "bin/jlink.exe").is_file():
        archive = fetch(jdk_url, DOWNLOADS / "jdk-21.0.7.zip", jdk_checksum)
        extract(archive, jdk)
        archive.unlink()
    receipts.append({"id": "jdk", "version": "Temurin 21.0.7+6", "sha256": jdk_checksum, "url": jdk_url})
    gradle_url = "https://services.gradle.org/distributions/gradle-8.11.1-bin.zip"
    checksum = fetch(gradle_url + ".sha256", DOWNLOADS / "gradle-8.11.1-bin.zip.sha256").read_text().strip().split()[0]
    gradle = CACHE / "gradle-8.11.1"
    if not (gradle / "bin/gradle.bat").is_file():
        archive = fetch(gradle_url, DOWNLOADS / "gradle-8.11.1-bin.zip", checksum)
        extract(archive, gradle)
        archive.unlink()
    write(ROOT / "android/gradle/wrapper/gradle-wrapper.properties",
          "distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\n"
          "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.11.1-bin.zip\n"
          f"distributionSha256Sum={checksum}\nnetworkTimeout=120000\nvalidateDistributionUrl=true\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n")
    receipts.append({"id": "gradle", "version": "8.11.1", "sha256": checksum, "url": gradle_url})
    for target in ("aarch64-linux-android", "x86_64-linux-android"):
        name = f"rust-std-1.88.0-{target}.tar.xz"
        url = "https://static.rust-lang.org/dist/2025-06-26/" + name
        expected = fetch(url + ".sha256", DOWNLOADS / (name + ".sha256")).read_text().split()[0]
        destination = CACHE / "rust-sysroot"
        if not (destination / "lib/rustlib" / target / "lib").is_dir():
            archive = fetch(url, DOWNLOADS / name, expected)
            extract(archive, destination, lambda path: path.startswith("lib/"), strip=2)
            archive.unlink()
        receipts.append({"id": target, "version": "1.88.0", "sha256": expected, "url": url})
    json_write(CACHE / "build-tools-receipt.json", receipts)
    print("Gradle and both Android Rust targets are ready.")


if __name__ == "__main__":
    prepare()
