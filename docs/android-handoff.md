# 拾词 Android：新窗口开发上下文

更新于 2026-11-08。本文件是安卓开发的新窗口入口；完整需求与验收以 [安卓开发计划](android-plan.md) 为准。

用户准备在新窗口开始完成安卓开发。已选定 **Kotlin／Jetpack Compose 界面＋Rust 业务核心＋现有 librime／Lua 引擎规则**，并认可保存的手机键盘设计参考。下一项是实际执行 P0，再按 P1–P4 推进可安装、可日常使用的安卓开发预览。美观是首版要求，需要和输入功能一起完成。

## 1. 工作目录与分支

| 用途 | 本机目录 | 分支 |
| --- | --- | --- |
| 新窗口的安卓开发 | `.` | `codex/android-dev` |
| 另一个聊天的 Windows／词库开发 | `.` | `codex/technical-spike` |

安卓独立 worktree 已创建并绑定过本聊天，新窗口应选择上表的安卓目录。开工先核对实际状态：

```powershell
Set-Location -LiteralPath '.'
git rev-parse --show-toplevel
git status --short --branch
git log -5 --oneline
git worktree list
```

交接整理前，安卓 HEAD 为 `7b16a7d`，工作区干净；本轮在其上补充接续文档。规划提交为 `a4d859b`，Windows 功能基线为 `7713de7`。这些是检查点，不要求新窗口回退到这些提交；实时文件和 Git 状态优先。

安卓编辑、暂存、提交和构建输出均留在安卓 worktree。保留 `.` 中另一任务的文件、分支与后台工作；无需再次整理原目录或创建新的分支／worktree。两个 worktree 的工作文件与索引独立，共享 Git 对象和分支引用，后续合并同一文件仍可能需要处理普通 Git 冲突。详见 [并行开发说明](parallel-development.md)。

## 2. 当前已经完成什么

- **完成**：安卓与 Rust 计划、P0–P4 验收条件、独立 worktree、用户认可的交互设计参考，以及 Windows 后续接入共享核心的路线。
- **可以复用**：现有全拼／自然码／小鹤方案、Lua 释义与提交规则、本地数据流程、Windows 会话动作保护及相应行为样本。
- **尚未开始**：Android 工程、Rust crate、JNI 桥接和 Android 平台的 Rime 构建。当前没有开发 APK、模拟器输入闭环或安卓真机测试结果。
- **工具链待定位与配置**：本轮 PATH 未检出 `java`、`javac`、`cargo`、`rustc`、`adb`、`gradle`、`cmake`、`ninja`；未发现默认 Android SDK、Android Studio、Cargo 或 Java 安装目录。Python 可用，路径为 `D:/Python/Python313/python.exe`。此检查不证明工具没有装在其他位置，新窗口应先调查再补齐环境。
- **数据可用于开发预览**：现有 200 条英文释义仍待人工审核，可用于标明性质的开发验证。词库扩充是另一聊天的任务，其进程和数量会变化；旧文档中的 30／80／300 等数字不是实时进度。移动端开工不依赖扩充完成，不在安卓任务中重启外部模型请求或手写扩充词库。

本轮只准备开发上下文，没有执行 P0，也没有安装或升级开发工具。旧文档中的 Windows 构建、桌面测试、安装／卸载和词库授权属于相应历史任务，不能自动变成安卓任务的待办。

## 3. 已确认的产品与视觉方向

- 首版提供 26 键、全拼、自然码双拼、小鹤双拼，以及英文／数字／符号输入、删除、空格和编辑器动作键。
- 候选采用**英文在上、中文在下**。点击任意一行和普通空格选词都提交中文；长按或释义按钮查看全文，只有明确点击“输入英文”才提交英文。
- “显示英文释义”与“记住中文选词习惯”是独立设置；保留跨三种方案的本地中文学习、暂停学习和逐词遗忘。
- 采用 Kotlin／Compose 定制键盘与设置页。已认可的参考为浅色、清浅绿强调色 `#2d6b53`、柔和有层次的按键、9 CSS px 圆角、英语显示开启；同时保存深色参考。原生尺寸使用 dp／sp，并在设备上调整。
- 浅深色、字号、键盘高度、轻微触感／按压反馈、长词／缺词、窄屏、横屏、系统 inset 和放大字体均属于首版设计范围。详细视觉条件在计划第 2 节，P2 必须交付原生还原和真实交互观察。
- 首版离线运行，使用本地词库。密码及禁止个性化学习的编辑器需要特殊处理，用户词典和 Android 备份规则按计划实现。
- 九宫格、滑行、语音、手写、账号、云同步、整句 AI 翻译、英语预测纠错和复杂复习系统留待后续。

