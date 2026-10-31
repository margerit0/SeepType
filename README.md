# Windows 英语学习输入法（工作名）

在正常中文拼音输入过程中显示简短英文释义。v0.5 设计已确认，阶段 3 的核心隔离验证已通过；目前交付的是原生测试宿主，尚无系统输入法安装包。

**设计试用：[轻量候选条原型 v0.5](prototype/index.html)**（浏览器直接打开）。紧凑双行、圆角、学习开关和翻页动画的完整交互仍以此为基线。旧两套方案保留在 prototype/archive/v0.2。

**原生验证：[构建与运行说明](experiments/phase3/README.md)**。当前工作目录中可运行 `experiments/phase3/build/ui_probe.exe`，需保留项目中的依赖缓存与实验数据目录。它使用真实 WeaselUI 和安装包内的 Rime DLL，不注册或安装系统输入法。

![真实原生绘制缓冲区预览](experiments/phase3/results/previews/native-light.png)

2026-11-01：18 项 Rime/Lua 检查、28 项原生内部交互检查、24 组 DPI 参数布局测量通过；18 项隔离窗口桌面检查已完成（上轮恢复 12 项，本轮新增 6 项）。真实键鼠验证发现并修复了系统现有 IME 截走宿主字母按键的问题。预览来自原生绘制缓冲区，不是桌面截图。

- [需求与范围](docs/product.md)
- [设计输入与待比较方案](docs/design.md)
- [技术调查、证据与验证计划](docs/architecture.md)
- [数据来源与许可](docs/data-sources.md)
- [进度及新窗口接续入口](docs/progress.md)

已确认采用开源路线，目标为 Windows 11 x64、简体中文全拼。下一步将实验中的学习逻辑和布局接入正式会话、菜单、设置与原生动画；完整 Weasel/TSF 构建、应用兼容性和安装/卸载仍未测试。
