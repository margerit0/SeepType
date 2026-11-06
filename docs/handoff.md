# 新窗口接续上下文

更新：2026-11-07（Asia/Shanghai）。工作目录：`.`。分支：`codex/technical-spike`。

本文件用于新聊天快速接续。产品化开发基于 `135157a`；本次从中断聊天继承了未提交的实现，继续修正可重复构建与注册恢复。最新提交请以 `git log` 为准。仅运行受改动影响的阶段 6 检查，没有重跑历史测试、启动 Computer Use 或执行系统安装/注册。新窗口先核对当前 Git 状态，再按下述断点继续。

## 当前任务与下一步

项目已命名为 **拾词输入法（StudyIME）**，采用 Weasel + Rime + Lua，目标为 Windows 11 x64、简体中文全拼。v0.5 原生界面、x64 服务和高 DPI 修正保持不变。现已提供可脱离仓库运行的 **0.5.0-dev.1 开发预览包**、对应源码材料和默认只预演的安装/卸载脚本；实际安装/注册及公开发布条件仍未完成。现有 200 条词库人工审核状态保持 0/200。

用户要求继续许可、标识、打包与安装产物开发，并明确实际安装/注册前另行授权。下一断点是：

1. **先看 [产品打包](packaging.md) 和 [软件许可汇总](software-licenses.md)，复用现有产物继续。** 独立 GUID/管道/目录、图标与版本资源、四个 x64 程序、最小中文数据、固定 ZIP、源码材料和安装/卸载脚本已实现。仍须处理 WTL/MS-PL 与 GPL 相容性、原始 Rime CI 构建输入核验、中文词典底层混合来源三项许可/来源阻止项。官方 DLL 内的 octagram 是 GPLv3，不能统一标为 BSD。
2. 复用现有 200 条审核稿，收到真实人工审核记录后再导入。不要重选一批词、自动批准词义，或将程序验证当成人工审核。当前正式词库导出被正确阻止。
3. **Computer Use 按用户要求留后处理。** 后续修复正常审批通路后，再做真实键鼠、设置、动画、多显示器及记事本/浏览器/VS Code 验收。
4. 实际安装、输入法注册、卸载验收和系统输入设置修改尚未授权。具体产物和默认预演计划已经可审阅；需要执行 `-Apply` 或这些系统变更时再取得明确授权。不要把脚本预演当成实际安装成功。

**用户已明确确认产品名「拾词输入法（StudyIME）」及新代码 GPL-3.0-or-later。不要再问同一选择。** 词库单独 CC BY-SA 4.0，见 [COPYING.md](../COPYING.md)。上游文件保留自己的许可，全部再分发核验仍未完成；源码材料齐备不等于许可问题已经解决。

## 本轮产品产物与证据

- 产物在 `.\.cache\packaging\dist`：`StudyIME-0.5.0-dev.1-windows-x64-preview.zip`、`StudyIME-0.5.0-dev.1-source-materials.zip`、`SHA256SUMS.txt` 和 `package-report.json`。摘要和大小以该目录清单为准，不复制易过期的值到交接文档。
- 展开包在 `.cache/packaging/stage/StudyIME-0.5.0-dev.1`。`Install.cmd` / `Uninstall.cmd` 默认只输出计划；实际命令要求显式 `-Apply`，且开发预览另需 `-AllowDevelopment`。
- 产品原生输出：`.cache/packaging/build/bin/StudyIME.TSF.x64.dll`、`StudyIME.Service.exe`、`StudyIME.Settings.exe`、`StudyIME.Registrar.exe`。正式源码在 `src/study/windows/Product*`，产品配置在 `packaging/product.json`，构建仍复用阶段 4 构建器的 `--product` 模式。
- **12 项打包、12 项预演与校验、8 项独立目录检查通过，其中实际 Rime IPC 子检查为 22/22；新增注册恢复内存模拟 28/28。** 报告在 `experiments/phase6/results`。运行检查使用包含中文和空格的目录及独立用户数据，服务已正常停止；没有注册或改变系统输入配置。
- 产品源码树从固定提交和正式生成器完整生成，忽略旧 `.cache/study-weasel` 的残留头文件及上游工作区修改；不要重新把这些缓存作为编译输入。MSVC 使用 `/experimental:deterministic` 与 `/pathmap`，项目/生成源码及 Boost/Rime 依赖内容均有摘要。
- **同机不同目录空缓存复建已通过：** 源码 ZIP 在含中文和空格的目录恢复后，记录输入及四个原生程序全部一致，再生成的完整运行 ZIP 也逐字节相同；约 390 秒，未联网。见 `source-materials.json` 与 `source-package-rebuild.json`。不要把早期 `source-materials-initial.json`、`source-materials-relative-paths.json` 的不一致记录当作当前结果。跨机器和官方 Rime DLL 的原始 CI 环境仍未重现。
- 后续仅脚本/说明改动时，通过 `runtime-evidence-binding.json` 核对既有原生和数据摘要，不重跑已通过的真实引擎检查。源码包只调整说明时，通过 `source-evidence-binding.json` 核对非文档成员及原生构建输入，避免再次完整编译。
- 14 份固定源码归档和完整许可在 `licensing` 的锁中记录，缓存已准备；普通构建与打包默认离线，不重复下载。
- 当前仅 x64 前端、未签名，不支持原地升级；真实注册、应用路由、失败恢复、占用卸载、32 位应用与多用户场景仍未验收。

