# 拾词 Android：开发预览接续

更新于 2026-11-13。完整产品范围见 [安卓计划](android-plan.md)，实际构建、报告与限制见 [验证记录](android-validation.md)，构建命令见 [Android README](../android/README.md)。

当前已实现 Kotlin／Compose 界面＋Rust 会话核心＋固定 Rime／Lua，并完成本次 P0–P3 的模拟器范围及开发预览材料。P0／P1 检查点为 `b5fa54f`；历史交付目录由原缓存中的 `delivery-latest.json` 标识，本轮源码与证据见独立缓存的 `release-stability-latest.json`。P4 的性能目标尚未全部达到，真机等项目也仍待补验；不要重新从空工程开始。用户已允许在合适时提交，所有提交保持在现有 Android 分支。

**最新断点：** 本轮从 `d8a859c` 建立独立工作树，修复了缓存 Compose 内容重开时漏记绘制的问题。正常安装的 Release 已连续完成三组各 180 次按键和 20 次重开，候选与暖态重开目标均达到。两组新进程启动 p95 为 736.66／640.43 ms，500 ms 目标仍未达到。历史 Compose／ART／系统进程崩溃本轮未再次观察到，根因仍未确认；绘制计时修复不能称为这些运行时崩溃的修复。preview.2 继续待定。

本轮证据目录为 `.cache/android/release-stability-worktree/evidence/investigation-20261113T122422Z`，性能原始组在同缓存的 `evidence/performance-investigation/20261113T134252455751Z-show-draw-fixed`。它们优先于下文历史交付数字；后续摘要入口为 `.cache/android/release-stability-latest.json`。

**新增 Windows 手动验收入口：** 根目录双击 `启动安卓验收.cmd`，会自动准备可操作的真实 APK 手机窗口，并提供输入场景、原生设置、显示预设、截图和录像。入口源码为 `tools/android/acceptance.py` 与 `acceptance_ui.py`，使用现有 Release 输入法和 Debug 原生输入页；使用方法、本轮 14／28／16 项检查及冷启动验证见 [一键交互验收](android-acceptance.md)。产物在专用缓存的 `acceptance` 目录。本轮未重新导出开发预览 ZIP，原交付材料和真机待办仍保留各自范围。

## 工作目录与授权

| 用途 | 目录 | 分支 |
| --- | --- | --- |
| Android 崩溃与性能任务 | `.` | `codex/android-dev` |
| 另一窗口的皮肤任务 | `.` | 由皮肤任务管理，不在这里切分支或改文件 |
| 另一聊天的 Windows／词库任务 | `.` | 由另一任务管理，不能在这里修改或切换 |

源码、暂存与提交只在 Android worktree。用户已批准将本任务新增的工具、下载、模拟器和构建产物放在 `.cache/android`，通过目录联接保留工程路径；`.cache/android-cache-location.json` 记录归属。继续复用已有 JDK／Rust／Visual Studio 工具，不重复整理另一工作树。分工历史见 [并行开发说明](parallel-development.md)。

本工作树独占 `.cache/android/release-stability-worktree` 中的 Gradle 缓存、构建输出、准备资源、临时文件与证据；已安装 SDK／JDK 只读复用。设备为 `StudyIME_Stability_API35_20261113`，ADB `127.0.0.1:5581`，独立 ADB server 端口 `5041`。运行命令前设置 `$env:ADB_SERVER_SOCKET='tcp:localhost:5041'`，不要覆盖另一任务的 5555／5561 安装。设备数据保留；使用情况与启动参数见 `.cache/android/isolation.json` 和 `emulator-process.json`。

收尾时本任务的 API 35 AVD 已关闭并保留数据；其他任务的模拟器继续运行。额外创建的 `StudyIME_Stability_API30_20261113` 三次因可用磁盘空间不足而未启动，未执行应用兼容性检查；分区缩小参数未生效，需满足模拟器约 7.2 GiB 的创建空间要求后再补验。详细准备失败和设备结束状态保存在本轮证据的 `api30-environment-outcome.json`、`final-device-state.json`。

开工先看实时状态，文档中的提交只是检查点，不要求回退：

```powershell
git rev-parse --show-toplevel
git status --short --branch
git log -5 --oneline
```

## 当前能力与验证断点

- 已实现 26 键、全拼／自然码／小鹤双拼、中英文／数字／符号、删除、空格和编辑器动作；设置与启用引导齐全。
- 原生双行候选、展开／翻页、完整释义、浅深色、字号与高度、按压反馈、大字号与横屏已实现。候选第一次出现保持窗口高度，避免快速触摸因重布局丢失。
- 同一输入框的隐藏重开与受校验的连接重启保留组合；输入框代次、候选版本、唯一提交 ID 和旧触摸取消保护迟到操作。
- 资源逐文件校验、损坏重建、失败回退及用户词典独立保存已实现；200 条英文仍未人工审核。
- 本轮 Release `0.1.0-preview.1` 的 SHA-256 为 `f62e302a49a0918bcbd1133c1ed68c727175c5afd1a5674c2ba0bc48db850506`，保持正式 R8 与资源压缩。构建收据绑定实际源文件；没有生成 preview.2 包。
- 本轮重新通过 Release 的 16 项输入交互、18 项生命周期及 40 次重开检查；Debug 最小缓存绘制用例完成同一测试 APK 的修复前后对照。已有原生、资源和视觉证据按改动范围复用。原生库和生成词库逐字节不变，键盘布局／皮肤代码未改，当前 APK 的原生及 ZIP 对齐另行复核通过。
- 三组候选绘制 p95 为 37.65／37.15／34.61 ms，p99 为 54.22／46.37／42.32 ms；重开 p95 为 57.88／53.16／38.02 ms。每组严格核对 180 个交付／绘制／配对样本及 20 个重开样本、完整正文、无合并／丢弃／待绘制输入，三组 IME PID 相同。新进程启动目标和历史运行时崩溃定位仍未收尾。
- 修复过无障碍关闭后发送通知的崩溃；无障碍关闭输入回归已加入交付检查。浏览器测试每次加载带唯一标记的新页面，防止上轮合成内容残留。

