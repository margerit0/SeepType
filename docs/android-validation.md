# 拾词 Android 开发预览验证

更新于 2026-11-14（北京时间）。本页记录原生 Android 实现和实际验证，网页原型只用于视觉参考。

## 2026-11-14：新一轮启动对照与等待点定位

已完成新一轮任务 1、2，详见 [启动基线对照与首次绘制等待定位](android-startup-baseline-wait.md)。实时接管 HEAD 为 `6c24652`，皮肤／剪贴板合入提交保留；比较使用冻结 A `0fc9993` 与 B `9be4dea`，固定 B 编辑器和测试 APK。该对照不能当作当前合入版产品的 Release 验收。

A→B→B→A 四批各 20 个新进程，全部 show／真实 draw／ready 配对完整，编译状态均为正常安装的 `verify`。p95 依次为 **1454.68／1956.10／748.03／760.99 ms**，均未达到 500 ms。两个方向的 B−A 中位数约 +22–23 ms，但尾延迟差异反向，同版本和宿主状态变化较大，未建立诊断开销的因果结论，也没有证明零开销。

复用旧 trace 后只补 3 次 B 启动：主线程两段主要等待由 RenderThread 在 `setSurface` 和首次 `DrawFrames` 结束附近唤醒；新的 CPU 栈落在图形命令到 QemuPipe／goldfish 驱动的通信路径。首次 `setStopped → runSync` 前后同步调用是源码支持的候选，阻塞栈采样源 `EINVAL` 失败与 18 个 CPU 栈展开错误均原样保留，具体主线程函数尚未直接确认。时钟域、实际就绪帧、调度覆盖与唤醒关系已用独立 SQL 核验；渲染结束不等于物理显示。

本次 83 次启动无运行边界内崩溃；恢复冻结 B 后已关闭本任务 AVD 并保留数据，其他 AVD 与 WSL boot 未变。未实施产品优化、未重跑最终全套 Release 回归，也未做 API 30 或磁盘准备。新证据位于 `evidence/startup-baseline-wait-20261113T1923433697860Z`，独立入口为 `.cache/android/startup-baseline-wait-latest.json`。前轮封存档案和 `release-stability-latest.json` 保留原含义。

## 2026-11-14：前轮故障采集、有限复现、启动定位与最终 Release 回归

本轮从交接提交 `0fc9993c79b3c4ed0ae29af55cec1de2982d4431` 接续任务 1、2、3、5，仍使用 `.`／`codex/android-dev` 和专用缓存 `.cache/android/release-stability-worktree`。设备为 `StudyIME_Stability_API35_20261113`，API 35 x86_64，ADB `127.0.0.1:5581`、server `5041`。任务 4（API 30 及磁盘准备）、其他工作树和 preview.2 交付不在本轮范围。

**最终只保留诊断与采集增强；历史崩溃根因和启动 500 ms 目标仍未解决。** `Keyboard.kt`、`EngineHost.kt`、`StudyInputMethodService.kt` 已恢复交接版；`StartupTimings.kt` 新增实际线程 CPU 时长、单调时钟锚点及启用系统追踪时的 Perfetto 分段。资源逐文件核验、R8、资源压缩和原始计时终点保留。

### 最终构建与功能

| 包 | 最终 SHA-256 |
| --- | --- |
| org.studyime.android | `31ab41223ce5a0a438f6e07ef0b1d869ebb07e904b48eca25674e159aedc2e60` |
| org.studyime.android.debug | `05694011be29147c7adcb699b809f45b7e8df76e1a81722b05dfa8c1a4c55d64` |
| org.studyime.android.debug.test | `59c8013ef1b817f5cdde003e2f231cc0f6a72eb62cf03d5ec9216a78651a8987` |

最终 `assembleRelease`、`assembleDebug`、`testDebugUnitTest`（3 项）、`assembleDebugAndroidTest`、`lintDebug`、`lintRelease` 成功；40 项 Python 主机检查通过。最终 APK 正常覆盖安装、保留数据，编译状态为 `verify / reason=install`，未强制 AOT。Release **16 项输入、18 项生命周期、40 次重开**和 Debug 缓存绘制最小回归通过，APK 前后身份一致，无本次 runtime fatal。171 条原生／生成资源与交接版逐字节相同；6 个准备原生输入、8 个 APK 库及 ELF／ZIP 16 KB 静态对齐重新通过。原生功能、38 项布局及 42 张截图按未改动范围复用，未重跑或冒称真机验收。

