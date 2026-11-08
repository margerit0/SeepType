"""Exercise all three input schemes through real Rime and isolated product IPC.

No installation or normal user data is involved. The keyboard oracle below is
a syllable/key table, independent of the shipped Rime regular expressions.
"""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.lexicon import pipeline as lex
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, write_changed
from tools.packaging.engine_client import EngineProbe
from tools.packaging.package import payload, stage
from tools.packaging.verify_engine import validate_words, pinyin_for


FINALS = {
    "study_double_pinyin": {
        "iu": "q", "ia": "w", "ua": "w", "uan": "r", "van": "r", "ue": "t", "ve": "t",
        "ing": "y", "uai": "y", "uo": "o", "un": "p", "vn": "p", "ong": "s", "iong": "s",
        "iang": "d", "uang": "d", "en": "f", "eng": "g", "ang": "h", "ian": "m", "an": "j",
        "iao": "c", "ao": "k", "ai": "l", "ei": "z", "ie": "x", "ui": "v", "ou": "b", "in": "n",
    },
    "study_flypy": {
        "iu": "q", "ei": "w", "uan": "r", "ue": "t", "ve": "t", "un": "y", "uo": "o", "ie": "p",
        "ong": "s", "iong": "s", "ing": "k", "uai": "k", "ai": "d", "en": "f", "eng": "g",
        "iang": "l", "uang": "l", "ang": "h", "ian": "m", "an": "j", "ou": "z", "ia": "x",
        "ua": "x", "iao": "n", "ao": "c", "ui": "v", "in": "b",
    },
}
SCHEMAS = ["study", *FINALS]


def encode_syllable(syllable, schema):
    syllable = re.sub(r"[1-5]", "", syllable.lower().replace("u:", "v"))
    if not re.fullmatch("[a-z]+", syllable):
        raise ValueError("Unsupported oracle syllable: " + syllable)
    if syllable[0] in "aoe":
        if len(syllable) == 1:
            return syllable * 2
        if len(syllable) == 2:
            return syllable
        return syllable[0] + FINALS[schema][syllable]
    initial = next((part for part in ["zh", "ch", "sh"] if syllable.startswith(part)), syllable[0])
    final = syllable[len(initial):]
    return {"zh": "v", "ch": "i", "sh": "u"}.get(initial, initial) + FINALS[schema].get(final, final)


