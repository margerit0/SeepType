# 拾词 Android 开发预览

Kotlin / Jetpack Compose 输入法，Rust 管理会话与候选动作，NDK 构建固定的 librime / Lua。最低 API 29，目标 API 35；同时打包 `arm64-v8a` 和 `x86_64`。功能范围及验收见 [完整计划](../docs/android-plan.md)，接续状态见 [交接文档](../docs/android-handoff.md)。

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

## 数据和恢复

首轮使用固定 CC-CEDICT / wordfreq / Unihan 数据生成 121,505 条中文词条，携带 200 条**待人工审核**的英文释义。`prepare_data.py` 复用现有词库流程，不加入网页原型中的示例，不启动词库扩充请求。原始来源、摘要、署名和审核记录随生成资源保存。

资源按摘要生成版本，在后台校验、部署和编译，成功后切换活动版本。用户词典独立保存在 `noBackupFilesDir/rime/user`；三种方案共用它。应用不申请网络权限，用户词典和设置均显式排除 Android 备份。卸载应用仍会删除其本机数据。

## 模拟器和验证

本机使用已有 WSL2 / KVM 运行无窗口 AOSP Android 11 x86_64 模拟器，AVD 和系统镜像也在专用 D 盘缓存。Windows ADB 连接 `emulator-5554`：

```powershell
python -X utf8 tools/android/emulator.py install
python -X utf8 tools/android/emulator.py start
python -X utf8 tools/android/device.py devices -l
python -X utf8 tools/android/build.py tests
python -X utf8 tools/android/build.py apk --debug
python -X utf8 tools/android/run_device_checks.py install
python -X utf8 tools/android/run_device_checks.py native
python -X utf8 tools/android/run_device_checks.py ime
python -X utf8 tools/android/build.py lint
```

`native` 在隔离的合成用户词典中执行真实 JNI / Rust / Rime / Lua 验证，包含三种方案各 200 条中英文样本、候选动作保护、隐私、学习和遗忘。`ime` 使用真实 Android 编辑器和系统输入法窗口操作；调试用编辑器不会打进发布优化包。测试结果及安装 APK 摘要位于 `.cache/android/evidence`，命令日志位于 `.cache/android/logs`。

原生 ELF / APK 的 16 KB 对齐检查与实际在 16 KB 页面设备运行是两项不同验证。模拟器测试也不能替代真机触感、60 Hz / 高刷新率表现及常用第三方应用验收；交付记录会分别列出结果和待补验项。

## 源码边界

- `app`：系统输入法、InputConnection、串行引擎工作线程、Compose 界面和本机设置。
- `../crates/study-core`：输入框代次、会话版本、候选目标、提交 ID、配置及模式策略。
- `../crates/study-rime-sys`、`study-rime`：窄 C ABI、原生资源拥有关系及权威 Lua 协议。
- `../crates/study-android`：不透明 JNI 句柄、线程约束和异常边界。
- `native`、`../tools/android`：固定来源恢复、暂停新学习补丁、NDK / Rust / Gradle 构建与验证。

新增源码采用 GPL-3.0-or-later，第三方组件保留原许可；词库来源和审核状态与软件实现分别记录。
