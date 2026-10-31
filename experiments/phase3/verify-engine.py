"""Exercise the actual DLL via the standalone host; only synthetic test input."""
from pathlib import Path
import json
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)
checks = []


class Probe:
    def __init__(self, user=HERE / "runtime/user"):
        self.stderr = (user / "probe-stderr.txt").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(HERE / "build/engine_probe.exe"), str(ROOT / ".cache/weasel-0.17.4/rime.dll"),
             str(HERE / "runtime/shared"), str(user), "study"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.version = self.read()

    def read(self):
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"Probe terminated: {self.process.poll()}; inspect isolated stderr")
        return json.loads(line)

    def command(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        return self.read()

    def start(self, text, schema="study"):
        self.command("schema " + schema)
        self.command("clear")
        return self.command("type " + text)

    def close(self):
        self.process.stdin.write("quit\n")
        self.process.stdin.flush()
        self.process.wait(timeout=15)
        self.stderr.close()
        if self.process.returncode:
            raise RuntimeError(f"Probe exit {self.process.returncode}")


def check(name, passed, evidence):
    checks.append({"name": name, "passed": bool(passed), "evidence": evidence})


p = Probe()
version = p.version
check("bundled DLL and Lua load", version["version"] == "1.13.1" and version["lua_module"], version)
base = p.start("pingguo", "study_base")
on = p.start("pingguo")
check("real simplified candidates retain order", [c["text"] for c in base["candidates"]] == [c["text"] for c in on["candidates"]], {"base": base, "learning": on})
check("exact local definition", on["candidates"][0] == {"text": "苹果", "comment": "apple"}, on)
off = p.command("key 65477 0")  # F8, experiment toggle only.
check("mid-composition toggle restores original comments", off["input"] == "pingguo" and off["candidates"] == base["candidates"], off)
blocked = p.command("key 65293 5")
check("disabled English consumes key without committing", blocked["commit"] == "" and blocked["input"] == "pingguo" and blocked["action"] == "disabled", blocked)
zh = p.command("key 32 0")
check("Chinese space commit while disabled", zh["commit"] == "苹果", zh)
p.start("pingguo")
p.command("option learning_mode 1")
en = p.command("key 65293 5")
check("Ctrl Shift Enter commits full English", en["commit"] == "apple" and en["input"] == "", en)
repeat = p.command("key 65293 5")
check("repeated English action cannot duplicate commit", repeat["commit"] == "", repeat)
p.start("pingguo")
p.command("highlight 1")
missing = p.command("key 65293 5")
check("missing definition preserves composition", missing["commit"] == "" and missing["input"] == "pingguo" and missing["action"] == "no-definition", missing)
missing_zh = p.command("key 32 0")
check("missing definition remains selectable in Chinese", missing_zh["commit"] == "平果", missing_zh)
long = p.start("zhishichanquan")
full = p.command("key 65293 5")
check("long English commits untruncated", full["commit"] == "intellectual property rights", {"page": long, "commit": full})
first = p.start("shishi")
second = p.command("key 65366 0")
p.command("highlight 1")
paged = p.command("snapshot")
selected = paged["candidates"][paged["selected"]]["text"] if paged["candidates"] else None
selected_zh = p.command("key 32 0")
check("page selection uses current page", second["page"] == 1 and selected_zh["commit"] == selected, {"first": first, "second": second, "highlight": paged, "commit": selected_zh})
p.start("shishi")
english_page = p.command("key 65366 0")
english_commit = p.command("key 65293 5")
check("English submission after paging uses new page", english_page["page"] == 1 and english_page["candidates"][0] == {"text": "适时", "comment": "at the right time"} and english_commit["commit"] == "at the right time", {"page": english_page, "commit": english_commit})
partial = p.start("pingguoyinhang")
partial_index = next(i for i,c in enumerate(partial["candidates"]) if c["text"] == "苹果")
p.command("highlight " + str(partial_index))
partial_en = p.command("key 65293 5")
check("partial English blocked without lost input", partial_en["commit"] == "" and partial_en["input"] == "pingguoyinhang" and partial_en["action"] == "partial-composition", {"before": partial, "after": partial_en})
partial_zh = p.command("key 32 0")
check("partial Chinese selection keeps remainder", bool(partial_zh["input"]) and partial_zh["commit"] == "", partial_zh)
completed_zh = p.command("key 32 0")
check("remaining segment can complete normally", completed_zh["commit"] == "苹果银行", completed_zh)
perf = {}
for schema, enabled, name in [("study_base", 0, "baseline"), ("study", 0, "learning_off"), ("study", 1, "learning_on")]:
    p.command("schema " + schema)
    p.command("option learning_mode " + str(enabled))
    perf[name] = p.command("bench 300")
p.close()

for mode in ("missing", "malformed"):
    isolated = HERE / "runtime" / (mode + "-user")
    shutil.copytree(HERE / "runtime/user", isolated, dirs_exist_ok=True)
    lexicon = isolated / "lua/lexicon.lua"
    if mode == "missing":
        lexicon.unlink(missing_ok=True)
    else:
        lexicon.write_text("this is deliberately invalid lua !!!", encoding="utf-8")
    bad = Probe(isolated)
    candidates = bad.start("pingguo")
    committed = bad.command("key 32 0")
    check(mode + " data fails open for Chinese", candidates["load"] == "missing" and candidates["candidates"][0]["text"] == "苹果" and committed["commit"] == "苹果", {"candidates": candidates, "commit": committed})
    bad.close()

report = {"scope": "actual extracted Weasel 0.17.4 x86 DLL, isolated synthetic input only", "version": version,
          "checks": checks, "performance": perf,
          "limitations": ["21 test-only pairs; not a production dictionary", "timings include decoding plus first-page materialization, not isolated lookup time", "not TSF or application compatibility tests"]}
(RESULTS / "engine.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
for item in checks:
    print(("PASS " if item["passed"] else "FAIL ") + item["name"])
print(json.dumps(perf, ensure_ascii=False))
raise SystemExit(0 if all(c["passed"] for c in checks) else 1)