## 接续阅读入口

以下文档中，最新日期条目优先于历史记录；旧“尚未接入 TSF/UI”等描述不能当成当前状态。

| 文件 | 用途 |
| --- | --- |
| [progress.md](progress.md) | 权威进度、用户决策与授权、历史检查及未完成项 |
| [native-ui.md](native-ui.md) | 正式 v0.5、DPI、构建命令及验证边界 |
| [lexicon.md](lexicon.md) | 200 条审核稿、审核导入与数据导出流程 |
| [data-sources.md](data-sources.md) | 数据许可、软件许可现状与尚未完成的再分发工作 |
| [packaging.md](packaging.md) / [software-licenses.md](software-licenses.md) | 当前产品、安装产物、源码材料和许可阻止项 |
| [computer-use-issue.md](computer-use-issue.md) | 审批服务故障和用户指定的处理顺序 |
| [阶段 4 README](../experiments/phase4/README.md) / [study-ipc.md](study-ipc.md) | 隔离服务、真实 TSF 及会话动作细节，修改相应路径时再读 |
| [dependencies.lock.json](../experiments/phase3/dependencies.lock.json) | 固定依赖、下载来源及哈希 |

更早的接续聊天：推进 Windows 英语学习输入法。主要结论与证据已落盘，无需从最初调查重新开始。

## 已确认的设计与实现约束

- v0.5：紧凑横条、英文在上中文在下、圆角、无左侧深色条；工具区、独立完整释义浮层、设置与定宽翻页均须保留。
- 空格、数字、普通点击中文或英文显示区域都提交中文；只有明确的英文菜单或配置快捷键提交英文。F2/悬停显示完整释义，不直接提交英文。
- 翻页动画 180ms，学习开关动画 240ms；已有原生实现，不要以静态界面替代。
- 只对精确中文候选查询本地词表，不猜上下文、不拆句翻译、不用在线翻译补洞。
- 英文动作目前只允许完整组合候选，不能丢弃剩余拼音；必须使用现有会话/候选版本保护。
- 当前 Lua 使用单一英文值，显示和提交文本必须相同；审核工具会拒绝不一致记录。
- 正式源码在 `src/study/windows/`，通过 `experiments/phase4/prepare-tsf.py` 和 `prepare-weasel.py` 生成覆盖层。不要只修改 `.cache` 中的生成文件或上游源码副本。

## 前期功能提交

| 提交 | 内容 |
| --- | --- |
| `ebd4e9e` | 200 条有来源词库审核稿、审核工具、确定性数据导出及真实引擎验证 |
| `48a1efb` | 各 DPI 原生预览、宿主 Per Monitor V2 清单及候选窗 DPI 修正 |
| `1811663` | v0.5 正式 TSF UI、x64 学习服务与普通选词等修复 |

已解决普通选词没有 commit 响应、学习开关重置页码/选中项、设置保存失败覆盖内存偏好、MSAA 对象/DLL 生命周期等问题。不要再次将这些列为未修复事项；真实物理鼠标复验仍须单独完成。

## “像 720p”问题的结论

用户截图上方是旧的 **600×55 PNG 在 150% 下被放大为约 900×82**，与双线性放大后的像素比对吻合。文字栅格化后再插值放大造成模糊。

