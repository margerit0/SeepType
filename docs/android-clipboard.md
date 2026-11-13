# Android 剪贴板历史

本功能在 `codex/android-clipboard-history` 独立分支开发，基于已有默认／轻彩皮肤的 `ec9d133`。工作树为 `.`。

## 使用

- 键盘待机工具栏点剪贴板图标，首次点“开启剪贴板历史”。也可在应用的“键盘设置 → 剪贴板”打开“保存剪贴板历史”。默认关闭。
- 正在输入拼音时，长按候选展开按钮打开快捷设置，再点剪贴板图标。面板沿用键盘高度，横屏时使用整个键盘宽度。
- 点条目粘贴完整文本；有拼音组合时先完成当前中文选词，再粘贴。选中的正文会被替换，换行、空格和 emoji 按原样提交。
- 最多保存 50 条，重复文本移到最近位置。最多置顶 10 条；置顶排在前面，容量满时淘汰最旧的未置顶条目。
- 每条可取消置顶或删除。清空与关闭功能均需在界面确认，包含置顶条目；关闭同时停止记录。
- 删除历史不改变 Android 系统剪贴板。相同系统剪贴板版本不会因重开键盘或进程重建而自动恢复到历史；主动重新复制会产生新记录。

## 范围与隐私

记录仅在功能开启、输入法服务运行且 Android 允许读取剪贴板时进行。输入法重新显示时也会检查当前剪贴板，但无法找回服务未运行期间被覆盖的内容，不提供常驻后台服务或云同步。

密码（含数字密码）及设置 `IME_FLAG_NO_PERSONALIZED_LEARNING` 的输入框暂停记录并禁用历史入口。剪贴板带 `android.content.extra.IS_SENSITIVE` 标记时不读取文本；受保护期间只记住该系统剪贴板版本，回到普通输入框后不会补录它。

只接受单条纯文本值，不打开 URI／内容提供者，不处理图片、Intent 或多条 ClipData。忽略空白、NUL、无效 Unicode 和超过 **4096 UTF-8 字节**的文本，不做截断；约相当于 1365 个常见汉字或 1024 个四字节 emoji。此上限与现有引擎的 `literal` 事件一致。

历史在应用私有的 `noBackupFilesDir/clipboard/history-v1.json` 中保存，不写入日志，不参与 Android 云备份或设备迁移。卸载会删除本机历史。序列化的 I/O 队列配合 `AtomicFile` 保存；写入失败会保留上次成功状态并在界面提示，不把失败的删除显示为成功。

## 实现与验证入口

- `android/app/src/main/java/org/studyime/android/clipboard`：容量／去重／置顶策略、原子文件存储、串行仓库和系统剪贴板监听。
- `ui/ClipboardPanel.kt`：原生历史面板；两种皮肤、浅深色、横屏、大字号及无障碍节点。
- `ime/StudyInputMethodService.kt`：受保护输入框策略、监听生命周期、当前输入框代次核对；粘贴仍走原串行引擎和提交 ID 防重逻辑。
- JVM 测试覆盖容量淘汰、置顶上限、去重、关闭清空、删除后不重录、受保护版本以及 UTF-8／Unicode 边界。
- `ClipboardHistoryTest` 在 Debug 原生输入页使用合成剪贴板，检查真实粘贴、选区、旧触摸、隐私、文件重读和屏幕布局，结果输出到专用缓存。
- `ClipboardPersistenceTest` 通过独立 Debug 测试进程操作 Release 键盘，强制结束再重开输入法进程，核验置顶恢复、真实粘贴及删除后不重录。

持久化测试在强停后显式打开应用并核对 PID 已变化，再重新绑定输入法。Android 对短时间内重复强停的服务可能延迟重新启动；本用例验证新进程读取历史文件，不把系统自动重连等待当成持久化或启动性能结果。

本任务构建产物在 `D:/StudyIME-Android-Clipboard-Cache`，与原工作树输出隔离；复用已有 JDK／SDK 工具以及复制到本任务缓存的原生库、资源和 Gradle 依赖。没有修改 Rust／JNI 输入，因此此次无需重建原生库。

在本工作树根目录执行：

```powershell
python -X utf8 tools/android/build.py tests
python -X utf8 tools/android/build.py apk --debug
python -X utf8 tools/android/build.py lint
python -X utf8 tools/android/run_device_checks.py install --serial 127.0.0.1:5555
python -X utf8 tools/android/run_device_checks.py clipboard --serial 127.0.0.1:5555
python -X utf8 tools/android/collect_device_evidence.py clipboard --serial 127.0.0.1:5555
python -X utf8 tools/android/build.py apk
python -X utf8 tools/android/device.py --serial 127.0.0.1:5555 install -r android/app/build/outputs/apk/release/app-release.apk
python -X utf8 tools/android/run_device_checks.py clipboard-persistence --serial 127.0.0.1:5555 --ime-package org.studyime.android
```

`clipboard` 使用 Debug 应用自己的仓库与合成输入页；不传 `--ime-package`。报告为 `.cache/android/evidence/clipboard-history-report.json`，截图在同目录的 `clipboard/`。设备序列号须以实际 `devices -l` 为准；模拟器测试不能替代真机及厂商后台策略验收。

## 本轮验证

2026-11-13 完成设备检查，2026-11-14 整理原生截图和交付文件。全部结果与同一组 APK 摘要核对，汇总保存在 `.cache/android/evidence/clipboard-feature-summary.json`。

| 项目 | 结果 |
| --- | --- |
| JVM 单元测试 | 11 项通过，其中 8 项剪贴板策略测试 |
| Debug／Release 编译与 Lint | 通过，Lint 无错误；警告记录保留在报告中 |
| Android 15 / API 35 剪贴板场景 | 68 项检查通过 |
| Android 11 / API 30 剪贴板场景 | 68 项检查通过 |
| Release 新进程恢复与删除后不重录 | 16 项检查通过，两次核对 PID 变化 |
| Release 原有输入交互回归 | 16 项检查通过 |
| 原生布局截图 | 每台模拟器 8 张，已核对两种皮肤、浅深色、320 dp／2 倍字号和横屏 |

按设备归档的报告与截图在 `.cache/android/evidence/clipboard-api35`、`clipboard-api30`；Release 的结果为 `release-clipboard-persistence-report.json` 和 `release-ime-interaction-report.json`。失败尝试保留在 `evidence/history` 与各次构建日志中，未改写为通过结果。

开发 APK：`D:/StudyIME-Android-Clipboard-Cache/delivery/StudyIME-clipboard-history.apk`（16,478,981 字节，含 arm64-v8a 与 x86_64）。SHA-256：`f9275f6ff6fd2e69984fdf5bc1d15e543716fa3e420d5d2f4d703d1ff714bd2c`。该文件与本工作树的 Release 输出一致，使用原有本地开发签名。
