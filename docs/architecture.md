# 技术调查与验证计划

更新：2026-10-31。原生技术仍处于源码/官方资料核查；**没有编译、加载 DLL、运行输入法、注册 TSF 或修改系统输入设置**。阶段 2 的网页原型已完成并通过浏览器交互检查，这不代表以下原生验证项已通过。

原型使用原生 HTML/CSS/JavaScript；`prototype/ime-candidates.html` 为可编辑源，`prototype/index.html` 为 visualize 工具生成的独立预览页，运行无需 Node/构建服务。该预览包装工具不属于输入法产品依赖。测试用 HTTP 服务仅绑定 127.0.0.1，不涉及系统安装。详见 [原型说明](../prototype/README.md)。

设计现已迭代为 v0.5 轻量横条：后续优先验证 HorizontalLayout 与同排小工具区，旧纵向学习型不再作为当前实现提案。详情按需浮出，需校验不抢焦点及关闭时机。原型按容器宽度减少每页项数仅用于小窗口展示，尚未验证原生 Rime 动态页大小；不得直接当作已解决的接口能力。用户新增学习模式 240ms 收起/展开动画，现仅在网页原型实现；原生窗口尺寸、锚点、绘制与状态同步需要单独验证，不能将 CSS 动画当作原生可行性证据。

## 版本与证据

| 对象 | 本次查看基线 | 已知与限制 |
| --- | --- | --- |
| Weasel | `0.17.4`，`9cc96e20dc71b80876b12f689bb5863c76c2a7ed` | GitHub latest 正式发行 API 本次返回此版本，发行于 2025-06-04；建议技术验证先用此基线 |
| librime | Weasel 子模块 `1c23358157934bd6e6d6981f0c0164f05393b497`；另核查 `1.13.1` 工作流 | Weasel 0.17.0 日志写升级至 1.13.1；不能据此推断 0.17.4 安装包内 DLL 的精确构建 |
| librime 当前正式发行 | API 返回 `1.17.0`，2026-06-06 | 仅记录现状，不因其较新就替换验证基线 |
| librime-lua | `6da5d6cedb853380ed1b5b9b6979cb1a9c028353` | 这是本次阅读的上游源码，不是已确认与 0.17.4 捆绑的插件版本 |
| 朙月拼音 | `56b934b099dfbeab842320f13aa8b461a6ab3e42` | 评估 `luna_pinyin_simp`，继承主方案并启用简化字；尚未固定完整部署依赖 |