现已导出 96/120/144/192 DPI 预览，并给文本宿主、组件检查程序和设置程序嵌入 Per Monitor V2 清单。候选窗口初始化读取自身 DPI；实际 TSF 宿主测到 **144 DPI、900×83 物理像素**。对比页：[previews-v05/index.html](../experiments/phase4/results/previews-v05/index.html)；高清图：[dpi-192.png](../experiments/phase4/results/previews-v05/dpi-192.png)；诊断：[dpi-preview-diagnosis.json](../experiments/phase4/results/dpi-preview-diagnosis.json)。

`CandidateUi.cpp` 的渲染目标 `SetDpi(96,96)` 用于物理像素 1:1 绘制，字体、布局和位图已经缩放，不能再乘一次 DPI。分层窗口继续灰度抗锯齿，不要未经验证强制 ClearType。DPI 不感知应用、多显示器移动和系统缩放切换仍未验收。

## 词库状态与操作

**200 条、10 类各 20 条、37 条重点复核；人工通过 0 条、待审核 200 条。** 保存 202 条来源原文，多出的两条用于“苹果”“妻子”的其他词义/读音。建议词义、原文、修改说明与审核状态分别保留。

来源为固定 CC-CEDICT `2026-11-06T08:10:12Z` 快照，125369 个源词条，许可 CC BY-SA 4.0。完整许可、署名和适用改编说明已保存。

- 审核数据：[data/lexicon/entries.json](../data/lexicon/entries.json)；来源锁：[source.lock.json](../data/lexicon/source.lock.json)；原文：[sources/entries.json](../data/lexicon/sources/entries.json)。
- 审核入口：[docs/lexicon-review.html](lexicon-review.html)；生成模板：`tools/lexicon/review.html`；流程工具：`tools/lexicon/pipeline.py`。
- 审核页支持搜索、类别/状态/重点筛选、修改英文与逐条决定；修改英文后重新待审。审核绑定整批和逐条摘要，导入先全量校验再原子替换。
- 审核导出的 JSON 仅包含本次实际修改/决定，避免重新署名已有审核；测试中的假审核者只存在于临时测试目录，没有写入产品数据。
- 默认正式导出在存在任何待审核项时失败；全部审核后只导出通过项，拒绝空词库。
- **200 条现进入明确标识的产品开发预览；仍是待人工审核数据。默认阶段 4 交互宿主继续使用 21 条 test-only 词对。**

以下是操作入口，不要求接续时全部重跑；只有相关修改或新审核记录才运行必要检查。

```powershell
# 在 . 下执行
python tools/lexicon/pipeline.py validate
python tools/lexicon/pipeline.py review --output docs/lexicon-review.html
python tools/lexicon/pipeline.py import-review "<真实人工审核 JSON 路径>"
python tools/lexicon/pipeline.py build --mode preview --output .cache/lexicon-preview
# 当前会正确拒绝 200 条待审核数据：
python tools/lexicon/pipeline.py build --output .cache/lexicon-release

# 修改词库流程或运行时后，按影响范围选择：
python tools/lexicon/verify.py
.\experiments\phase5\build-probe.cmd
python experiments/phase5/verify-lexicon-runtime.py
```

审核数据导入成功后重新生成审核页。审核页的 200 条数据和 JavaScript 语法已检查，浏览器实际操作未验收。

开发数据包：`.\.cache\lexicon-preview\study-daily-200-preview.zip`，82,096 字节；SHA256：`ca9a8a5b998fdb18cfb79621e81d3f104b897c9bc53a955714639acd578e4d20`。相同输入与工具版本两次导出字节一致。它是词库预览包，不是输入法安装包。

完整源文本 SHA256：`ff107587bc1d593dd5d7a49c179d4aa749cb89b3a1423876e0cd2dca197b672b`；压缩包 SHA256：`7708295976336e3c077b05df0f3beb598caccf1dddf01c9b04c90828d8810cd9`。完整文件在 `.cache/dictionaries/cc-cedict/<压缩包哈希>.txt` 和 `.txt.gz`。`fetch-source` 优先复用缓存，“最新下载”若与固定哈希不同就拒绝替换，不自动更新锁。

`.gitattributes` 已保留旧补丁规则并固定数据/工具 LF；官方完整许可证使用 `-text whitespace=-blank-at-eof` 保留原始字节与末尾空行。不要裁剪许可证来消除格式提示，否则会破坏来源摘要。

## 已保存的验证证据

本次交接仅核对文件与现有记录，没有重跑以下测试。