def input_for(entry, data, schema):
    if schema == "study":
        return pinyin_for(entry, data)
    syllables = re.split(r"[\s'-]+", data.sources[entry["source_entry_sha256"]]["pinyin"].strip())
    return "".join(encode_syllable(part, schema) for part in syllables)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=["engine", "ipc", "all"], default="all")
    parser.add_argument("--legacy-package", type=Path, default=CACHE / "stage/StudyIME-0.5.0-dev.2")
    args = parser.parse_args()
    files, manifest = payload()
    work = CACHE / "verification" / ("double-pinyin-" + uuid.uuid4().hex)
    package = work / "product 中文"
    stage(files, package)
    executable = CACHE / "build/bin/StudyIME.EngineProbe.exe"
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "section": args.section,
        "scope": "Isolated Rime C API and real product IPC with synthetic input; no installed TSF or physical input",
        "product_version": manifest["product"]["version"], "work_directory": work.relative_to(ROOT).as_posix(),
        "native_build_sha256": file_hash(CACHE / "build/native-build.json"),
        "rime_dll_sha256": file_hash(package / "bin/rime.dll"),
        "engine_probe_sha256": file_hash(executable),
        "ipc_probe_sha256": file_hash(CACHE / "build/bin/StudyIME.DoublePinyinProbe.exe"),
        "schema_sha256": {name: file_hash(package / "data/shared" / (name + ".schema.yaml")) for name in SCHEMAS},
        "source_lock_sha256": file_hash(ROOT / "licensing/double-pinyin.lock.json"),
        "checks": [], "word_regressions": {}, "ipc": [],
    }

    def check(name, passed, **detail):
        report["checks"].append({"name": name, "passed": bool(passed), **detail})
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            raise AssertionError(name)

    def find_current(probe, current, word):
        for _ in range(80):
            for index, candidate in enumerate(current["candidates"]):
                if candidate["text"] == word:
                    return current, index
            if current["last"]:
                break
            current = probe.command("key 65366 0")
        raise AssertionError("Missing segmented candidate: " + word)

    def engine_checks():
        user = work / "engine-user"
        shutil.copytree(package / "data/user-template", user)
        probe = EngineProbe(executable, package / "bin/rime.dll", package / "data/shared", user)
        try:
            report["engine_startup"] = probe.receive(timeout=55)
            data = lex.validate()
            # Explicit examples also exercise every zero-initial convention,
            # the two layouts' differing finals, and the standard u/v aliases.
            common = [("aa", "阿"), ("ee", "饿"), ("oo", "哦"), ("ai", "爱"), ("an", "安"),
                      ("ao", "熬"), ("ou", "欧"), ("en", "嗯"), ("er", "儿"), ("ah", "昂"), ("eg", "鞥"),
                      ("nv", "女"), ("lv", "绿"), ("nt", "虐"), ("lt", "略"), ("ju", "句"), ("jv", "句"),
                      ("qu", "去"), ("qv", "去"), ("xu", "需"), ("xv", "需"), ("yu", "雨"), ("yv", "雨"),
                      ("vsgo", "中国"), ("xtxi", "学习")]
            specific = {
                "study_double_pinyin": [("nihk", "你好"), ("ni'hk", "你好"), ("al", "爱"), ("aj", "安"),
                                        ("ez", "诶"), ("jp", "军"), ("yp", "云"), ("xtxc", "学校"), ("pgyb", "朋友")],
                "study_flypy": [("nihc", "你好"), ("ni'hc", "你好"), ("ad", "爱"), ("aj", "安"),
                                ("ew", "诶"), ("jy", "军"), ("yy", "云"), ("xtxn", "学校"), ("pgyz", "朋友")],
            }
            for schema in SCHEMAS:
                probe.command("schema " + schema)
                probe.command("user_learning 0")
                words = validate_words(probe, data, input_for=lambda entry, corpus: input_for(entry, corpus, schema))
                report["word_regressions"][schema] = words
                check(schema + " preserves all 200 English annotations and Chinese/English commits",
                      len(words) == 200 and all(item["passed"] for item in words))
                if schema == "study":
                    continue
                for code, chinese in common + specific[schema]:
                    _, index = probe.find(code, chinese, pages=80)
                    actual = probe.command("choose " + str(index))
                    check(schema + " maps " + code + " to " + chinese,
                          actual["commit"] == chinese and not actual["input"])
                code = "nihc" if schema == "study_flypy" else "nihk"
                probe.command("clear")
                probe.command("type " + code)
                erased = probe.command("key 65288 0")
                restored = probe.command("type " + code[-1])
                check(schema + " edits a two-key syllable with backspace",
                      erased["input"] == code[:-1] and restored["input"] == code and
                      any(item["text"] == "你好" for item in restored["candidates"]))

            # Teach a new phrase by selecting two segments in Flypy, then
            # inspect/forget it through the other schemes using the same DB.
            probe.command("schema study_flypy")
            probe.command("user_learning 1")
            page, index = probe.find("nihc", "拟", pages=80)
            partial = probe.command("choose " + str(index))
            check("Flypy partial selection waits for the rest of the phrase", not partial["commit"] and bool(partial["input"]))
            _, index = find_current(probe, partial, "好")
            combined = probe.command("choose " + str(index))
            check("Flypy segmented selection commits a new phrase", combined["commit"] == "拟好")
            for schema, code in [("study_flypy", "nihc"), ("study", "nihao"), ("study_double_pinyin", "nihk")]:
                probe.command("schema " + schema)
                page, index = probe.find(code, "拟好")
                check(schema + " shares the phrase learned from Flypy segments", page["page"] == 0 and index == 0)
            probe.command("forget 0")
            probe.command("schema study_flypy")
            page = probe.command("type nihc")
            check("forgetting the new phrase in natural double pinyin also affects Flypy", page["candidates"][0]["text"] != "拟好")
        finally:
            probe.close()

    def run(command, *, env=None, timeout=55):
        result = subprocess.run([str(arg) for arg in command], cwd=ROOT, env=env, timeout=timeout,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(Path(command[0]).name + " exited " + str(result.returncode) + ": " +
                               result.stdout.decode("utf-8", errors="replace")[-5000:])
        return result

    def ipc_run(user, mode):
        env = {**os.environ, "STUDYIME_DEV_SESSION": uuid.uuid4().hex, "STUDYIME_DEV_DATA_ROOT": str(user)}
        service = package / "bin/StudyIME.Service.exe"
        result_file = work / (mode + "-ipc.json")
        try:
            old_settings = (user / "settings.ini").read_bytes() if mode == "upgrade" else None
            old_template = (user / "rime/default.custom.yaml").read_bytes() if mode == "upgrade" else None
            run([service, "--prepare-data"], env=env)
            if mode == "upgrade":
                check("deployment preserves the old settings bytes", (user / "settings.ini").read_bytes() == old_settings)
                check("deployment preserves the old single-schema user customization", (user / "rime/default.custom.yaml").read_bytes() == old_template)
                check("the old full-pinyin schema deploys both new prisms through dependencies",
                      all((user / "rime/build" / (schema + ".prism.bin")).exists() for schema in SCHEMAS))
            run([service, "--ensure-running"], env=env)
            result = run([CACHE / "build/bin/StudyIME.DoublePinyinProbe.exe", result_file, mode], env=env)
            print(result.stdout.decode("utf-8", errors="replace"), end="", flush=True)
        finally:
            run([service, "--stop"], env=env, timeout=20)
            if result_file.exists():
                report["ipc"].append({"mode": mode, **json.loads(result_file.read_bytes())})

    def ipc_checks():
        ipc_run(work / "product-user", "exercise")
        ipc_run(work / "product-user", "restart")
        legacy = args.legacy_package.resolve()
        upgrade = work / "upgrade-user"
        old_rime = upgrade / "rime"
        shutil.copytree(legacy / "data/user-template", old_rime)
        custom = old_rime / "study.custom.yaml"
        custom.write_bytes(b"patch:\n  translator/enable_user_dict: true\n")
        probe = EngineProbe(executable, legacy / "bin/rime.dll", legacy / "data/shared", old_rime)
        try:
            probe.receive(timeout=55)
            _, index = probe.find("shijian", "实践")
            probe.command("choose " + str(index))
            page, index = probe.find("shijian", "实践")
            check("the unmodified dev.2 engine seeds an old learned record", page["page"] == 0 and index == 0)
        finally:
            probe.close()
        custom.unlink()
        probe = EngineProbe(executable, legacy / "bin/rime.dll", legacy / "data/shared", old_rime)
        try:
            probe.receive(timeout=55)
            compiled = (old_rime / "build/study.schema.yaml").read_text(encoding="utf-8")
            check("upgrade starts with the actual old compiled schema", "enable_user_dict: false" in compiled)
        finally:
            probe.close()
        (upgrade / "settings.ini").write_bytes(b"version=1\nlearning=0\nlarge_text=1\nreduce_motion=0\ntheme=dark\nshortcut=alt_enter\n")
        marker = old_rime / "keep-user-file.txt"
        marker.write_bytes(b"existing user file\n")
        ipc_run(upgrade, "upgrade")
        check("the input-scheme upgrade preserves unrelated user files", marker.read_bytes() == b"existing user file\n")

    failure = None
    try:
        if args.section in ["engine", "all"]:
            engine_checks()
        if args.section in ["ipc", "all"]:
            ipc_checks()
    except Exception as error:
        failure = str(error)
    all_checks = report["checks"] + [item for group in report["ipc"] for item in group["checks"]]
    word_checks = [item for group in report["word_regressions"].values() for item in group]
    report.update({"error": failure, "check_count": len(all_checks), "word_regression_count": len(word_checks),
                   "passed": failure is None and bool(all_checks) and all(item["passed"] for item in all_checks + word_checks)})
    write_changed(ROOT / "experiments/phase6/results" / ("double-pinyin-" + args.section + ".json"), json_bytes(report))
    print(json.dumps({key: report[key] for key in ["passed", "check_count", "word_regression_count", "error"]}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