### 故障采集及有限复现

现场采集现在包括准备／触发命令、Windows／WSL 负载和模拟器进程、设备 boot／PID／启动时间、设备时区与 uptime、退出原因和新增 text／proto tombstone。使用运行标记及前后差异归属事件；旧记录、时钟变化和身份不明记录分开。采集错误不能覆盖原始异常，任一必要采集失败均不能保持 `complete=true`。

两次受控 `/system/bin/sleep` SIGSEGV 仅用于采集工具自测。首次发现 `SI_USER from pid` 是信号发送者，修正后使用实际崩溃 PID，重新注入验证本次 tombstone 冻结及旧 tombstone 排除。真实 1 秒 instrumentation 超时检查验证原超时保留、现场冻结完成后再停止专用 Debug runner。以上均不是历史产品崩溃的正向复现。

固定交接 APK、同一编辑器／运行器和正常安装，设 **8 组／25 分钟**预算检查连续运行时间。完成 **7 组、1,260 次按键、140 次重开**，IME PID 始终为 `1314`；整段运行标记内无 runtime fatal、无本次归属 tombstone，系统和 boot 稳定。第 8 组触及预算，主机 adb 超时；含采集的总耗时为 **1517.63 秒**。边界外远端 runner 后来产生的 23 词及 `Missing enabled key: space` 报告另存，不计通过覆盖，也不归类为历史崩溃。

这次超时促使工具补上远端清理，以及剩余时间不足已观测完整组时不再启动下一组。有限复现不是暖态全通过：部分组出现候选或重开尾延迟超标，原始数据保留。历史去重的 **21 个事件（15 IME、1 测试／编辑器、5 系统）**仍无正向最小复现，根因未确认；未复现不能排除应用、ART、测试或虚拟化层。

### 启动定位与撤回的试验

原版三次 Perfetto 追踪显示首次 traversal 约 **514–580 ms**；主线程其中约 **392–417 ms 处于 S 等待**，实际 Running 约 **50–82 ms**。RenderThread 的 EGL 初始化、shader 编译与 swap 工作明显；`FIRST_MAIN_QUEUE` 为 **167–294 ms**，与首次未就绪帧的同步渲染重叠。新增线程 CPU 数据的一组对照中，资源核验 CPU 中位约 **31 ms**、Rime 创建约 **60 ms**，对应墙钟中位约 83／180 ms；这些阶段可能重叠，不能相加推导因果。

固定交接 Debug 编辑器／测试 APK，仅正常覆盖安装不同 Release，各取 20 次无追踪启动：

| 对照 | 启动 p95（ms） | 证据目录 |
| --- | ---: | --- |
| 原版 0fc9993 | 601.66 | `baseline-startup-control` |
| 首次准备时延后禁用按键 | 544.09 | `deferred-keys-startup-control` |
| 再延后工具栏 | 545.59 | `minimal-preparation-startup-control` |
| 首次预绘制最多等待 250 ms | 787.97 | `initial-draw-gate-startup-control` |
| 服务创建时提前准备引擎 | 1016.56 | `engine-preparation-startup-control` |
| 后期回装同一原版 | 700.59 | `baseline-return-control` |
| 只重启本任务 AVD 后的原版 | 661.83 | `baseline-after-restart-control` |
| 同条件复测延后按键版本 | 713.81 | `retained-after-restart-control` |

延后按键的早期收益在重启后的同条件对照中未复验，提前准备引擎和首次预绘制等待反而更慢，所有行为调整均已撤回。延后工具栏的 3 次追踪内 Compose 计时较快，但 ready frame 对应的 RenderThread 结束仍约 513–553 ms，且无追踪 20 次没有稳定收益，不能拿来替代正式验收。该 RenderThread 关联不是物理显示延迟，原版绝对锚点还有推算误差。

