# 技术方案与阶段 3 验证

更新：2026-11-01。以已确认的 v0.5 为设计基线，核心隔离实验通过。当前是 Rime + WeaselUI 测试宿主，不是完整系统输入法；没有运行 WeaselSetup、WeaselDeployer、WeaselServer 或注册 TSF。

## 已固定的基线

| 组件 | 实际使用与证据 |
| --- | --- |
| Weasel 源码 | 0.17.4，提交 `9cc96e20dc71b80876b12f689bb5863c76c2a7ed` |
| 运行时 | 该安装包内的 x86 `rime.dll`，运行时报告 librime 1.13.1；x64 Windows 上使用 x86 宿主 |
| Lua | 实际 DLL 的 lua 模块、filter、processor、ShadowCandidate、读取选中候选和提交 API 均已运行；精确插件源码提交尚未追溯 |
| C API 头文件 | 官方 x64 librime 1.13.1 归档中的头文件；没有以其 DLL 替代包内 x86 DLL |
| 中文数据 | Weasel 发行附带的朙月简体方案、词典与 OpenCC 数据，复制到独立 shared/user 目录；实验关闭用户词典学习 |
| 英文数据 | 21 个自拟 test-only 词对；没有正式分发词库 |
| 工具链 | VS 2019 Build Tools 16.11.48；MSVC 目录 14.29.30133，cl 文件版本 14.29.30159；SDK 10.0.19041.0；Python 3.13；Boost 1.84.0 头文件 |

用户在原聊天中已单独授权补装 C++ ATL x86/x64，安装成功。其余安装格式文件仅解包读取。准确下载 URL、源码提交与 SHA256 见 [依赖锁文件](../experiments/phase3/dependencies.lock.json)。本次重新校验固定缓存通过；没有进行全新机器/空缓存构建测试。

