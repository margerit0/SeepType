# 阶段 3：隔离技术验证

2026-11-01，v0.5 设计基线的核心隔离验证通过。此目录是测试程序，**不是系统输入法或安装包**。它没有运行 WeaselSetup、WeaselDeployer、WeaselServer，没有注册 TSF 或修改系统输入设置。

## 结果与预览

| 检查 | 结果 |
| --- | --- |
| 实际 Rime/Lua 候选与提交 | [18/18 通过](results/engine.json) |
| 原生创建、绘制和内部交互 | [27/27 通过](results/native-ui.json)，只向自身窗口发送同进程消息 |
| 96/120/144/192 DPI 布局参数 | [24/24 通过](results/native-layout.json) |
| 真实桌面鼠标与快捷键 | [未测试](results/desktop-interaction.json)：用户已授权，但电脑操作工具仍未放行 ui_probe |

![浅色原生候选条](results/previews/native-light.png)

![深色原生候选条](results/previews/native-dark.png)

另见 [长英文](results/previews/native-long.png)、[第二页](results/previews/native-page-two.png)、[学习关闭](results/previews/native-closed.png)。这些图片直接保存自真实 Weasel 绘制缓冲区，并非桌面截图或 HTML 模拟。当前实际窗口 DPI 为 144；96/120/192 仅做参数测量，没有切换系统显示设置。

## 依赖与重复构建

已用 VS 2019 Build Tools 16.11.48、MSVC 14.29 工具集、Windows SDK 10.0.19041.0、Python 3.13 构建。C++ ATL x86/x64 已经用户单独授权安装。构建环境仅对当前子进程生效；可用 `STUDY_VS_ROOT` 指向已有 VS2019，不修改系统 PATH。

实际 DLL 是 Weasel 0.17.4 安装包中的 **x86** 版本，运行时报告 librime 1.13.1；宿主也编译为 x86。另一个官方 x64 librime 归档只供头文件和版本资料。固定 URL、源码提交及 SHA256 见 [dependencies.lock.json](dependencies.lock.json)。

从项目根目录的 PowerShell 依次执行：

```powershell
python experiments/phase3/fetch-deps.py
python experiments/phase3/prepare-runtime.py
./experiments/phase3/build-engine.cmd
python experiments/phase3/verify-engine.py
python experiments/phase3/prepare-ui-patch.py
./experiments/phase3/build-ui.cmd
python experiments/phase3/verify-native.py
```

遇到任何非零退出码先停止排查。`build-ui.cmd debug` 可生成保留栈帧的未优化诊断构建，map 文件和崩溃报告用于定位；当前构建不依赖本机曾失败的 PDB 调试链接。

下载仅来自锁文件中的官方来源并校验哈希。两个安装格式的 EXE 只交给解包工具读取，不执行安装；Boost 只提取头文件。没有自动安装工具链、更新依赖或改系统配置的脚本。本次从已有固定缓存构建并重新验哈希；全新机器/空缓存流程尚未测试。

`runtime/shared` 是上游方案、词典和 OpenCC 的独立副本；`runtime/user` 是实验目录，中文用户学习关闭。准备脚本只更新实验目录，不与已安装 Rime 的用户数据混用。故障检查使用独立的 missing-user / malformed-user。

## 人工运行

完成上述准备后，可以在当前目录树中双击 `build/ui_probe.exe`；它会从自身位置定位项目根目录。也可在项目根目录执行：

```powershell
./experiments/phase3/build/ui_probe.exe
```

不要只复制 EXE 到别处运行，它依赖项目中的 `.cache/` 和 `runtime/`。

宿主提供苹果、多候选、长英文、缺词示例，以及翻页、学习开关、英文动作和浅深色按钮。空格/数字/普通候选点击用于中文；`Ctrl+Shift+Enter` 用于英文；F8 是实验学习开关，退格用于修改拼音。所有按钮都属于测试宿主，正式产品仍以 v0.5 原型的工具区与菜单为准。

真实电脑操作工具的访问许可仍未生效。内部测试已验证上述处理路径，但未声称物理键盘、鼠标、窗口焦点或其他应用的实际操作通过。

## 代码与测试边界

- `engine_probe.cpp` / `verify-engine.py`：官方 C API 加载真实 DLL，执行自拟拼音与合成按键；含候选顺序、开关、长词、第二页英文、分段保护、词表缺失/损坏和暖态对照。
- `fixtures/lua/study.lua`：启动时精确词表加载；ShadowCandidate 保留原候选。英文动作重新读取真实选中候选和完整词值，拒绝无释义/关闭学习/未完成分段，保留中文组合。
- `StudyEngine.*`：把 Rime API 与 ATL 编译单元分开，修复本机二者头文件组合导致的静态初始化异常；不修改引擎。
- `StudyLayout.*`：真实 StandardLayout 子类，英文在上，序号和中文在下，整项共享点击区域，长英文由 DirectWrite 省略。
- `ui_probe.cpp` / `verify-native.py`：真实 Win32 + WeaselUI 宿主；启动、参数测量、同进程消息回归、绘制缓冲区导出。没有 OS 输入注入或桌面捕获。PNG 编码使用 Python 标准库。
- `patches/weasel-ui-spike.patch`：一个上游文件增加 10 行，分别用于实验布局选择和仅观察自身绘制缓冲区；不是正式 IPC 或配置方案。

21 个自拟词对全部是 **test-only**，未人工验收，不得直接作为正式分发词库。时延统计包含解码和第一页候选生成，不是单次查词耗时，也不能外推大词库。来源与许可见 [项目记录](../../docs/data-sources.md)。

完整 Weasel 服务/TSF、会话 IPC、正式英文菜单/浮层、工具区、设置、两种原生动画、翻页定宽、安装卸载及记事本/浏览器/VS Code 兼容性仍未完成或未测试。

## 结束与清理

关闭宿主窗口即结束实验；没有安装输入法，因此没有系统输入法卸载步骤。`.cache/`、`build/`、`runtime/` 是忽略的可重建材料，不进入 Git；源代码、锁文件、补丁和验证结果进入 Git。不要清理或修改用户现有的 Rime 数据目录。
