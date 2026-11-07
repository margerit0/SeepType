# StudyIME 接续说明

项目：`.`，分支 `codex/technical-spike`。本轮继续推进用户已授权的开发、许可来源处理与验证；真实系统安装仍未执行。提交与工作区实时状态请以 `git status --short --branch`、`git log -5 --oneline` 为准。

## 2026-11-07 新窗口先读

用户最新原话：**“我会开一个新的窗口继续任务，帮我准备上下文，可以用 computer use”**。此前暂缓 Computer Use 的安排已被这条新指令更新；新窗口可以直接使用 Computer Use 推进本项目的界面操作和验收，不重复询问工具使用许可。本轮只准备交接，没有进行新的桌面操作，也没有确认旧审批错误已恢复。

当前产品提交为 **`503e8a6`**（`feat: build StudyIME dev.2 from traced sources`）；其后的交接提交仅更新文档。dev.2 收尾完成：最终 15 项归档检查和 12 项安装默认预演全部通过，工作区在交接编辑前干净。最终运行 ZIP 与已复建版本一致；源码包仅更新 README 与打包说明，55 项产品构建输入、9 项 Rime 构建输入未变。全项目仍有人工审核及安装后桌面验收待办。

新窗口建议顺序：

1. 读取本文件、`docs/computer-use-issue.md`，检查 Git 状态。直接沿用已有产品和报告，不重复完整构建、历史测试或许可调查。
2. 使用当前会话提供的 Computer Use 正常入口读取窗口状态，再针对项目测试窗口操作。先阅读当前 `computer-use` 技能及其所需 guidance/confirmations；旧的 `sky.list_apps` 审批 404 只是历史故障，不代表当前工具仍不可用。不要擅自修改审批配置或用其他 UI 自动化绕过工具限制。
3. 可先进行无需系统注册的 v0.5 真实键鼠复验。现成入口为 `python experiments/phase4/start-text-host.py --service-x64`，设置入口为 `python experiments/phase4/start-settings.py`。宿主状态、日志和 PID 在 `experiments/phase4/runtime/interactive-*`；该入口是阶段 4 的 21 条测试数据及旧实验二进制，不是 dev.2 产品安装验收。需要验证 dev.2 时先明确绑定当前产品二进制和隔离数据；不可把旧宿主通过写成新产品或外部应用通过。
4. 优先检查普通点击上下两行都提交中文、明确英文菜单/快捷键、F2/悬停完整释义、翻页、学习开关、设置、失焦及动画中输入。保存实际观察及对应二进制/环境，只有改动影响到已测路径时才补必要程序检查。
5. 原有 200 条英文保持待人工审核；收到实际审核记录后再导入。系统安装/注册/卸载、与已有小狼毫并存以及记事本/浏览器/VS Code 的安装后路由仍待验收。最新话语明确允许 Computer Use，未明确答复上一轮“是否授权在本机进行安装、注册及卸载恢复测试”的问题；实际 `-Apply` 前再就这项系统操作确认，不要重复询问已经允许的普通工具操作。

本次只修改交接、进度与历史故障文档，这三份文件不进入现有源码材料包；交付包、产品代码和验证结果不需因此重建。

## 当前版本

**0.5.0-dev.2**，产品名拾词输入法（StudyIME），Windows 11 x64。新代码和原创图标 GPL-3.0-or-later 已获用户确认，不要重新询问。英文学习数据及中文基础词库的适用改编为 CC BY-SA 4.0；Unicode 原始数据保留自己的 Unicode License V3。

原先三个具体许可/来源阻止项已处理：

- 产品不再编译 WTL：布局使用 ATL 几何类型与 HDC，服务改为 Win32 消息循环，TSF 继续使用原有 CandidateUi。旧 Weasel WTL 源文件只存在于独立的原始 Git bundle 中。
- Rime 1.13.1 从固定源码构建，仅含 Lua 插件。glog、LevelDB、yaml-cpp、marisa、OpenCC 均有实际编译输入及静态库记录；不使用官方预编译 DLL。
- 中文基础为固定 CC-CEDICT 简体词形/读音＋wordfreq 中文词频。多音单字按 Unihan kHanyuPinlu 分配读音权重，修正了 xing/省、dai/大、zhao/着等整字词频误用。保留 121,505 条词形/读音记录、120,786 个不同词形以及 124,551 条原始行引用。

