# Android 预览版真机回归

只在明确指定的测试设备上运行。保持手机解锁，先选一个非拾词的默认键盘，测试期间不要操作其他应用。测试使用自带的合成编辑器；不读取个人文本、文件和剪贴板，不录屏、不截图，也不收集系统日志或窗口树。测试会短暂切换默认输入法和旋转设置，通过拾词界面保存并恢复方案和英文开关。

## 构建与运行

从已提交的集成版本按 [Android 构建说明](../android/README.md#构建环境)准备原生库和资源，再构建 Release、Debug 和 Debug 测试 APK：

```powershell
python -X utf8 tools/android/build.py apk
python -X utf8 tools/android/build.py apk --debug
python -X utf8 tools/android/build.py tests
```

在指定测试设备上更新本次的 Release。签名不一致时不要卸载用户现有版本或清除数据。然后运行：

```powershell
python -X utf8 tools/android/validate_phone.py `
  --adb .cache/android/sdk/platform-tools/adb.exe `
  --serial TEST_PHONE_SERIAL `
  --release android/app/build/outputs/apk/release/app-release.apk `
  --debug android/app/build/outputs/apk/debug/app-debug.apk `
  --test android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk `
  --output .cache/android/physical-validation/RUN_NAME `
  --sections native recovery ime input reopen --install-helpers
```

替换 `TEST_PHONE_SERIAL` 和 `RUN_NAME`，每次用新的输出目录。脚本冻结三个 APK，核对已安装包的 SHA-256、Debug／Release 的 Rime 和详情资源，以及测试包是否包含当前固定快照的原生用例。`--install-helpers` 只更新 Debug 和测试 APK，不替换 Release。

- `native` 用当前快照的原生矩阵验证输入、会话和保护规则；`recovery` 在隔离数据目录验证资源修复。
- `ime` 和 `input` 用 Release 键盘验证真实提交。`input` 还检查三种方案、两条「解决」释义、显式输入 `solve` 和离线专名「流浪地球」。
- `reopen` 检查 40 次重开均达到就绪绘制；`lifecycle` 和 `performance` 为可选的较长回归。Compose 绘制计时不等于物理显示延迟。

若系统把合成密码框路由至另一键盘，可加 `--exclude-system-routed-password`。脚本必须确认不同键盘实际显示且拾词节点不可用，才把相关检查记为 `blockedChecks`、`coverageComplete=false`；不会关闭系统安全键盘。不要只看 `passed`，也要检查覆盖范围、恢复结果和已安装包摘要。失败时保留原目录；若提示有未恢复的测试设置，要先恢复原设置再重跑。

`archive/android-dev-preview.2` 保留旧词库、旧矩阵与历史手机结果。那些结果只属于 `preview.2`，不能作为 `preview.3` 的真机证据。
