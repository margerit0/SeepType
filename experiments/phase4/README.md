# 阶段 4：会话动作、原生英文菜单与 Weasel IPC

**2026-11-07 最新接续：v0.5 原生界面与 x64 服务已实现。** 双行候选、工具区、独立释义、原生设置、翻页定宽和两种动画已接入真实 TSF；修复普通选词无响应与学习开关重置页面/选中项。详见 [原生 UI 接续](../../docs/native-ui.md)。下文 2026-11-05 内容为历史实现及验证边界，旧报告保持原样。

从项目根目录执行 `experiments/phase4/build-native-x64.cmd` 顺序构建 TSF、文本宿主、设置和 x64 服务。定向验证：`verify-native-ui.py`（47 项）、`verify-selection.py --service-x64`（7 项）、`verify-text-host.py --v05 --service-x64`（27 项）；编辑回归使用 `verify-text-host.py --service-x64 --report experiments/phase4/results/tsf-text-host-v05-x64.json`（16 项）。x86 服务的 7 项 IPC 和 27 项 TSF/UI 结果另有保留。

交互运行：`python experiments/phase4/start-text-host.py --service-x64`；设置：`python experiments/phase4/start-settings.py`。目前仍依赖仓库与缓存，不是安装包。Computer Use 审批错误按用户要求留后修复，程序检查不等于物理键鼠验收。

更新：2026-11-05。已实现会话版本模块、统一 Lua 英文动作、隔离宿主 Win32 菜单，以及真实 Weasel 服务端与客户端的版本化 IPC。菜单 16 项、IPC 27 项证据已保留；本轮新增服务窗口线程调度，14 项定向检查通过。后续新增真实 TSF 学习前端源码接入及完整 x64 TSF DLL 编译链接，16 项定向检查通过；实际 TSF 编辑/可见菜单未验证，当前仍不是系统输入法安装包。

## 实现

- `src/study/SessionActions.*` 为每个会话分配独立身份和递增版本。输入、翻页、选中项变化、学习开关、失焦使旧动作失效；切回相同候选或重建会话也不能复活旧动作。
- `src/study/lua/study_core.lua` 是唯一的词表查询、提交资格和英文提交实现。键盘及菜单均检查真实选中候选的完整范围、光标和学习状态，再提交完整词值。缺词不显示其他上游注释为英文；原始候选仍由 ShadowCandidate 保留。
- `StudyEngine` 适配器先向 Lua 查询目标，菜单关闭后再验证版本、页、索引、拼音、光标、中文和完整英文。当前查询不读取或消耗应用尚未领取的提交文本。
- `src/study/windows/EnglishMenu.*` 提供原生菜单，显示完整释义和明确的“输入英文”；学习关闭、缺词或部分拼音时禁用该动作并解释原因。隔离宿主可右键候选或按 F2 / Shift+F10 打开。F2 当前复用菜单，设计中的独立释义浮层仍待实现。
- F8 仅保留在阶段 3 的实验包装器，未成为正式模块快捷键。正式工具区、设置和两种动画仍待开发。
- `src/study/RimeSession.*` 绑定 `RimeWithWeaselHandler` 已有的真实会话；不另建 Rime 实例，不领取应用 commit。`StudyService.*` 管理每个会话的临时目标、焦点和版本，并增加服务实例身份来隔离重启前的请求。
- `StudyProtocol.*` 提供有限长度的 Inspect / CommitEnglish / SetLearning 请求。客户端只传版本和候选编号，英文值从服务端 Lua 重新查询。正常 Weasel 响应携带 capability 和当前版本；提交继续走标准 commit 响应。
- [weasel-study-ipc.patch](patches/weasel-study-ipc.patch) 接入原 `WeaselClientImpl`、`WeaselServerImpl` 与 `RimeWithWeaselHandler`。管道使用每连接独立缓冲区，修正请求体偏移、空消息残留及连接竞态；旧请求或无效报文不能再次提交英文。
- `src/study/windows/WindowDispatcher.*` 把会话操作统一调度到服务窗口线程；`WeaselPipeServer.inc` 只在连接工作线程收发，退出时取消并 join 全部线程，取消跨线程 Rime/UI 锁。Rime 后台通知使用复制邮箱。设计与生命周期契约见 [service-dispatch.md](../../docs/service-dispatch.md)。

Lua 内部接口 `inspect-v1` / `commit-v1` 仍通过 Rime 会话临时属性和零键码分派；新增 `study.v1` 在 Weasel IPC 层验证后调用它们。查询及拒绝动作不读取应用待取 commit。输入文字不写入新增正式模块日志，不联网。[协议与接入说明](../../docs/study-ipc.md)。