实际源码材料见 `licensing/product-sources.lock.json`，共 10 份上游材料。librime 的旧 data/、Luna 混合词典、essay、octagram、predict 和官方 DLL 不在本版产品源码材料中。保留的 Luna 文件只有三个方案/拼写文件及原许可证。原始开发缓存不用删除，也不能作为产品构建的隐式输入。

## 英文审核不能跳过

**原有 200 条、人工通过 0 条、待审核 200 条。** 没有更换这批数据、没有添加测试审核者或合成人工决定。中文基础词库扩大不等于增加英文释义：英文仍只精确查询这 200 条，缺词留空。

审核入口 `docs/lexicon-review.html`，流程为 `tools/lexicon/pipeline.py`。只有实际人工导出的审核 JSON 才导入；修改英文后恢复待审。正式导出与正式打包仍会拒绝待审数据。不要为了结束任务而自动批准、替换批次或把程序检查称为人工审核。

## 本轮验证及边界

- 产品 Renderer：15 项布局、回调及动画检查；9 张静态预览与已保存的 v0.5 PNG 像素一致，包括 96/120/144/192 DPI。
- 包与安装预演：15 项打包、12 项默认计划/完整性、8 项独立目录运行检查（含 22 项实际 Rime IPC 子检查）。
- 当前引擎：200/200 释义、中英文提交；6 组多音单字检查；16 组各 200 次合成输入耗时。其作用范围是当前机器的程序接口，不代表物理键鼠、安装后路由或真实应用兼容性。
- 中文来源：121,505 条全部有原始词形与拼音对应，共 124,551 条引用；重复导出字节一致。
- 注册恢复：原有 28 项内存模拟仍有效，生产注册逻辑未因这轮数据与引擎改造而改变，没有无故重跑。
- 最终离线源码复建已通过：同机独立中文路径中的四个产品文件、Rime DLL、构建记录及完整运行 ZIP 均逐字节一致，核对了 209 份项目文件和 16 份恢复材料。`source-materials.json` 记录复建过程；最终文档调整由 `source-evidence-binding.json` 关联到已验证源码包。运行、绘制、引擎与中文来源报告分别通过 `runtime-evidence-binding.json`、`artifact-evidence-binding.json` 关联到当前产物，不把 dev.1 报告或失败尝试当作 dev.2 成功证明。

原有 50/29 项 UI/TSF、25 项词库流程以及更早 IPC/菜单/桌面实验报告保留。修改相应路径或出现新问题后才跑必要检查，不从头重跑历史套件。

原始等权重、字符频率、wordfreq 对比报告记录了选择过程，当前版本应以 `source-built-engine.json` 为准。`source-built-engine-reading-order-initial.json` 中“zhang 必须张排第一”是过严的初始检查：长/张都属常用读音，最终允许二者之一排首位并要求两者都在第一页，没有为这个样例改写频率数据。

## 构建与交付

```powershell
.\tools\packaging\build.cmd
python tools/packaging/package.py --mode preview --with-sources --stage .cache/packaging/stage/StudyIME-0.5.0-dev.2
python tools/packaging/verify.py
python tools/packaging/verify_engine.py
python tools/packaging/verify_renderer.py
python tools/dictionary/audit.py
python tools/packaging/verify_sources.py --build
```

这些是维护入口，不要求接续时全部重跑。普通构建默认离线：VS2019 19.29、ATL、SDK 10.0.19041.0 已安装；Ninja 复用 VS，CMake 3.31.6 来自固定便携归档。不要重复安装工具链。

