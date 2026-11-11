# Windows 一键交互验收

在当前 Android worktree 中双击根目录的 **启动安卓验收.cmd**，会打开“拾词 · Windows 验收面板”和可用鼠标操作的手机窗口。

手机画面来自本机 Android 模拟器；键盘、候选、释义和设置运行实际 Release APK。普通输入、搜索、密码等输入框由独立 Debug APK 中的原生 `EditText` 承载。验收面板不绘制或模拟产品键盘，也不需要浏览器。

## 使用

1. 等面板显示“已就绪”，在手机画面中点按字母键。全拼方案可试 `gongyuan`。
2. 点候选的任意一行输入中文；按住候选打开释义，再点“输入英文”提交英文。右键相当于 Android 返回，`Alt+F` 切换全屏。
3. 在面板中选择输入场景并点“打开场景”。支持普通、多行、搜索、双输入框、密码、数字、邮箱、网址、电话、禁止个性化以及只记录动作的发送场景。
4. 点“键盘设置”操作 APK 中的真实设置，包括全拼／自然码／小鹤、英文显示、中文学习、主题、键盘高度、字号和动画；“应用首页”可体验原有启用状态和随手记。
5. “显示与布局”可切换标准竖屏、320 dp 窄屏、横屏、系统字号和系统浅深色。独立设置为浅色或深色的键盘不会跟随系统主题。
6. 点“保存截图”或“开始录像”记录问题。“结束录像”保存 MP4；每段最多 120 秒，到时自动收尾。录像过程中先结束录像再切换显示预设。

鼠标点按、长按和拖动对应真实 Android 触摸操作。当前输入法的拼音流程面向触屏键盘；电脑字母键通过 Android 外接键盘路径输入，不能当作触屏拼音按键验收。截图和录像也不用于测量手机物理显示延迟。

“重新开始输入”和切换场景只重开测试输入页，不清空词典或设置。关闭面板会结束本次录制、关闭手机窗口，并恢复启动前的屏幕尺寸、密度、字体、旋转、休眠、系统主题和默认输入法；在 APK 内手动修改的偏好保留。模拟器继续运行，方便下次快速进入。只关闭手机窗口后，可用面板的“手机窗口”重新打开。

## 位置与版本

工具与输出遵循现有 `.cache/android-cache-location.json`；本机实际位于：

- `.cache/android/acceptance/tools`：锁定版本的 scrcpy，保留上游完整包与随附文件。
- `.cache/android/acceptance/captures`：PNG、MP4 和同名 JSON；面板“打开记录”直接打开此目录。
- `.cache/android/acceptance/sessions`：每次启动的日志、安装 APK 摘要、初始设备状态和操作事件。
- `.cache/android/acceptance/restore-state.json`：异常关闭后的待恢复状态。下次正常启动在同一模拟器上先恢复，再开启新会话。

面板显示实际 Release 版本和 APK 摘要。安装前后均校验设备中的 APK；版本相同时跳过安装，更新时只使用覆盖安装，不卸载或清除数据。保存证据前再次核对设备 APK，防止把更换后的程序误记为原版本。截图／录像不自动宣称“人工验收通过”。

## 启动与构建

当前 Windows 开发机已准备好 Python、JDK、SDK、WSL2／KVM 和项目 AVD。入口复用这些环境；首次自动下载约 11 MB 的 scrcpy，之后离线使用。下载 URL、版本和 SHA-256 见 `android/acceptance-tools.lock.json`，官方发布地址不可用时使用同一上游的资产 API，仍要求相同摘要。

入口只连接本机 `StudyIME_API30` 开发模拟器，核对 AVD 名称和模拟器属性后才安装、切换输入法或修改显示。不会自动选中 USB 手机、另一 AVD 或远程设备，不会终止共享 ADB 服务，也不改变全局 PATH 或 Windows 输入法。

源码和现有 APK 组装记录不一致时，入口使用现有 Gradle 流程增量组装 Release／Debug，采用仅本次有效的较低内存参数。原生 Rust／C++／工具链源码有变化时会提示先执行 [Android README](../android/README.md) 中的原生构建步骤，避免把旧 `.so` 当成新代码。新的工作机仍需先按该文档准备完整开发环境。

也可以从仓库根目录运行：

```powershell
python -X utf8 tools/android/acceptance.py
python -X utf8 tools/android/acceptance.py --serial 127.0.0.1:5555
python -X utf8 -m unittest tools.android.test_acceptance -v
```

启动错误会保留在该会话的 `launcher-errors.log`；构建详细日志在 `.cache/android/logs/gradle-acceptance.log`。关闭时恢复失败会保留待恢复记录，不伪报恢复完成。不要通过删除整个缓存来重试，这里还保存开发签名、词库构建输入和已有验证材料。

## 验证范围

2026-11-11，已在当前 Windows 开发机完成：

- 14 项工具检查：设备隔离、覆盖安装、APK 身份、截图失败处理、录制状态、恢复失败保留和单实例锁等。
- 28 项入口集成检查：11 种原生输入页、4 个 Release 页面、窄屏／横屏／字号／主题、截图、录像、窗口重开、异常退出后恢复以及正常关闭恢复。报告在 `.cache/android/acceptance/launcher-verification.json`。
- 16 项真实 Release 输入检查：中文候选、空格、长按释义、完整英文提交、删除、焦点切换、编辑器动作、密码、邮箱和数字等；使用现有 `ImeInteractionTest`，报告在 `.cache/android/evidence/release-ime-interaction-report.json`。
- Release／Debug 组装与 `lintDebug` 通过；最终构建日志为 `.cache/android/logs/gradle-acceptance-final.log`。验收用增量构建以 448 MB 堆和 Serial GC 在本机通过，没有改变全局配置。
- 手动触发的原生录像为 590×1280 H.264、7.473 秒，已完整解码；PNG／MP4 都带实际 APK 摘要。
- 将本项目模拟器正常关机后，从根目录入口重新启动成功；保留安装数据并核对 Release APK，记录在 `.cache/android/acceptance/cold-start-check.json`。

本轮 Release APK SHA-256 为 `4b9c0c0914dafd2cec3a087914c0165c95a703884278391f44bd5fa16a457d8f`；加入中文手动体验说明的 Debug 宿主为 `c06f213a7bbdfe82d4942feb8ad09d5da3e394c006d47584083ffb6484abce14`。这些是开发入口验证，不代表用户已经验收通过；手机触感、真机性能和应用兼容性仍按安卓计划补验。

Windows 面板和真实手机窗口已实际观察，远程操作中出现过前台焦点变化和窗口激活失败；完整输入回归由模拟器上的原生 UI 检查执行，没有把每项都记为 Windows 物理鼠标观察。已修复实际检查发现的单实例锁读取冲突、新版 scrcpy GPU 就绪日志识别，以及低可提交内存下的首次增量构建失败。

既有发布材料仍由 `docs/android-validation.md` 和 `delivery-latest.json` 标识；本轮未重新导出发布 ZIP。开发入口的截图与录像独立保存，重跑的原生输入报告由原有工具保留旧报告后更新。
