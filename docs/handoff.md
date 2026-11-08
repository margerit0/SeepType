# StudyIME 接续说明

Windows／词库工作目录：`.`，已恢复分支 `codex/technical-spike`。本聊天安卓开发使用独立工作树 `.`、分支 `codex/android-dev`；规划分支为 `codex/android-rust-plan`。提交与工作区实时状态请以 `git status --short --branch`、`git log -5 --oneline` 为准，目录分工见 [并行开发说明](parallel-development.md)。**当前 dev.2 已注销，输入法配置与注册树已恢复；DLL 最后清理等待 Windows 重启。以下最新断点优先于历史快照。**

## 2026-11-08 最新目录断点：双工作树分离完成

用户确认原任务仍在运行，要求“先只隔离安卓”。本聊天已从计划提交 `a4d859b` 创建并绑定独立工作树，检出 `codex/android-dev`；后续安卓工作只在此目录进行。没有复制原目录的未提交词库改动。

隔离时 `.` 仍在 `codex/android-rust-plan`，当时按用户要求未改原目录。用户随后询问整理时，实测后台 PID `45044` 已结束、没有匹配的词库工作进程；状态为 `stopped-incomplete`、已返回 80/300 项、两路均因 `non-retryable-error` 停止、不确定请求为 0。已备份并把原目录恢复到 `codex/technical-spike`，13 项工作区改动与词库断点已核对保留，仍未提交。详细过程及本机备份位置见 [并行开发记录](parallel-development.md)。

安卓可以从 P0 开始，不依赖词库扩充完成。当前只有计划和网页参考；Rust／JDK／Android SDK／NDK 的安装位置、配置和版本仍需核定。本次未重启词库 API 请求。下方词库数量和后台状态为历史快照，继续词库任务时读取原目录实时记录。

## 2026-11-08 最新规划断点：安卓与 Rust 共享核心

用户强调手机端“美观很重要”，认可本聊天的键盘示意，并要求开新分支写计划。已从 `7713de7` 建立 `codex/android-rust-plan`，入口为 [安卓开发与 Rust 共享核心计划](android-plan.md)。[网页示意及浅深色参考](../prototype/android/README.md)已保存在仓库，使用固定演示词，不能作为正式词库或 Android 验收证据。

计划采用 Kotlin／Compose 定制界面＋Rust 业务核心＋现有 Rime／Lua，首版为 26 键、全拼／两套双拼、双行候选、明确英文提交及本地学习。用户随后追问 Windows 是否也应改用 Rust；计划提出在安卓核心稳定后，让现有 C++ TSF／服务／界面通过窄 C ABI 接入，逐步统一业务逻辑，继续使用已有引擎和规则。

本轮仅完成分支、计划和设计参考，未创建 Android／Rust 工程、编译 APK、安装手机输入法或改动 Windows 产品。继续此方向时先读计划并从 P0 固定设备、工具链和 Kotlin→Rust→Rime 最小构建开始。下方 Windows 打包／卸载及词库审核断点仍然有效，不因新增平台规划而自动继续执行。

## 2026-11-08 最新功能断点：自然码与小鹤双拼完成

用户要求“先 commit，然后完成支持双拼和小鹤双拼的开发”，并选择“自然码双拼＋小鹤双拼”。已先提交原有全部进展为 `3baa5ba`，再完成三种输入方案、原生设置、切换时组合保护、共享学习／遗忘、英文释义和升级兼容。说明：[double-pinyin.md](double-pinyin.md)。当前新工作只涉及双拼及必要的回归修复，没有推进外部模型词库生成或旧版实际卸载。

原生构建、79 项引擎检查、三种方案合计 600 条英文／中文提交回归、69 项真实 IPC／升级检查、60 项词频回归、18 项组件与 9 组像素比对通过。设置窗口在独立用户目录中实际选择、保存并重开两种双拼，取消也保持原设置。产品翻页 IPC 已修复为返回真实成功／失败；其旧行为原本总返回失败。报告均在 `experiments/phase6/results/double-pinyin-*`，未把程序输入写成外部应用 TSF 验收。

仍是 `0.5.0-dev.3` 内部构建，**没有新运行／源码 ZIP，也没有安装新版**；后续按 [优化待办](optimization-todo.md) 统一打包。引擎和设置窗口用过的隔离目录保留为证据，测试服务与设置窗口已关闭。以下“词频完成、等待小鹤”的记录是本轮之前的断点，不再代表双拼状态。真实系统卸载与英文人工审核的未完成事项仍有效。

## 2026-11-08 最新功能断点：词频完成，先不生成 dev.3

