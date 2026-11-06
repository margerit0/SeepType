# 拾词输入法软件许可与来源汇总

2026-11-07。范围为 **StudyIME 0.5.0-dev.1 / Windows 11 x64 开发预览包**。新写代码与原创图标已由用户确认使用 GPL-3.0-or-later；英文词库继续遵循 CC BY-SA 4.0。此清单记录已取得的材料和尚未解决的事项，不把“已收集许可”标成“全部可以发布”。

机器可读清单：[components.json](../licensing/components.json)。固定源码归档、URL、提交和摘要：[sources.lock.json](../licensing/sources.lock.json)。补充许可原文与摘要：[notices.lock.json](../licensing/notices.lock.json)。完整许可保存在 [licensing/third-party](../licensing/third-party)，数据声明保存在 [data/lexicon](../data/lexicon/README.md)。

| 实际组成 | 许可及证据 | 当前处理 |
| --- | --- | --- |
| StudyIME 新代码、原创图标 | GPL-3.0-or-later；[用户确认后的声明](../COPYING.md) | 随包附完整 GPL 文本与对应项目源文件 |
| 修改版 Weasel | 0.17.4，`9cc96e20dc71b80876b12f689bb5863c76c2a7ed`；GPLv3 | 保留原始源码、许可、v0.5 覆盖层与产品覆盖层；品牌资源换为拾词，版权声明保留在随附材料 |
| WTL 头文件 | 随上述 Weasel 提交；原头文件标明 MS-PL | 保存原声明和完整 MS-PL；与 GPL 结合的相容性尚待解决，列为发布阻止项 |
| Boost serialization/thread/chrono 与头文件 | 1.84.0，BSL-1.0；固定原始归档摘要 | 使用已有工具链编译，源码材料附原始归档与声明 |
| 官方 x64 `rime.dll` | 1.13.1；SHA256 `2d8f1bc3737635a11d9fb1bfca4dc9e70533633930a8a0142a81ca879c39c45b` | 记录原归档及文件摘要、PE 架构和导入；核心为 BSD-3-Clause，但 DLL 内还包含 GPLv3 插件，不能统一标为 BSD |
| librime-lua / octagram / predict | 包内 version-info 分别为 `e3912a4` / `dfcc151` / `920bd41`；完整提交已固定 | lua、predict 为 BSD-3-Clause；**octagram 为 GPLv3**。未启用模块不会消除已嵌入代码的许可义务，均收录原文及源码 |
| Lua | 二进制包含 Lua 5.4.7 版本和版权字符串；匹配 `thirdparty` 固定提交 `115e000c...` 的 5.4.7 源码 | 保存完整 `lua.h` 中的 MIT 授权；不把插件的 BSD 许可当成 Lua 的许可 |
| glog、LevelDB、yaml-cpp、marisa-trie、OpenCC | 从固定 librime 提交的 gitlink 取得版本；分别 BSD-3-Clause、BSD-3-Clause、MIT、BSD-2-Clause/LGPL-2.1 双许可、Apache-2.0 | 保存归档及所有随附许可；marisa 使用其 BSD 选项；保留 OpenCC 内嵌 marisa、RapidJSON、Darts（BSD-3-Clause）声明 |
| Windows / MSVC | VS2019、MSVC 19.29，静态 CRT；Windows 系统 API | 工具链单独安装；不复制 Windows 系统 DLL 或随包提供完整 VS 工具链 |
| 中文方案与预设 | 固定 Luna Pinyin `95930900...`、prelude `3c602fdb...`、essay `573bbeb5...`；上游 LGPLv3 | 内容与原缓存逐文件换行归一化后匹配，保存完整源文本、来源感谢和 LGPL/GPL 文本；底层混合词典来源核验尚未全部完成 |
| OpenCC 转换数据 | 固定 OpenCC 1.1.7 源码中的 TSCharacters/TSPhrases 与 t2s 配置 | 使用可直接追溯的文本词典；配置中的 `ocd2` 改为 `text`，逐文件记录改动；不分发无法逐字追溯的缓存编译词典 |
| 英文 200 条审核稿 | 固定 CC-CEDICT 快照，CC BY-SA 4.0 | 来源许可、署名、变更记录齐备；人工审核仍为 0/200，只能作明确标识的开发预览 |

公开发布仍有三个许可/来源阻止项：WTL 的 MS-PL 与 GPL 组合问题；官方 Rime 二进制原始 CI 缓存、工具链与全部静态依赖构建输入尚未独立重现；中文词典底层混合来源再分发核验未完成。完整源码材料、来源锁和许可文本有助于解决这些问题，但不能替代解决结果。除此之外，词义人工审核、实际安装/卸载与桌面验收仍是独立的产品发布门槛。

产品运行包只选择所需文件，不复制上游安装器、更新器、curl/WinSparkle、plum、7-Zip 程序或无关输入方案。源码材料保留依赖仓库原有测试/工具源码及其许可，这不表示这些测试程序进入运行包。

所有收集工具默认复用本地固定材料。首次收集或恢复缺失材料须显式传 `--fetch`，下载后核对锁定摘要；普通构建、打包、验证不联网。新增依赖只能显式扩展锁，不能静默移动已有版本。
