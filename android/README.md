# 拾词 Android 开发预览

Kotlin / Jetpack Compose 输入法，Rust 管理会话与候选动作，NDK 构建固定的 librime / Lua。最低 API 29，目标 API 35；同时打包 `arm64-v8a` 和 `x86_64`。功能范围及验收见 [完整计划](../docs/android-plan.md)，接续状态见 [交接文档](../docs/android-handoff.md)，实际版本、设备与限制见 [验证记录](../docs/android-validation.md)。

## 离线词库

Android 使用[共享开发词库快照](../data/lexicon-expansion/android-runtime/snapshot.json)。全拼、自然码和小鹤均使用同一快照，候选栏和英文提交仍只使用该候选／读音的默认英文义项。Android 公开预览采用 AI 语义审校与自动引擎回归，不设置人工逐条复审门槛；见[发布说明](../docs/releases.md#维护者首次公开发布)。

来源、摘要与后续同步方式见 [词库快照](../data/lexicon-expansion/android-runtime/README.md)。常规 APK、测试和一键验收构建会检查并刷新旧词库资源，不需要重新编译 JNI 库，也不需要访问 Windows 工作目录。

另附 [420 条影视与游戏专名](../data/lexicon-expansion/android-names/README.md)，由 Wikidata 固定修订和开发侧校对读音生成，随 APK 离线更新。三种方案沿用原有用户词典，无联机查词或专题包下载。实测分别见 [首版验证](../docs/android-offline-names-validation.md) 与 [作品名补录验证](../docs/android-offline-names-supplement-validation.md)。

## 单词详情

点底栏的详情键或长按候选，打开沿用当前皮肤的浮卡。浮卡按实际读音把默认译法置顶，并列展示该读音的其他义项、词性和中文用法；有搭配和中英例句时一并展示。可以对照用法，但只有「输入 <默认英文>」会提交英文。关闭不会改变输入，隐藏英文时仍可打开选词学习操作。

原创搭配和中英例句随词库批次更新。详情资源独立放在 APK 中，打开卡片时才按需读取。没有例句的词只展示已有内容。

## 构建环境

从仓库根目录执行以下 Python 命令。当前构建脚本以 Windows x64 为宿主，需要 Python 3.11+、Rust 1.88.0 的 MSVC 宿主工具链，以及已有的 Visual Studio C++ Build Tools / CMake / Ninja。脚本不会更新全局工具或系统 PATH。

固定版本见 [toolchain.lock.json](toolchain.lock.json)、[sdk.lock.json](sdk.lock.json)、[Gradle 依赖锁](app/gradle.lockfile) 和 [Cargo.lock](../Cargo.lock)。完整 Temurin JDK、SDK、NDK、Gradle 分发和 Android Rust 标准库由准备脚本下载、核对摘要并安装到专用缓存。无需全局 Gradle 或 Android Studio。

Android SDK、模拟器和构建缓存默认放在 `.cache/android`。如需使用其他本地磁盘，请按迁移脚本为当前检出配置缓存。

另一台电脑可使用默认的 worktree 内缓存；若需在全新空目录迁移，可使用 `tools/android/migrate-cache.ps1 -Destination <专用目录>`。脚本逐文件校验后才移除原缓存。构建时可通过 `STUDY_RUST_BIN`、`STUDY_JAVA_HOME`、`STUDY_CMAKE` 和 `STUDY_NINJA` 指定已经安装的相应工具。

```powershell
python -X utf8 tools/android/build.py prepare
python -X utf8 tools/android/build.py apk
```

首次准备会下载锁定输入并构建两个 ABI。后续改动 Rust 或 C++ 后，分别运行下面的增量构建，再组装 APK：

```powershell
python -X utf8 tools/android/build_rust.py --abi all
python -X utf8 tools/android/build_native.py --abi all
python -X utf8 tools/android/build.py apk
python -X utf8 tools/android/verify_artifact.py --apk android/app/build/outputs/apk/release/app-release.apk
```

发布优化的开发包位于 `app/build/outputs/apk/release/app-release.apk`，包名为 `org.studyime.android`。`build.py apk --debug` 生成包名带 `.debug` 的测试版本，两者独立保存本机词频。开发包使用缓存内生成的本地开发签名，不是商店发布签名。保留该签名才能覆盖安装而不清除应用数据；密钥不进入 Git。

## 皮肤

键盘设置可独立选择“默认 / 轻彩”与“自动 / 浅色 / 深色”。轻彩使用离线打包的 Quicksand 字体、原生矢量双层键标和原布局；换肤保留当前输入。待机点设置图标，输入时长按候选展开按钮即可进入。使用方法、字体来源和原生验证见[皮肤说明](../docs/android-skins.md)。

拼音还没选词时，按回车或空格会原样提交字母（例如 `ni`），不会同时插入空格、换行或触发发送／搜索。要输入汉字，直接点候选词；没有待选拼音时，回车和空格照常使用。

在普通文本框混输时，输入 `home` 可以直接点同名候选。切到「英」后，第一候选保留原始大小写，输入至少两个字母可看到最多三条离线补全，例如输入 `hom` 后点 `home`。空格提交原文并加空格，回车提交原文后执行输入框动作。补全词形来自 CEFR-J 1.5，按 wordfreq 3.1.1 的英语词频排序。密码、邮箱、网址和要求关闭建议的输入框使用原有输入方式。

候选卡片按显示的中英文内容适配宽度；竖屏候选条放不下时可左右滑动，展开按钮和下方键位保持不动。展开后，超宽词条会换行显示。

## 表情符号

工具栏第二个按钮打开表情面板，可在字母页和「123／符号」页使用；正在输入拼音时，展开候选也能进入表情面板。支持按分类浏览、查看本机最近使用的表情，以及长按有变体的表情选择肤色。点选后会先确认尚在编辑的拼音，再插入完整的 Unicode 表情；可以连续选择，点「返回键盘」回到原键盘页。

面板使用 AndroidX Emoji Picker，只提交文本，不下载表情包，也不需要联网。可显示的表情取决于设备和接收应用的字体。密码、数字、邮箱／网址、要求 ASCII 或要求停用个性化的输入框不启用表情入口。

## 数据和恢复

中文基础词典使用固定的 CC-CEDICT / wordfreq / Unihan 数据；英文释义和补充读音来自上述开发快照。`prepare_data.py` 不启动词库扩充或联网查词。原始来源、摘要、署名和审核记录见快照及 APK 许可资料。

资源按摘要生成版本，在后台校验、部署和编译，成功后切换活动版本。用户词典独立保存在 `noBackupFilesDir/rime/user`；三种方案共用它。应用不申请网络权限，用户词典和设置均显式排除 Android 备份。卸载应用仍会删除其本机数据。

## 模拟器和验证

**Windows 手动交互验收：** 在仓库根目录双击 `启动安卓验收.cmd`，打开本地验收面板和真实 APK 的可操作手机窗口。支持输入场景、设置、窄屏／横屏、截图和录像，详见 [一键验收说明](../docs/android-acceptance.md)。

本机使用已有 WSL2 / KVM 运行无窗口 AOSP Android 11 x86_64 模拟器，AVD 和系统镜像也在专用 D 盘缓存。以 `devices -l` 的实际序列号为准；本次 Windows ADB 使用 `127.0.0.1:5555`，脚本缺省值仍为 `emulator-5554`：

```powershell
python -X utf8 tools/android/emulator.py install
python -X utf8 tools/android/emulator.py start
python -X utf8 tools/android/device.py devices -l
python -X utf8 tools/android/build.py tests
python -X utf8 tools/android/build.py apk --debug
python -X utf8 tools/android/run_device_checks.py install --serial 127.0.0.1:5555
python -X utf8 tools/android/run_device_checks.py native --serial 127.0.0.1:5555
python -X utf8 tools/android/run_device_checks.py ime --serial 127.0.0.1:5555
python -X utf8 tools/android/run_device_checks.py word-details --serial 127.0.0.1:5555
python -X utf8 tools/android/run_device_checks.py offline-names-engine --serial 127.0.0.1:5555
python -X utf8 tools/android/run_device_checks.py offline-names-ui --serial 127.0.0.1:5555
python -X utf8 tools/android/run_device_checks.py offline-names-coverage --serial 127.0.0.1:5555
python -X utf8 tools/android/build.py lint
```

`native` 在隔离的合成用户词典中执行真实 JNI / Rust / Rime / Lua 验证，包含三种方案各 234 条中英文样本（包括保留的旧候选、新增词、补充读音和多音字）、候选动作保护、隐私、学习和遗忘。`ime` 使用真实 Android 编辑器和系统输入法窗口操作；调试用编辑器不会打进发布优化包。测试结果及安装 APK 摘要位于 `.cache/android/evidence`，命令日志位于 `.cache/android/logs`。

优化 APK 的输入检查使用独立 Debug 编辑器与测试运行器，实际键盘是 Release 进程。先安装 Release，再运行相关检查；每次开始前都会读取设备中的 APK 并验证摘要：

```powershell
python -X utf8 tools/android/device.py --serial 127.0.0.1:5555 install -r android/app/build/outputs/apk/release/app-release.apk
python -X utf8 tools/android/run_device_checks.py ime --serial 127.0.0.1:5555 --ime-package org.studyime.android
python -X utf8 tools/android/run_device_checks.py emoji --serial 127.0.0.1:5555 --ime-package org.studyime.android
python -X utf8 tools/android/run_device_checks.py lifecycle --serial 127.0.0.1:5555 --ime-package org.studyime.android
python -X utf8 tools/android/run_device_checks.py apps --serial 127.0.0.1:5555 --ime-package org.studyime.android
python -X utf8 tools/android/run_device_checks.py performance --serial 127.0.0.1:5555 --ime-package org.studyime.android
python -X utf8 tools/android/run_device_checks.py recording --serial 127.0.0.1:5555 --ime-package org.studyime.android
python -X utf8 tools/android/collect_device_evidence.py recording --serial 127.0.0.1:5555
python -X utf8 tools/android/check_unassisted_input.py --serial 127.0.0.1:5555
python -X utf8 tools/android/measure_startup.py --serial 127.0.0.1:5555 --samples 10
```

`apps` 只操作模拟器中的离线浏览器页面与虚构号码短信草稿，不发送消息。`recording` 保存未剪辑的原生屏幕录像；后续的 `check_unassisted_input.py` 在无障碍已关闭时验证普通输入，不启用 UiAutomation。

`measure_startup.py` 只在专用模拟器上更换新输入法进程，保留已部署词库与用户数据，记录每个新进程首次显示回调到可用绘制的耗时、可读取的 RSS 高水位与就绪后 PSS。它不清理操作系统文件缓存，也不把回调前的进程创建时间或就绪后 PSS 当成完整冷启动／PSS 峰值。

Debug 侧的 `recovery`、`scenarios`、`visual` 分别覆盖资源故障、特殊输入／导航／设置，以及四种宽度 × 四档字号 × 浅深色。运行后用 `collect_device_evidence.py visual`、`scenarios`、`performance` 收集相应截图和诊断文件，均需传相同的 `--serial`。`verify_design.py` 测量真实主题颜色及 320 dp 截图中的工具触区；逐图审阅另记 `visual-review.json`。

集成候选可用 `draw` 检查计数清零后不会主动触发新绘制，用 `reopen --ime-package org.studyime.android` 检查 Release 键盘连续隐藏和重开（均需传相同的 `--serial`）。模拟器工具不应用于真机；真机使用独立的[限定回归流程](../docs/android-phone-validation.md)。

原生 ELF / APK 的 16 KB 对齐检查与实际在 16 KB 页面设备运行是两项不同验证。模拟器测试也不能替代真机触感、60 Hz / 高刷新率表现及常用第三方应用验收；交付记录会分别列出结果和待补验项。

## 交付开发包

`build.py` 在成功组装后记录源文件、准备好的原生库／资源、构建日志和 APK 的摘要。只修改文档不改变 APK 构建输入；修改代码后需要重新组装并更新受影响的设备报告。原生校验还会用固定 NDK 重做符号剥离，核对 APK 中由本工程准备的 6 个原生输入及 2 个 AndroidX 原生库的 ABI、依赖与 16 KB 布局。

完成验证和图像审阅后，在 `codex/android-dev` 提交源码与文档，再运行：

```powershell
python -X utf8 tools/android/package_preview.py
```

脚本要求工作区干净，拒绝功能验证未通过或与当前 APK／测试运行器不匹配的报告，以及已变化的截图或录像。性能初始目标按实测值核对，未达标状态写入交付清单和说明，不冒充生产验收通过。输出 APK、该提交的源码 ZIP、实际第三方原生源码 ZIP、验证 ZIP、公开签名、依赖清单和 SHA-256 清单。最新位置记录在 `.cache/android/delivery-latest.json`，本机实际输出位于 `.cache/android/delivery`；开发私钥不进入这些材料。

## 源码边界

- `app`：系统输入法、InputConnection、串行引擎工作线程、Compose 界面和本机设置。
- `../crates/study-core`：输入框代次、会话版本、候选目标、提交 ID、配置及模式策略。
- `../crates/study-rime-sys`、`study-rime`：窄 C ABI、原生资源拥有关系及权威 Lua 协议。
- `../crates/study-android`：不透明 JNI 句柄、线程约束和异常边界。
- `native`、`../tools/android`：固定来源恢复、暂停新学习补丁、NDK / Rust / Gradle 构建与验证。

新增源码采用 GPL-3.0-or-later，第三方组件保留原许可；词库来源和审核状态与软件实现分别记录。
