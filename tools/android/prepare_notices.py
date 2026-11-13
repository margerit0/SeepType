"""Retain actual notices from the resolved, locked Android and Rust inputs."""
import io
import json
from pathlib import Path
import tomllib
import xml.etree.ElementTree as ET
import zipfile

from tools.android.common import CACHE, ROOT, digest, json_write, fetch
from tools.android.build_env import tool_env, ndk


def payload():
    result = {}
    components = []
    fonts = ROOT / "android/app/src/main/assets/fonts"
    for font in json.loads((fonts / "manifest.json").read_text(encoding="utf-8")):
        components.append({"ecosystem": "Font", **font})
        result["notices/fonts/" + font["licenseFile"]] = (fonts / font["licenseFile"]).read_bytes()
    registry = CACHE / "cargo/registry/src"
    packages = tomllib.loads((ROOT / "Cargo.lock").read_text(encoding="utf-8"))["package"]
    apache = next(registry.glob("*/jni-0.21.1/LICENSE-APACHE")).read_bytes()
    result["notices/android/Apache-2.0.txt"] = apache
    for item in packages:
        if "source" not in item:
            continue
        matches = list(registry.glob("*/" + item["name"] + "-" + item["version"]))
        if not matches:  # Non-host Windows targets in Cargo.lock were not built.
            continue
        source = matches[0]
        metadata = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))["package"]
        record = {"ecosystem": "Cargo", "name": item["name"], "version": item["version"],
                  "license": metadata.get("license", ""), "authors": metadata.get("authors", []),
                  "repository": metadata.get("repository", ""), "crateSha256": item["checksum"],
                  "scope": "Android runtime or host build dependency; see Cargo dependency graph"}
        components.append(record)
        prefix = "notices/rust/" + source.name + "/"
        for file in source.iterdir():
            if file.is_file() and file.name.lower().startswith(("license", "copying", "notice", "copyright")):
                result[prefix + file.name] = file.read_bytes()
        if item["name"] == "cesu8":
            for name in ("src/lib.rs", "src/unicode.rs"):
                text = (source / name).read_text(encoding="utf-8")
                result[prefix + Path(name).name + "-copyright.txt"] = text.split("\n\n", 1)[0].encode("utf-8")
        if not any(key.startswith(prefix) for key in result):
            result[prefix + "AUTHORS.txt"] = (json.dumps(record, ensure_ascii=False, indent=2) + "\nApache-2.0 license text: ../../android/Apache-2.0.txt\n").encode("utf-8")

    gradle = CACHE / "gradle-home/caches/modules-2/files-2.1"
    for line in (ROOT / "android/app/gradle.lockfile").read_text(encoding="utf-8").splitlines():
        if not any(name in line for name in ("debugRuntimeClasspath", "releaseRuntimeClasspath")) or line.startswith("#") or "=" not in line:
            continue
        coordinate, _ = line.split("=", 1)
        if coordinate.count(":") != 2:
            continue
        group, artifact, version = coordinate.split(":")
        folder = gradle / group / artifact / version
        files = sorted(folder.glob("*/*"))
        records = []
        pom_licenses = []
        for file in files:
            if file.suffix == ".pom":
                pom = ET.parse(file).getroot()
                ns = {"m": "http://maven.apache.org/POM/4.0.0"}
                pom_licenses.extend({"name": element.findtext("m:name", namespaces=ns), "url": element.findtext("m:url", namespaces=ns)} for element in pom.findall("m:licenses/m:license", ns))
            if file.suffix not in (".aar", ".jar"):
                continue
            records.append({"file": file.name, "sha256": digest(file)})
            with zipfile.ZipFile(file) as archive:
                archives = [("", archive)]
                if "classes.jar" in archive.namelist():
                    archives.append(("classes/", zipfile.ZipFile(io.BytesIO(archive.read("classes.jar")))))
                for nested_prefix, nested in archives:
                    for name in nested.namelist():
                        if not name.endswith("/") and any(token in Path(name).name.lower() for token in ("license", "notice", "copying")):
                            result[f"notices/android/{group}/{artifact}-{version}/{nested_prefix}{name}"] = nested.read(name)
        components.append({"ecosystem": "Maven", "coordinate": coordinate, "licenses": pom_licenses, "artifacts": records,
                           "source": f"https://maven.google.com/{group.replace('.', '/')}/{artifact}/{version}/" if group.startswith("androidx.") else
                           f"https://repo.maven.apache.org/maven2/{group.replace('.', '/')}/{artifact}/{version}/"})

    rust = Path(tool_env()["RUSTC"]).parent.parent / "share/doc/rust"
    for file in (rust / "licenses").glob("*.txt"):
        result["notices/rust/standard-library/licenses/" + file.name] = file.read_bytes()
    result["notices/rust/standard-library/COPYRIGHT-library.html"] = (rust / "COPYRIGHT-library.html").read_bytes()
    result["notices/android/NDK-NOTICE.txt"] = (ndk() / "NOTICE").read_bytes()
    graphics_source = fetch("https://dl.google.com/dl/android/maven2/androidx/graphics/graphics-path/1.0.1/graphics-path-1.0.1-sources.jar",
        CACHE / "downloads/graphics-path-1.0.1-sources.jar", "9f1b5995b9577a8876525c3411ebb2a49f9ef0e875f6aec3059e807596dc6ca6")
    with zipfile.ZipFile(graphics_source) as source:
        header = source.read("androidx/graphics/path/ConicConverter.kt").decode("utf-8").split("*/", 1)[0] + "*/\n"
        result["notices/android/graphics-path-1.0.1-copyright.txt"] = header.encode("utf-8")
    lua = (CACHE / "src/librime/plugins/lua/thirdparty/lua5.4/lua.h").read_text(encoding="utf-8")
    result["notices/third-party/lua/COPYRIGHT.txt"] = lua[lua.rfind("/********"):lua.rfind("#endif")].encode("utf-8")
    result["notices/dependencies.json"] = (json.dumps(components, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    combined = ["拾词 Android 第三方依赖许可\n版本和来源详见 dependencies.json。包含运行组件及构建期间使用的组件。\n"]
    for path, content in sorted(result.items()):
        if not path.endswith(".html") and path != "notices/dependencies.json":
            combined.append("\n\n--- " + path + " ---\n" + content.decode("utf-8", errors="replace"))
    result["notices/THIRD-PARTY.txt"] = "".join(combined).encode("utf-8")
    json_write(CACHE / "dependency-receipt.json", components)
    return result