- 四个产品文件：`.cache/packaging/build/bin`。
- 产品生成的 Weasel 源码：`.cache/packaging/weasel`。生成器从固定 Git 提交取原文件，忽略旧上游工作区修改与 `.cache/study-weasel/include/WeaselUI.h` 的残留字段。
- Rime 源码构建：`.cache/rime-build`；记录 `rime-build.json`、`source-tree.json`、`include-trace.json`、`compile-commands.json`。
- 发布材料：`.cache/packaging/dist/StudyIME-0.5.0-dev.2-windows-x64-preview.zip` 及 `StudyIME-0.5.0-dev.2-source-materials.zip`。摘要和大小以该目录中的清单为准。
- `Install.cmd` / `Uninstall.cmd` 默认只输出计划。实际操作需要显式 `-Apply -AllowDevelopment`。

交接时的最终归档摘要：运行 ZIP 为 `7db1bf59ea0d918c6c132c717a9c7e7385426dd1bba3890479d5517f2c8d23a1`（23,800,449 字节）；源码 ZIP 为 `926e8ce52f14b50f4e94471806502f0fcb3fef7f547b7e24ef6e3230a221bb25`（252,967,645 字节）。展开目录为 `.cache/packaging/stage/StudyIME-0.5.0-dev.2`。

源码包会恢复固定的代码、Boost、CMake、CC-CEDICT、wordfreq 和 Unihan。`build.cmd` 先编译专用 Rime，再构建产品；不依赖旧官方 Rime 缓存。为 CL/Ninja 的中文诊断统一 UTF-8，复建验证通过独立隐藏控制台执行，避免改变用户终端。

首个 dev.2 复建目录 `fresh 中文 b82394308668` 在编译前因无控制台输出使用 GBK 而失败，不能作为成功证据。最终使用 `fresh 中文 a54add1526b2`：从空缓存离线构建后，五个二进制均一致；随后在同一独立目录修正 glog 测试路径宏和 RC 头文件记录，再构建并核对全部最终材料，未从原目录复制二进制。这是有记录的续建验证，同机工具链范围内通过，不声称最终源码包另做过一次全新空目录复建。不要用 cmd/PowerShell UI 自动化绕过 Computer Use 审批。

## 保持的 v0.5 约束

- 紧凑圆角双行候选，英文在上、中文在下；工具区、独立完整释义窗、设置、固定宽度翻页均保留。
- 空格、数字、普通点击中文行或英文行都提交中文；只有明确的英文菜单/配置快捷键提交英文。F2/悬停只看完整释义。
- 翻页 180ms，学习开关 240ms；不改为静态演示。学习开关保持候选与页码。
- 精确中文候选查询本地词表，不拆句、不猜上下文、不用在线翻译。
- 英文动作必须保留会话及候选版本保护；部分组合不能丢弃后续拼音。
- CandidateUi 的 SetDpi(96,96) 是物理像素 1:1 绘制，不要再次乘 DPI；层叠窗继续灰度抗锯齿。
- 产品探针必须使用独立的 STUDYIME_DEV_SESSION 和 STUDYIME_DEV_DATA_ROOT，不借用正常用户数据。

## 尚未完成及授权

真实人工审核、安装/注册/卸载及恢复验收、记事本/浏览器/VS Code 兼容性、系统缩放切换和多显示器仍待完成。当前为未签名 x64 开发预览，不支持原地升级，32 位前端尚未提供。

本轮至今没有获得实际安装/注册的授权；之前的“继续”用于推进开发。后续如果用户对明确的安装问句同意，应直接在其已批准范围内推进，不重复询问。不要自行改默认输入法。

**Computer Use 已获用户 2026-11-07 最新指令允许，可以恢复。** 2026-11-06 的暂缓安排已过时。此前 sky.list_apps 在执行前遭审批服务 404（所选 gpt-6-luna 模型不受该服务支持），历史记录见 `docs/computer-use-issue.md`；本次交接没有重试或修改配置，不声称工具已实测恢复。使用当前窗口的工具与技能，不照搬旧 API 或假定旧模型、端点仍是当前配置。工具使用授权不自动等于输入法系统安装授权。

用户已允许必要时 commit；继续复用当前工作区，不主动开新聊天/工作树。不主动委派子 agent；当前没有适用的 AGENTS.md。用户后续明确指令优先于此交接快照。