原版与按键延后追踪经核对无 ftrace overrun／drop／parse error；36 个 setup notice 是模拟器不存在的物理 GPU 驱动事件。最初 Perfetto 配置路径被 SELinux 拒绝的尝试原样保留，后续使用官方 stdin 配置方式，没有更改 SELinux。试验性门控／提前准备专项测试只编译过、未运行设备验证，不声称通过；最终源码中已撤回。

### 最终常规 Release 性能

两组各 20 次新进程启动及连续三组暖态均使用上表最终 APK，无追踪、未清数据、未强制编译；正式测量期间本窗口没有并行 Gradle 或其他 instrumentation。

| 连续组 | 按键／重开 | 候选绘制 p95／p99（ms） | 暖态重开 p95（ms） | 结果 |
| --- | --- | ---: | ---: | --- |
| 1 | 180／20 | 44.95／49.58 | 63.20 | 覆盖、正文、运行时及暖态目标通过 |
| 2 | 180／20 | 45.22／53.40 | 70.87 | 覆盖、正文、运行时及暖态目标通过 |
| 3 | 180／20 | 43.64／55.52 | 71.93 | 覆盖、正文、运行时及暖态目标通过 |

三组均精确取得 180 个交付／绘制／有序阶段配对及 20 个重开样本，逐词和最终正文正确，无合并、丢弃、pending 或缺失样本。三组 IME PID 始终为 `13544`，系统关键进程和 boot 未变，整段日志及退出／tombstone 归属无本次运行时崩溃。

两组新进程启动 p95 为 **799.69／980.15 ms**，最大值为 **841.52／1053.10 ms**，均超过 500 ms。每个新进程恰好一个完整显示／就绪绘制对。整体比较保留 `completed=true、coverageComplete=true、threeWarmGroupsPassed=true、timingTargetsMet=false、passed=false`；三组暖态均达标，启动仍未达标。启动边界仍为首次 `onStartInputView` 至真实就绪 Compose 绘制，排除回调前进程创建和物理显示延迟。旧环境的较快结果、少量带追踪样本和撤回版结果均不能覆盖本次未达标。

最初最终回归的主机包装脚本在功能检查结束后因安装参数覆盖 argparse 变量而失败，性能阶段尚未开始；失败脚本及原 `final-diagnostics/validation.json` 未修改。修复变量名后，单独继续正式性能序列，同一源码和三份 APK 身份再次核对。该主机编排错误不属于产品崩溃，后续完整结果记录在 `final-diagnostics/performance-continuation.json`。

本轮报告、机器摘要、源码输入和失败现场在专用缓存的 `evidence/continuation-1235-20261113T152157390451Z`；正式性能在 `evidence/performance-investigation/20261113T182953264318Z-final-diagnostics-perf`。`evidence-index.json` 与 `artifact-manifest.json` 同时绑定调查目录、正式比较和引用的独立运行目录，`report-verification.json` 记录封存核验；最终提交和当前入口见 `.cache/android/release-stability-latest.json`。ARM64 真机、实际 16 KB 页面、高刷新率、TalkBack 等仍待验，不能宣称 P4 完整结束。


## 2026-11-13：上轮独立工作树 Release 历史记录

以下数字对应交接提交 `0fc9993` 的当轮 APK，不是 2026-11-14 最终诊断版的结果。

本轮基线是 `d8a859c`，工作树为 `.`，分支 `codex/android-dev`。缓存和证据独占 `.cache/android/release-stability-worktree`，设备为 API 35 x86_64 的 `StudyIME_Stability_API35_20261113`／`127.0.0.1:5581`，ADB server 为 `5041`；另一窗口的源码、构建输出及模拟器安装保留。

**已修复重开绘制漏样本；历史运行时崩溃的根因仍未确认。** 原 APK 第三组在第 14 次重开时有 14 次显示请求、13 个绘制样本，键盘截图已显示，IME 和系统 PID 未变，也没有本次新 fatal。最小 Compose 用例确认父 `ComposeView.invalidate()` 会复用子内容显示列表。显示请求现在更新一个仅在绘制中读取的状态，实际绘制回调才消费计时；没有人为补计样本。

最小用例按服务真实顺序在绘制前初始化计数器，同一测试 APK 在原版失败、修复版通过。早期测试在首次绘制中创建状态，和服务的真实次序不同；该失败和修正后的对照均保留，未作为 Release 验收。Release 另完成 40/40 次真实键盘重开。

