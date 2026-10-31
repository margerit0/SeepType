# 阶段 4：会话动作与原生英文菜单

2026-11-01。已开始分步正式实现，本批完成可复用的会话版本模块、统一 Lua 英文动作，并在现有隔离宿主接入 Win32 英文菜单。完整 Weasel 服务/IPC/TSF 尚未接入，当前仍不是系统输入法安装包。

## 实现

- `src/study/SessionActions.*` 为每个会话分配独立身份和递增版本。输入、翻页、选中项变化、学习开关、失焦使旧动作失效；切回相同候选或重建会话也不能复活旧动作。
- `src/study/lua/study_core.lua` 是唯一的词表查询、提交资格和英文提交实现。键盘及菜单均检查真实选中候选的完整范围、光标和学习状态，再提交完整词值。缺词不显示其他上游注释为英文；原始候选仍由 ShadowCandidate 保留。
- `StudyEngine` 适配器先向 Lua 查询目标，菜单关闭后再验证版本、页、索引、拼音、光标、中文和完整英文。当前查询不读取或消耗应用尚未领取的提交文本。
- `src/study/windows/EnglishMenu.*` 提供原生菜单，显示完整释义和明确的“输入英文”；学习关闭、缺词或部分拼音时禁用该动作并解释原因。隔离宿主可右键候选或按 F2 / Shift+F10 打开。F2 当前复用菜单，设计中的独立释义浮层仍待实现。
- F8 仅保留在阶段 3 的实验包装器，未成为正式模块快捷键。正式工具区、设置和两种动画仍待开发。

接口 `inspect-v1` / `commit-v1` 通过 Rime 会话临时属性和内部零键码分派；普通按键不会生成该内部请求。这个适配器只证明同进程中的动作边界，没有声称已完成跨进程协议。输入文字不写入正式模块日志，不联网。

## 构建与检查

先完成[阶段 3 依赖准备](../phase3/README.md)，然后从项目根目录运行：

```powershell
python experiments/phase3/prepare-runtime.py
./experiments/phase4/build-actions.cmd
python experiments/phase4/verify-actions.py
./experiments/phase3/build-ui.cmd
python experiments/phase3/verify-engine.py
python experiments/phase3/verify-native.py
```

不要与交互宿主同时运行共享实验数据的检查程序。任何一步非零退出码都应先停止排查。

| 检查 | 状态 |
| --- | --- |
| 真实 Rime/Lua 的版本与动作行为 | [20/20 通过](results/session-actions.json) |
| 既有 Rime/Lua 引擎回归 | [18/18 通过](../phase3/results/engine.json) |
| 原生内部交互与绘制 | [28/28 通过](../phase3/results/native-ui.json) |
| DPI 参数布局 | [24/24 通过](../phase3/results/native-layout.json) |
| 新菜单的实际右键、点击、失焦及连续输入 | [未测试](results/desktop-menu.json)：Computer Use 被用户物理 Esc 停止，尚未打开新构建 |

阶段 3 的 18 项桌面观察仍保留其原被测二进制哈希，不能当作新菜单或新焦点处理的桌面实测。菜单弹出、真实菜单选择和焦点返回需下次继续验证；没有重新请求应用授权的必要。

运行产物仍为 `experiments/phase3/build/ui_probe.exe`，依赖当前目录树。关闭窗口即可退出，没有安装或注册步骤。

## 接续

先完成已编译菜单的真实桌面检查，修复观察到的问题；然后接入正式 Weasel 会话/IPC，并继续右侧工具区、设置、释义浮层和 v0.5 的动画。安装标识、隔离数据目录、完整构建与许可材料完成后，再就具体安装动作请求用户同意。
