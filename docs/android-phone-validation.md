# Android 个人手机回归入口

此入口使用固定的 Release 输入法、独立 Debug 编辑器和测试组件。只运行包内合成用例，使用禁止个性化学习的测试输入框；学习、遗忘和资源破坏用例在 Debug 应用自己的隔离目录执行。

不调用模拟器专用的 `RuntimeCapture`、`collect_device_evidence` 或 `profile_performance`。不采集全局 logcat、截图、窗口层级文件、个人文件或剪贴板内容。测试报告中的正文仅来自专用合成编辑器。测试期间手机须保持解锁。

## 固定构建输入

```powershell
python -B -X utf8 tools/android/prepare_data.py --source-cache .
python -B -X utf8 -c 'from tools.android.build import gradle; gradle([":app:assembleDebug", ":app:assembleDebugAndroidTest", ":app:testDebugUnitTest", "--offline"], log="phone-validation-build")'
```

`--source-cache` 仅按摘要读取已有原始依赖归档，不运行 Windows 产品或修改其工作区。完整准备流程还会生成 `reviewed-smoke.json`、`reviewed-full.json`、`reviewed-cases-manifest.json`。仅重新生成测试数据可运行 `python -B -X utf8 tools/android/expanded_lexicon.py`；完整干净环境仍应先执行正式准备流程。

固定快照为 `adopted-expansion-all-20261114`。3,195 个运行时读音在全拼、自然码、小鹤中生成 9,585 项用例；每项检查当前主释义、完整英文提交、过期 token 拒绝及中文提交。3,401 条采用记录的所有原始文件由快照摘要绑定；未被当前单释义界面选作主释义的保留义项，不冒称具有独立 UI 提交覆盖。

原有 600 项基础用例保留输入，根据当前固定快照更新期望释义。若以后基础用例出现必须区分读音的词，生成器会拒绝不明确的期望值。

Debug 与 Release 的生成资源必须逐文件一致。主程序不变时复用已测的 Release；测试 APK 独立绑定 `.cache/android/assembly-debugandroidtest.json`，包括生成用例摘要。主程序有变化时重新构建、安装、核对身份并补跑受影响验证。

## 分段执行

```powershell
python -B -X utf8 tools/android/validate_phone.py `
  --adb .cache/android/sdk/platform-tools/adb.exe `
  --serial PHONE_SERIAL `
  --release PATH_TO_PINNED_RELEASE_APK `
  --debug android/app/build/outputs/apk/debug/app-debug.apk `
  --test android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk `
  --output .cache/android/physical-validation/RUN_NAME `
  --sections lexicon native recovery --install-helpers
```

将 `PHONE_SERIAL`、Release 路径及 `RUN_NAME` 替换为本次明确选择的值。输出目录必须是全新的、属于此工作树的目录。`--install-helpers` 只更新 Debug 和测试组件，拒绝悄悄替换固定 Release。

- `lexicon`：9,585 项新词库矩阵。
- `native`：原有 600 项及真实 JNI、会话、隐私、跨方案学习、遗忘和资源修复检查。
- `recovery`：隔离目录内的资源部署中断、损坏和回退。
- `ime input lifecycle`：当前 Release 的真实编辑器交互、三方案中英文提交、分段组合、选区、快速输入和生命周期。
- `performance reopen`：默认三组固定性能序列，每组 180 次按键和 20 次重开，加 40 次重开；限定一个最多 30 分钟的窗口。覆盖与性能目标分开报告。

同一设备上的这些命令必须顺序执行；不能同时运行两个 instrumentation 或另一自动输入任务。失败后先查看该次自己的报告，再决定需要重跑的最小范围。不要覆盖失败目录或追加批次挑较快结果。

## 系统安全键盘路由

若合成密码框被系统路由至另一键盘，可在 `--sections ime input lifecycle` 时显式加 `--exclude-system-routed-password`。入口先运行独立诊断，核实拾词仍是默认设置、密码框实际由另一组件显示且拾词节点不可用；满足条件后才将两项密码 UI 检查记为受阻，并继续其余输入框。不会切换安全键盘开关。未指定该参数时仍要求密码 UI 通过。

`passed` 表示实际执行的断言与恢复成功；`coverageComplete=false` 和 `blockedChecks` 明确表示完整范围未通过。发布或人工验收必须检查这两个字段，不能只读取 `passed`。诊断仅保留键盘组件标识、显示／锁屏布尔值及拾词自己的计时，不保存完整输入法服务转储。

本机结果见 2026-11-14 续测报告（内部记录）。普通框曾有一次键盘节点不可用，其失败记录保留，续跑通过不替代根因定位。

## 恢复和边界

入口记录并恢复原默认输入法、拾词原启用状态和原旋转设置。界面测试通过拾词自己的快捷设置保存并恢复原方案和英文开关；不读取应用私有个人词典。恢复记录保存在输出目录 `restore.json`，各阶段结果、实际 APK、源码摘要和执行命令一起保存。

原生词库测试使用 Debug 宿主加载产品原生库和相同资源；Release UI 测试才证明真实优化输入法向 InputConnection 交付。性能终点为 Compose 绘制记录，不等于物理屏幕呈现。有限样本通过不代表历史崩溃根因已经消除，也不代替其他系统版本、TalkBack、实际 16 KB 页面和用户常用应用验收。