当前 Release SHA-256：`f62e302a49a0918bcbd1133c1ed68c727175c5afd1a5674c2ba0bc48db850506`。正常覆盖安装、保留应用数据，API 35 编译状态为 `verify / reason=install`；R8 和资源压缩开启。

| 连续组 | 按键／重开 | 候选绘制 p95 / p99（ms） | 暖态重开 p95（ms） | 结果 |
| --- | --- | ---: | ---: | --- |
| 1 | 180 / 20 | 37.65 / 54.22 | 57.88 | 覆盖、输入正文、运行时和暖态延迟目标通过 |
| 2 | 180 / 20 | 37.15 / 46.37 | 53.16 | 同上 |
| 3 | 180 / 20 | 34.61 / 42.32 | 38.02 | 同上 |

三组都严格取得 180 个交付、绘制和有序阶段配对，20/20 次就绪重开；无合并、丢弃或待绘制输入，无漏字或重复提交。IME PID 始终为 `11384`，系统关键 PID 和 boot ID 未变。各次日志边界、APK 前后摘要、正文和慢样本均保留。

两组各 20 次新进程启动 p95 为 **736.66／640.43 ms**，未达到 500 ms；因此整体比较 `completed=true`、`coverageComplete=true`、`threeWarmGroupsPassed=true`，但 `passed=false`。旧交接中的 450.83／465.85 ms 属于先前环境，不能覆盖本轮未达标结果。计时终点仍为首次 `onStartInputView` 至就绪 Compose 绘制，排除回调前进程创建和物理显示延迟。

随后固定同一 Debug 编辑器和测试 APK，仅覆盖安装不同 Release 做各 20 次启动对照：原 `d8a859c` p95 为 **631.91 ms**，修复版为 **595.26 ms**，两组均超标且无运行时故障。该对照没有证明启动超标由本轮改动造成，也不抵销先前两组失败；全部记录在本轮 `startup-apk-control` 目录，结束后已普通覆盖安装恢复当前 Release。

性能组在 `.cache/android/evidence/performance-investigation/20261113T134252455751Z-show-draw-fixed`，定位及最小复现在 `.cache/android/evidence/investigation-20261113T122422Z`。摘要入口为 `.cache/android/release-stability-latest.json`。原生库和生成词库逐字节不变，生成的 ART baseline profile 随 DEX 更新；当前 APK 的 6 个原生输入、8 个打包库及 ELF／ZIP 16 KB 静态对齐重新核对通过，已有原生功能和视觉证据按改动范围复用。

历史 21 个去重故障包括 15 个 IME、1 个测试／编辑器、5 个系统事件。旧 crash buffer 跨运行复用，不能把其全部异常归到当前测试；AOT／关闭 R8 等旧实验也不构成正式通过。本轮工具加入持续日志标记、进程与 boot 身份、固定 APK 前后校验、逐词／精确样本断言，并把覆盖结果和延迟结果分开。主机侧 32 项检查通过。未找到可复现历史 ART／Compose 运行时故障的正向最小用例；不据此排除应用、ART 或虚拟化层。

当前 Release 的 **16 项真实输入交互、18 项生命周期检查**重新通过，运行前后 APK 身份一致且未记录本次 runtime fatal；报告在本轮 `affected-regressions` 目录。Debug／Release Lint 对最终源码无 Error 或 Fatal，构建和 32 项主机检查日志在专用缓存 `logs` 中。既有 38 项布局、42 张截图和原生引擎用例按未改动范围复用，没有重做或冒称真机验收。

独立纯 Java 混合引用／浮点／双精度／长整数及 JIT／GC 探针完成 40 万轮，未观察到异常；它仅为未触发对照，不能用来确认或排除历史崩溃根因。额外 API 30 兼容性补测尚未运行：新的独立 AVD 三次在创建数据分区前因 D 盘空间不足退出，缩小分区参数未生效。环境准备失败、启动命令和日志见本轮 `api30-environment-outcome.json`；它们不是应用运行时崩溃。API 35 AVD 已关闭并保留数据，其他任务的模拟器未操作。