设计文件位于 [手机原型目录](../prototype/android/README.md)：[可操作网页](../prototype/android/index.html)、[设计源片段](../prototype/android/concept.html)、[浅色参考](../prototype/android/light.png)、[深色参考](../prototype/android/dark.png)。它们是网页示意与固定例词，不能算作 Kotlin／Android 的运行结果，示例释义也不能导入生产词库。本机聊天可视化目录无需复制，仓库中已保存接续所需参考。

Windows 后续在安卓核心稳定后，通过窄 C ABI 逐步复用 Rust 的会话与候选业务；现有 C++ TSF／Win32 界面／服务和 librime 继续保留。W0–W3 是后续路线，不作为本轮安卓 P0–P4 的前置任务。

## 4. 接续阅读与源码入口

先阅读 [完整安卓计划](android-plan.md) 和 [设计参考说明](../prototype/android/README.md)，再根据实施阶段读取下列入口。已有 [通用交接](handoff.md) 和 [项目进度](progress.md) 保存大量 Windows 历史，安卓范围和当前下一步以本文件及安卓计划为准。

| 要解决的问题 | 现有入口 |
| --- | --- |
| 跨任务目录与缓存边界 | [parallel-development.md](parallel-development.md) |
| 英文查询、资格和完整英文提交 | [study_core.lua](../src/study/lua/study_core.lua)、[Lua 入口](../packaging/data/rime.lua) |
| 会话版本、候选绑定及动作失效规则 | [RimeSession.cpp](../src/study/RimeSession.cpp)、[SessionActions.cpp](../src/study/SessionActions.cpp) |
| 三种拼音方案 | [全拼](../packaging/data/study.schema.yaml)、[自然码](../packaging/data/study_double_pinyin.schema.yaml)、[小鹤](../packaging/data/study_flypy.schema.yaml)、[双拼说明](double-pinyin.md) |
| 中文学习和逐词遗忘 | [word-frequency.md](word-frequency.md)、[现有 Rime 构建与补丁逻辑](../tools/packaging/build_rime.py) |
| 引擎与依赖来源 | [product-sources.lock.json](../licensing/product-sources.lock.json)、[来源恢复逻辑](../tools/packaging/product_sources.py) |
| 词库导出、审核与许可 | [lexicon.md](lexicon.md)、[data/lexicon](../data/lexicon/README.md)、[中文基础数据](../data/chinese/README.md)、[software-licenses.md](software-licenses.md) |
| 现有行为回归样本 | [双拼检查](../tools/packaging/verify_double_pinyin.py)、[学习检查](../tools/packaging/verify_frequency.py)、[阶段 6 记录](../experiments/phase6/README.md) |

现有 Rime 锁定提交为 `1c23358157934bd6e6d6981f0c0164f05393b497`，librime-lua 为 `e3912a4b3ac2c202d89face3fef3d41eb1d7fcd6`；具体档案、摘要与依赖仍以锁文件为准。Windows 构建脚本可参考其固定输入与补丁，不是 Android 构建入口。特别注意 `Memory::OnCommit` 中的 `study_user_learning` 暂停学习补丁；仅复制 YAML 无法保留这一行为。

## 5. 新窗口从 P0 开始实施

