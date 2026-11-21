# 拾词 Android：开发预览接续

更新于 2026-11-11。完整产品范围见 [安卓计划](android-plan.md)，实际构建、报告与限制见 [验证记录](android-validation.md)，构建命令见 [Android README](../android/README.md)。

当前已实现 Kotlin／Compose 界面＋Rust 会话核心＋固定 Rime／Lua，并完成本次 P0–P3 的模拟器范围及开发预览材料。P0／P1 检查点为 `b5fa54f`；后续源码提交与交付目录由 `.cache/android/delivery-latest.json` 标识。P4 的性能目标尚未全部达到，真机等项目也仍待补验；不要重新从空工程开始。用户已允许在合适时提交，所有提交保持在现有 Android 分支。

**新增 Windows 手动验收入口：** 根目录双击 `启动安卓验收.cmd`，会自动准备可操作的真实 APK 手机窗口，并提供输入场景、原生设置、显示预设、截图和录像。入口源码为 `tools/android/acceptance.py` 与 `acceptance_ui.py`，使用现有 Release 输入法和 Debug 原生输入页；使用方法、本轮 14／28／16 项检查及冷启动验证见 [一键交互验收](android-acceptance.md)。产物在专用缓存的 `acceptance` 目录。本轮未重新导出开发预览 ZIP，原交付材料和真机待办仍保留各自范围。

**2026-11-20 · Android 词库同步：** 已导入 Windows 分支 `1977d31` 的已接入开发快照：13,137 条英文开发记录，包含按读音匹配默认释义的运行逻辑。来源及复建见 [快照说明](../data/lexicon-expansion/android-runtime/README.md)。资源版本 `9efd4fb487a254b47f31` 已组装进 Debug 和 Release APK，并逐字节核对词典及 Lua；Android API 30 x86_64 模拟器实际通过 702 条三方案词库用例和 36 项引擎／会话检查。随后已将带相同词库的 Release APK 重建为 `0.1.0-preview.3`（`versionCode=3`），以实际 APK 清单为准。未在真机安装。下文的 200 条词库和原 APK 摘要属于历史验收构建，不代表当前源码。

## 工作目录与授权

| 用途 | 目录 | 分支 |
| --- | --- | --- |
| Android | `.` | `codex/android-dev` |
| 另一聊天的 Windows／词库任务 | `.` | 由另一任务管理，不能在这里修改或切换 |

源码、暂存与提交只在 Android worktree。用户已批准将本任务新增的工具、下载、模拟器和构建产物放在 `.cache/android`，通过目录联接保留工程路径；`.cache/android-cache-location.json` 记录归属。继续复用已有 JDK／Rust／Visual Studio 工具，不重复整理另一工作树。分工历史见 [并行开发说明](parallel-development.md)。

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
- 本轮最终构建：Release `0.1.0-preview.1`，约 16.16 MB，SHA-256 `4b9c0c0914dafd2cec3a087914c0165c95a703884278391f44bd5fa16a457d8f`。完整 Debug／测试 APK 摘要见验证记录。
- 本轮已通过 600 条三方案中英文用例、33 项引擎检查、16 项 Release 输入、14 项生命周期、11 项资源恢复与 15 项特殊场景；浏览器／短信草稿 4 项通过。38 项布局检查、42 组原生截图与 36.34 秒原生录像已完成，并复核了窄屏、大字号和导航边界。
- 暖态候选绘制 p95 两次为 84.43／58.38 ms，尚未达到 50 ms 初始目标；复测 p99 为 78.29 ms、暖态重开 p95 为 76.21 ms。10 个新进程首次显示回调至可用绘制 p95 为 3085.80 ms，500 ms 目标也未达到。完整样本、内存、计时边界及未达标标记随开发预览保留。
- 修复过无障碍关闭后发送通知的崩溃；无障碍关闭输入回归已加入交付检查。浏览器测试每次加载带唯一标记的新页面，防止上轮合成内容残留。

最终交付必须由当前源码与实际安装 APK 的报告共同支持。`.cache/android/evidence/history` 保留旧报告与失败尝试；不要把它们改成当前通过结果。`.cache/android/assembly-debug.json`、`assembly-release.json` 绑定源码、生成资源、原生库与构建日志；`package_preview.py` 会拒绝不匹配的报告、截图或录像。

## 已确认的产品约定

1. 候选英文在上、中文在下。点任何一行都提交中文；拼音输入中按回车或空格原样提交拼写；长按／释义按钮只打开面板，明确点击“输入英文”才提交英文。
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

1. 先读取验证记录和 `.cache/android/delivery-latest.json`，核对当前源码及 APK 摘要；已有功能、图像和录像证据不因切换聊天而失效。
2. 下一轮重点是候选 p95 和新进程启动性能：先对资源逐文件校验、引擎初始化及 Compose／模拟器调度做分段分析，使用相同设备与输入序列比较，保留未达标样本。交付脚本 `tools/android/package_preview.py` 会把实际性能状态写入清单。
3. 用户已选择先模拟器。真机 arm64、实际 16 KB 页面、物理触感／60 Hz／高刷新率、真实 TalkBack、锁屏和常用应用仍需补验；不要宣称 P4 全部完成。
4. 旋转后的正文与继续输入已验证，跨 Activity／进程重建的原生分段组合不保证恢复。详细限制保持在验证记录。
5. 词库扩充由另一聊天负责；本轮不启动模型请求，不将未审核扩充草稿自动导入，不把旧文档数字当成其当前进度。Windows W0–W3 也不是本轮前置任务。
