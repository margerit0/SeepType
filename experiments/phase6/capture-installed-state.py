"""Read-only installation checkpoints; does not register or activate a TIP."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import winreg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.packaging.common import file_hash, json_bytes, product

CLASS = "{FEB10355-3C08-5342-B75C-5873F1CA04DF}"
PRODUCT = "{D89859C5-5A51-53E6-8199-DF3407D2908B}"
WEASEL = "{A3F4CDED-B1E9-41EE-9CA6-7B4D0DE6CB0A}"


def registry_tree(hive, path, view=winreg.KEY_WOW64_64KEY):
    def read(key):
        subkeys, values, _ = winreg.QueryInfoKey(key)
        result = {"values": [], "children": {}}
        for index in range(values):
            name, value, kind = winreg.EnumValue(key, index)
            if isinstance(value, bytes):
                value = {"binary_hex": value.hex()}
            result["values"].append([name, value, kind])
        result["values"].sort(key=lambda item: item[0].casefold())
        for name in sorted(winreg.EnumKey(key, i) for i in range(subkeys)):
            with winreg.OpenKey(key, name, 0, winreg.KEY_READ | view) as child:
                result["children"][name] = read(child)
        return result
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as key:
            tree = read(key)
        return {"exists": True, "sha256": hashlib.sha256(json_bytes(tree)).hexdigest(), "tree": tree}
    except FileNotFoundError:
        return {"exists": False}


def snapshot():
    package = ROOT / ".cache/packaging/stage" / ("StudyIME-" + product()["version"])
    target = Path(os.environ["ProgramFiles"]) / "StudyIME" / product()["version"]
    normal = Path(os.environ["LOCALAPPDATA"]) / "StudyIME"
    registry = {}
    for name, hive, path, view in [
        ("study_class", winreg.HKEY_LOCAL_MACHINE, rf"Software\Classes\CLSID\{CLASS}", winreg.KEY_WOW64_64KEY),
        ("study_machine_tip", winreg.HKEY_LOCAL_MACHINE, rf"Software\Microsoft\CTF\TIP\{CLASS}", winreg.KEY_WOW64_64KEY),
        ("study_user_tip", winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\CTF\TIP\{CLASS}", winreg.KEY_WOW64_64KEY),
        ("study_app", winreg.HKEY_LOCAL_MACHINE, rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{PRODUCT}", winreg.KEY_WOW64_64KEY),
        ("study_user", winreg.HKEY_CURRENT_USER, r"Software\StudyIME", winreg.KEY_WOW64_64KEY),
        ("keyboard_preload", winreg.HKEY_CURRENT_USER, r"Keyboard Layout\Preload", winreg.KEY_WOW64_64KEY),
        ("keyboard_substitutes", winreg.HKEY_CURRENT_USER, r"Keyboard Layout\Substitutes", winreg.KEY_WOW64_64KEY),
        ("weasel_class", winreg.HKEY_LOCAL_MACHINE, rf"Software\Classes\CLSID\{WEASEL}", winreg.KEY_WOW64_64KEY),
        ("weasel_machine_tip", winreg.HKEY_LOCAL_MACHINE, rf"Software\Microsoft\CTF\TIP\{WEASEL}", winreg.KEY_WOW64_64KEY),
        ("weasel_machine", winreg.HKEY_LOCAL_MACHINE, r"Software\Rime\Weasel", winreg.KEY_WOW64_64KEY),
        ("weasel_user", winreg.HKEY_CURRENT_USER, r"Software\Rime\Weasel", winreg.KEY_WOW64_64KEY),
        ("machine_tips_x64", winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\CTF\TIP", winreg.KEY_WOW64_64KEY),
        ("machine_tips_x86", winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\CTF\TIP", winreg.KEY_WOW64_32KEY),
    ]:
        registry[name] = registry_tree(hive, path, view)
    ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); $languageItems = Get-WinUserLanguageList; $languageState = @(foreach ($languageItem in $languageItems) { [ordered]@{ LanguageTag = $languageItem.LanguageTag; InputMethodTips = @($languageItem.InputMethodTips) } }); [ordered]@{ default_override = Get-WinDefaultInputMethodOverride; languages = $languageState } | ConvertTo-Json -Depth 6 -Compress"
    state = subprocess.run([str(ps), "-NoProfile", "-NonInteractive", "-Command", command],
                           capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    receipt = target / "install-receipt.json"
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "package": str(package), "package_manifest_sha256": file_hash(package / "package-manifest.json"),
        "target": str(target), "target_exists": target.exists(),
        "installed_binaries": {p.name: file_hash(p) for p in sorted((target / "bin").glob("*")) if p.is_file()},
        "receipt": json.loads(receipt.read_text(encoding="utf-8-sig")) if receipt.exists() else None,
        "normal_data_root": str(normal), "normal_data_exists": normal.exists(),
        "normal_data_files": {p.relative_to(normal).as_posix(): file_hash(p) for p in sorted(normal.rglob("*")) if p.is_file()},
        "input_settings": json.loads(state.stdout.decode("utf-8-sig")), "registry": registry,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json_bytes(result))
    print(json.dumps({"output": str(args.output), "target_exists": result["target_exists"],
                      "receipt": result["receipt"], "input_settings": result["input_settings"]}, ensure_ascii=False))