用户先确认完成原生词频与产品控制，随后明确：“先别生成 dev.3，我后续还要加入双拼功能，小鹤双拼，然后再 dev.3。”已完成并验证词频，后续先加入小鹤双拼，再统一生成 dev.3。不要因 `packaging/product.json` 已用于内部测试而直接导出新版归档；本轮没有运行新版打包、安装或源码归档导出。

实现入口：[word-frequency.md](word-frequency.md)，下一项与高级排序：[optimization-todo.md](optimization-todo.md)。默认开启用户词典，独立 `user_learning` 偏好在中文提交前同步；原生 `Memory::OnCommit` 只加暂停判定，排序和保存仍由 Rime 负责。右键“忘记此词”经过版本绑定的服务 IPC，保留组合与待取提交。固定 ZIP 时间戳会误导旧的部署检查，现已在服务启动时完整检查方案，保留旧词频与设置。

60 项词频/迁移检查和 200 条英文回归通过；17 项组件与 9 组像素比对通过；7 项设置窗口观察通过。结构化结果为 `experiments/phase6/results/word-frequency.json`、`word-frequency-settings.json`、`source-built-engine.json`、`product-renderer.json`。内部构建为临时 `0.5.0-dev.3`，新功能未做安装后的 TSF 外部应用验收。所有新测试服务和设置窗口均已关闭，正常用户数据与旧版安装目录未改。

## 2026-11-08 最新桌面断点：浏览器跳过，等待重启后最后清理

用户最新要求：**“那就先跳过浏览器测试，进行别的任务”**。不再尝试 Chrome 原生接口，不把 DOM/页面读取写成输入法验收。记事本与 VS Code 中文/英文提交、悬停/F2、重复保护、跨应用焦点、服务断线恢复、125%/150% 实际缩放、单屏右下角布局和点击已观察；翻页后连续输入有时序记录，但没有逐帧动画证明。只有一台显示器，多显示器仍未验证。

本机卸载实际执行后 profile/CLSID 已注销。发现 TSF 留下本产品空目录，修复 `packaging/windows/Common.ps1` 与 `Uninstall.ps1`：仅清理已注销、收据匹配、结构已知且完全无值的自有 TIP 空键。8 项隔离注册表检查通过，同一函数已清理本机残留。32/64 位完整 TIP 树、默认覆盖、语言列表、键盘和小狼毫配置均与安装前一致；正常用户数据文件逐字节未变。

收据现为 `cleanup-pending / registered=false`。当前 Codex、资源管理器、Chrome、记事本与 ApplicationFrameHost 仍映射 DLL，重试仍保留一个 DLL、六个支持/记录文件和应用列表项。已关闭项目 VS Code 窗口及记事本测试标签，其他记事本文档保留；所有拾词服务和本地 HTTP 测试服务均已停止。**不要声称完整卸载通过，也不要强制结束当前 Codex 或用户文档。**

下一步由用户保存工作并重启 Windows，之后沿用已有卸载授权，通过管理员 PowerShell 再执行安装目录的 `Uninstall.ps1 -Apply -AllowDevelopment`，或使用 `experiments/phase6/run-approved-install-step.ps1 -Action uninstall` 保存结果到 `installed-desktop-followup-20261108/uninstall-after-restart`。重新捕获注册/文件快照，确认安装目录与应用列表项消失且输入设置仍一致，再更新汇总。现有支持脚本与收据保持原始安装包摘要，未私自替换。

后续证据：[完整桌面/卸载记录](installed-desktop-acceptance.md)、[结构化汇总](../experiments/phase6/results/installed-desktop-followup-20261108/summary.json)。收据修复源码已同步；本次卸载修复的源码/运行包由 [增量验证报告](../experiments/phase6/results/source-uninstall-update-20261108/summary.json) 绑定，保留原生构建与历史归档，不包含并行词库草稿。旧有 200 条仍全部待人工审核，保持开发预览。

## 2026-11-08 最新词库断点：30/300 项，等待服务恢复

已接续原会话，按用户授权并行使用 Gemini 与 Grok（high）。本轮新增 10 项，累计 30 项、59 个义项，全部待审核。Gemini 随后返回 429 上游饱和，Grok 连续两次 504；当前没有在途请求。剩余 270 项尚未生成。累计尝试 14 次，输出预留 57,344 token，保留原有 60 次/245,760 token 总上限。

双模型分工、原始响应、合并草稿及审核清单均已保存。42 项离线测试通过；静态检查发现 11 个义项缺少中文触发词，4 个义项与源词表大小写不同，尚未人工审核或导入运行时。详见 [最新扩充记录与续跑命令](lexicon-expansion.md) 和 `experiments/lexicon-expansion/results/pilot-progress-20261108.json`。

