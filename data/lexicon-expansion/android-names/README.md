# Android 离线影视／游戏专名

这是随 Android APK 固定发布的精选名称，不是热榜、订阅或下载包。全拼、自然码、小鹤加载同一张附加词典。Windows 词库快照只是基底，文件和摘要均不改动。

- **2026-11-21，420 条：** 在首版 381 条之后追加 39 个作品名（20 部剧集、16 款游戏、3 部电影）。共 206 部电影、20 部剧集、17 款游戏、177 个角色；首版条目原样保留，排头 12 条仍是先行样本。
- **怎么挑补录：** 先用 381 条 APK 实测 113 个备选作品名，优先补三种方案均未在前 8 页找到的名称。像《漫长的季节》《隐秘的角落》原来就能合成完整首选，不再重复收。补录的实际名次和设备范围见[验证记录](../../../docs/android-offline-names-supplement-validation.md)。
- **中文来源：** [Wikidata 结构化数据（CC0）](https://www.wikidata.org/wiki/Wikidata:Copyright)。`names.tsv` 的 `qid`、`revision`、`label_lang` 固定逐条所选标签，`work_qid` 区分影视作品和同名角色。例如钟离选择 `Q107287615`，不是同姓条目。按 [sources.json](sources.json) 的 URL 模板读取固定修订，不依赖当前标签。优先选 `zh-cn`，遇到缺项再选核对过的 `zh-hans`／`zh`。`alias:zh` 等形式表示同一修订的 `aliases` 中有完全匹配的中文名，而不是自动转写；例如《琅琊榜》和《空洞骑士》。`series` 与 `film`／`game` 一样是作品，`qid` 与 `work_qid` 相同。仍不收入无依据别名、夹杂拉丁字母或标点的标题、同名不明实体、或发音未确定的词。
- **读音与英文：** `pinyin` 是开发侧校对过的无调拼音，每字一个音节，`ü` 用 `v`（如「铃芽之旅」的 `lv`）；`dev-checked` 不代表人工发布审批。不要把 Wikidata 的英文标签当官方译名。当前只给「芙宁娜」附了另有 [HoYoverse 官方依据](https://genshin.hoyoverse.com/en/news/detail/113484) 的 `Furina`；其他专名不新增英文释义。英文匹配实际读音，不能覆盖快照已有词义。
- **排序：** 仅同词形且同读音才算重复。与 Windows 基底重复的词跳过；策展表内重复报错。同音不同词保留，并输出 `notices/android-names/collisions.json`。专名条目权重固定为 `1`，不从热度取权；对典型冲突用实际引擎回归校验，而不从权重推断 UI 排名。

## 更新与重建

1. 先明确选题和待补名称，再用 Wikidata 核对实体、简体标签或可核对的同实体别名、修订号和归属；核对各字在该专名里的读法。必要时另记独立的官方英文依据。不复制第三方词表或说明文字。
2. 保持 TSV 表头、UTF-8、分音节读音和行末制表符（英文空白时），更新来源日期/说明。APK 清单和构建收据包含 `offlineNames.tsvSha256`、条数等；三种方案的 Android 专用补丁只把翻译器数据表换为聚合词典，用户词典 ID 仍是 `cedict_study`。
3. 正常构建会检测名称文件变化，重新生成并按资源摘要部署。不加入网络权限，构建不访问 Wikidata。用 `python -X utf8 -m unittest tools.android.test_offline_names` 跑输入校验，设备命令与证据见 [Android 验证记录](../../../docs/android-offline-names-validation.md)。