## 2026-11-11：初始开发预览历史记录

以下 APK、API 30 和性能数字仅对应当时的交付，不是当前修复版的验收结果。

**开发预览的功能、原生布局和构建验证已完成，性能初始目标尚未全部达成。** 采用用户已确认的“先模拟器、真机稍后补验”安排。版本为 `0.1.0-preview.1`，使用本机开发签名；最终源码提交、交付文件和摘要由 `.cache/android/delivery-latest.json` 及交付目录的 `manifest.json` 确定。P4 的性能优化与真机验收继续保留为未完成项。

## 构建与被测环境

| 项目 | 实际值 |
| --- | --- |
| 分支／工作目录 | `codex/android-dev`；`.` |
| Release 包 | `org.studyime.android`；R8 优化与资源压缩；16,156,378 字节（约 16.16 MB／15.41 MiB） |
| Release SHA-256 | `4b9c0c0914dafd2cec3a087914c0165c95a703884278391f44bd5fa16a457d8f` |
| Debug SHA-256 | `ba8b638e0ae0b9f7015f4bcb5df29cd3b604910dcf8e610fc444341e14e8d10f` |
| 测试 APK SHA-256 | `11ea8d899396cba6ed9257008ad10020d51b32a5353a15653bacafd7e5acbfe2` |
| 系统 | AOSP Android 11／API 30 x86_64；`Android/sdk_phone_x86_64/generic_x86_64:11/RSR1.210722.013.A2/10067904:userdebug/test-keys` |
| 模拟器 | WSL2／KVM，`StudyIME_API30`，2 vCPU、SwiftShader、名义 60 Hz 虚拟显示、4 KB 页面；客体报告 RAM 2,028,600 kB（约 1.93 GiB）；ADB `127.0.0.1:5555` |
| 布局 | 默认 1080×2340、440 dpi；矩阵使用 320 dpi 和对应宽度覆盖 320／360／390／430 dp |
| 平台配置 | minSdk 29、targetSdk／compileSdk 35；打包 `arm64-v8a` 和 `x86_64` |
| 工具链 | Temurin JDK 21.0.7+6、Gradle 8.11.1、AGP 8.9.2、Kotlin 2.1.20、Compose BOM 2025.04.01、NDK 27.2.12479018、Rust 1.88.0 |
| 词库 | 版本 `edb1ed9f5b709883961a`；121,505 条中文、200 条英文；人工审核通过 0 条 |

新增工具、下载、模拟器与构建输出实际存放在 `.cache/android`，通过目录联接保留工程内路径。Windows／词库开发目录 `.` 未被用作本任务输出目录。

## 本轮实现与修复

- 候选采用英文在上、中文在下；任意一行的普通点击和空格提交中文，长按后明确点击“输入英文”才提交完整词表值。英文开关、中文学习、三种拼音方案和逐词遗忘保持独立的会话保护。
- 浅深色、按键层次、9 dp 圆角、窄屏候选数量、大字号功能图标、横屏、设置页与固定的释义操作区按原型方向实现。复核截图后修正 320 dp／1.3 倍字号下的“中/英”标签裁切，提前使用单字和图标。输入动画与引擎工作线程分离。
- 输入框重新连接时，只有输入框身份、可见预编辑、选区与引擎版本一致才恢复组合；旧候选动作失效。隐藏重开保留同一输入框的组合，旧触摸不能落到新输入框。
- 资源逐文件核对摘要，部署中断或损坏时重建资源；新引擎初始化失败可回退到已验证的旧版本。用户词典始终独立保存。
- 无障碍通知在界面遍历后发送，并在发送时检查服务仍已启用，修复关闭 UiAutomation 后的实际崩溃。首个候选出现时保持候选区高度，修复快速触摸被窗口重布局取消的问题。
- 浏览器回归使用本轮唯一标记的新页面，避免把上一轮合成文本误认为本轮输入。此测试连续两次运行通过；短信只写虚构号码的草稿并清空，没有发送消息。
- 打包核对实际安装 APK、测试运行器、当前源码／资源、原生符号剥离结果、截图、录像和报告摘要，拒绝混用旧验证材料。

## 功能与布局结果

