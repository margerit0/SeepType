# 拾词 Android：开发预览接续

更新于 2026-11-14。完整产品范围见 [安卓计划](android-plan.md)，实际构建、报告与限制见 [验证记录](android-validation.md)，构建命令见 [Android README](../android/README.md)。

当前已实现 Kotlin／Compose 界面＋Rust 会话核心＋固定 Rime／Lua，并完成本次 P0–P3 的模拟器范围及开发预览材料。P0／P1 检查点为 `b5fa54f`；历史交付目录由原缓存中的 `delivery-latest.json` 标识，本轮源码与证据见独立缓存的 `release-stability-latest.json`。P4 的性能目标尚未全部达到，真机等项目也仍待补验；不要重新从空工程开始。用户已允许在合适时提交，所有提交保持在现有 Android 分支。

**最新断点（2026-11-14，一加 12 真机）：** 已接入 3,401 条开发词库并安装 preview.2。补齐资源的新包首次部署就绪 690.670 ms；20 次新进程启动 p95 120.830 ms、20 次同进程重开 p95 29.727 ms，达到本次 500 / 100 ms 目标。修正词库测试复用 generation 导致 Start 被拒绝的问题，42 项三方案合成 JNI/Rime/Lua 用例全部通过；主程序未为此次续测修改。原默认输入法及原启用状态恢复，测试辅助包保留。详见 真机续测报告（内部记录），新证据在 `.cache/android/physical-device-20261114/continuation-20261114`。历史崩溃、全套 Release 回归及其他设备验收不因本次通过而关闭。

**前轮断点（任务 1、2，模拟器）：** 已完成固定 B 编辑器／测试 APK 的 A→B→B→A 启动对照，共 80 个新进程，覆盖完整、无本次运行时崩溃，四批 p95 均未达到 500 ms。两次 B−A 的 p50 为 +23.38／+22.33 ms，p95 为 +501.43／−12.97 ms；宿主及同版本时段变化明显，未建立诊断开销的因果结论，也没有证明零开销。复用旧 trace 并补 3 次 B 启动后，主要等待关联到 RenderThread 的 `setSurface` 和首次 `DrawFrames`；图形 CPU 栈显示 QemuPipe／goldfish 通信。前后两次 `setStopped → runSync` 是源码支持的阻塞调用候选，因阻塞 perf 事件源被 `EINVAL` 拒绝，具体主线程函数栈仍未确认。详见 [启动对照与等待定位报告](android-startup-baseline-wait.md)。本次没有产品优化、最终全套 Release 回归、API 30 补测或磁盘准备。

新入口为 `.cache/android/startup-baseline-wait-latest.json`，证据目录是 `.cache/android/release-stability-worktree/evidence/startup-baseline-wait-20261113T1923433697860Z`。开工实时 HEAD 为 `6c24652`，皮肤与剪贴板合入提交完整保留；被测 A／B 分别冻结于 `0fc9993`／`9be4dea`，本次结果不是当前合入产品的 Release 验收。已恢复冻结 B、核对三份 APK，并关闭专用 AVD、保留数据，其他 AVD 与 WSL boot 不变。

**前轮断点：** 从交接提交 `0fc9993` 接续任务 1、2、3、5。已补齐故障现场与宿主关联采集；有限运行完成 7 组、1,260 次按键和 140 次重开，历史崩溃未复现，根因仍未确认。启动追踪定位到首次绘制中的大量主线程等待与 RenderThread 工作，但四种准备／绘制调整未获得可复验的收益，均已撤回；最终产品只新增启动诊断数据。最终 Release 的输入、生命周期与重开回归通过，三组暖态共 540 次按键、60 次重开均达标；两组各 20 次启动 p95 为 799.69／980.15 ms，500 ms 目标仍未达到。原始结果见验证记录。P4 和 preview.2 仍未收尾。