最终交付必须由当前源码与实际安装 APK 的报告共同支持。`.cache/android/evidence/history` 保留旧报告与失败尝试；不要把它们改成当前通过结果。`.cache/android/assembly-debug.json`、`assembly-release.json` 绑定源码、生成资源、原生库与构建日志；`package_preview.py` 会拒绝不匹配的报告、截图或录像。

## 已确认的产品约定

1. 候选英文在上、中文在下。点任何一行和普通空格都提交中文；长按／释义按钮只打开面板，明确点击“输入英文”才提交英文。
2. 英文值由 Lua／Rime 在提交前重新核验。仅整段组合且光标在末尾可输入英文；缺词、部分组合、过期动作和关闭英文显示时拒绝，并保留正常输入。
3. 英文显示与中文学习是独立开关。暂停学习保留已有词频；三种方案共用安卓本机用户词典；逐词遗忘不改正文。输入方案等本次组合完成后再切换。
4. 首版离线运行，未申请网络权限。密码停用学习和释义，尊重禁止个性化学习标志；用户词典和设置显式排除 Android 备份。
5. 清浅绿、柔和按键与 9 dp 圆角沿用认可方向；原生按 dp／sp 验证。网页示意中的固定例词不能加入运行词库。
6. 九宫格、滑行、语音、手写、英语预测纠错、账号／云同步、AI 翻译和 Windows Rust 接入属于后续范围。

参考：[说明](../prototype/android/README.md)、[可操作示意](../prototype/android/index.html)、[浅色](../prototype/android/light.png)、[深色](../prototype/android/dark.png)。网页参考不能充当 Android 运行结果。

## 源码与工具入口

| 内容 | 入口 |
| --- | --- |
| 输入连接、生命周期与交付计时 | `android/app/src/main/java/org/studyime/android/ime` |
| Compose 键盘、候选及释义 | `android/app/src/main/java/org/studyime/android/ui/Keyboard.kt` |
| 启用引导、设置和本机数据说明 | `android/app/src/main/java/org/studyime/android/MainActivity.kt` |
| 串行引擎与资源部署 | `android/app/src/main/java/org/studyime/android/engine` |
| Rust 会话策略及 JNI | `crates/study-core`、`study-rime-sys`、`study-rime`、`study-android` |
| Lua 权威释义与动作 | `src/study/lua/study_core.lua`、`packaging/data/rime.lua` |
| 构建／设备验证／打包 | `tools/android`；固定版本见 `android/toolchain.lock.json` 和锁文件 |
| 设备用例 | `android/app/src/androidTest/java/org/studyime/android` |
| 词库及许可 | [词库说明](lexicon.md)、[软件许可](software-licenses.md)、`licensing/product-sources.lock.json` |

Rime 固定为 `1c23358157934bd6e6d6981f0c0164f05393b497`，librime-lua 为 `e3912a4b3ac2c202d89face3fef3d41eb1d7fcd6`。Android 使用 NDK 编译并携带 `Memory::OnCommit` 暂停中文学习补丁，不能替换成 Windows DLL 或另一任务的用户词典。

## 交付与下一步

1. 先读取验证记录、`.cache/android/isolation.json` 和 `.cache/android/release-stability-latest.json`，核对实时 Git、实际 APK 与源码摘要。旧开发预览交付位于原共享缓存，不能当作本轮新包。
2. 继续定位历史运行时崩溃，并核对新进程启动的同设备对照。新的 `runtime_evidence.py` 按日志标记截取每次运行，分别记录 IME、测试和系统故障；`profile_performance.py` 分别报告覆盖完成与延迟目标，失败及慢样本完整保留。不要关闭 R8、跳过断言或沿用不匹配的成功报告。
3. 用户已选择先模拟器。真机 arm64、实际 16 KB 页面、物理触感／60 Hz／高刷新率、真实 TalkBack、锁屏和常用应用仍需补验；不要宣称 P4 全部完成。
4. 旋转后的正文与继续输入已验证，跨 Activity／进程重建的原生分段组合不保证恢复。详细限制保持在验证记录。
5. 词库扩充由另一聊天负责；本轮不启动模型请求，不将未审核扩充草稿自动导入，不把旧文档数字当成其当前进度。Windows W0–W3 也不是本轮前置任务。