| 报告 | 已完成的范围 |
| --- | --- |
| [native-v05.json](../experiments/phase4/results/native-v05.json) | 50/50 原生组件检查 |
| [native-v05-dpi-tsf-x64.json](../experiments/phase4/results/native-v05-dpi-tsf-x64.json) | 高 DPI 修正后 29/29 真实 TSF/UI 集成检查，x64 服务 |
| [lexicon-validation.json](../experiments/phase5/results/lexicon-validation.json) | 200 条来源、摘要、类别及审核状态核对 |
| [lexicon-pipeline.json](../experiments/phase5/results/lexicon-pipeline.json) | 25/25 审核导入与导出流程检查 |
| [lexicon-runtime-x64.json](../experiments/phase5/results/lexicon-runtime-x64.json) | 200/200 条真实 x64 Rime/Lua 候选释义、完整英文提交、普通中文提交；都在第一页，13 条非首候选 |
| [lexicon-package.json](../experiments/phase5/results/lexicon-package.json) | 预览包、逐文件摘要、确定性重建与正式导出阻止记录 |

之前的 x86/x64 服务各 27 项 TSF、各 7 项选词 IPC、x64 服务 16 项编辑会话，以及更早引擎/菜单/桌面/调度报告均保留。只有新改动影响对应路径或出现新问题时，才补充必要验证，不无故重跑。

程序内部 Rime/TSF/MSAA 调用和 DirectWrite 绘制缓冲区预览不能替代真实键鼠、已安装 TIP 自动路由或外部应用兼容性验收。小词表性能也不能外推到大词库。

## 构建环境与当前产物

Windows / PowerShell。VS2019、ATL 和固定 Weasel/Rime/Boost 缓存已准备，不要重复安装或下载。固定 Weasel 0.17.4 源码提交：`9cc96e20dc71b80876b12f689bb5863c76c2a7ed`。当前 x64 Rime 为 1.13.1，使用已有官方缓存；版本及哈希见原生整合文档和依赖锁。

```powershell
# 仅在修改后需要重建或用户需要交互宿主时运行
.\experiments\phase4\build-native-x64.cmd
python experiments/phase4/start-text-host.py --service-x64
python experiments/phase4/start-settings.py
```

已核对存在的产物路径：

- `.\experiments\phase4\build\tsf-x64\study_weasel_x64.dll`
- `.\experiments\phase4\build\study_service_x64.exe`
- `.\experiments\phase4\build\tsf_text_host_x64.exe`
- `.\experiments\phase4\build\study_settings_x64.exe`

上面列出的是阶段 4 隔离宿主，仍依赖仓库与缓存，共用 `experiments/phase4/runtime/interactive-settings.ini`。新产品包使用独立完整目录，不依赖仓库；两者都尚未被安装/注册为系统输入法。新窗口不要假设旧交互进程仍在运行。

## Computer Use 记录与协作约束

此前 `node_repl` 中的 `@oai/sky` 初始化成功，但 `sky.list_apps()` 在执行前被自动审批服务阻断：`404：当前 API 不支持所选模型 gpt-6-luna`。当时请求走 `https://anyrouter.top/v1/responses`，属于审批服务模型配置问题，不是动作被判定不安全。

用户后来明确要求“把那个 computer use 的问题记录，先完成后续开发，之后再修复”，此要求优先于更早“先修复再自动验收”的答复。之后没有重试或修改审批配置，不能声称已恢复。恢复时先读取届时适用的 Computer Use 技能与工具说明，通过正常审批通路，不使用 PowerShell 或其他 UI 自动化绕过审批。

用户已允许必要时 commit，并已批准 v0.5 设计、开源路线和此前 ATL 补装。原聊天对 `ui_probe.exe` 的操作许可已给出，不必重复询问同一授权；它不等同于系统安装/输入法注册授权。用户希望直接推进已授权工作，不反复确认、不停在计划、不重复调查和已完成测试。

本次环境未发现适用的 `AGENTS.md`。用户将自行开新窗口，不要主动创建新聊天。继续复用当前合适的工作区，不要仅为接续聊天而新建工作树。本轮未使用子 agent，当前指令也未授权主动委派；后续聊天的实际权限、工具和协作规则以该会话提供的指令为准。

本次交接文件提交与功能基线分开记录；接续时使用 `git status --short --branch` 和 `git log -5 --oneline` 获取实时状态，不把本文件快照当作永久状态。