来源：[Weasel 0.17.4](https://github.com/rime/weasel/releases/tag/0.17.4)、[源码树](https://github.com/rime/weasel/tree/9cc96e20dc71b80876b12f689bb5863c76c2a7ed)、[librime 1.13.1](https://github.com/rime/librime/releases/tag/1.13.1)。单独 x64 归档中的 Lua 提交记录不等于 x86 DLL 的来源证明。

## 实际路径与补丁边界

Rime 全拼候选 → 简化字/去重 → Lua 精确查表 → ShadowCandidate 附加 comment → Weasel 双行布局。中文 text、顺序和原始候选不被改写；关闭学习或缺少释义时返回原候选。词表一次加载到内存，没有每键文件读取、联网查询或输入历史记录。

键盘英文动作位于 Lua processor：读取当前会话的真实选中候选，重新查表并检查开关、候选范围和光标位置。`Ctrl+Shift+Enter` 提交完整词表值，不从省略后的显示注释取文本。无释义、学习关闭、非完整组合时消费该专用动作且保留组合，避免回退提交拼音或丢字。空格、数字和普通点击继续选择中文。

原 [HorizontalLayout.cpp](https://github.com/rime/weasel/blob/0.17.4/WeaselUI/HorizontalLayout.cpp) 把 label/text/comment 横向排列，现有配置未提供本设计所需的上下两行。实验增加 `StudyLayout`，继承真实 StandardLayout，英文置于中文上方；整项共用高亮和点击区，长英文由 DirectWrite 单行省略。

[weasel-ui-spike.patch](../experiments/phase3/patches/weasel-ui-spike.patch) 对一个上游文件增加 **10 行**：7 行编译期开关选择新布局，3 行把本窗口已经生成的绘制缓冲区交给测试观察器。观察器只在明确的内部测试采样点写文件，不读取桌面；正常运行不采集画面。原 HorizontalLayout、librime 引擎和 IPC 均未修改。

学习状态在实验宿主中暂借注释颜色控制双行空间；这不是正式配置协议。实验外围按钮也不代表最终工具区或设置。正式实现需明确学习状态、候选版本和菜单动作在会话/前端之间的传递，避免陈旧候选提交，不复制第二套翻译逻辑。

## 验证结果

| 验证 | 结果与适用范围 |
| --- | --- |
| 真实引擎与 Lua | 18/18：加载、候选顺序、精确释义、开关、中文/英文提交、长词完整值、当前页关联、分段保护、缺失/损坏词表回退 |
| 原生窗口与内部交互 | 27/27：创建、真实绘制、两行命中区、鼠标消息选择、选词后重建、翻页后的英文、无释义开关、浅深主题、退格及 20 轮连续操作；全部是同进程的自身窗口消息 |
| DPI 参数布局 | 24/24：普通/长英文/缺词 × 学习开关 × 96/120/144/192 DPI；英文区和中文区都在同项点击范围内 |
| 原生预览 | 保存 5 张真实 Weasel 绘制缓冲区图，并检查双行、长词省略和主题；不是桌面截图 |
| 真实桌面鼠标/快捷键 | **未测试**。用户已明确授权 ui_probe，但电脑操作工具仍返回 `Computer Use was not approved to use ui_probe` |
| 完整服务/TSF、三个实际应用、安装卸载 | **未测试** |

记录：[engine.json](../experiments/phase3/results/engine.json)、[native-ui.json](../experiments/phase3/results/native-ui.json)、[native-layout.json](../experiments/phase3/results/native-layout.json)、[桌面检查状态](../experiments/phase3/results/desktop-interaction.json)。

本机当前窗口 DPI 为 144，普通候选区域为 744×81，学习关闭为 744×55。96 DPI 参数下对应 498×55 / 498×38；宽度未包含尚未实现的右侧工具区。没有实际切换系统缩放或执行多显示器测试。

### 暖态性能

同一次合成输入 `pingguo`，每组 300 个样本，统计包含输入解码和第一页候选生成，单位毫秒：

| 状态 | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| 不含 Lua 扩展的基准 | 0.238 | 0.340 | 0.471 |
| 扩展加载、学习关 | 0.675 | 1.141 | 1.286 |
| 扩展加载、学习开 | 0.667 | 1.180 | 1.384 |

本次学习开与基准的 p95 相差约 0.84ms，低于实验设定的 2ms 参考目标。它不是单次查词耗时或普遍延迟保证；不能外推到大词库、所有输入和实际应用。词库扩充前仍需冷启动、内存和更多输入分布测量。

## 本次修复及维护要点

1. **ATL 初始化丢失**：本机 MSVC 下，同一编译单元包含 Rime API 头文件和 ATL 时，Rime 头文件的 `.CRT$XCU` 声明影响 selectany 初始化。最小对照中 ATL 的 cbSize/LockCount 从 44/-1 变为 0/0，注册窗口类时崩溃。将 Rime API 移入 `StudyEngine.cpp`，UI 只包含普通 C++ 数据接口后恢复；启动检查已覆盖。没有修改上游头文件，不推断官方完整构建也存在此问题。
2. **候选窗口生命周期**：Weasel 鼠标选词后销毁 popup，下一次组合必须重建。宿主按真实 Weasel 窗口类 atom 查找自身候选窗，不能把其他同线程输入窗口当成候选窗。
3. **只有样式变化时刷新**：缺词候选的 comment 始终为空，仅改变学习状态不会让 UI::Update 发现候选变化。宿主显式刷新布局和绘制，避免收起/展开失效。
4. **构建诊断**：本机 PDB 调试链接曾报 LNK1101；当前使用正常可构建的 /O2 或 /Od 加栈帧和 map 文件定位，不依赖该 PDB 路径。实验未进一步修改工具链。

## 后续实现边界

- 保留 v0.5 全部目标：右侧工具区、英文菜单与完整释义浮层、设置、翻页定宽、180ms 翻页和 240ms 学习开关动画。它们尚未原生实现，不是设计删减。
- 固定并构建完整 Weasel 服务/TSF 组件，核对现有前端与 Lua 动作的会话同步、样式序列化和失焦清理；当前宿主没有验证 IPC。
- 安装前先确定产品标识、目录和现有小狼毫的关系，制作可审阅安装方案；系统安装、默认输入法及输入设置变更仍须单独明确授权。
- 扩充约 200 条词表前完成具体来源快照、人工释义审核与再分发条件核查。当前 21 条只供实验。
- 上游升级时重放独立补丁并重跑实际候选、布局、提交与生命周期检查；自动合并成功不等于运行兼容。
