# 拾词输入法软件与数据许可

2026-11-07，**StudyIME 0.5.0-dev.2 / Windows 11 x64 开发预览**。新代码和原创图标为用户已确认的 GPL-3.0-or-later；中文基础词库与英文学习数据分别遵循 CC BY-SA 4.0。

这版通过移除 WTL、从固定源码构建专用 Rime/Lua，以及更换中文基础词库，处理了 dev.1 的三个具体许可/来源阻止项。人工词义审核、实际安装/卸载及桌面验收仍未完成，开发预览不能视为正式发布。

机器清单：[components.json](../licensing/components.json)。实际随产品源码包提供的材料：[product-sources.lock.json](../licensing/product-sources.lock.json)。早期原始收集记录：[sources.lock.json](../licensing/sources.lock.json)。完整软件许可保存在 `licensing/third-party`；选择后的源码文件保留原始字节与原归档摘要。

| 实际组成 | 许可与处理 |
| --- | --- |
| StudyIME 新代码、原创图标 | GPL-3.0-or-later；完整文本与 [版权声明](../COPYING.md) 随包提供 |
| 修改版 Weasel 0.17.4 | 固定 `9cc96e20dc71b80876b12f689bb5863c76c2a7ed`，保留上游 GPLv3、原源码 bundle、正式生成器与修改补丁 |
| WTL | MS-PL；**不再编译或链接到产品**。只有未修改的独立 Weasel 源码 bundle 保留原 WTL 源文件与声明 |
| Boost 1.84.0 | BSL-1.0；固定原始归档，编译 serialization/thread/chrono，保留实际包含头文件与库摘要 |
| Rime 1.13.1 | 核心 BSD-3-Clause；从固定源码构建，记录编译命令、源文件、头文件、静态库和工具链。运行包和源码包均不使用官方预编译 DLL |
| librime-lua / Lua 5.4.7 | 插件 BSD-3-Clause，Lua MIT。只编入 Lua 插件；octagram、predict 不在新 DLL 或产品源码材料中 |
| glog、LevelDB、yaml-cpp | 分别 BSD-3-Clause、BSD-3-Clause、MIT；由固定源码编译 |
| marisa-trie | BSD-2-Clause / LGPL-2.1 双许可，选用 BSD 条件；OpenCC 使用同一份单独构建的 marisa 库 |
| OpenCC 1.1.7、Darts、RapidJSON | 分别 Apache-2.0、BSD-3-Clause、MIT 及随附声明；代码仍为 Rime 静态依赖。产品直接输出来源中的简体词形，不分发旧转换词典 |
| Luna Pinyin 方案代码与 prelude 预设 | LGPLv3；Luna 只保留三个方案/拼写规则文件及许可证。**Luna 混合词典、essay 和 librime 的旧 data/ 预设不在交付源码材料中** |
| CC-CEDICT 中文词形/读音 | 固定 2026-11-06 快照，CC BY-SA 4.0；简体字段、明确普通话读音、逐条原文行摘要、转换说明与署名齐备 |
| wordfreq 3.1.1 中文词频 | 数据明确允许按 CC BY-SA 4.0 再分发；保留 Robyn Speer、源语料及 SUBTLEX 作者的完整署名，注明 SUBTLEX 为免费开放数据。原始再分发声明完整随包保存；运行包不包含其 Python 运行库或 jieba 词典 |
| 英文 200 条审核稿 | 固定 CC-CEDICT 来源，CC BY-SA 4.0；仍为 **0 条人工通过、200 条待审**，没有扩大、替换或自动批准 |
| Unicode Unihan 17.0.0 | Unicode License V3；使用 kHanyuPinlu 分配多音单字的读音权重，保留原始频率和贡献者说明 |
| CMake 3.31.6 | 仅为源码复建提供固定官方便携包，保留 BSD-3-Clause 及全部随附声明；不进入运行包 |
| Windows / MSVC / SDK / Ninja | 使用已有 VS2019 / SDK，静态 CRT；不复制 Windows 系统 DLL 或完整 VS 工具链 |

WTL 的处理依据是 [GNU 对 MS-PL 的说明](https://www.gnu.org/licenses/license-list.html#ms-pl)。解决方式是从组合程序中移除 WTL，未声称 MS-PL 与 GPL 变得相容。产品使用 Win32 消息循环和 ATL 几何类型，v0.5 候选窗继续由 `CandidateUi` 绘制。编译包含记录拒绝任何 WTL 头文件。

专用引擎入口为 `tools/packaging/build_rime.py`。librime 不含旧 `data/`，不构建需要那些预设的独立命令行工具；所需部署功能仍由 DLL 的 C API 提供。上游字节、选择规则、原始归档摘要、选择后归档摘要及补丁均可核对。新 DLL 只包含 Lua 插件，不沿用 dev.1 官方 DLL 内嵌 octagram 的组成声明。

中文基础词库说明见 [data/chinese](../data/chinese/README.md)，固定来源见 [sources.lock.json](../data/chinese/sources.lock.json)。wordfreq 的 [原始 README](../licensing/third-party/wordfreq/README.md) 明确写明数据可以按 CC BY-SA 4.0 再分发，保留了作者取得的 SUBTLEX 再分发许可及完整引用。导出只使用精确中文词形的频率档位，没有从用户输入中收集数据。

普通构建、导出及复建验证默认离线，复用固定材料。首次收集或恢复缺失文件需显式下载并核对锁定摘要，不自动跟随最新版。历史官方二进制和旧混合词典可留在原开发缓存用于既有实验，但不属于本版运行包或产品源码包。

剩余产品发布门槛由 `package-manifest.json` 列出：真实人工词义审核、安装/卸载及实际 TSF/桌面验收，以及开发通道标识。安装、注册和 Computer Use 的既有授权边界保持有效。
