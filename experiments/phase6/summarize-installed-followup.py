"""Assemble recorded desktop/uninstall evidence without synthesizing new input."""
from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/phase6/results/installed-desktop-followup-20261108"
RAW = ROOT / ".cache/packaging/installed-evidence/raw-registry-20261108"


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    baseline = read(RAW / "before-install.json")
    before = read(RAW / "before-final-uninstall.json")
    final_checkpoint = RAW / "after-final-checks-before-restart.json"
    after = read(final_checkpoint if final_checkpoint.exists() else RAW / "after-empty-tip-cleanup.json")
    checkpoints = ["before-final-uninstall", "after-uninstall-in-use", "after-empty-tip-cleanup"]
    if final_checkpoint.exists():
        checkpoints.append(final_checkpoint.stem)
    for name in checkpoints:
        original = RAW / (name + ".json")
        projected = copy.deepcopy(read(original))
        for key in ("machine_tips_x64", "machine_tips_x86"):
            projected["registry"][key].pop("tree", None)
        projected["raw_snapshot"] = {"path": original.relative_to(ROOT).as_posix(), "sha256": digest(original)}
        write(RESULTS / (name + ".json"), projected)
    differences = sorted(key for key in baseline["registry"] if baseline["registry"][key] != after["registry"][key])
    assert differences == ["study_app"], differences
    assert baseline["input_settings"] == after["input_settings"]
    assert before["normal_data_files"] == after["normal_data_files"]
    assert after["receipt"]["status"] == "cleanup-pending" and not after["receipt"]["registered"]
    record = read(RESULTS / "apps-session.json")
    saved = {}
    for app in ("notepad", "vscode"):
        original = Path(record["work"]) / ("StudyIME-" + app + "-acceptance.txt")
        destination = RESULTS / (app + "-final-saved.txt")
        shutil.copyfile(original, destination)
        saved[app] = {"path": destination.name, "sha256": digest(destination), "text": destination.read_text(encoding="utf-8-sig")}
    assert saved["notepad"]["text"] == "你好"
    assert saved["vscode"]["text"].splitlines()[0] == "你好hello你好你好"
    assert "".join(saved["vscode"]["text"].splitlines()[1:]).strip() == "你好"
    observations = [json.loads(line) for line in (RESULTS / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
    ids = {item["id"] for item in observations}
    required = {"vscode-hover", "vscode-ordinary-english-row", "vscode-f2", "vscode-english-shortcut",
                "vscode-repeat-protection", "cross-app-stale-action", "vscode-focus-return", "disconnect-cleared",
                "disconnect-stale-shortcut", "disconnect-reconnected-commit", "display-125-click", "display-restored",
                "page-rapid-input", "right-edge-candidates", "bottom-edge-definition", "bottom-edge-click"}
    assert required <= ids
    screenshots = {}
    for item in observations:
        for name in item["screenshots"]:
            path = (RESULTS / name).resolve()
            assert path.is_relative_to(RESULTS.resolve()) and path.is_file()
            screenshots[name] = digest(path)
    package = read(ROOT / "experiments/phase6/results/source-uninstall-update-20261108/summary.json")
    assert package["status"] == "passed" and package["reproduced_runtime_identical"]
    remaining = {p.relative_to(Path(after["target"])).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size}
                 for p in Path(after["target"]).rglob("*") if p.is_file()}
    assert remaining["bin/StudyIME.TSF.x64.dll"]["sha256"] == record["installed_input_hashes"]["bin/StudyIME.TSF.x64.dll"]
    browser = read(RESULTS / "browser-status.json")
    references = read(RESULTS / "loaded-modules-after-retry.json")
    services = read(RESULTS / "isolated-service-cleanup.json")
    assert all(item["exit_code"] == 0 for item in services)
    result = {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "status": "recorded_with_deferred_cleanup",
        "scope": "Installed dev.2 desktop observations and actual unregister/cleanup attempts; browser input skipped by user.",
        "observations": len(observations), "required_observation_ids": sorted(required), "screenshots": screenshots,
        "saved_documents": saved, "browser": browser,
        "multi_monitor": {"status": "not_tested", "attached_displays": len(read(RESULTS / "display-inventory.json"))},
        "animation_timing": "Sequential native input and page-return/input were observed; no frame-by-frame timing proof.",
        "display_scale_restored_percent": 150, "normal_user_data_files_unchanged": True,
        "default_and_language_settings_match_pre_install": True,
        "input_registry_trees_match_pre_install": True, "remaining_registry_difference": differences,
        "registered": False, "uninstall_complete": False, "receipt_status": "cleanup-pending",
        "remaining_installation_files": remaining, "dll_reference_processes": references,
        "initial_uninstall": read(RESULTS / "uninstall-in-use/uninstall-result.json"),
        "empty_tip_cleanup_and_retry": read(RESULTS / "empty-tip-cleanup/empty-tip-cleanup.json"),
        "test_cleanup": {"isolated_services_stopped": services, "all_studyime_services_observed_stopped": True,
                         "test_vscode_window_closed": True, "test_notepad_tab_closed": True,
                         "other_notepad_documents_preserved": True, "local_http_server_stopped": True,
                         "evidence": "Native Computer Use window observations and process/HTTP-server checks in this chat."},
        "package_update": package,
        "next_step": "Save work and restart Windows to release the mapped DLL, then run the validated installed Uninstall.ps1 with -Apply -AllowDevelopment in an elevated 64-bit PowerShell. Capture final state and require the app-list entry and installation directory to be absent."
    }
    write(RESULTS / "summary.json", result)
    print(json.dumps({"observations": len(observations), "screenshots": len(screenshots), "registered": False,
                      "uninstall_complete": False, "input_registry_restored": True, "user_data_unchanged": True}))


if __name__ == "__main__":
    main()