报告保存在 `.cache/android/evidence`，日志保存在 `.cache/android/logs`。设备报告记录本次实际安装的 APK 和测试运行器摘要；Release 交互由独立 Debug 编辑器／运行器驱动，输入法本身运行 Release APK。

| 范围 | 最终结果 | 报告 |
| --- | --- | --- |
| 真实 JNI／Rime／Lua | 600 条三方案中英文用例＋33 项引擎、学习、隐私及句柄检查通过 | `native-engine-report.json` |
| 资源恢复 | 11 项通过：中断、损坏、失败回退、重建索引、释放与用户数据保留 | `resource-recovery-report.json` |
| 真实输入连接 | 16 项通过：中英文、长按、重复动作、表情删除、焦点与特殊编辑器动作 | `release-ime-interaction-report.json` |
| 生命周期 | 14 项通过：重启、选区、旧触摸、延后方案、旋转后重新聚焦、快速输入、重开及进程重建 | `release-lifecycle-report.json` |
| 独立应用 | 4 项通过：浏览器中文、完整英文、多行及短信草稿中文 | `release-app-editor-report.json` |
| 特殊场景 | 15 项通过：长／缺／部分释义、取消、长按、删除、数字密码、网址、拼音分隔、导航和大字号浮层 | `scenario-report.json` |
| 视觉矩阵 | 38 项结构检查、42 组原生截图通过；字体与宽度组合逐图复核 | `visual-matrix-report.json`、`visual-review.json` |
| 对比度／触区 | 测量的普通文字颜色组合最低 4.89:1；4 个工具按钮均达到 48 dp 触区 | `design-measurements.json` |
| 原生交互录像 | 9 个操作步骤通过；780×1688、36.34 秒未剪辑视频完整解码，抽帧复核 9 张 | `release-preview-recording-report.json` |
| 关闭无障碍后的输入 | 4 项通过：进程启动、中文提交、隐藏后新输入框及进程持续运行 | `release-unassisted-input-report.json` |
| 新进程启动与内存 | 10 个新进程测量完成；首次可用绘制 p95 3.09 秒，未达到 500 ms 初始目标 | `release-startup-report.json` |
| Rust／Kotlin | 16 项 Rust 策略与 3 项 Kotlin 提交保护检查通过 | `rust-policy-tests.log`、JUnit XML |
| Android lint | Debug／Release 均无 Error 或 Fatal；保留依赖更新、屏幕尺寸 API、KTX 及 Debug 合成文案提示 | `lint-results-debug.xml`、`lint-results-release.xml` |
| 原生打包 | 6 个准备好的原生输入＋2 个 AndroidX 原生库的 ABI、依赖闭包、ELF 与 ZIP 16 KB 对齐通过 | `apk-native-layout.json` |

浏览器为 AOSP WebView Shell 1.0，WebView 83.0.4103.120；短信为 AOSP Messaging 1.0.001。这里没有微信或用户日常应用的通过记录。

浏览器测试曾因复用旧页面残留合成文本而失败，加入新页面标记后连续两次通过。后续整套运行中，测试浏览器在加载前被 SIGKILL 终止，系统没有提供终止原因；启动独立的新浏览器进程后，最终 APK 的 4 项检查通过。两类失败与最终通过报告分开保留，没有把页面未启动算成输入成功。

图像审阅由本次开发助手对原生截图和录像抽帧执行，和布局结构断言分别记录；没有冒充用户验收或真实 TalkBack 使用。视觉参考仍是 `prototype/android/light.png`、`dark.png` 和 `concept.html`。

## 性能与内存

同一 Release APK 完成两组暖态测量，每组 180 次按键、30 次连续选词及 20 次键盘重开，正文校验通过、未记录候选绘制前的按键合并。首组在应用测试后执行；复测在新进程测量后、停止专用测试浏览器后执行。设备、词库与输入序列相同；两组数据都保留，不能把较快的一组外推成稳定真机结果。

| 指标（ms） | 首组 | 复测 | 初始目标与结果 |
| --- | ---: | ---: | --- |
| 按键到 InputConnection 交付 p95 | 35.30 | 19.33 | 记录基线 |
| 按键到 Compose 绘制 p95 | 84.43 | 58.38 | ≤50；均未达标 |
| 按键到 Compose 绘制 p99 | 324.20 | 78.29 | ≤100；复测达到，存在波动 |
| 暖态显示到可用绘制 p95 | 90.99 | 76.21 | ≤100；两组达到 |

