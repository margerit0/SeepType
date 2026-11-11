"""Build Android resources from existing, verified data; never invent entries."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, fetch, json_write, safe, write
from tools.dictionary.cedict import files as chinese_files
from tools.lexicon import pipeline


def prepare(source_cache=None):
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
    snapshot = (ROOT / inputs[-1]["archive"]).with_suffix("")
    write(snapshot, raw)
    lexicon = pipeline.validate(ROOT / "data/lexicon", snapshot)
    english = pipeline.build_files(lexicon, "preview")
    chinese = chinese_files()
    generated = ROOT / "android/app/src/main/assets/generated"
    payload = {}
    for name in ("study.schema.yaml", "study_double_pinyin.schema.yaml", "study_flypy.schema.yaml", "rime.lua"):
        payload["rime/" + name] = (ROOT / "packaging/data" / name).read_bytes()
    payload["rime/lua/study_core.lua"] = (ROOT / "src/study/lua/study_core.lua").read_bytes()
    payload["rime/lua/lexicon.lua"] = english["lexicon.lua"]
    payload["rime/cedict_study.dict.yaml"] = chinese["cedict_study.dict.yaml"]
    for source in (CACHE / "src/rime-prelude").glob("*.yaml"):
        payload["rime/" + source.name] = source.read_bytes()
    for source in (CACHE / "src/rime-luna-pinyin").glob("*.yaml"):
        payload["rime/" + source.name] = source.read_bytes()
    payload["rime/default.custom.yaml"] = b"patch:\n  schema_list:\n    - schema: study\n    - schema: study_double_pinyin\n    - schema: study_flypy\n  menu/page_size: 5\n"
    for name, content in english.items():
        if name not in ("lexicon.lua", "review.html"):
            payload["notices/english/" + name] = content
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
    payload["notices/README.txt"] = (
        "拾词 Android 开发预览 0.1.0-preview.1\n"
        "新 Kotlin、Rust 和桥接代码：GPL-3.0-or-later。\n"
        "中文基础数据：CC-CEDICT 2026-11-06，wordfreq 3.1.1，Unihan 17.0.0；完整署名见 chinese。\n"
        "英文释义：200 条开发审核稿，人工通过 0 条；不是已审核的正式词库。\n"
        "Rime、librime-lua、LevelDB、marisa、OpenCC、yaml-cpp、Boost 与双拼方案的许可见 third-party。\n"
        "AndroidX、Kotlin 与 kotlinx.coroutines：Apache-2.0；Rust 标准库及 JNI/serde 依赖：MIT / Apache-2.0。\n"
        "NDK libc++：Apache-2.0 WITH LLVM-exception。源码、锁文件、构建脚本随开发预览材料提供。\n"
        "输入、释义和学习均在本机执行；不申请网络权限，用户词典不进入 Android 备份。\n"
    ).encode("utf-8")
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(payload.items())}
    version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:20]
    for old in generated.rglob("*") if generated.exists() else []:
        if old.is_file() and old.relative_to(generated).as_posix() not in payload and old.name != "manifest.json":
            safe(old).unlink()
    for name, content in payload.items():
        write(generated / name, content)
    manifest = {"format": 1, "version": version, "chineseSnapshot": cedict_lock["snapshot_date"],
                "chineseEntries": json.loads(chinese["provenance.json"])["dictionary_entries"],
                "englishEntries": len(lexicon.entries), "humanApproved": lexicon.counts["approved-for-distribution"],
                "status": "developer-preview", "files": hashes}
    json_write(generated / "manifest.json", manifest)
    json_write(CACHE / "data-receipt.json", {**manifest, "inputs": receipts})
    # Reuse the independent, already reviewed syllable-to-key oracle. Importing
    # these pure helpers does not execute any Windows packaging or engine test.
    from tools.packaging.verify_double_pinyin import SCHEMAS, input_for
    cases = [{"schema": schema, "input": input_for(entry, lexicon, schema), "chinese": entry["chinese"],
              "english": entry["commit_english"]} for schema in SCHEMAS for entry in lexicon.entries]
    json_write(ROOT / "android/app/src/androidTest/assets/generated/engine-cases.json", cases)
    print(json.dumps({key: value for key, value in manifest.items() if key != "files"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cache", type=Path, help="Optional read-only raw source archive cache; all hashes must match")
    args = parser.parse_args()
    prepare(args.source_cache)
