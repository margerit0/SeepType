# 拾词输入法（StudyIME）

在正常中文拼音输入过程中显示简短英文释义。沿用已确认的 v0.5 双行候选、工具区、独立释义、设置和两种动画，现提供 x64 开发预览运行包、源码材料及安装/卸载脚本。实际安装、注册和部分桌面验收已完成；当前已注销，最后的占用文件清理等待 Windows 重启，正式发布条件仍未满足。

**安卓开发：[开发预览与接续入口](docs/android-handoff.md)**。独立 worktree 使用 `codex/android-dev`；已实现 Kotlin／Compose 键盘、Rust 会话核心和 Rime／Lua，支持全拼、自然码和小鹤双拼。构建与安装见 [Android README](android/README.md)，真实版本、原生视觉及模拟器结果见 [验证记录](docs/android-validation.md)。用户选择先用模拟器，真机与高刷新率等项目另行补验；200 条英文释义仍是待人工审核的开发数据。

**工作区新增：[自然码双拼与小鹤双拼](docs/double-pinyin.md)**。设置可选择全拼、自然码双拼或小鹤双拼，三者共享[中文选词学习](docs/word-frequency.md)、逐词遗忘和英文释义。600 条中英文回归、148 项双拼／会话检查、词频与候选窗回归、原生设置窗口检查通过。当前为内部 dev.3 构建，尚未导出新版运行／源码 ZIP 或安装；[后续待办](docs/optimization-todo.md)已更新。

**设计试用：[轻量候选条原型 v0.5](prototype/index.html)**（浏览器直接打开）。紧凑双行、圆角、学习开关和翻页动画的完整交互仍以此为基线。旧两套方案保留在 prototype/archive/v0.2。

**当前原生入口：[实现、构建与验证](docs/native-ui.md)**。运行 `python experiments/phase4/start-text-host.py --service-x64` 打开真实 TSF 双文本区宿主，`python experiments/phase4/start-settings.py` 打开设置。需保留当前仓库、缓存和实验数据；这些命令不注册或安装输入法。

![v0.5 原生绘制缓冲区预览](experiments/phase4/results/previews-v05/dpi-192.png)

高 DPI 修正后 50 项组件检查和 29 项 x64 TSF/UI 检查通过；此前 27 项 TSF/UI 与 7 项选词 IPC 的 x86/x64 报告及 16 项 x64 编辑回归报告保留。程序验证与[安装后的真实桌面观察](docs/installed-desktop-acceptance.md)分别记录；Chrome 原生网址识别失败后，用户选择跳过浏览器测试。

**最新进展：[拾词输入法（StudyIME）开发预览包](docs/packaging.md)**。产品名称已确认，新代码采用 GPL-3.0-or-later，词库单独使用 CC BY-SA 4.0。dev.2 已移除产品 WTL 依赖，从固定源码构建仅含 Lua 的 Rime，接入 121,505 条可追溯中文基础记录；[许可与来源](docs/software-licenses.md)及默认只预演的安装/卸载脚本随包提供。已验证实际安装和注销，修复 PowerShell 收据更新及 TSF 空注册表目录残留。

针对性检查包括打包、安装预演、独立目录运行（含 22 项真实 Rime IPC）和原生预览像素比对。同机中文路径中的离线原生复建已通过；脚本修订后在同一独立源码目录重新验证并导出运行包，对应关系见 [打包记录](docs/packaging.md)。28 项注册恢复内存模拟的既有证据保留；本机注销、占用重试与 8 项空 TIP 清理检查另有实际记录。

**词库：[200 条审核稿与导出流程](docs/lexicon.md)**。[离线审核页](docs/lexicon-review.html)支持逐条修改和记录决定。当前人工通过 0 条，产品包使用明确标识的审核预览；默认阶段 4 交互宿主仍用 21 条测试词对。既有 25 项审核流程报告保留；由于更换了引擎与中文基础数据，200 条释义和中英文提交已在当前包上重新核验。下面保留早期阶段摘要。

**英语扩充：[离线目标清单与外部 API 流程](docs/lexicon-expansion.md)**。已固定 5,040 个 IELTS 工作目标与 8,845 个 CEFR 分级词形，合并为 10,625 个目标；20 个场景主题和首批 300 项请求计划已准备。用户指定外部 Gemini 生成；当前 `/v1` 认证读取正常，但模型在服务默认分组无可用渠道，4 次接口生成尝试均失败，新译词仍为 0。用户正调整渠道，保留 Gemini。

2026-11-01：18 项 Rime/Lua 检查、28 项原生内部交互检查、24 组 DPI 参数布局测量通过；18 项隔离窗口桌面检查已完成（上轮恢复 12 项，本轮新增 6 项）。真实键鼠验证发现并修复了系统现有 IME 截走宿主字母按键的问题。预览来自原生绘制缓冲区，不是桌面截图。

新增的[会话动作与英文菜单](experiments/phase4/README.md)通过 20 项真实会话检查，另有 16 项菜单桌面观察已从中断聊天恢复。**真实 Weasel 客户端与服务端的 27 项跨进程检查通过**，涵盖英文提交、学习开关、失焦、会话重建、服务重启和并发连接。此次没有重跑阶段 3 或已有菜单检查。

- [需求与范围](docs/product.md)
- [设计输入与待比较方案](docs/design.md)
- [技术调查、证据与验证计划](docs/architecture.md)
- [数据来源与许可](docs/data-sources.md)
- [进度及新窗口接续入口](docs/progress.md)

目标为 Windows 11 x64，支持简体中文全拼、自然码双拼和小鹤双拼。后续为 dev.3 统一打包、重启后的最后卸载清理、现有 200 条词义的人工复核及多显示器验收；浏览器按用户要求跳过。原三项许可/来源问题已处理。详见 [进度](docs/progress.md) 与 [交接](docs/handoff.md)。
