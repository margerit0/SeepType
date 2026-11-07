# 中文基础词库

StudyIME 的简体中文候选使用固定 CC-CEDICT `2026-11-06T08:10:12Z` 的中文词形和普通话读音，以 wordfreq 3.1.1 的中文词频排序。词库数据及适用改编按 **CC BY-SA 4.0** 分发，软件源码单独遵循其软件许可。

保留完整汉字词形及带声调的普通话来源；导出时使用来源中的简体字段、拼音转小写、去声调数字、`u:` 转 `v`，合并同词形和同拼音的重复词义。混合文字/标点词形和非标准普通话读音不进入这个全拼方案。每个输出词条都有原始 CC-CEDICT 行摘要对应关系。

权重按精确中文词形查询 wordfreq 的 Chinese large 词表，将其负 centibel 档位 `i` 转为 `max(1, floor(10 ** ((900-i)/100)))`；未收录的词形权重为 1。对于具有多个导出读音的单字，按 Unicode Unihan 17.0.0 `kHanyuPinlu` 的读音频次比例分配整字权重，未知读音计 1，分配结果取整且最低为 1。避免把高频字的全部频率同时赋予罕用读音。这是固定频率估计，不读取用户输入，也不使用在线服务；没有针对 200 条英文审核稿提高权重。

来源及署名：

- **CC-CEDICT community contributors**，由 MDBG 发布，基于 Paul Andrew Denisowski 的 CEDICT。官网：[CC-CEDICT](https://cc-cedict.org/wiki/)。完整快照及许可见仓库 `data/lexicon/source.lock.json`，运行包将其同时保存为 `data/chinese/cc-cedict-source.lock.json`。
- **Robyn Speer 和 wordfreq contributors**：[wordfreq](https://github.com/rspeer/wordfreq)，引用：Robyn Speer (2022), [rspeer/wordfreq v3.0](https://doi.org/10.5281/zenodo.7199437)。wordfreq 数据声明明确允许以 CC BY-SA 4.0 再分发；软件代码为 Apache-2.0。
- **Unicode, Inc.**：Unihan 17.0.0，数据版权 2025，遵循完整随附的 Unicode License V3。[kHanyuPinlu 说明](https://www.unicode.org/reports/tr38/#kHanyuPinlu) 保留了《现代汉语频率词典》及 Richard Cook、Ross Paterson、Tom Bishop 的来源与贡献说明。本项目只使用字符读音及频次，未复制原书正文。
- wordfreq 的原始语料、Google Books、Wikipedia、Leeds Internet Corpus、ParaCrawl、OpenSubtitles 及 **SUBTLEX 作者**的完整署名和文献保存在随附 `WORDFREQ-README.md` / `licensing/third-party/wordfreq/README.md`。SUBTLEX 是免费开放的数据；该说明保留了 Marc Brysbaert 授权 wordfreq 为任何用途再分发、要求作者署名的声明。中文 SUBTLEX 文献：Cai, Q. & Brysbaert, M. (2010), [SUBTLEX-CH](https://doi.org/10.1371/journal.pone.0010729)。

生成器为 `tools/dictionary/cedict.py`，固定频率来源见 [sources.lock.json](sources.lock.json)。输出附原文行摘要、转换说明和完整 CC BY-SA 4.0 许可。wordfreq 的分词器、jieba 词典和 Python 运行库不进入产品。

这部分只负责中文候选与排序。英文释义仍来自原有 **200 条待人工审核**的数据；没有扩大、替换或自动批准那批英文词条。输入法的日常词序、长句和真实应用体验仍需要桌面验收。

仓库保留等权重、仅按字符频次加权以及 wordfreq 的对比记录，见 `tools/dictionary/compare.py` 与阶段 6 报告。当前方案使用 wordfreq 的词频，并以 Unihan 修正多音单字的读音权重。