用户已提供两个模型凭据，当前会话可按原授权继续；不要要求重复发送。凭据未写入项目配置。服务恢复后复用同一分工和收据，以 `tools.lexicon_expand.parallel_run --execute --retry-failed` 续跑，不能重新全量发送或更换模型。当前词库任务未操作已安装输入法；下方历史安装/卸载事项保持原状态。

## 2026-11-08 当前词库任务：离线准备完成，等待后续 API 配置

用户最新要求：**「那么先按照你的计划开始执行，需要调用模型的话我可以提供 api key 和 base url，你不要负责生成词库」**。对配置询问选择了 **「先完成离线准备，稍后配置 API（推荐）」**。按这个范围完成离线工具和源词表；不要由对话模型手写新英文释义或填充场景词条。

入口为 [英语扩充流程](lexicon-expansion.md)、`tools/lexicon_expand/cli.py`、`data/lexicon-expansion/`。ECDICT 固定提交中的 `ielts` 标签为 5,040 个目标，CEFR-J / Octanove 合并为 8,845 个不同词形，两者并集 10,625 个。IELTS 精确英文义项参考命中 4,130 个、未命中 910 个；这是 CC-CEDICT 参考匹配，不是翻译完成率。所有来源与摘录都有固定摘要。

`.cache/lexicon-expansion/prepared/` 中有目标目录与覆盖报告，`pilot/` 中有默认 300 项计划（200 个 IELTS 目标＋20 个场景的 100 个名额，共 40 个请求）。场景仅有主题配置；新译词 0 条、真实模型调用 0 次。外部传输测试使用隔离模拟响应，不能当作 API 连通性或生成质量证明。

后续用户提供 base URL、模型名并配置 `STUDYIME_LEXICON_API_KEY` 后，把非敏感接口配置放到 `.cache/lexicon-expansion/api.local.json`。先 `config --check-key` 与不带 `--execute` 的 `generate` 预演；按届时用户的执行安排启动首批。工具支持单独 JSON 模式/输出 token 参数、逐请求留痕和断点续跑，不把 key 写进请求清单。默认 300 项、累计 60 次尝试、预留输出 245,760 token 上限；初始 40 次的输出预留上界为 163,840。未知实际价格，不声称金额。

v2 API 草稿全部待审核，多个词义各自保存，主词义不自动选定。当前没有 v2 正式发布或自动运行时导入路径；收到实际生成结果后再推进审核、中文触发词和预览集成。旧有 200 条、现有运行包及已安装产品没有被此轮扩充修改。不要绕过原有人工审核要求。离线验证入口 `tools/lexicon_expand/verify.py`，报告 `experiments/lexicon-expansion/results/offline-checks.json`。

此前已安装产品的卸载恢复和外部应用检查仍未完成，事实与授权保留在下节。当前英语词库任务不要求重跑桌面、打包、安装或既有原生套件。

## 2026-11-08 最新断点：已安装，记事本部分验收通过

用户已明确回答：**“允许安装，完成应用测试后卸载恢复”**。授权范围包括 `C:\Program Files\StudyIME\0.5.0-dev.2` 的安装、独立输入法注册、记事本/浏览器/VS Code 测试及之后卸载恢复，保持现有默认输入法配置。无需重复询问这一范围的授权；Windows 管理员确认由用户手动完成。

首次实际安装发现 Windows PowerShell 5.1 把 `File.Replace` 的 `$null` 备份路径转换为空字符串，更新安装记录失败，停在复制阶段且未注册。修复为 `[NullString]::Value`，**4 项真实收据文件操作检查、12 项安装预演通过**。失败文件经原卸载脚本清理，唯一临时收据移入证据目录，注册和输入设置恢复到安装前；随后修订包实际安装成功。详见 [安装与桌面记录](installed-desktop-acceptance.md) 和 [结构化汇总](../experiments/phase6/results/installed-desktop-20261108/summary.json)。

当前注册目录内的安装记录是 `installed / registered=true`，清单 SHA256 为 `be847600406f9ad3ba53657a20ca33b60f4cb632e47da15e69fd34c405ab4605`。记事本真实系统路由已加载安装目录的 dev.2 DLL；空格中文提交、F2 只看释义、明确英文快捷键及重复动作保护均观察通过，保存文本为 `你好hello`。测试使用独立 `STUDYIME_DEV_SESSION=66bcec7716f24f8297a5a1a818699b33` 与 `.cache/packaging/installed-apps/66bcec7716f24f8297a5a1a818699b33/user`，未用旧 21 条实验数据。原未注册宿主 `E_FAIL` 报告仍有效，不能据实际应用通过改写其结果。

