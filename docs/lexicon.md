# 200 条词库准备与审核流程

2026-11-07。此阶段完成可审核词库、来源追溯、可重复导出和真实引擎验证。200 条是审核稿，尚无人工作出通过决定。

## 当前数据

初始范围为 10 类各 20 条：问候与交流、日期与时间、家庭与关系、食物与饮食、家居与生活、出行与地点、工作与学习、数码与购物、身体与自然、活动与感受。每条使用精确中文词形，只查本地表。

来自 [CC-CEDICT](https://cc-cedict.org/wiki/) 的 2026-11-06T08:10:12Z 快照，共 125369 个源词条。原文件头、官方网页均声明 CC BY-SA 4.0；已保留官方完整许可、署名及改编说明。实际使用的 202 条源记录已随仓库保存；原始压缩包与全文留在缓存。见 [来源锁定](../data/lexicon/source.lock.json) 和 [数据说明](../data/lexicon/README.md)。

每条保留原词条 SHA256、源文件行号和改写说明。37 条需重点核对：包括“苹果”的水果义/公司名、“妻子”的不同读音、“问题”的 question/problem、“邮件”的电子/纸质邮件、“保存”的电脑操作义。未直接把词典第一段说明当作提交值；量词、参见、括号标签和省略号不会自动进入英文提交。

## 审核与导出

打开 [离线审核页](lexicon-review.html)。可筛选类别、搜索中英文、只看重点条目，逐条选择通过或暂不收录。修改英文后，该条会重新变为待审核。页面保存浏览器草稿，下载 JSON 只包含本次实际修改或作出决定的条目，不会重署他人已经完成的审核。

导入下载的记录：

    python tools/lexicon/pipeline.py import-review "<审核记录 JSON 路径>"
    python tools/lexicon/pipeline.py review --output docs/lexicon-review.html

导入会核对整个批次和每条原文的摘要，记录审核者、时区时间、最终文本摘要及修改说明；数据发生变化时旧审核不能继续使用。输入先完整校验再原子替换，损坏或过期审核不会覆盖当前数据。审核者署名来自记录本身，本地流程不提供身份认证。

生成开发预览：

    python tools/lexicon/pipeline.py build --mode preview --output .cache/lexicon-preview

该目录含 Lua 词表、审核页、逐条记录、源记录、许可、署名、文件哈希清单与确定性 ZIP。预览明确标记开发数据。词库显示与提交文本必须一致；当前运行时尚未实现两者分离。

完成整批人工审核后生成正式词库数据：

    python tools/lexicon/pipeline.py build --output .cache/lexicon-release

默认模式是正式导出。只要还有待审核条目就失败；全部已审核时仅导出通过的记录，拒绝项不进入 Lua；空词库也会被拒绝。机器检查不能将条目标成人工通过。当前 200 条待审核，因此尚无正式词库数据包。

这里只导出词库数据。默认阶段 4 交互宿主仍使用原来的 21 条测试词对；本次 200 条仅进入独立阶段 5 运行目录。正式接入产品与安装打包继续在后续阶段完成。

## 可重复性与验证

    python tools/lexicon/pipeline.py validate
    python tools/lexicon/verify.py
    .\experiments\phase5\build-probe.cmd
    python experiments/phase5/verify-lexicon-runtime.py

- [来源检查](../experiments/phase5/results/lexicon-validation.json)：200 条记录逐条对照完整源快照验证行号、原文及摘要；10 个类别各 20 条；当前人工通过 0 条。
- [25 项流程检查](../experiments/phase5/results/lexicon-pipeline.json)：重复词形、错误来源、许可缺失、控制字符、词典元信息、过期审核、部分审核、审核失效、导入原子性和导出完整性。测试中的“审核者”只存在于独立临时测试目录，未写入产品数据。
- [200/200 真实引擎检查](../experiments/phase5/results/lexicon-runtime-x64.json)：沿用现有 C API 探针，另编 x64 程序，在真实 librime 1.13.1 / librime-lua 中逐条核对候选页释义、完整英文提交和普通中文提交。200 条均在第一页找到，13 条不是首候选。
- [数据预览包记录](../experiments/phase5/results/lexicon-package.json)：归档排序、固定时间戳、逐文件摘要；相同输入与工具版本的两次导出字节一致。数据源 JSON 固定 LF，官方许可原始字节保持不变，避免 Git 换行转换破坏摘要。

需要完整源快照时：

    python tools/lexicon/pipeline.py fetch-source

优先使用已有缓存；官方“最新下载”若已更新而不再匹配固定哈希，命令会失败，不会悄悄换源。200 条审核和导出本身只依赖仓库中保留的源记录，不要求重新下载全量词典。

审核页的 200 条数据与 JavaScript 语法已检查；浏览器实操还未验收。上述程序验证不构成人工语言审核、已安装 TSF 路由、真实应用兼容性或大词库性能结论。原阶段 3/4 数据、运行目录和旧报告未被替换。Computer Use 问题继续按用户安排暂缓。

## 后续

使用实际人工审核记录逐步收敛词义；独立推进软件第三方许可汇总、最终产品标识和可审阅安装/卸载产物。之后再恢复 Computer Use，并开展真实应用和桌面验收。