前轮证据目录为 `.cache/android/release-stability-worktree/evidence/continuation-1235-20261113T152157390451Z`，报告为其中的 `故障采集与启动定位及Release回归报告.md`；正式性能组在同缓存的 `evidence/performance-investigation/20261113T182953264318Z-final-diagnostics-perf`。其摘要入口 `.cache/android/release-stability-latest.json` 保留原提交、源码和 APK 含义，没有被本次对照覆盖。更早的缓存绘制修复及 736.66／640.43 ms 启动结果属于 `0fc9993` 的历史记录，保留在 `investigation-20261113T122422Z`。

**新增 Windows 手动验收入口：** 根目录双击 `启动安卓验收.cmd`，会自动准备可操作的真实 APK 手机窗口，并提供输入场景、原生设置、显示预设、截图和录像。入口源码为 `tools/android/acceptance.py` 与 `acceptance_ui.py`，使用现有 Release 输入法和 Debug 原生输入页；使用方法、本轮 14／28／16 项检查及冷启动验证见 [一键交互验收](android-acceptance.md)。产物在专用缓存的 `acceptance` 目录。本轮未重新导出开发预览 ZIP，原交付材料和真机待办仍保留各自范围。

## 工作目录与授权

| 用途 | 目录 | 分支 |
| --- | --- | --- |
| Android 崩溃与性能任务 | `.` | `codex/android-dev` |
| 另一窗口的皮肤任务 | `.` | 由皮肤任务管理，不在这里切分支或改文件 |
| 另一聊天的 Windows／词库任务 | `.` | 由另一任务管理，不能在这里修改或切换 |

源码、暂存与提交只在 Android worktree。用户已批准将本任务新增的工具、下载、模拟器和构建产物放在 `.cache/android`，通过目录联接保留工程路径；`.cache/android-cache-location.json` 记录归属。继续复用已有 JDK／Rust／Visual Studio 工具，不重复整理另一工作树。分工历史见 [并行开发说明](parallel-development.md)。

本工作树独占 `.cache/android/release-stability-worktree` 中的 Gradle 缓存、构建输出、准备资源、临时文件与证据；已安装 SDK／JDK 只读复用。设备为 `StudyIME_Stability_API35_20261113`，ADB `127.0.0.1:5581`，独立 ADB server 端口 `5041`。运行命令前设置 `$env:ADB_SERVER_SOCKET='tcp:localhost:5041'`，不要覆盖另一任务的 5555／5561 安装。设备数据保留；使用情况与启动参数见 `.cache/android/isolation.json` 和 `emulator-process.json`。

本任务 AVD 已在实时核对后安全关闭并保留数据，WSL boot 和另外两个模拟器身份未变；收尾状态、最后安装摘要及编译状态见本轮 `final-device-state.json`。下次启动或停止前仍须重新核对 AVD、端口和进程命令行。`environment-restart-01` 另存仅重启本任务 AVD 的启动对照。任务 4（API 30 补测及磁盘准备）不在本轮范围；既有 API 30 启动失败记录留在上轮目录，不在这里继续准备磁盘。

开工先看实时状态，文档中的提交只是检查点，不要求回退：

```powershell
git rev-parse --show-toplevel
git status --short --branch
git log -5 --oneline
```

## 当前能力与验证断点

以下完整功能及暖态回归数字属于前轮冻结 B（`9be4dea`）。本次只完成该冻结输入上的启动对照和定位，没有把这些结果升级为皮肤／剪贴板合入版的当前验收。

