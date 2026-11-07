"""Compare the proposed CC-CEDICT base with the current product's Chinese data."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.dictionary.cedict import files as cedict_files
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, sha256, write_changed
from tools.packaging.engine_client import EngineProbe
from tools.packaging.package import payload
from tools.packaging.verify_engine import validate_words, benchmarks
from tools.lexicon import pipeline as lex

SAMPLES = [("ni", "你"), ("wo", "我"), ("ta", "他"), ("de", "的"), ("shi", "是"),
           ("le", "了"), ("bu", "不"), ("zai", "在"), ("you", "有"), ("ren", "人"),
           ("hao", "好"), ("zhongguo", "中国"), ("shurufa", "输入法"), ("xiexie", "谢谢"),
           ("jintian", "今天"), ("women", "我们"), ("xianzai", "现在"), ("diannao", "电脑"),
           ("zhe", "这"), ("na", "那")]


def samples(probe):
    results = []
    for pinyin, expected in SAMPLES:
        probe.command("clear")
        page = probe.command("type " + pinyin)
        item = {"pinyin": pinyin, "expected": expected, "first_page": [candidate["text"] for candidate in page["candidates"]]}
        try:
            page, index = probe.find(pinyin, expected)
            item["rank"] = page["page"] * 5 + index + 1
        except ValueError:
            item["rank"] = None
        results.append(item)
    return results


def summary(checks, examples):
    return {"review_words_passed": sum(item["passed"] for item in checks), "review_words": len(checks),
            "review_words_on_first_page": sum(item.get("page") == 0 for item in checks),
            "review_words_ranked_first": sum(item.get("page") == 0 and item.get("candidate_index") == 0 for item in checks),
            "common_samples": len(examples), "common_samples_ranked_first": sum(item["rank"] == 1 for item in examples),
            "common_samples_on_first_page": sum(item["rank"] is not None and item["rank"] <= 5 for item in examples)}


def compare(weighting="uniform"):
    data = lex.validate()
    product_files, manifest = payload()
    baseline = json.loads((ROOT / "experiments/phase6/results/source-built-engine.json").read_bytes())
    if not baseline["passed"] or baseline["rime_dll_sha256"] != sha256(product_files["bin/rime.dll"]) or baseline["lexicon_content_sha256"] != data.content_hash:
        raise ValueError("Run the current product engine verification first")
    current_inputs = {name: sha256(content) for name, content in product_files.items() if name.startswith(("bin/", "data/shared/", "data/user-template/"))}
    if current_inputs != baseline["runtime_input_hashes"]:
        raise ValueError("The product dictionary/runtime changed; verify the current engine before comparison")
    generated = cedict_files(weighting, comparison=True)
    provenance = json.loads(generated["provenance.json"])
    work = CACHE / "verification" / ("dictionary-" + uuid.uuid4().hex)
    executable = CACHE / "build/bin/StudyIME.EngineProbe.exe"
    output = {}
    previous_path = ROOT / "experiments/phase6/results/chinese-dictionary-comparison.json"
    previous = json.loads(previous_path.read_bytes()) if weighting != "uniform" and previous_path.exists() else None
    for variant in ["current", "cedict_" + weighting]:
        if variant == "current" and previous and previous["baseline_report_sha256"] == file_hash(ROOT / "experiments/phase6/results/source-built-engine.json") and [(item["pinyin"], item["expected"]) for item in previous["variants"]["current"]["common_samples"]] == SAMPLES:
            output[variant] = previous["variants"]["current"]
            print("Reused unchanged current-dictionary comparison", flush=True)
            continue
        root = work / variant
        shared, user = root / "shared", root / "user"
        for name, content in product_files.items():
            if name.startswith("data/shared/"):
                if variant != "current" and name.endswith(("luna_pinyin.dict.yaml", "essay.txt")): continue
                write_changed(shared / name[len("data/shared/"):], content)
            elif name.startswith("data/user-template/"):
                write_changed(user / name[len("data/user-template/"):], content)
        if variant != "current":
            schema = (shared / "study.schema.yaml").read_text(encoding="utf-8")
            if schema.count("  prism: study") != 1: raise ValueError("Unexpected product schema layout")
            schema = schema.replace("  dictionary: cedict_study\n", "")
            schema = schema.replace("  prism: study", "  dictionary: cedict_study\n  prism: study").replace("    - simplifier\n", "")
            write_changed(shared / "study.schema.yaml", schema)
            write_changed(shared / "cedict_study.dict.yaml", generated["cedict_study.dict.yaml"])
        dll = root / "rime.dll"
        write_changed(dll, product_files["bin/rime.dll"])
        probe = EngineProbe(executable, dll, shared, user)
        try:
            startup = probe.receive(timeout=120)
            examples = samples(probe)
            checks = baseline["checks"] if variant == "current" else validate_words(probe, data, progress=False)
            timing = baseline["benchmarks"] if variant == "current" else benchmarks(probe)
        finally:
            probe.close()
        output[variant] = {"startup": startup, "summary": summary(checks, examples),
                           "common_samples": examples, "review_checks": checks, "benchmarks": timing}
        print(variant + ": " + json.dumps(output[variant]["summary"]), flush=True)
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "product_data_switched": False,
              "english_review_counts": data.counts, "source_provenance": provenance, "variants": output,
              "rime_dll_sha256": sha256(product_files["bin/rime.dll"]), "probe_sha256": file_hash(executable),
              "baseline_report_sha256": file_hash(ROOT / "experiments/phase6/results/source-built-engine.json"),
              "work_directory": work.relative_to(ROOT).as_posix(),
              "limits": ["This is a Chinese dictionary comparison only, not human approval of English glosses", "Derived weights are not a modern word-frequency corpus", "Synthetic samples do not establish everyday typing quality"]}
    report_name = {"uniform": "chinese-dictionary-comparison.json", "unicode": "chinese-dictionary-weighted-comparison.json", "wordfreq": "chinese-dictionary-wordfreq-comparison.json"}[weighting]
    write_changed(ROOT / "experiments/phase6/results" / report_name, json_bytes(report))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weighting", choices=["uniform", "unicode", "wordfreq"], default="uniform")
    args = parser.parse_args()
    compare(args.weighting)