已部署资源下的 10 个新进程：首次 `onStartInputView` 回调到可用绘制 p50 1016.23 ms、p95 3085.80 ms，500 ms 初始目标未达到。未清理操作系统文件缓存，此计时也不包含回调前的进程创建时间。首轮隔离资源部署加引擎初始化为 1151 ms，仅一次样本。

计时边界为按键回调入队至 InputConnection 交付／Compose 绘制记录，包含对应排队时间，不含触摸识别、GPU 呈现及物理屏幕延迟。按键序列使用合成文本，计时计数器本身只保存有界耗时数据，不记录原始输入、候选或应用名称。下一步需分析候选绘制的尾部延迟和新进程资源校验／引擎初始化成本，再在真机确认预算。

稳定运行内存和反复开关后内存从 Release 进程的 `dumpsys meminfo` 取得。生命周期报告里的 `sameProcessPssKb*` 来自 Debug 测试进程，不能当成独立 Release 输入法的内存。

首组 PSS 为 51,355→51,514 KiB（增加 159 KiB）；复测为 52,341→51,039 KiB。10 个新进程就绪后 PSS 为 42,471–57,418 KiB，内核记录的进程 RSS 高水位为 178,300–183,680 KiB（约 174–179 MiB）。PSS 和 RSS 的统计口径不同，这些短序列不构成长时间内存稳定性结论。安装后的 `base.apk` 分配块为 15,784 KiB；未把它当成包含编译缓存、资源和用户词典的全部安装占用。

原始材料为 `release-performance-report.json`、`performance/run-after-apps.json`、两组 meminfo／gfxinfo、`performance/device-environment.json`、`release-startup-report.json` 及 `startup` 目录。交付 `manifest.json` 和 `README.txt` 明确携带性能目标未全部达成的状态。

## 未完成的设备验收与已知边界

- 真机 arm64、Android 10 下限和更新的 Android 版本尚未实测；实际 16 KB 页面设备、60 Hz／高刷新率物理呈现、触感、邻键误触体验和真实 TalkBack 仍待补验。
- 已测同一输入框的框架重启和隐藏重开。旋转导致 Activity 重建时保留正文；应用可能失去编辑器焦点，继续输入用例会重新点选输入框并确认焦点，尚不能保证恢复原 Rime 分段组合。进程重建后保留应用正文，不恢复上一次进程的原生候选会话。
- 隔离目录中实际首次资源部署与引擎初始化为 1.151 秒（一次样本）。新进程测量与已部署资源下的暖态输入分别报告，仍不覆盖回调前的进程创建、物理屏幕呈现、完整冷启动 PSS 峰值或安装后全部私有数据占用。
- 锁屏／解锁、OEM 编辑器及微信等常用应用仍需在目标设备检查。模拟器的浏览器／短信结果不外推到这些应用。
- 200 条英文释义均待人工审核；当前是离线开发预览，不自动接入另一聊天的扩充草稿，不宣称正式词库审核完成。

## 构建与交付复现

使用 [Android README](../android/README.md) 的准备、构建、安装与验证命令。每次功能修改后运行受影响检查；最终交付核对完整报告集合。原生源码修改必须先用 NDK／Rust 脚本重建，再组装 APK，不能只运行 Gradle。

本次属于锁定输入下的增量原生／Gradle 构建，未把最终源码 ZIP 在另一台机器上做全新空缓存复建。源码包包含构建脚本、锁文件及许可；第三方原生源码归档包含实际构建使用的来源与补丁，依赖收据记录其余 Maven／Cargo／工具链来源。

提交后运行 `python -X utf8 tools/android/package_preview.py`，生成 APK、项目源码、第三方原生源码、验证证据、公开签名与权限清单及 SHA-256 清单。打包脚本要求当前工作区干净，核对报告所用 Debug／Release／测试 APK、源码输入、图像和录像；开发签名私钥不进入归档。历史失败尝试保留在本机 evidence/history 与日志目录，不能作为成功证据。
