"""Verify native word learning, product controls and a dev.2 user-data upgrade.

All input is synthetic and every mutable path is below a new verification
directory. No registration, installed service or normal user data is touched.
"""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.packaging.common import ROOT, CACHE, file_hash, json_bytes, write_changed
from tools.packaging.engine_client import EngineProbe
from tools.packaging.package import payload, stage


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-package", type=Path, default=CACHE / "stage/StudyIME-0.5.0-dev.2")
    args = parser.parse_args()
    files, manifest = payload()
    work = CACHE / "verification" / ("frequency-" + uuid.uuid4().hex)
    package = work / "product 中文"
    stage(files, package)
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(),
              "product_version": manifest["product"]["version"],
              "scope": "Isolated real product IPC and Rime C API; synthetic input; no installed TSF or physical input",
              "work_directory": work.relative_to(ROOT).as_posix(), "checks": [], "ipc": [],
              "native_build_sha256": file_hash(CACHE / "build/native-build.json"),
              "rime_dll_sha256": file_hash(package / "bin/rime.dll"),
              "frequency_probe_sha256": file_hash(CACHE / "build/bin/StudyIME.FrequencyProbe.exe"),
              "engine_probe_sha256": file_hash(CACHE / "build/bin/StudyIME.EngineProbe.exe")}

    def check(name, passed, **detail):
        report["checks"].append({"name": name, "passed": bool(passed), **detail})
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            raise AssertionError(name)

    def run(args, *, env=None, timeout=55):
        result = subprocess.run([str(arg) for arg in args], cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"{Path(args[0]).name} exited {result.returncode}: " +
                               result.stdout.decode("utf-8", errors="replace")[-5000:])
        return result

    def ipc_run(user, mode):
        env = {**os.environ, "STUDYIME_DEV_SESSION": uuid.uuid4().hex,
               "STUDYIME_DEV_DATA_ROOT": str(user)}
        service = package / "bin/StudyIME.Service.exe"
        result_file = work / (mode + "-ipc.json")
        try:
            run([service, "--prepare-data"], env=env)
            run([service, "--ensure-running"], env=env)
            result = run([CACHE / "build/bin/StudyIME.FrequencyProbe.exe", result_file, mode], env=env)
            print(result.stdout.decode("utf-8", errors="replace"), end="", flush=True)
        finally:
            run([service, "--stop"], env=env, timeout=20)
            if result_file.exists():
                report["ipc"].append({"mode": mode, **json.loads(result_file.read_text(encoding="utf-8"))})

    def find_current(probe, word, current=None):
        current = current or probe.command("key 0 0")
        for _ in range(80):
            for index, item in enumerate(current["candidates"]):
                if item["text"] == word:
                    return current, index
            if current["last"]:
                break
            current = probe.command("key 65366 0")
        raise AssertionError("Missing synthetic segment: " + word)

    def segmented(probe):
        probe.command("clear")
        page = probe.command("type nihao")
        page, index = find_current(probe, "拟", page)
        partial = probe.command("choose " + str(index))
        if partial["commit"]:
            raise AssertionError("Segmented fixture committed too early")
        page, index = find_current(probe, "好", partial)
        return probe.command("choose " + str(index))

    failure = None
    try:
        user = work / "engine-user"
        shutil.copytree(package / "data/user-template", user)
        probe = EngineProbe(CACHE / "build/bin/StudyIME.EngineProbe.exe", package / "bin/rime.dll", package / "data/shared", user)
        try:
            report["engine_startup"] = probe.receive(timeout=55)
            before = probe.command("type nihao")
            check("synthetic new phrase is not initially preferred", before["candidates"][0]["text"] != "拟好")
            committed = segmented(probe)
            check("segmented selection commits the complete new phrase", committed["commit"] == "拟好", actual=committed["commit"])
            page, index = probe.find("nihao", "拟好")
            check("native user dictionary learns a segmented phrase", page["page"] == 0 and index == 0)
            probe.command("forget " + str(index))
            probe.command("clear")
            page = probe.command("type nihao")
            check("forgetting removes a learned phrase from first place", page["candidates"][0]["text"] != "拟好")
            probe.command("user_learning 0")
            committed = segmented(probe)
            probe.command("clear")
            page = probe.command("type nihao")
            check("paused segmented input still commits without relearning", committed["commit"] == "拟好" and page["candidates"][0]["text"] != "拟好")
            probe.command("user_learning 1")
            page, index = find_current(probe, "拟", page)
            probe.command("choose " + str(index))
            probe.command("key 65307 0")
            probe.command("clear")
            page = probe.command("type nihao")
            check("cancelled partial selection does not teach a phrase", page["candidates"][0]["text"] != "拟好")

            page, index = probe.find("tongyi", "同意")
            old_rank = page["page"] * 5 + index
            probe.command("highlight " + str(index))
            committed = probe.command("key 65293 5")
            page, index = probe.find("tongyi", "同意")
            check("English shortcut does not train the supplying Chinese word", committed["action"] == "english-committed" and committed["commit"] != "同意" and page["page"] * 5 + index == old_rank)

            probe.command("clear")
            probe.command("type shishi")
            page = probe.command("key 65366 0")
            index, target = next((i, item["text"]) for i, item in enumerate(page["candidates"]) if len(item["text"]) == 2)
            committed = probe.command("choose " + str(index))
            page, index = probe.find("shishi", target)
            check("selection beyond the first page also learns", committed["commit"] == target and page["page"] == 0 and index == 0, target=target)
        finally:
            probe.close()

        live_user = work / "product-user"
        ipc_run(live_user, "exercise")
        ipc_run(live_user, "restart")

        # Reproduce a dev.2 data directory, including its old compiled schema.
        # A temporary opt-in seeds a learned record using the unmodified old DLL.
        legacy = args.legacy_package.resolve()
        if not (legacy / "bin/rime.dll").exists():
            raise RuntimeError("The recorded dev.2 package is required for this upgrade test")
        upgrade_user = work / "upgrade-user"
        old_rime = upgrade_user / "rime"
        shutil.copytree(legacy / "data/user-template", old_rime)
        custom = old_rime / "study.custom.yaml"
        custom.write_text("patch:\n  translator/enable_user_dict: true\n", encoding="utf-8")
        probe = EngineProbe(CACHE / "build/bin/StudyIME.EngineProbe.exe", legacy / "bin/rime.dll", legacy / "data/shared", old_rime)
        try:
            probe.receive(timeout=55)
            page, index = probe.find("shijian", "实践")
            probe.command("choose " + str(index))
            page, index = probe.find("shijian", "实践")
            check("legacy engine seeded the upgrade fixture", page["page"] == 0 and index == 0)
        finally:
            probe.close()
        custom.unlink()
        # Recompile the real old default (learning disabled) while keeping the
        # seeded user database. Merely leaving the opt-in build here could hide
        # an upgrade that failed to deploy the new shared schema.
        probe = EngineProbe(CACHE / "build/bin/StudyIME.EngineProbe.exe", legacy / "bin/rime.dll", legacy / "data/shared", old_rime)
        try:
            probe.receive(timeout=55)
            page, index = probe.find("shijian", "实践")
            check("legacy compiled schema really has learning disabled", page["page"] * 5 + index + 1 == 3)
        finally:
            probe.close()
        legacy_settings = "version=1\nlearning=0\nlarge_text=1\nreduce_motion=0\ntheme=dark\nshortcut=alt_enter\n"
        (upgrade_user / "settings.ini").write_text(legacy_settings, encoding="utf-8")
        legacy_settings_bytes = (upgrade_user / "settings.ini").read_bytes()
        marker = old_rime / "user-kept.txt"
        marker.write_text("keep this existing user file\n", encoding="utf-8")
        ipc_run(upgrade_user, "upgrade")
        check("upgrade preserves the settings file byte for byte", (upgrade_user / "settings.ini").read_bytes() == legacy_settings_bytes)
        check("upgrade preserves unrelated files in the user directory", marker.read_text(encoding="utf-8") == "keep this existing user file\n")
        compiled = (old_rime / "build/study.schema.yaml").read_text(encoding="utf-8")
        check("upgrade redeploys the enabled schema", "enable_user_dict: true" in compiled and "0.5.1" in compiled)
    except Exception as error:
        failure = str(error)
    report["error"] = failure
    all_checks = report["checks"] + [item for group in report["ipc"] for item in group["checks"]]
    report["passed"] = failure is None and bool(all_checks) and all(item["passed"] for item in all_checks)
    report["check_count"] = len(all_checks)
    write_changed(ROOT / "experiments/phase6/results/word-frequency.json", json_bytes(report))
    print(json.dumps({"passed": report["passed"], "checks": len(all_checks), "error": failure}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