## 构建与检查

当前目录中的依赖、引擎与 UI 已准备并验证，**不要因接续聊天重新运行旧检查**。修改新增服务路径时，从项目根目录使用：

```powershell
./experiments/phase4/build-service.cmd
python experiments/phase4/verify-service.py
```

构建使用已有 VS2019，首次从已固定缓存归档补取 Boost serialization/thread/chrono 源码并编译，不下载或安装系统组件。`prepare-weasel.py` 从固定提交生成 `.cache/study-weasel` 覆盖层及可审阅补丁，不修改原 Weasel checkout；后续只重编发生变化的文件。

`verify-service.py` 在 `phase4/runtime` 使用阶段 3 已准备数据的独立副本，以随机名称建立 `StudyIme-Phase4-*` 管道。服务与客户端都是脚本创建的无控制台窗口子进程，结束后退出；不会连接或终止已安装小狼毫，也不操作桌面窗口。服务程序缺少隔离管道参数时直接退出，不回退到系统 Weasel 管道。

普通完整运行包含 25 项 IPC 检查和重启后的 2 项检查。本次首轮 24 项通过；分段检查原先比较了更换选中候选前后的显示文本，修正为比较尝试提交动作前后后，仅补测该项及重启。`--resume` 保留同一服务二进制上的已通过结果，各项客户端哈希写入报告；不是重新检查旧结果。

既有 `build-actions.cmd` / `verify-actions.py` 和阶段 3 命令仍保留，仅在相应旧路径被实际修改时使用。任何一步非零退出码应先排查该步。

| 检查 | 状态 |
| --- | --- |
| 真实 Rime/Lua 的版本与动作行为 | [20/20 通过](results/session-actions.json) |
| 既有 Rime/Lua 引擎回归 | [18/18 通过](../phase3/results/engine.json) |
| 原生内部交互与绘制 | [28/28 通过](../phase3/results/native-ui.json) |
| DPI 参数布局 | [24/24 通过](../phase3/results/native-layout.json) |
| 新菜单的实际右键、点击、失焦及连续输入 | [16/16 已恢复](results/desktop-menu.json)，包含 Shift+F10 修复；本轮未重跑 |
| 真实 Weasel 服务会话与跨进程 IPC | [27/27 通过](results/service-ipc.json)，包括并发连接及服务重启 |
| 窗口线程调度、连接退出和受影响的 Rime 动作 | [14/14 通过](results/service-dispatch.json)，含 200 次并发请求与慢客户端；不等于可见窗口测试 |

阶段 3 的 18 项桌面观察与阶段 4 的 16 项菜单观察分开保留来源。后者来自聊天 `01a1932b-0fd6-7ce0-b447-1343468abea0` 和 `01a19343-dab9-7af0-a6af-4cab916c0ccd`；此前聊天错误发生在记录落盘前，并非仍有菜单测试待做。

可视宿主仍是 `experiments/phase3/build/ui_probe.exe`；新产物为 `build/study_service.exe` 与 `build/service_client_test.exe`，由上述脚本配对运行。均依赖当前目录树，没有安装或注册步骤。新 IPC 测试没有创建可见服务候选窗，不能作为 UI 或真实应用测试结果。

## 接续

服务窗口线程调度已实现并验证；修改该路径时使用 `python experiments/phase4/verify-dispatch.py`，无需重跑旧完整 IPC、菜单、引擎和布局检查。新增 `dispatch_test.exe` 使用隐藏消息窗口和真实管道，未创建可见候选条。构建产物嵌入普通用户 `asInvoker` 清单，不要求提权。

本轮后续已接入真实 TSF 学习前端源码并构建 x64 DLL，最新断点在下节；实际编辑执行、工具区、独立浮层和两种动画继续待办。菜单、IPC 与线程调度已有证据，不要再次当作断点。

## 最新接续：x64 TSF 前端

见 [TSF 前端契约与断点](../../docs/tsf-frontend.md)。`build-tsf.cmd` 使用已有 VS2019 x64 编译器构建 `build/tsf-x64/study_weasel_x64.dll`，不需要下载、安装或注册。`verify-frontend.py` 使用原有已验证 x86 服务，仅检查新增的 x64 前端快照/状态/跨架构 IPC 与 DLL 无注册加载，结果在 [tsf-frontend.json](results/tsf-frontend.json)。真实编辑执行、菜单实操、完整原生 v0.5 UI 与 x64 服务仍待继续，不重复菜单/引擎/布局/调度旧报告。
