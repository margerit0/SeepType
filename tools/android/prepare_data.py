"""Build Android resources from existing, verified data; never invent entries."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, fetch, json_write, safe, write
from tools.android.english_completions import ASSET as ENGLISH_COMPLETIONS, build_index
from tools.android.offline_names import load_names
from tools.android.word_details import pack_details
from tools.dictionary.cedict import files as chinese_files

SNAPSHOT = ROOT / "data/lexicon-expansion/android-runtime"
STUDY_CORE = ROOT / "src/study/lua/study_core.lua"
ASSETS = ROOT / "android/app/src/main/assets/generated"
ENGINE_CASES = ROOT / "android/app/src/androidTest/assets/generated/engine-cases.json"
RUNTIME_ASSETS = {"lexicon.lua": "rime/lua/lexicon.lua", "cedict_study.dict.yaml": "rime/cedict_study.dict.yaml"}
SCHEMES = ("study", "study_double_pinyin", "study_flypy")
RIME_SOURCES = {
    **{f"rime/{schema}.schema.yaml": ROOT / f"packaging/data/{schema}.schema.yaml" for schema in SCHEMES},
    "rime/rime.lua": ROOT / "android/rime/rime.lua",
    "rime/lua/study_details.lua": ROOT / "android/rime/study_details.lua",
    "rime/study_android.dict.yaml": ROOT / "android/rime/study_android.dict.yaml",
    "rime/study_phrases.dict.yaml": ROOT / "android/rime/study_phrases.dict.yaml",
}
# The prism and the shared cedict_study user dictionary stay unchanged.
SCHEME_PATCH = b"patch:\n  menu/page_size: 9\n  translator/dictionary: study_android\n  translator/user_dict: cedict_study\n"
DETAIL_ROWS = "word-details.jsonl"
EXAMPLES = SNAPSHOT / "word-detail-examples.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_snapshot():
    lock = (SNAPSHOT / "snapshot.json").read_bytes()
    snapshot = json.loads(lock)
    if snapshot["schemaVersion"] != 1 or snapshot["releaseReady"] or snapshot["humanApproved"] != 0:
        raise ValueError("Expected a Windows development lexicon snapshot")
    payload = {}
    for name in (*RUNTIME_ASSETS, "engine-cases.json", DETAIL_ROWS):
        payload[name] = (SNAPSHOT / name).read_bytes()
        if hashlib.sha256(payload[name]).hexdigest() != snapshot["files"][name]:
            raise ValueError(f"Windows lexicon snapshot hash mismatch: {name}")
    core = STUDY_CORE.read_bytes()
    if hashlib.sha256(core).hexdigest() != snapshot["studyCoreSha256"]:
        raise ValueError("study_core.lua does not match the imported Windows runtime")
    return snapshot, lock, payload, core


def refresh_if_needed(source_cache=None):
    snapshot, lock, runtime, _ = load_snapshot()
    detail_hashes = {name: sha(content) for name, content in pack_details(runtime[DETAIL_ROWS], EXAMPLES.read_bytes()).items()}
    names, names_summary = load_names(runtime["cedict_study.dict.yaml"])
    expected = {ASSETS / "notices/english/snapshot.json": sha(lock),
                ASSETS / "rime/lua/study_core.lua": snapshot["studyCoreSha256"],
                ENGINE_CASES: snapshot["files"]["engine-cases.json"],
                **{ASSETS / asset: snapshot["files"][name] for name, asset in RUNTIME_ASSETS.items()},
                **{ASSETS / asset: digest(source) for asset, source in RIME_SOURCES.items()},
                **{ASSETS / f"rime/{schema}.custom.yaml": sha(SCHEME_PATCH) for schema in SCHEMES},
                **{ASSETS / asset: sha(content) for asset, content in names.items()},
                **{ASSETS / asset: expected_hash for asset, expected_hash in detail_hashes.items()}}
    # The archive may not have been restored yet in a fresh checkout.
    wordfreq_archive = json.loads((ROOT / "data/chinese/sources.lock.json").read_bytes())["wordfreq"]["archive"]
    if not (ROOT / wordfreq_archive).is_file():
        prepare(source_cache)
        return
    expected[ASSETS / ENGLISH_COMPLETIONS] = sha(build_index())
    expected[ASSETS / "notices/english/NOTICE.txt"] = digest(SNAPSHOT / "NOTICE.txt")
    expected[ASSETS / "notices/README.txt"] = sha(notice_text(snapshot))
    manifest = ASSETS / "manifest.json"
    existing = json.loads(manifest.read_bytes()) if manifest.is_file() else {}
    actual_files = {path.relative_to(ASSETS).as_posix() for path in ASSETS.rglob("*") if path.is_file()}
    declared_files = set(existing.get("files", {})) | set(detail_hashes) | {"manifest.json"}
    if (actual_files != declared_files or existing.get("detailFiles") != detail_hashes or
            existing.get("offlineNames") != names_summary or any(
        not path.is_file() or digest(path) != expected_hash for path, expected_hash in expected.items()
    )):
        prepare(source_cache)


def prepare(source_cache=None):
    snapshot, lock, runtime, study_core = load_snapshot()
    details = pack_details(runtime[DETAIL_ROWS], EXAMPLES.read_bytes())
    names, names_summary = load_names(runtime["cedict_study.dict.yaml"])
    source_cache = Path(source_cache).resolve() if source_cache else None
    chinese_lock = json.loads((ROOT / "data/chinese/sources.lock.json").read_text())
    cedict_lock = json.loads((ROOT / "data/lexicon/source.lock.json").read_text())
    artifact = cedict_lock["artifact"]
    inputs = [chinese_lock["wordfreq"], chinese_lock["unicode"],
              {**artifact, "archive": f".cache/dictionaries/cc-cedict/{artifact['archive_sha256']}.txt.gz"}]
    receipts = []
    for item in inputs:
        destination = ROOT / item["archive"]
        if not destination.exists() and source_cache:
            source = source_cache / item["archive"]
            if source.is_file() and digest(source) == item["archive_sha256"]:
                # Read only immutable, checked raw source archives. Never copy
                # Windows binaries, generated dictionaries or personal data.
                write(destination, source.read_bytes())
        fetch(item["url"], destination, item["archive_sha256"])
        receipts.append({"url": item["url"], "sha256": digest(destination), "archive": item["archive"]})
    raw = gzip.decompress((ROOT / inputs[-1]["archive"]).read_bytes())
    if hashlib.sha256(raw).hexdigest() != artifact["text_sha256"]:
        raise ValueError("CC-CEDICT text hash mismatch")
    write((ROOT / inputs[-1]["archive"]).with_suffix(""), raw)
    chinese = chinese_files()
    if hashlib.sha256(chinese["cedict_study.dict.yaml"]).hexdigest() != snapshot["baseDictionarySha256"]:
        raise ValueError("Imported supplemental readings were built on a different Chinese base dictionary")
    payload = {"rime/lua/study_core.lua": study_core,
               ENGLISH_COMPLETIONS: build_index(),
               **{asset: runtime[name] for name, asset in RUNTIME_ASSETS.items()},
               **{asset: source.read_bytes() for asset, source in RIME_SOURCES.items()},
               **names}
    for source in (CACHE / "src/rime-prelude").glob("*.yaml"):
        payload["rime/" + source.name] = source.read_bytes()
    for source in (CACHE / "src/rime-luna-pinyin").glob("*.yaml"):
        payload["rime/" + source.name] = source.read_bytes()
    payload["rime/default.custom.yaml"] = b"patch:\n  schema_list:\n    - schema: study\n    - schema: study_double_pinyin\n    - schema: study_flypy\n  menu/page_size: 9\n"
    # Android's compact strip shows 6–7 entries and the expanded panel shows
    # nine. Override each schema locally; the Windows five-entry menu is shared
    # source and must retain its original configuration.
    for schema in SCHEMES:
        payload[f"rime/{schema}.custom.yaml"] = SCHEME_PATCH
    payload["notices/english/snapshot.json"] = lock
    payload["notices/english/NOTICE.txt"] = (SNAPSHOT / "NOTICE.txt").read_bytes()
    payload["notices/english/legacy-preview-NOTICE.txt"] = (ROOT / "data/lexicon/NOTICE.txt").read_bytes()
    expansion = ROOT / "data/lexicon-expansion"
    payload["notices/english/sources.lock.json"] = (expansion / "sources.lock.json").read_bytes()
    for name in ("CEFRJ-README.md", "ECDICT-LICENSE.txt"):
        payload["notices/english/" + name] = (expansion / "notices" / name).read_bytes()
    for name, content in chinese.items():
        if name != "cedict_study.dict.yaml":
            write(CACHE / "data-materials/chinese" / name, content)
            if name != "source-mapping.json":
                payload["notices/chinese/" + name] = content
    for source in [ROOT / "LICENSE", ROOT / "licensing/product-sources.lock.json", ROOT / "licensing/double-pinyin.lock.json"]:
        if source.is_file():
            payload["notices/" + source.name] = source.read_bytes()
    source_lock = json.loads((ROOT / "licensing/product-sources.lock.json").read_text())
    for item in source_lock["sources"]:
        for notice in item["notices"]:
            payload["notices/" + notice["path"].removeprefix("licensing/")] = (ROOT / notice["path"]).read_bytes()
    for name in ("rime-double-pinyin/LICENSE", "boost/LICENSE_1_0.txt"):
        payload["notices/third-party/" + name] = (ROOT / "licensing/third-party" / name).read_bytes()
    from tools.android.prepare_notices import payload as dependency_notices
    if (ROOT / "Cargo.lock").is_file() and (CACHE / "cargo/registry/src").is_dir():
        payload.update(dependency_notices())
    payload["notices/README.txt"] = notice_text(snapshot)
    hashes = {name: sha(content) for name, content in sorted(payload.items())}
    version = sha(json.dumps(hashes, sort_keys=True).encode())[:20]
    # Detail assets are covered by build/packaging receipts, but neither
    # copied nor hashed during Rime startup. Kotlin reads the signed APK.
    payload.update(details)
    for old in ASSETS.rglob("*"):
        # Only the root manifest is replaced below; same-named nested files
        # from another preview must not survive in the signed APK.
        if old.is_file() and old != ASSETS / "manifest.json" and old.relative_to(ASSETS).as_posix() not in payload:
            safe(old).unlink()
    for name, content in payload.items():
        write(ASSETS / name, content)
    manifest = {"format": 1, "version": version, "chineseSnapshot": cedict_lock["snapshot_date"],
                "chineseEntries": snapshot["chineseDictionaryRows"], "englishEntries": snapshot["acceptedRecords"],
                "englishTriggerReadings": snapshot["englishTriggerReadings"], "humanApproved": snapshot["humanApproved"],
                "windowsLexiconCommit": snapshot["windowsCommit"],
                "englishRegressionCases": len(json.loads(runtime["engine-cases.json"])),
                "status": "developer-preview", "files": hashes, "offlineNames": names_summary,
                "detailFiles": {name: sha(content) for name, content in details.items()}}
    write(ENGINE_CASES, runtime["engine-cases.json"])
    json_write(ASSETS / "manifest.json", manifest)
    json_write(CACHE / "data-receipt.json", {**manifest, "inputs": receipts})
    print(json.dumps({key: value for key, value in manifest.items() if key not in ("files", "detailFiles")}, ensure_ascii=False))


def notice_text(snapshot):
    return (
        "拾词 Android 开发预览 · 许可与数据来源\n"
        "新 Kotlin、Rust 和桥接代码：GPL-3.0-or-later。\n"
        "中文基础数据：CC-CEDICT 2026-11-06，wordfreq 3.1.1，Unihan 17.0.0；完整署名见 chinese。\n"
        f"英文词库：{snapshot['acceptedRecords']:,} 条开发记录；仅作开发预览，未获人工发布审批。来源见 english。\n"
        "英文拼写补全：The CEFR-J Wordlist Version 1.5. Compiled by Yukio Tono, Tokyo University of Foreign Studies. "
        "词形去重并按 wordfreq 3.1.1 英语词频排序，派生索引采用 CC BY-SA 4.0；原始署名见 english 和 chinese。\n"
        "安卓影视与游戏专名：Wikidata 结构化标签（CC0-1.0）及项目分音节读音；固定来源见 android-names。\n"
        "安卓日常、网络和游戏补充词组：参考 wordfreq 筛选和 CC-CEDICT 读音，CC BY-SA 4.0；原始署名见 chinese。\n"
        "Rime、librime-lua、LevelDB、marisa、OpenCC、yaml-cpp、Boost 与双拼方案的许可见 third-party。\n"
        "AndroidX、Kotlin 与 kotlinx.coroutines：Apache-2.0；Rust 标准库及 JNI/serde 依赖：MIT / Apache-2.0。\n"
        "NDK libc++：Apache-2.0 WITH LLVM-exception。源码、锁文件、构建脚本随开发预览材料提供。\n"
        "Quicksand 和 Fredoka 字体：SIL OFL 1.1；原始 TTF、固定来源和许可随 APK 提供。\n"
        "输入、释义和学习均在本机执行；不申请网络权限，用户词典不进入 Android 备份。\n"
    ).encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cache", type=Path, help="Optional read-only raw source archive cache; all hashes must match")
    args = parser.parse_args()
    prepare(args.source_cache)
