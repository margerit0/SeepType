"""Package a verified preview, matching source checkout, dependencies and evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.android.common import CACHE, ROOT, digest, json_write, safe, write
from tools.android.build_env import tool_env
from tools.android.build import input_hashes
from tools.android.verify_artifact import verify


REQUIRED_REPORTS = ["native-engine-report.json", "resource-recovery-report.json", "release-ime-interaction-report.json",
    "release-lifecycle-report.json", "release-performance-report.json", "release-app-editor-report.json",
    "scenario-report.json", "visual-matrix-report.json", "design-measurements.json",
    "release-preview-recording-report.json", "release-unassisted-input-report.json", "release-startup-report.json", "visual-review.json"]


def validate_evidence(apk):
    apk_hash = digest(apk)
    debug_hash = digest(ROOT / "android/app/build/outputs/apk/debug/app-debug.apk")
    test_hash = digest(ROOT / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk")
    current_inputs = input_hashes()
    for variant, expected in (("release", apk_hash), ("debug", debug_hash)):
        receipt = json.loads((CACHE / ("assembly-" + variant + ".json")).read_text(encoding="utf-8"))
        if receipt["apkSha256"] != expected or receipt["inputHashes"] != current_inputs or not receipt["inputsUnchangedDuringBuild"]:
            raise ValueError("Assemble the current unchanged sources before packaging: " + variant)
        if digest(CACHE / "logs" / receipt["log"]) != receipt["logSha256"]:
            raise ValueError("Assembly log no longer matches its receipt: " + variant)
    reports = {}
    for name in REQUIRED_REPORTS:
        path = CACHE / "evidence" / name
        value = json.loads(path.read_text(encoding="utf-8"))
        if not value.get("passed"):
            raise ValueError("Required verification has not passed: " + name)
        if name.startswith("release-"):
            if value.get("imeApkSha256") != apk_hash:
                raise ValueError("Release evidence belongs to a different installed APK: " + name)
        if name not in ("design-measurements.json", "visual-review.json", "release-unassisted-input-report.json"):
            build = value.get("installedBuild", {})
            if build.get("apkSha256") != debug_hash or build.get("testApkSha256") != test_hash:
                raise ValueError("Evidence belongs to a different debug app or test runner: " + name)
        reports[name] = {"sha256": digest(path), "imeApkSha256": value.get("imeApkSha256"),
                         "installedBuild": value.get("installedBuild"), "scope": value.get("scope")}
    performance = json.loads((CACHE / "evidence/release-performance-report.json").read_text(encoding="utf-8"))
    # These are initial measurement budgets for a development preview, not
    # functional pass flags. Preserve failures in the delivery manifest instead
    # of discarding measured results or implying production-device acceptance.
    warm = performance["warmTimings"]
    targets = {
        "candidateDrawP95Target50Ms": warm["keyToComposeDrawMs"]["p95"] <= 50,
        "candidateDrawP99Target100Ms": warm["keyToComposeDrawMs"]["p99"] <= 100,
        "warmReadyP95Target100Ms": warm["showInputViewToReadyDrawMs"]["p95"] <= 100,
    }
    if any(performance.get(name) is not result for name, result in targets.items()):
        raise ValueError("Performance target flags differ from the measured timings")
    reports["release-performance-report.json"]["initialTargets"] = targets
    startup = json.loads((CACHE / "evidence/release-startup-report.json").read_text(encoding="utf-8"))
    cold_target = startup["readyDrawMs"]["p95"] <= 500
    if startup.get("callbackColdP95Target500Ms") is not cold_target:
        raise ValueError("Startup target flag differs from the measured timing")
    reports["release-startup-report.json"]["initialTarget500Ms"] = cold_target
    recording = json.loads((CACHE / "evidence/release-preview-recording-report.json").read_text(encoding="utf-8"))
    video = recording["video"]
    if video["file"] != "recording/preview-interactions.mp4" or digest(CACHE / "evidence" / video["file"]) != video["sha256"]:
        raise ValueError("Screen recording differs from the verified interaction run")
    measurements = json.loads((CACHE / "evidence/design-measurements.json").read_text(encoding="utf-8"))
    hierarchy_hashes = {name: digest(CACHE / "evidence/visual" / name) for name in
                        ("320dp-font1.0-light-idle.xml", "320dp-font1.0-light.xml")}
    if measurements["sourceSha256"] != digest(ROOT / "android/app/src/main/java/org/studyime/android/ui/Theme.kt") or \
       measurements.get("hierarchyHashes") != hierarchy_hashes:
        raise ValueError("Design measurements do not match the current theme and visual capture")
    review = json.loads((CACHE / "evidence/visual-review.json").read_text(encoding="utf-8"))
    if review.get("debugApkSha256") != debug_hash or review.get("imeApkSha256") != apk_hash:
        raise ValueError("Visual review belongs to a different build")
    reviewed = review.get("files", {})
    visual = json.loads((CACHE / "evidence/visual-matrix-report.json").read_text(encoding="utf-8"))
    if not visual.get("captures") or any("visual/" + name not in reviewed for name in visual["captures"]):
        raise ValueError("Visual matrix captures have not all been reviewed")
    if reviewed.get(video["file"]) != video["sha256"]:
        raise ValueError("Visual review does not include the verified recording")
    for name, expected in reviewed.items():
        path = safe(CACHE / "evidence" / name)
        if not path.is_relative_to((CACHE / "evidence").resolve()) or digest(path) != expected:
            raise ValueError("Reviewed visual evidence has changed: " + name)
    unassisted = json.loads((CACHE / "evidence/release-unassisted-input-report.json").read_text(encoding="utf-8"))
    observed = {item["package"]: item["sha256"] for item in unassisted.get("observedInstalledApks", [])}
    if observed.get("org.studyime.android") != apk_hash or observed.get("org.studyime.android.debug") != debug_hash:
        raise ValueError("Unassisted input evidence belongs to different installed builds")
    for variant in ("debug", "release"):
        lint = ET.parse(ROOT / f"android/app/build/reports/lint-results-{variant}.xml")
        if any(issue.get("severity") in ("Error", "Fatal") for issue in lint.iter("issue")):
            raise ValueError("Android lint has errors: " + variant)
    tests = list((ROOT / "android/app/build/test-results/testDebugUnitTest").glob("TEST-*.xml"))
    if not tests or any(int(ET.parse(path).getroot().get(key, 0)) for path in tests for key in ("failures", "errors")):
        raise ValueError("Kotlin unit verification is missing or failed")
    if "test result: ok. 16 passed; 0 failed;" not in (CACHE / "logs/rust-policy-tests.log").read_text(encoding="utf-8"):
        raise ValueError("The 16 Rust policy regressions have not passed")
    return reports


def package():
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("Commit the reviewed source and documentation before packaging the source snapshot")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if branch != "codex/android-dev":
        raise ValueError("Preview must come from the authorized Android worktree branch")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    apk = ROOT / "android/app/build/outputs/apk/release/app-release.apk"
    verify(apk)
    apk_hash = digest(apk)
    reports = validate_evidence(apk)
    with zipfile.ZipFile(apk) as bundle:
        resources = json.loads(bundle.read("assets/generated/manifest.json"))
        for name, expected in resources["files"].items():
            if hashlib.sha256(bundle.read("assets/generated/" + name)).hexdigest() != expected:
                raise ValueError("Packaged resource hash mismatch: " + name)
    output = safe(CACHE / "delivery" / ("0.1.0-preview.1-" + head[:10]))
    output.mkdir(parents=True, exist_ok=True)
    installed = output / "StudyIME-0.1.0-preview.1-arm64-x86_64.apk"
    shutil.copy2(apk, installed)
    source = output / "StudyIME-Android-source.zip"
    subprocess.run(["git", "archive", "--format=zip", "--prefix=studyime/", "--output", str(source), head], cwd=ROOT, check=True)
    native = output / "StudyIME-native-sources.zip"
    with zipfile.ZipFile(native, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        source_root = CACHE / "src"
        for file in sorted(source_root.rglob("*")):
            if file.is_file():
                bundle.write(file, "native-sources/" + file.relative_to(source_root).as_posix())
        bundle.write(ROOT / "android/native/patches/rime-android.patch", "rime-android.patch")
        bundle.write(CACHE / "native-sources.json", "original-source-receipts.json")
    evidence = output / "StudyIME-verification.zip"
    with zipfile.ZipFile(evidence, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        evidence_root = CACHE / "evidence"
        for file in sorted(evidence_root.rglob("*")):
            relative = file.relative_to(evidence_root)
            current = relative.parts[0] in ("visual", "scenarios", "performance", "startup", "recording") or relative.as_posix() in (
                *REQUIRED_REPORTS, "apk-native-layout.json", "unassisted-input.png", "visual-review.json", "review-contact-sheet.png")
            if file.is_file() and current and file.suffix in (".json", ".xml", ".png", ".txt", ".mp4") and "failure" not in file.name:
                bundle.write(file, relative.as_posix())
        for file in (ROOT / "android/app/build/reports").glob("lint-results-*.xml"):
            bundle.write(file, "checks/" + file.name)
        for file in (ROOT / "android/app/build/test-results/testDebugUnitTest").glob("TEST-*.xml"):
            bundle.write(file, "checks/" + file.name)
        bundle.write(CACHE / "logs/rust-policy-tests.log", "checks/rust-policy-tests.log")
        for variant in ("debug", "release"):
            receipt = CACHE / ("assembly-" + variant + ".json")
            bundle.write(receipt, "checks/" + receipt.name)
            log = json.loads(receipt.read_text(encoding="utf-8"))["log"]
            if "checks/" + log not in bundle.namelist():
                bundle.write(CACHE / "logs" / log, "checks/" + log)
        bundle.writestr("verification-binding.json", json.dumps({"gitCommit": head, "apkSha256": apk_hash, "reports": reports}, ensure_ascii=False, indent=2))
    tools = CACHE / "sdk/build-tools/35.0.0"
    signatures = subprocess.check_output([str(tools / "apksigner.bat"), "verify", "--verbose", "--print-certs", str(apk)], env=tool_env(), text=True, encoding="utf-8")
    write(output / "APK-SIGNATURE.txt", signatures)
    permissions = subprocess.check_output([str(tools / "aapt.exe"), "dump", "permissions", str(apk)], text=True, encoding="utf-8")
    if "android.permission.INTERNET" in permissions:
        raise ValueError("Offline preview unexpectedly requests network access")
    write(output / "APK-PERMISSIONS.txt", permissions)
    for name in ("dependency-receipt.json", "data-receipt.json", "native-sources.json", "build-tools-receipt.json", "assembly-release.json"):
        shutil.copy2(CACHE / name, output / name)
    readme = """拾词 Android 0.1.0-preview.1

