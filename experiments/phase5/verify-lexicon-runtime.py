"""Check all proposed words through the actual x64 Rime/Lua engine, without UI."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tools.lexicon import pipeline as lex

sys.stdout.reconfigure(encoding="utf-8")
data = lex.validate()
files = lex.build_files(data, "preview")
RUNTIME = HERE / "runtime" / data.content_hash[:16]
SHARED, USER = RUNTIME / "shared", RUNTIME / "user"
EXE = HERE / "build/engine_probe_x64.exe"
DLL = ROOT / ".cache/rime-1.13.1/dist/lib/rime.dll"
RUNTIME.mkdir(parents=True, exist_ok=True)
shutil.copytree(ROOT / ".cache/weasel-0.17.4/data", SHARED, dirs_exist_ok=True)
(USER / "lua").mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / "experiments/phase3/fixtures/study.schema.yaml", USER / "study.schema.yaml")
shutil.copy2(ROOT / "src/study/lua/study_core.lua", USER / "lua/study_core.lua")
lex.atomic_write(USER / "lua/lexicon.lua", files["lexicon.lua"])
lex.atomic_write(USER / "rime.lua", b'local core = require("study_core")\nstudy_filter = core.filter\nstudy_keys = core.keys\n')
lex.atomic_write(USER / "default.custom.yaml", b"patch:\n  schema_list:\n    - {schema: study}\n")


class Probe:
    def __init__(self):
        self.output = queue.Queue()
        self.error_log = (RUNTIME / "engine.log").open("wb")
        self.process = subprocess.Popen([str(EXE), str(DLL), str(SHARED), str(USER), "study"],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
            text=True, encoding="utf-8", bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.output.put(json.loads(line))
                except ValueError:
                    self.output.put(RuntimeError("Unexpected probe output: " + line[:300]))
        finally:
            self.output.put(None)

    def receive(self, timeout=15):
        try:
            result = self.output.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Rime probe response timed out") from None
        if result is None:
            raise RuntimeError("Rime probe exited before completing the request")
        if isinstance(result, Exception):
            raise result
        return result

    def command(self, text):
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()
        return self.receive()

    def find(self, pinyin, chinese):
        self.command("clear")
        current = self.command("type " + pinyin)
        first_page = [candidate["text"] for candidate in current["candidates"]]
        for _ in range(30):
            for index, candidate in enumerate(current["candidates"]):
                if candidate["text"] == chinese:
                    return current, index
            if current["last"]:
                break
            current = self.command("key 65366 0")
        raise ValueError(f"Expected word absent from first 30 pages; first page: {first_page}")

    def close(self):
        try:
            if self.process.poll() is None:
                self.process.stdin.write("quit\n")
                self.process.stdin.flush()
                self.process.stdin.close()
                if self.process.wait(timeout=15):
                    raise RuntimeError("Rime probe returned a nonzero exit code")
            elif self.process.returncode:
                raise RuntimeError(f"Rime probe exited {self.process.returncode}")
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.reader.join(timeout=2)
            self.process.stdout.close()
            self.error_log.close()


def pinyin_for(entry):
    value = data.sources[entry["source_entry_sha256"]]["pinyin"].lower().replace("u:", "v")
    value = re.sub(r"[1-5\s'-]", "", value)
    lex.require(re.fullmatch("[a-z]+", value), f"Unsupported pinyin: {value}")
    return value


checks, startup, failure = [], None, None
translations = {e["chinese"]: e["commit_english"] for e in data.entries}
probe = None
try:
    probe = Probe()
    startup = probe.receive(timeout=55)
    lex.require(startup["pointer_bits"] == 64 and startup["lua_module"], "Expected x64 Rime with Lua")
    for entry in data.entries:
        pinyin = pinyin_for(entry)
        item = {"id": entry["id"], "chinese": entry["chinese"], "pinyin_input": pinyin,
                "expected_english": entry["commit_english"], "passed": False}
        try:
            page, index = probe.find(pinyin, entry["chinese"])
            item["page"] = page["page"]
            item["candidate_index"] = index
            item["page_annotations_match"] = page["load"] == "ready" and all(
                candidate["comment"] == translations.get(candidate["text"], "") for candidate in page["candidates"])
            probe.command("highlight " + str(index))
            committed = probe.command("key 65293 5")
            item["english_commit_matches"] = (committed["commit"] == entry["commit_english"] and
                                              committed["input"] == "" and committed["action"] == "english-committed")
            _, index = probe.find(pinyin, entry["chinese"])
            chinese = probe.command("choose " + str(index))
            item["ordinary_chinese_preserved"] = chinese["commit"] == entry["chinese"] and chinese["input"] == ""
            item["passed"] = all(item[key] for key in
                ("page_annotations_match", "english_commit_matches", "ordinary_chinese_preserved"))
            if not item["passed"]:
                item["actual_english"] = committed["commit"]
                item["actual_chinese"] = chinese["commit"]
        except ValueError as error:
            item["error"] = str(error)
        checks.append(item)
        if not item["passed"]:
            print("FAIL " + entry["chinese"] + ": " + json.dumps(item, ensure_ascii=False), flush=True)
        elif len(checks) % 50 == 0:
            print(f"Checked {len(checks)}/{len(data.entries)} words through x64 Rime/Lua", flush=True)
except Exception as error:
    failure = str(error)
finally:
    if probe:
        try:
            probe.close()
        except Exception as error:
            failure = failure or str(error)

paths = [Path(__file__), HERE / "build-probe.cmd", ROOT / "experiments/phase3/engine_probe.cpp",
         ROOT / "experiments/phase3/fixtures/study.schema.yaml", ROOT / "src/study/lua/study_core.lua",
         Path(lex.__file__), lex.DATA / "entries.json", lex.DATA / "source.lock.json",
         lex.DATA / "sources/entries.json"]
report = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "scope": "Actual x64 Rime/Lua with the 200-entry REVIEW PREVIEW in a separate runtime; programmatic synthetic input only.",
          "passed": failure is None and len(checks) == len(data.entries) and all(item["passed"] for item in checks),
          "error": failure, "startup": startup, "lexicon_content_sha256": data.content_hash,
          "runtime_lua_sha256": lex.sha256(files["lexicon.lua"]),
          "review_counts": data.counts, "word_count": len(checks), "checks": checks,
          "binaries": {str(path.relative_to(ROOT)): lex.sha256(path.read_bytes()) for path in (EXE, DLL)},
          "sources": {str(path.relative_to(ROOT)): lex.sha256(path.read_bytes()) for path in paths},
          "limits": ["Proposed meanings still require human review", "No TSF, physical keyboard, browser or desktop acceptance",
                     "No system installation or input setting changes", "No large-dictionary performance claim",
                     "Phase 3/4 fixtures, runtime and previous reports are not replaced"]}
lex.atomic_write(HERE / "results/lexicon-runtime-x64.json", lex.json_bytes(report))
print(f"{sum(item['passed'] for item in checks)}/{len(data.entries)} proposed words passed.")
if failure:
    print(failure, file=sys.stderr)
raise SystemExit(0 if report["passed"] else 1)