版本资料：[Weasel release](https://github.com/rime/weasel/releases/tag/0.17.4)、[Weasel 变更日志](https://github.com/rime/weasel/blob/0.17.4/CHANGELOG.md)、[Weasel 树与子模块](https://api.github.com/repos/rime/weasel/git/trees/0.17.4?recursive=1)、[librime release](https://github.com/rime/librime/releases/tag/1.17.0)。最终版本清单还须包含工具链、插件、方案、词典、二进制哈希，当前表不等于构建锁文件。

## 五项关键调查结论

1. **Lua 路线有上游支持，所选安装包的实际能力未验证。** librime 1.13.1 的 [发布工作流](https://github.com/rime/librime/blob/1.13.1/.github/workflows/release-ci.yml) Windows 任务显式包含 `hchunhui/librime-lua`；Weasel 历史日志也记录包含 Lua。读取的 Lua [README](https://github.com/hchunhui/librime-lua/blob/6da5d6cedb853380ed1b5b9b6979cb1a9c028353/README.md) 支持 processor/filter 等扩展；[types.cc](https://github.com/hchunhui/librime-lua/blob/6da5d6cedb853380ed1b5b9b6979cb1a9c028353/src/types.cc) 存在候选 comment、ShadowCandidate、get_selected_candidate、set_option、commit_text 等绑定。阶段 3 必须检查实际加载的库版本并运行最小脚本，不能拿新源码代替旧二进制验证。
2. **未找到配置即可满足上下双行的证据，预计需前端补丁。** 检查 [默认配置](https://github.com/rime/weasel/blob/0.17.4/output/data/weasel.yaml)、[配置说明](https://github.com/rime/weasel/wiki/Weasel-%E5%AE%9A%E5%88%B6%E5%8C%96) 和 [HorizontalLayout.cpp](https://github.com/rime/weasel/blob/0.17.4/WeaselUI/HorizontalLayout.cpp)：label、text、comment 共用基础 y，x 依次增长，align_type 调整行内对齐。`horizontal` 只是候选横排；`vertical_text` 是文字竖排，不是上下双行。[VerticalLayout.cpp](https://github.com/rime/weasel/blob/0.17.4/WeaselUI/VerticalLayout.cpp) 也把注释放在同项横向位置。向 comment 塞换行或交换中英文 text 会影响几何/提交语义，不作为架构方案。
3. **预计改动集中在候选窗口，但不承诺只改一个文件。** 布局测量、文本/注释矩形、整项高亮和命中区需要一致；截断、DPI、屏幕避让也须核验。涉及 HorizontalLayout（若选 A）或 VerticalLayout（若选 B）、Layout/StandardLayout 辅助逻辑、WeaselPanel 绘制/鼠标事件。新增样式字段可能涉及 `include/WeaselIPCData.h` 的初始化/比较/序列化和 `RimeWithWeasel.cpp` 的 `_UpdateUIStyle`；学习状态也需由会话传给 UI。接口调整后需构建配套客户端与服务端，不能假定混搭旧文件安全。
4. **键盘英文提交优先 Lua，鼠标入口由前端承接。** 当前 `WeaselPanel::OnLeftClickedUp` 用 UI 回调选词，`RimeWithWeasel` 用当前页候选 API，不能让 Lua 独自绘制或接收新的右键菜单操作。建议前端只发出针对当前会话/候选的语义动作，最终统一走同一词表校验和提交逻辑；具体桥接要实验。避免模拟系统键盘、剪贴板粘贴或双份翻译逻辑。来源：[WeaselPanel](https://github.com/rime/weasel/blob/0.17.4/WeaselUI/WeaselPanel.cpp)、[RimeWithWeasel](https://github.com/rime/weasel/blob/0.17.4/RimeWithWeasel/RimeWithWeasel.cpp)、[IPC 数据](https://github.com/rime/weasel/blob/0.17.4/include/WeaselIPCData.h)。
5. **用少量职责清楚的补丁维护。** 不改 librime 核心、解码排序或 TSF 协议行为；优先以现有 comment 传展示文本。学习状态/鼠标动作所需协议变化先实验证明必要性。UI 补丁、Lua 模块、词表/构建工具分开，记录每个补丁的上游提交、理由、文件、验证步骤。每次上游升级重放并检查实际行为，不把“可自动合并”当成兼容通过。

## 推荐模块边界

Rime 全拼候选 → 简化字/去重后的最终候选 → Lua 学习 filter 精确查表、附加 comment → Weasel 双行展示。中文 text、排序及选词语义保持不变；需保留候选原有元信息/注释，学习关闭时恢复，不直接不可逆覆盖共享候选。

英文动作读取当前会话的真实选中候选，再校验最终中文词形、候选范围、学习开关及可提交值；不从已省略的 comment 提取英文，不用翻页前的序号缓存。分段组合先采用 design.md 的受限提交规则，避免简单 commit_text + clear 丢掉未提交的内容。

首批小词表启动时一次加载为 Lua 内存映射；按候选精确查询，不每键读盘、不联网、不遍历整个候选流或词库。扩充前测量冷启动、内存与查词开销，再决定是否引入索引，当前不引入数据库服务。查词失败时返回原候选。学习关闭走短路；不增加输入历史日志。引擎自学习用户词典、调试日志、错误转储的隐私行为需单独审查。

## 构建调查

[INSTALL.md](https://github.com/rime/weasel/blob/0.17.4/INSTALL.md) 提及 VS C++/ATL/MFC、CMake、Boost、NSIS；该版 [release-ci.yml](https://github.com/rime/weasel/blob/0.17.4/.github/workflows/release-ci.yml) 实际使用 windows-2019、VS2019 配置、Boost 1.84.0。文档与 CI 年代不一，下一阶段以可复现实验选工具链，不能据此宣称当前已可构建。

CI 调用 `get-rime.ps1 -use dev`，未指定 tag。[脚本](https://github.com/rime/weasel/blob/0.17.4/get-rime.ps1) 默认请求最新正式 release；dev 是构建用途，不是夜间版。插件安装脚本也可能拉取浮动分支。因此需锁定源码/产物及 SHA-256，禁用构建中的隐式更新；检查并移除 MVP 不需要的自动更新入口。当前没有运行这些脚本。

本机只检查 PATH：git、Python、Node、rg 可用；cmake、cl、msbuild 未在 PATH 找到，**不等同于没有安装 Visual Studio**。后续可只读检查 vswhere；本轮未安装工具链。尚未审计独立产品与已装小狼毫的注册标识、安装路径、用户目录是否冲突，不能声称可并存。

## 阶段 3 最小实验与门槛（全部未测试）

| 验证 | 优先隔离办法 | 必须记录的结果 |
| --- | --- | --- |
| 基础引擎与 Lua 可运行 | 固定产物 + 独立用户/共享目录，rime_api_console 或等价测试程序 | 实际版本、Lua 组件加载、真实全拼候选 |
| 本地释义 | 约 20 条审核样例接真实候选 | 候选排序/中文未变；简化字与翻页后关联准确；缺失回退 |
| 双行原生布局 | 独立 WeaselUI 测试窗口，不注册系统输入法 | 高亮/点击区域、长英文、空释义；100/125/150/200% 缩放 |
| 英文提交 | 向隔离会话发送约定按键并检查 commit | 当前候选、无释义、长词完整值、重复键、部分组合无丢字 |
| 开关 | 组合中关闭/重开与会话切换 | 无误提交，无旧英文残留，布局状态一致 |
| 性能与故障 | 合成输入对照无学习版；词表损坏/缺失 | 查词耗时 p50/p95/p99、总延迟、内存；建议暖态每页新增 p95 ≤2ms 作为实验目标，不是实测承诺 |

用户确认设计后推进这些实验；设计期间仅可按需做小实验。通过后才正式实现。安装测试另行取得用户对具体隔离环境/安装动作的明确同意，不更换系统默认输入法。最终记事本、浏览器、VS Code、安装/卸载及显示缩放目前均为“未测试”。