1. **确认环境并固定版本**：核对已有 JDK、Android SDK／NDK、Rust、CMake 及可用模拟器／设备。暂以 Android 10／API 29 起、`arm64-v8a` 为目标，`x86_64` 用于模拟器；具体手机尚未指定。这些是规划假设，compileSdk、targetSdk 和各工具版本在 P0 选择、记录并锁定。Gradle 工程应提供 Wrapper，不能把全局 Gradle 缺失当作必须安装独立 Gradle 的结论。
2. **建立最小工程**：按计划新增 `android/app`、`crates/study-core`、`crates/study-rime-sys`、`crates/study-rime`、`crates/study-android`，先打通 Kotlin→JNI→Rust。上述目录是拟建位置，交接时尚不存在；Windows bridge 留待后续阶段。
3. **接入真实 Rime／Lua 与开发数据**：从固定来源恢复所需源码，用 NDK 构建 Android 原生库，携带现有必要补丁。资源部署使用安卓自己的目录与输出；Windows DLL、二进制缓存和另一个 worktree 的用户词典不能用作安卓产物。检查目标 ABI、C++ 运行时和 16 KB 页面兼容性。
4. **完成 P0 的真实证明**：Kotlin 成功加载 Rust 动态库，Android 环境中初始化固定 Rime／Lua，输入拼音并返回真实候选。记录构建命令、版本、ABI、数据来源、运行环境和结果；静态编译、模拟器运行、真机运行分别记录。
5. **继续 P1–P4**：P1 完成 IME 生命周期、预编辑与中文／英文提交闭环；P2 按参考实现完整视觉与触摸；P3 接入两套双拼、学习、设置和恢复；P4 完成实际设备／应用验证与开发预览 APK 交付。阶段通过后继续推进，设备或外部条件缺失时准确标出受影响的验收项。

计划第 10 节中的“本次仅规划”等描述属于最初规划阶段。新窗口收到开发指令后应进入实现，不需要再次仅编写一份同内容计划。

## 6. 实现时保留的关键约定

- Kotlin 拥有 `InputConnection`，区分 composing text 与最终提交，根据 `EditorInfo` 处理发送、搜索、下一项、完成和换行。
- 引擎事件经一个串行工作线程进入 Rust／Rime。每次返回不可变完整快照，携带输入框代次、会话版本、组合和候选，避免按键路径上大量细碎 JNI 调用。
- 输入框切换立即提升代次，丢弃旧结果；每条提交使用唯一 ID，连接失效或结果不确定时不盲目重发，旧结果不能写入新输入框。
- 英文必须来自引擎重新验证的完整词表值。仅整段组合且光标位于末尾时允许提交；部分组合、过期候选、关闭英语显示均拒绝英文动作并保留正常输入状态。
- Compose 在 InputMethodService 中的 Lifecycle／SavedState／ViewModel owner 与释放要在 P1 验证；磁盘部署、动画和词典编译不阻塞按键线程。
- Rime context／commit 借用文本及时复制并配对释放；初始化与关闭只有明确拥有者；panic、编码、空值、句柄和错误在 FFI 边界处理。
- 数据升级保留用户词典，三种方案共用本机学习数据。新词库按明确版本与审核状态接入，开发预览不能表述为正式审核通过。

## 7. 验证与进度记录

阶段完成时记录源码提交、工具链、ABI、命令、产物路径与摘要，以及实际通过和未完成的条件。保持本文件的当前断点和安卓计划勾选项同步，保存可复现的构建说明，让后续聊天可以继续。

针对变化运行必要检查；历史 Windows 用例可移植，但原有 Windows 报告和网页截图都不能充当 Android 已通过的证据。原生截图／交互记录、模拟器结果和真机结果需说明各自环境。现有人工词库审核不会因完成 APK 而自动完成，最终交付按开发预览说明数据状态。

## 8. 可复制到新窗口的开场指令

```text
请接续完成拾词输入法的 Android 开发。
工作目录：.
使用现有分支 codex/android-dev，先核对当前 Git 状态。
先读 ./docs/android-handoff.md，并按其中链接阅读完整计划和设计参考。
已确定 Kotlin／Compose 界面＋Rust 业务核心＋现有 Rime／Lua，美观是首版要求。
从 P0 的工具链与 Kotlin→Rust→Rime 最小工程开始实际实现，按 P1–P4 推进可安装的开发预览 APK，保留真实验证证据与未完成项。
只在安卓 worktree 开发；. 的 Windows／词库任务由另一聊天负责。
```
