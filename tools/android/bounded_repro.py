"""Bound continuous-uptime reproduction using fixed, normally installed APKs."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.build import input_hashes
from tools.android.common import CACHE, ROOT, digest, json_write, safe, write
from tools.android.profile_performance import environment
from tools.android.run_device_checks import installed_apk, test
from tools.android.runtime_evidence import RuntimeCapture


def reproduce(serial, expected_avd, apk_directory, output, rounds=8, minutes=25):
    if not 1 <= rounds <= 12 or not 1 <= minutes <= 60:
        raise ValueError("Use 1-12 rounds and a 1-60 minute active-work limit")
    initial = environment(serial, expected_avd)
    if "reason=cmdline" in initial["releaseDexopt"]:
        raise ValueError("This reproduction requires normal installation compiler state")
    output = safe(output)
    output.mkdir(parents=True, exist_ok=False)
    apks, observed = {}, []
    for package in ("org.studyime.android", "org.studyime.android.debug", "org.studyime.android.debug.test"):
        source = apk_directory / (package + ".apk")
        identity = installed_apk(serial, package, source)
        destination = output / source.name
        shutil.copy2(source, destination)
        if digest(destination) != identity["sha256"]:
            raise RuntimeError("APK changed during freeze")
        apks[package] = destination
        observed.append(identity)
    for variant in ("release", "debug"):
        source = apk_directory / ("assembly-" + variant + ".json")
        receipt = json.loads(source.read_text(encoding="utf-8-sig"))
        package = "org.studyime.android" + (".debug" if variant == "debug" else "")
        if not receipt["inputsUnchangedDuringBuild"] or receipt["apkSha256"] != digest(apks[package]):
            raise ValueError("Frozen APK has no matching successful assembly receipt")
        shutil.copy2(source, output / source.name)
    inputs = input_hashes()
    for path in (ROOT / "tools/android").glob("*.py"):
        write(output / "harness" / path.name, path.read_bytes())
    report = {"startedAt": datetime.now(timezone.utc).isoformat(), "hypothesis": "Failure incidence increases with uninterrupted IME/device uptime",
              "onlyVariedFactor": "Cumulative repetitions and elapsed uptime; same APKs, editor, sequence and installation",
              "limits": {"rounds": rounds, "activeMinutes": minutes}, "installedApks": observed,
              "gitHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "harnessInputs": inputs, "environmentBefore": initial, "rounds": [], "completed": False,
              "historicalCrashRootCause": "unconfirmed", "outcome": "incomplete"}
    json_write(output / "reproduction.json", report)
    runtime = RuntimeCapture(serial, output / "runtime", "org.studyime.android", require_ime_continuity=True)
    started = time.monotonic()
    try:
        with runtime:
            started = time.monotonic()
            for index in range(rounds):
                remaining = minutes * 60 - (time.monotonic() - started)
                completed = report["rounds"]
                durations = [row["elapsedSeconds"] - (completed[i - 1]["elapsedSeconds"] if i else 0)
                             for i, row in enumerate(completed)]
                # Do not begin a round that cannot fit the durations already
                # observed. Keep the hard per-command timeout as a backstop.
                if remaining <= 0 or (durations and remaining < max(durations[-3:]) + 15):
                    report["stopReason"] = "active-time-limit"
                    break
                attempt_started = datetime.now(timezone.utc)
                print(f"Bounded uptime round {index + 1}/{rounds}; elapsed {time.monotonic() - started:.1f}s", flush=True)
                try:
                    value = test("performance", serial, "org.studyime.android", apks=apks, timeout=min(1200, remaining), capture_runtime=True)
                finally:
                    source = CACHE / "evidence/release-performance-report.json"
                    if source.is_file():
                        value = json.loads(source.read_text(encoding="utf-8"))
                        if datetime.fromisoformat(value["run"]["startedAt"]) >= attempt_started:
                            json_write(output / f"round-{index + 1:02d}.json", value)
                            report["rounds"].append({"file": f"round-{index + 1:02d}.json", "passed": value["passed"],
                                "assessment": value.get("performanceAssessment"), "initialImePid": value.get("initialImePid"),
                                "finalImePid": value.get("finalImePid"), "elapsedSeconds": time.monotonic() - started,
                                "runtimeDirectory": value["runtimeEvidence"]["directory"]})
                            json_write(output / "reproduction.json", report)
                if len(report["rounds"]) > 1 and report["rounds"][-2]["finalImePid"] != value["initialImePid"]:
                    raise RuntimeError("IME replaced between uptime rounds")
            report["observedInstalledApksAfter"] = [installed_apk(serial, item["package"], sha256=item["sha256"]) for item in observed]
            report["environmentAfter"] = environment(serial, expected_avd)
            if inputs != input_hashes():
                raise RuntimeError("Source/harness inputs changed during reproduction")
        report["completed"] = runtime.summary["passed"] and all(row["passed"] for row in report["rounds"])
        report["outcome"] = "not-reproduced" if report["completed"] else "runtime-or-capture-failure"
    except BaseException as error:
        report["failure"] = str(error)
        report["outcome"] = "failure-preserved-before-retry"
        raise
    finally:
        report["elapsedSeconds"] = time.monotonic() - started
        report["finishedAt"] = datetime.now(timezone.utc).isoformat()
        report["runtimeEvidence"] = runtime.summary
        report["exactCoverage"] = {"completedRounds": sum(row["passed"] for row in report["rounds"]),
            "deliveredKeys": 180 * sum(row.get("assessment", {}).get("coverageComplete", False) for row in report["rounds"]),
            "readyReopens": 20 * sum(row.get("assessment", {}).get("coverageComplete", False) for row in report["rounds"])}
        json_write(output / "reproduction.json", report)
    print(json.dumps({key: report[key] for key in ("outcome", "exactCoverage", "elapsedSeconds")}), flush=True)
    if not report["completed"]:
        raise RuntimeError("Reproduction did not finish with complete evidence")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--expected-avd", required=True)
    parser.add_argument("--apk-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--minutes", type=int, default=25)
    args = parser.parse_args()
    reproduce(args.serial, args.expected_avd, args.apk_directory, args.output, args.rounds, args.minutes)