- 已实现 26 键、全拼／自然码／小鹤双拼、中英文／数字／符号、删除、空格和编辑器动作；设置与启用引导齐全。
- 原生双行候选、展开／翻页、完整释义、浅深色、字号与高度、按压反馈、大字号与横屏已实现。候选第一次出现保持窗口高度，避免快速触摸因重布局丢失。
- 同一输入框的隐藏重开与受校验的连接重启保留组合；输入框代次、候选版本、唯一提交 ID 和旧触摸取消保护迟到操作。
- 资源逐文件校验、损坏重建、失败回退及用户词典独立保存已实现；200 条英文仍未人工审核。
- 本轮 Release `0.1.0-preview.1` 的 SHA-256 为 `31ab41223ce5a0a438f6e07ef0b1d869ebb07e904b48eca25674e159aedc2e60`，保持 R8 与资源压缩，正常覆盖安装，`verify / reason=install`。构建收据绑定实际源文件；没有生成 preview.2 包。
- 本轮重新通过 Release 的 16 项输入交互、18 项生命周期及 40 次重开，以及 Debug 缓存绘制最小回归。最终构建、单元检查、Debug／Release Lint 和 40 项 Python 检查通过。171 条原生／生成资源与原版逐字节相同，6 个准备原生输入、8 个 APK 库及 ELF／ZIP 16 KB 静态对齐重新通过；已有原生功能、38 项布局和 42 张截图按未改动范围复用。
- 正式回归固定三份 APK，核对每组 180 个交付／绘制／阶段配对、20 个重开样本、逐词和最终正文；覆盖完成与性能达标分列。启动边界仍为 `onStartInputView` 至真实就绪 Compose 绘制，新增线程 CPU 时长与单调时钟锚点没有改变终点。新进程启动目标和历史运行时崩溃定位仍未收尾。
- 两次受控原生故障注入仅用于采集工具自测，正确识别实际崩溃 PID 并排除旧 tombstone；不是历史崩溃复现。真实 1 秒超时检查验证先冻结现场、后停止专用 Debug runner，保留原始超时。有限复现第 8 组预算超时及边界外报告不计入通过覆盖。
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
| 故障现场、宿主与退出原因关联 | `tools/android/runtime_evidence.py`、`host_evidence.py`、`runtime_artifacts.py` |
| 有限复现与正式性能回归 | `tools/android/bounded_repro.py`、`profile_performance.py` |
| 启动墙钟／线程 CPU／追踪锚点 | `android/app/src/main/java/org/studyime/android/diagnostics/StartupTimings.kt` |
| 设备用例 | `android/app/src/androidTest/java/org/studyime/android` |
| 词库及许可 | [词库说明](lexicon.md)、[软件许可](software-licenses.md)、`licensing/product-sources.lock.json` |

Rime 固定为 `1c23358157934bd6e6d6981f0c0164f05393b497`，librime-lua 为 `e3912a4b3ac2c202d89face3fef3d41eb1d7fcd6`。Android 使用 NDK 编译并携带 `Memory::OnCommit` 暂停中文学习补丁，不能替换成 Windows DLL 或另一任务的用户词典。

## 交付与下一步

1. 先读取验证记录、`.cache/android/isolation.json` 和 `.cache/android/startup-baseline-wait-latest.json`，核对实时 Git、实际 APK 与源码摘要。`release-stability-latest.json` 仍指前轮封存结果；旧开发预览交付也不能当作当前合入版的新包。
2. 继续产品优化前读 [启动对照与等待定位报告](android-startup-baseline-wait.md) 的两项假设和未确认之处。新一轮任务 1、2 已在 80 次无追踪／3 次诊断启动上限内结束；不要追加批次挑较快结果。后续应在保留已合入改动的实际源码上建立基线，再检验首次引擎调度优先级或图形通信工作量的改动，不重复已撤回的门控／提前准备方案。历史崩溃仍缺少正向最小用例。保留故障现场与慢样本，不关闭 R8、不改变资源校验或计时终点。
3. 用户已选择先模拟器。真机 arm64、实际 16 KB 页面、物理触感／60 Hz／高刷新率、真实 TalkBack、锁屏和常用应用仍需补验；不要宣称 P4 全部完成。
4. 旋转后的正文与继续输入已验证，跨 Activity／进程重建的原生分段组合不保证恢复。详细限制保持在验证记录。
5. 词库扩充由另一聊天负责；本轮不启动模型请求，不将未审核扩充草稿自动导入，不把旧文档数字当成其当前进度。Windows W0–W3 也不是本轮前置任务。
