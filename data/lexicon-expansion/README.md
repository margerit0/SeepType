# 英语词汇扩充的来源与主题配置

2026-11-08。本目录保存外部词表的固定快照、可追溯的目标词形和场景主题配置，不包含新编的英文释义。用户指定新释义与场景词汇由后续配置的外部 API 生成，本轮只完成离线准备。

| 文件 | 用途 | 固定范围 |
| --- | --- | --- |
| `sources/ielts-ecdict.jsonl` | IELTS 工作清单、词频排序参考 | ECDICT 提交 `39cfb9672c0906b63569e0453c2e6abfb9ab182a` 中恰好带 `ielts` 标签的 5,040 行 |
| `sources/cefrj-vocabulary-profile-1.5.csv` | A1–B2 词形、词性与分级 | CEFR-J 1.5，7,799 个原始记录 |
| `sources/octanove-vocabulary-profile-c1c2-1.0.csv` | C1–C2 词形、词性与分级 | Octanove 1.0，2,136 个原始记录 |
| `scenarios.json` | 20 个生活、留学与雅思话题的主题配置 | 仅分类与范围；没有预填英语词条 |
| `sources.lock.json` | 提交、URL、原文件/摘录哈希、使用字段、署名 | 原始快照与摘录分别固定，更新必须显式换版本 |
| `api.example.json` | 后续外部服务配置示例 | 不含 API key；示例地址与模型不能执行 |

CEFR 斜杠分隔的拼写变体分别保留，大小写归一后保留原始写法和各词性，得到 8,845 个不同词形。与 IELTS 工作清单合并后为 10,625 个目标。没有推断词族，也没有把 CEFR 等级当作 IELTS 标签。该 IELTS 清单不是官方大纲或所有雅思词汇的全集。

ECDICT 只摘录 `word`、`tag`、`bnc`、`frq`，另记原逻辑行号与完整行的规范化 SHA256；没有复制其中的中文/英文释义、例句、音标或音频。其完整 CSV 留在忽略目录，后续可用 `verify-sources --full` 对照原始文件复算摘录。

来源与许可分别保留：

- ECDICT：上游仓库声明 MIT；完整原文保存在 `notices/ECDICT-LICENSE.txt`。此处仅使用上述词形、标签与词频字段。
- CEFR-J：The CEFR-J Wordlist Version 1.5. Compiled by Yukio Tono, Tokyo University of Foreign Studies。其说明允许研究和商业使用并要求正确引用，原文在 `notices/CEFRJ-README.md`。
- Octanove：Octanove Vocabulary Profile C1/C2 Version 1.0，Octanove Labs；按 CC BY-SA 4.0 使用。完整许可复用 `../lexicon/licenses/CC-BY-SA-4.0.txt`，哈希列入来源锁。
- 离线请求里的中英释义参考来自已有的 CC-CEDICT 固定快照，沿用其来源、逐条摘要及 CC BY-SA 4.0。参考命中并不代表已选择或已审核的译词。

生成目录在 `.cache/lexicon-expansion/`。来源事实、外部模型草稿和旧有 200 条审核数据各自保留身份；本工具不把模型输出转换为人工审核记录，也没有发布或运行时导入命令。后续模型草稿的数据许可与发布条件需在实际采用时记录，不能仅由模型声称。

操作与格式说明见 [扩充流程](../../docs/lexicon-expansion.md)。
