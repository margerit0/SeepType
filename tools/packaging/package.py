"""Build a deterministic, relocatable StudyIME developer package offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, deterministic_zip, file_hash, json_bytes, package_path, product, sha256, write_changed
from tools.packaging.collect_licenses import source_files
from tools.lexicon import pipeline as lex
from tools.packaging.pe import inspect_pe
from tools.packaging.native_inputs import snapshot
from tools.packaging import rime_inputs
from tools.packaging.product_sources import locked_sources
from tools.dictionary.cedict import files as chinese_dictionary

DATA = {
    "rime-luna-pinyin": ["luna_pinyin.schema.yaml", "luna_pinyin_simp.schema.yaml", "pinyin.yaml"],
    "rime-prelude": ["default.yaml", "key_bindings.yaml", "punctuation.yaml", "symbols.yaml"],
}


def source_lock():
    value = locked_sources()
    for item in value["sources"]:
        if file_hash(ROOT / item["archive"]) != item["archive_sha256"]:
            raise ValueError(f"Changed source archive: {item['id']}")
        for notice in item["notices"]:
            if file_hash(ROOT / notice["path"]) != notice["sha256"]:
                raise ValueError(f"Changed upstream notice: {notice['path']}")
    notices = json.loads((ROOT / "licensing/notices.lock.json").read_text(encoding="utf-8"))
    for item in notices["notices"]:
        if file_hash(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"Changed supplemental notice: {item['path']}")
    if file_hash(ROOT / "LICENSE") != file_hash(ROOT / "licensing/third-party/weasel/LICENSE.txt"):
        raise ValueError("The complete GPL text no longer matches its recorded original")
    return value


def chinese_data(lock):
    payload, provenance = {}, []
    evidence = json.loads((ROOT / "licensing/chinese-data.lock.json").read_text(encoding="utf-8"))
    cache_evidence = {item["path"]: item for item in evidence["files"]}
    for source in lock["sources"]:
        if source["id"] not in DATA: continue
        archived = dict(source_files(ROOT / source["archive"]))
        for name in DATA[source["id"]]:
            original = archived[name]
            content = original
            changes = []
            if source["id"] == "opencc":
                relative = "opencc/" + Path(name).name
                if relative.endswith(".json"):
                    if content.count(b'"ocd2"') != 3:
                        raise ValueError("The pinned t2s configuration changed")
                    content = content.replace(b'"ocd2"', b'"text"').replace(b'.ocd2"', b'.txt"')
                    changes = ["Read pinned UTF-8 text dictionaries directly instead of untraced compiled ocd2 data."]
                cache_match = None
            else:
                relative = name
                recorded = cache_evidence["data/shared/" + name]
                if recorded["commit"] != source["commit"] or recorded["source_sha256"] != sha256(original):
                    raise ValueError("Chinese source data changed after its audit")
                cache_match = recorded["lf_normalized_match"]
            target = "data/shared/" + relative
            payload[target] = content
            provenance.append({"path": target, "component": source["id"], "commit": source["commit"],
                               "source_path": name, "source_sha256": sha256(original), "sha256": sha256(content),
                               "changes": changes, "matches_legacy_cache_after_lf_normalization": cache_match})
    base = chinese_dictionary()
    for name, content in base.items():
        target = "data/shared/" + name if name.endswith(".dict.yaml") else "data/chinese/" + name
        payload[target] = content
    payload["data/chinese/README.md"] = (ROOT / "data/chinese/README.md").read_bytes()
    payload["data/chinese/sources.lock.json"] = (ROOT / "data/chinese/sources.lock.json").read_bytes()
    payload["data/chinese/cc-cedict-source.lock.json"] = (ROOT / "data/lexicon/source.lock.json").read_bytes()
    metadata = json.loads(base["provenance.json"])
    provenance.append({"path": "data/shared/cedict_study.dict.yaml", "component": "cc-cedict-and-wordfreq",
        "sha256": metadata["dictionary_sha256"], "source_provenance": "data/chinese/provenance.json",
        "source_mapping": "data/chinese/source-mapping.json", "license": "CC-BY-SA-4.0",
        "changes": ["Use CC-CEDICT simplified headwords and explicit Mandarin readings", "Apply exact wordfreq Chinese headword frequencies; missing words get weight 1", "No mixed Luna dictionary or essay frequencies"]})
    return payload, sorted(provenance, key=lambda item: item["path"])


def release_blockers(data, audit):
    blockers = list(audit["release_blockers"])
    choice = json.loads((ROOT / "licensing/code-license.json").read_text(encoding="utf-8"))
    if choice["status"] != "approved": blockers.append({"id": "code-license", "detail": "New-code license is not approved."})
    if data.counts["pending"] or not data.counts["approved-for-distribution"]:
        blockers.append({"id": "human-lexicon-review", "detail": f"{data.counts['pending']} entries await human review; {data.counts['approved-for-distribution']} approved."})
    blockers += [{"id": "installed-and-desktop-acceptance", "detail": "Real install/uninstall, TSF automatic routing and deferred Computer Use acceptance are not complete."}]
    if product()["channel"] != "release": blockers.append({"id": "developer-channel", "detail": "Product identity and settings are marked developer preview."})
    return blockers


def native_build():
    record = json.loads((CACHE / "build/native-build.json").read_text(encoding="utf-8"))
    if record["product_version"] != product()["version"]: raise ValueError("Stale product version in native build")
    for name, expected in record["inputs"].items():
        if file_hash(ROOT / name) != expected: raise ValueError(f"Native source changed; rebuild before packaging: {name}")
    current = snapshot()
    if current != {"project": record["inputs"], "generated": record["generated_inputs"], "dependencies": record["dependency_inputs"]}:
        raise ValueError("Native project/generated/dependency input tree changed; rebuild before packaging")
    if file_hash(CACHE / "build/include-trace.json") != record["include_trace_sha256"]:
        raise ValueError("Native compiler include trace changed")
    for name, digest in json.loads((CACHE / "build/include-trace.json").read_bytes()).items():
        if file_hash(ROOT / name) != digest:
            raise ValueError("Native included header changed; rebuild: " + name)
    for name, item in record["binaries"].items():
        if file_hash(CACHE / "build/bin" / name) != item["sha256"]:
            raise ValueError(f"Native binary changed after its build record: {name}")
    return record


def payload(mode="preview"):
    data = lex.validate()
    audit = json.loads((ROOT / "licensing/components.json").read_text(encoding="utf-8"))
    blockers = release_blockers(data, audit)
    if mode == "release" and blockers:
        raise ValueError("Product release blocked:\n" + "\n".join(item["id"] + ": " + item["detail"] for item in blockers))
    record = native_build()
    lock = source_lock()
    files, provenance = chinese_data(lock)
    for name in record["binaries"]: files["bin/" + name] = (CACHE / "build/bin" / name).read_bytes()
    engine = rime_inputs.validate()
    runtime = ROOT / engine["binary"]["path"]
    files["bin/rime.dll"] = runtime.read_bytes()
    for name in ["study.schema.yaml", "weasel.yaml"]:
        files["data/shared/" + name] = (ROOT / "packaging/data" / name).read_bytes()
    for name in ["default.custom.yaml", "rime.lua"]:
        files["data/user-template/" + name] = (ROOT / "packaging/data" / name).read_bytes()
    files["data/user-template/lua/study_core.lua"] = (ROOT / "src/study/lua/study_core.lua").read_bytes()
    learning = lex.build_files(data, mode)
    files["data/user-template/lua/lexicon.lua"] = learning["lexicon.lua"]
    for name, content in learning.items(): files["data/lexicon/" + name] = content
    files["data/lexicon/README.md"] = (ROOT / "packaging/data/lexicon-readme.md").read_bytes()
    for file in sorted((ROOT / "licensing").rglob("*")):
        if file.is_file(): files[file.relative_to(ROOT).as_posix()] = file.read_bytes()
    for name in ["LICENSE", "COPYING.md", "docs/software-licenses.md"]:
        files[name] = (ROOT / name).read_bytes()
    files["README.txt"] = (ROOT / "packaging/README.txt").read_bytes()
    files["product.json"] = json_bytes(product())
    files["source-provenance/chinese-data.json"] = json_bytes(provenance)
    files["source-provenance/native-build.json"] = json_bytes(record)
    files["source-provenance/include-trace.json"] = (CACHE / "build/include-trace.json").read_bytes()
    files["source-provenance/rime-build.json"] = json_bytes(engine)
    for name in ["source-tree.json", "include-trace.json", "compile-commands.json"]:
        files["source-provenance/rime-" + name] = (rime_inputs.WORK / name).read_bytes()
    files["source-provenance/rime-version-info.txt"] = (
        "StudyIME source build: librime 1.13.1; merged plugins: lua only\n" +
        "\n".join(name + " " + item["commit"] for name, item in sorted(engine["source_archives"].items())) + "\n").encode("utf-8")
    files["source-provenance/runtime-dependencies.json"] = json_bytes({"rime.dll": {"sha256": engine["binary"]["sha256"], **inspect_pe(runtime)},
            "scope": "PE imports plus explicitly loaded packaged Rime; system DLLs are not copied."})
    files["assets/StudyIME.ico"] = (CACHE / "generated/StudyIME.ico").read_bytes()
    files["assets/StudyIME.svg"] = (ROOT / "packaging/artwork/StudyIME.svg").read_bytes()
    for name in ["Install.ps1", "Uninstall.ps1", "Install.cmd", "Uninstall.cmd"]:
        files[name] = (ROOT / "packaging/windows" / name).read_bytes()
    files["scripts/Common.ps1"] = (ROOT / "packaging/windows/Common.ps1").read_bytes()
    manifest = {"schema_version": 1, "product": product(), "mode": mode, "release_ready": not blockers,
                "release_blockers": blockers, "lexicon_review": data.counts,
                "archive_format": "ZIP_STORED; sorted UTF-8 paths; fixed 1980-01-01 timestamps; fixed permissions",
                "files": [{"path": name, "sha256": sha256(content), "bytes": len(content)} for name, content in sorted(files.items())]}
    files["package-manifest.json"] = json_bytes(manifest)
    return files, manifest


def source_materials():
    lock = source_lock()
    files = {}
    allowed = ("src/", "tools/", "packaging/", "licensing/", "data/lexicon/", "data/chinese/")
    candidates = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    for name in sorted(set(candidates)):
        if not name: continue
        include = name.startswith(allowed) or name in ["LICENSE", "COPYING.md", ".gitattributes", ".gitignore", "README.md"]
        if name.startswith("experiments/phase3/") or name.startswith("experiments/phase4/"):
            include = "/results/" not in name and Path(name).suffix in [".py", ".cmd", ".cpp", ".h", ".json", ".yaml", ".lua", ".patch", ".manifest", ".md"]
        if name in ["docs/software-licenses.md", "docs/packaging.md", "docs/license-proposal.md",
                    "docs/word-frequency.md", "docs/optimization-todo.md"]: include = True
        if name.startswith("experiments/phase4/results/previews-v05/") and name.endswith(".png"): include = True
        if include and (ROOT / name).is_file(): files["project/" + name] = (ROOT / name).read_bytes()
    materials = []
    for source in lock["sources"]:
        path = ROOT / source["archive"]
        name = "upstream/" + path.name
        files[name] = path.read_bytes()
        materials.append({"path": name, "sha256": source["archive_sha256"], "restore": source["archive"]})
    bundle = CACHE / "sources/weasel-9cc96e20.bundle"
    if not bundle.exists():
        subprocess.run(["git", "bundle", "create", str(bundle), "HEAD"], cwd=ROOT / ".cache/src/weasel", check=True)
    heads = subprocess.check_output(["git", "bundle", "list-heads", str(bundle)], text=True)
    if heads.strip() != "9cc96e20dc71b80876b12f689bb5863c76c2a7ed HEAD": raise ValueError("Unexpected Weasel source bundle revision")
    path = "upstream/" + bundle.name
    files[path] = bundle.read_bytes()
    materials.append({"path": path, "sha256": sha256(files[path]), "restore": ".cache/packaging/sources/" + bundle.name})
    dependencies = json.loads((ROOT / "experiments/phase3/dependencies.lock.json").read_text(encoding="utf-8"))
    for artifact in dependencies["artifacts"]:
        if artifact["name"] != "boost_1_84_0.tar.bz2": continue
        file = ROOT / ".cache/downloads" / artifact["name"]
        if file_hash(file) != artifact["sha256"]: raise ValueError("Changed build dependency archive: " + artifact["name"])
        name = "upstream/" + artifact["name"]
        files[name] = file.read_bytes()
        materials.append({"path": name, "sha256": artifact["sha256"], "restore": ".cache/downloads/" + artifact["name"]})
    for tool in json.loads((ROOT / "licensing/build-tools.lock.json").read_bytes())["tools"]:
        file = ROOT / tool["archive"]
        if file_hash(file) != tool["archive_sha256"]: raise ValueError("Changed fixed build tool: " + tool["id"])
        name = "build-tools/" + file.name
        files[name] = file.read_bytes()
        materials.append({"path": name, "sha256": tool["archive_sha256"], "restore": tool["archive"]})
    cedict = json.loads((ROOT / "data/lexicon/source.lock.json").read_bytes())["artifact"]
    unicode = json.loads((ROOT / "data/chinese/sources.lock.json").read_bytes())["unicode"]
    wordfreq = json.loads((ROOT / "data/chinese/sources.lock.json").read_bytes())["wordfreq"]
    data_materials = [
        (".cache/dictionaries/cc-cedict/" + cedict["archive_sha256"] + ".txt.gz", cedict["archive_sha256"]),
        (unicode["archive"], unicode["archive_sha256"]),
        (wordfreq["archive"], wordfreq["archive_sha256"]),
    ]
    for path, digest in data_materials:
        file = ROOT / path
        if file_hash(file) != digest: raise ValueError("Changed fixed dictionary source: " + path)
        name = "dictionary-sources/" + file.name
        files[name] = file.read_bytes()
        materials.append({"path": name, "sha256": digest, "restore": path})
    files["source-materials.json"] = json_bytes({"schema_version": 1, "product": product(), "materials": materials,
        "completeness": "Project, fixed source archives and portable CMake for building the product and Rime/Lua locally. No official prebuilt Rime DLL is supplied or used. Remaining release limitations: project/docs/software-licenses.md."})
    files["BUILD.txt"] = ("StudyIME source and build materials\n\n"
        "Prerequisites: Windows 11 x64, Python 3.13+, Git, VS2019 14.29 C++ tools, ATL and SDK 10.0.19041.0.\n"
        "The existing VS Ninja is used; a fixed portable CMake is supplied. No compiler or SDK installation is performed.\n"
        "From project/: python tools/packaging/bootstrap_sources.py ..\n"
        "Then: tools\\packaging\\build.cmd (builds Rime/Lua and all four product binaries)\n"
        "Then: python tools/packaging/package.py --mode preview\n"
        "All commands above are offline. No input method is installed or registered.\n"
        "Source and license review limitations: project/docs/software-licenses.md\n").encode("utf-8")
    return files


def stage(files, directory):
    directory = directory.resolve()
    if not directory.is_relative_to(CACHE.resolve()) or directory == CACHE.resolve():
        raise ValueError("Staging is restricted to a named directory under .cache/packaging")
    if directory.exists():
        actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
        if actual - files.keys(): raise ValueError("Refusing to overwrite a staging directory with unlisted files")
    for name, content in sorted(files.items()):
        package_path(name)
        destination = directory / name
        for parent in [destination, *destination.parents]:
            if parent.is_symlink() or parent.is_junction(): raise ValueError("Reparse point in staging path")
            if parent == CACHE: break
        write_changed(destination, content)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["preview", "release"], default="preview")
    parser.add_argument("--output", type=Path, default=CACHE / "dist")
    parser.add_argument("--with-sources", action="store_true")
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    files, manifest = payload(args.mode)
    filename = f"StudyIME-{product()['version']}-windows-x64-{args.mode}.zip"
    archive = args.output / filename
    deterministic_zip(archive, files)
    if args.stage: stage(files, args.stage)
    results = {filename: {"sha256": file_hash(archive), "bytes": archive.stat().st_size}}
    if args.with_sources:
        name = f"StudyIME-{product()['version']}-source-materials.zip"
        source = args.output / name
        deterministic_zip(source, source_materials())
        results[name] = {"sha256": file_hash(source), "bytes": source.stat().st_size}
    write_changed(args.output / "SHA256SUMS.txt", "".join(f"{item['sha256']}  {name}\n" for name, item in sorted(results.items())))
    report = {"product": product(), "archives": results, "payload_files": len(files),
              "release_ready": manifest["release_ready"], "lexicon_review": manifest["lexicon_review"]}
    write_changed(args.output / "package-report.json", json_bytes(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try: main()
    except (ValueError, FileNotFoundError) as error:
        raise SystemExit(str(error)) from error