随后准备跨应用焦点检查，在记事本输入 `n` 并启动独立 Chrome 本地测试页。选择/读取 Chrome 窗口时，Computer Use 因无法可靠识别当前浏览器 URL 触发保护，明确要求结束当轮。已立即停止，没有绕过限制。**Chrome 输入、VS Code、跨应用焦点结果、已注册产品卸载与恢复均未完成，测试窗口和服务未在中断后清理。** 恢复时先读取当前状态；记事本还恢复了用户原有标签，只操作本项目测试文档，不能关闭整个应用中的其他文档。工具原文见 [中断记录](computer-use-issue.md)。

运行 ZIP 已更新为 `c1c429adee39465f0740bf7ac6111dad799d097a83e39019a5975d02acf3648e`（23,800,624 字节）。与原包只有 `scripts/Common.ps1` 和 `package-manifest.json` 不同，所有原生文件和词库数据相同。原运行/源码 ZIP、清单与包报告保存在 `.cache/packaging/dist/before-receipt-fix-20261108/`。**源码 ZIP 尚未为这次安装脚本修复更新；旧源码复建和证据绑定仍对应旧包，不得声称修订包已经做过源码复建。** 后续更新源码包及绑定时按实际脚本变化处理，不能使用“仅文档变化”的假设。当前没有重建原生产品或重跑未受影响的历史套件。

原有 200 条英文仍全部待人工审核。用户现在要求先提交当前进展，再讨论加入“雅思词汇 + 日常常用词汇”的最佳方案；尚未导入新词库或改变审核标准。

## 2026-11-07 历史断点

**Computer Use 已实际恢复，14 项 v0.5 实验宿主键鼠功能观察通过。** 详见 [本轮桌面记录](desktop-acceptance.md) 和 [结构化报告](../experiments/phase4/results/desktop-v05-20261107.json)。范围是阶段 4 x64 / 21 条测试释义，不是 dev.2 产品或安装后外部应用通过。

本轮发现并修复交互验收宿主的退出检查顺序：外部可访问性 COM 引用在 `CoUninitialize` 后释放，定向实测 `DllCanUnloadNow` 从 `S_FALSE` 变为 `S_OK`，进程正常退出。产品 DLL/服务未改，历史测试未重跑。复用修复入口：`python experiments/phase4/start-text-host.py --service-x64 --host .cache/packaging/desktop-host-legacy/StudyIME.DesktopHost.exe`。必要时仅构建宿主：`experiments/phase6/build-desktop-host.cmd --legacy`。原默认宿主二进制未覆盖。

当前 dev.2 直接加载到未注册宿主时 `Activate` 返回 `0x80004005`，隔离服务已停止；[失败报告](../experiments/phase6/results/desktop-activation-dev2.json) 保留真实二进制绑定。新增产品宿主入口仅用于诊断，不要假定可进行产品桌面验收。产品使用正式系统 key-sink 登记，实验 DLL 跳过此路径；本轮未插桩定位内部失败点，也未执行系统注册。

下一步优先处理 dev.2 安装/注册、卸载恢复及外部应用验收的明确系统授权；准备好的计划目标为 `C:\Program Files\StudyIME\0.5.0-dev.2`，独立产品标识。悬停、动画中输入、断线、跨应用焦点与缩放/多显示器仍待实际观察。英文人工审核仍是 0/200。所有本轮测试窗口/进程已结束，隔离实验设置留下 `Alt+Enter`；正常用户数据和产品注册未改。

本轮只更改验收宿主/入口、报告和文档，不需重建产品包；现有运行和源码 ZIP 均保留原内容。以下“新窗口先读”是本轮开始前的交接快照，发生冲突时以上述最新断点为准。

## 2026-11-07 新窗口先读（本轮开始前快照）

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

真实人工审核、完整应用兼容性、已注册产品卸载恢复、系统缩放切换和多显示器仍待完成。实际安装、独立注册及记事本的 5 项观察已完成，见页首 2026-11-08 记录。当前为未签名 x64 开发预览，不支持原地升级，32 位前端尚未提供。

用户已明确允许安装、应用测试后卸载恢复；应在已批准范围内继续，不重复询问同一授权。当前产品仍安装，卸载待完成。不要自行改默认输入法配置。

**Computer Use 已获允许，但 2026-11-08 的 Chrome URL 识别保护使桌面工作中断。** 2026-11-06 的暂缓安排及审批 404 是历史情况。使用当前窗口的正常工具与技能，遵守保护提示，不照搬旧 API、猜测配置或绕过保护；详情见 `docs/computer-use-issue.md`。本次提交准备没有重试桌面操作。

用户已允许必要时 commit；继续复用当前工作区，不主动开新聊天/工作树。不主动委派子 agent；当前没有适用的 AGENTS.md。用户后续明确指令优先于此交接快照。