这是供本机安装和验证的开发预览，采用本地开发签名。支持的打包 ABI：arm64-v8a、x86_64；minSdk 29、targetSdk 35。
实际模拟器、测试边界、性能及未完成项见源码 docs/android-validation.md。真机、触感、高刷新率和实际 16 KB 页面设备需补验。

安装 APK 后打开「拾词」，按引导启用并切换键盘。普通点候选或按空格输入中文；长按后明确点「输入英文」才提交英文。
中文 121,505 条；英文 200 条均为待人工审核的开发数据。应用离线运行，不申请网络权限；用户词典不参与 Android 备份。

StudyIME-Android-source.zip 保存本次提交的完整项目源码、GPL-3.0-or-later 许可、锁文件和构建脚本。
StudyIME-native-sources.zip 保存实际构建使用的第三方源码（已应用 Android 补丁）及原始来源摘要。
Maven、Cargo、NDK 与工具链的版本、来源和许可随源码锁文件、dependency-receipt.json 和 APK 内 notices 分发。
按 android/README.md 的步骤可从固定输入重新构建；首次准备需要下载锁定的公开依赖，不依赖另一 Windows worktree。
StudyIME-verification.zip 包含实际运行报告、截图、交互录像及其对应构建摘要。报告中的绘制耗时不等于物理屏幕呈现延迟。
APK-SIGNATURE.txt 为公开签名信息；开发私钥不包含在这些材料中。
"""
    performance = json.loads((CACHE / "evidence/release-performance-report.json").read_text(encoding="utf-8"))
    startup = json.loads((CACHE / "evidence/release-startup-report.json").read_text(encoding="utf-8"))
    performance_summary = {
        "warmTimings": performance["warmTimings"],
        "initialWarmTargets": reports["release-performance-report.json"]["initialTargets"],
        "freshProcessReadyDrawMs": startup["readyDrawMs"],
        "initialFreshProcessTarget500Ms": startup["callbackColdP95Target500Ms"],
        "boundary": "Emulator Compose draw recording, not physical display latency; fresh-process timing starts at onStartInputView, with deployed resources and OS caches retained",
    }
    all_targets = all(performance_summary["initialWarmTargets"].values()) and performance_summary["initialFreshProcessTarget500Ms"]
    performance_summary["allInitialTargetsMet"] = all_targets
    readme += "\n性能初始目标：" + ("本次测量达到；物理设备仍需补验。" if all_targets else "尚未全部达到，需要继续优化；功能测试通过不代表性能预算通过。") + "\n"
    readme += "模拟器暖态候选绘制 p95 {:.2f} ms／p99 {:.2f} ms；新进程首次显示回调至可用绘制 p95 {:.2f} ms。\n".format(
        performance["warmTimings"]["keyToComposeDrawMs"]["p95"], performance["warmTimings"]["keyToComposeDrawMs"]["p99"], startup["readyDrawMs"]["p95"])
    write(output / "README.txt", readme)
    manifest = {"version": "0.1.0-preview.1", "gitCommit": head, "branch": branch, "apkSha256": apk_hash,
                "resourceVersion": resources["version"], "humanApprovedEnglish": resources["humanApproved"],
                "performance": performance_summary,
                "files": {file.name: {"bytes": file.stat().st_size, "sha256": digest(file)} for file in sorted(output.iterdir()) if file.is_file() and file.name != "manifest.json"}}
    json_write(output / "manifest.json", manifest)
    json_write(CACHE / "delivery-latest.json", {"directory": str(output), "manifest": manifest})
    print(json.dumps({"directory": str(output), "gitCommit": head, "apkSha256": apk_hash}, ensure_ascii=False))


if __name__ == "__main__":
    package()
