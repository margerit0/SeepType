"""Validate the source-built engine with the packaged data and 200 review entries."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, sha256, write_changed
from tools.packaging.engine_client import EngineProbe
from tools.packaging.package import payload, stage
from tools.lexicon import pipeline as lex


def pinyin_for(entry, data):
    value = data.sources[entry["source_entry_sha256"]]["pinyin"].lower().replace("u:", "v")
    value = re.sub(r"[1-5\s'-]", "", value)
    if not re.fullmatch("[a-z]+", value): raise ValueError("Unsupported pinyin: " + value)
    return value


def validate_words(probe, data, *, progress=True):
    checks = []
    translations = {entry["chinese"]: entry["commit_english"] for entry in data.entries}
    for entry in data.entries:
        pinyin = pinyin_for(entry, data)
        item = {"id": entry["id"], "chinese": entry["chinese"], "pinyin_input": pinyin, "passed": False}
        try:
            page, index = probe.find(pinyin, entry["chinese"])
            item.update({"page": page["page"], "candidate_index": index,
                "page_annotations_match": page["load"] == "ready" and all(
                    candidate["comment"] == translations.get(candidate["text"], "") for candidate in page["candidates"])})
            probe.command("highlight " + str(index))
            committed = probe.command("key 65293 5")
            item["english_commit_matches"] = committed["commit"] == entry["commit_english"] and committed["input"] == "" and committed["action"] == "english-committed"
            _, index = probe.find(pinyin, entry["chinese"])
            chinese = probe.command("choose " + str(index))
            item["ordinary_chinese_preserved"] = chinese["commit"] == entry["chinese"] and chinese["input"] == ""
            item["passed"] = all(item[key] for key in ["page_annotations_match", "english_commit_matches", "ordinary_chinese_preserved"])
            if not item["passed"]:
                item["actual_english"] = committed["commit"]
                item["actual_chinese"] = chinese["commit"]
        except ValueError as error:
            item["error"] = str(error)
        checks.append(item)
        if not item["passed"]:
            print("FAIL " + entry["chinese"] + ": " + json.dumps(item, ensure_ascii=False), flush=True)
        elif progress and len(checks) % 50 == 0:
            print(f"Checked {len(checks)}/{len(data.entries)} packaged words through source-built Rime/Lua", flush=True)
    return checks


def benchmarks(probe, count=200):
    results = []
    for query in ["shi", "de", "sh", "nihao", "zhongguo", "gongzuo", "mingtian", "xuexi",
                  "diannao", "pingguo", "woaini", "jintiantianqihenhao", "zhong", "shurufa", "zhe", "women"]:
        results.append(probe.command("bench " + str(count) + " " + query))
    return results


def verify():
    data = lex.validate()
    files, manifest = payload()
    work = CACHE / "verification" / ("engine-" + uuid.uuid4().hex)
    root = work / "relocated 中文 engine"
    stage(files, root)
    user = work / "user"
    prefix = "data/user-template/"
    for name, content in files.items():
        if name.startswith(prefix): write_changed(user / name[len(prefix):], content)
    executable = CACHE / "build/bin/StudyIME.EngineProbe.exe"
    dll = root / "bin/rime.dll"
    checks, timing, pronunciation_checks, startup, failure = [], [], [], None, None
    probe = None
    start = time.monotonic()
    try:
        probe = EngineProbe(executable, dll, root / "data/shared", user)
        startup = probe.receive(timeout=120)
        if not (startup["version"] == "1.13.1" and startup["pointer_bits"] == 64 and startup["lua_module"] and
                not startup["octagram_module"] and not startup["predict_module"]):
            raise ValueError("Unexpected source-built Rime modules or architecture")
        checks = validate_words(probe, data)
        for pinyin, expected in [("zhao", ["找"]), ("xing", ["行"]), ("dai", ["带"]), ("zhang", ["长", "张"]), ("huan", ["换"]), ("chong", ["冲"])]:
            probe.command("clear")
            page = probe.command("type " + pinyin)
            actual = [item["text"] for item in page["candidates"]]
            pronunciation_checks.append({"pinyin": pinyin, "allowed_first": expected, "required_on_first_page": expected,
                "actual_first_page": actual, "passed": bool(actual) and actual[0] in expected and all(word in actual for word in expected)})
        timing = benchmarks(probe)
    except Exception as error:
        failure = str(error)
    finally:
        if probe:
            try: probe.close()
            except Exception as error: failure = failure or str(error)
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Source-built x64 Rime/Lua with actual packaged dictionaries and the unchanged English review preview; isolated programmatic C API input",
              "passed": failure is None and len(checks) == len(data.entries) and all(item["passed"] for item in checks) and bool(pronunciation_checks) and all(item["passed"] for item in pronunciation_checks),
              "error": failure, "startup": startup, "checks": checks, "pronunciation_checks": pronunciation_checks, "benchmarks": timing,
              "seconds": round(time.monotonic() - start, 3), "review_counts": data.counts,
              "lexicon_content_sha256": data.content_hash, "native_build_sha256": file_hash(CACHE / "build/native-build.json"),
              "rime_build_sha256": sha256(files["source-provenance/rime-build.json"]), "rime_dll_sha256": file_hash(dll),
              "probe_sha256": file_hash(executable), "dictionary_bytes": {name: len(content) for name, content in files.items() if name.startswith("data/shared/")},
              "compiled_data_bytes": {path.name: path.stat().st_size for path in sorted((user / "build").glob("*")) if path.is_file()},
              "runtime_input_hashes": {name: sha256(content) for name, content in files.items() if name.startswith(("bin/", "data/shared/", "data/user-template/"))},
              "limits": ["No human approval is implied for the English meanings", "Synthetic latency on this machine only; no desktop, installed TSF or multi-application acceptance"],
              "work_directory": work.relative_to(ROOT).as_posix()}
    write_changed(ROOT / "experiments/phase6/results/source-built-engine.json", json_bytes(report))
    print(str(sum(item["passed"] for item in checks)) + "/" + str(len(data.entries)) + " words passed", flush=True)
    if not report["passed"]: raise SystemExit(failure or "Source-built Rime regression")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    verify()
