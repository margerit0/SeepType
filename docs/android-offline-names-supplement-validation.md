# Android 离线专名补录：381 → 420 条

2026-11-21，`codex/android-offline-names`。在[首版 381 条](android-offline-names-validation.md)后追加 39 条：20 部剧集、16 款游戏、3 部电影。保留原始 TSV 前缀、Windows 词库快照及三种方案的 `cedict_study` 用户词典 ID。没有添加拉丁字母、数字或标点版标题的归一化，也没有在线候选、热榜或下载器。

用相同的测试 APK、同一个关闭网络的 WSL2／KVM Android 11（API 30、x86_64）模拟器，分别安装 381 条和 420 条 Debug APK。两轮均使用独立词典、关闭学习，以全键序测了相同的 113 个备选作品名（339 次探针），至多检查 8 页 Rime 候选。选中的 39 条在旧包三种方案均未找到，并逐条固定 Wikidata 实体、中文标签或别名和修订。像「漫长的季节」「隐秘的角落」三种方案原本就能合成完整首选，未重复打包。

| 词条 | 全拼 / 自然码 / 小鹤 | 381 条：旧首选（目标未在搜索范围内） | 420 条：目标名次与首选 |
| --- | --- | --- | --- |
| 琅琊榜 | `langyabang` / `lhyabh` / `lhyabh` | 琅琊帮 | 琅琊榜，第 1 |
| 庆余年 | `qingyunian` / `qyyunm` / `qkyunm` | 情欲年 | 庆余年，第 1 |
| 空洞骑士 | `kongdongqishi` / `ksdsqiui` / `ksdsqiui` | 空洞其实 | 空洞骑士，第 1 |
| 双人成行 | `shuangrenchengxing` / `udrfigxy` / `ulrfigxk` | 双人成型 | 双人成行，第 1 |
| 艾尔登法环 | `aierdengfahuan` / `aierdgfahr` / `aierdgfahr` | 爱二等罚锾 | 艾尔登法环，第 1 |
| 鸣潮 | `mingchao` / `myik` / `mkic` | 明朝 | 明朝、冥钞、**鸣潮**（第 3） |
| 浪浪山小妖怪 | `langlangshanxiaoyaoguai` / `lhlhujxcykgy` / `lhlhujxnycgk` | 郎朗讪笑妖怪 | 浪浪山小妖怪，第 1 |

表内结果在三种方案一致。**38 条在三种方案都是引擎第 1；「鸣潮」在三种方案都是第 3，「明朝」仍是第 1。** 这些是引擎名次，不等同于折叠候选条可见性。[39 条的全部 117 项对照及两条未添加对照词](android-offline-names-supplement-comparison.json)含实际键序、前三候选和提交内容。

## 验证范围

- **模拟器引擎：** 全部 420 条 × 3 个方案（1,260 次）均找到完整候选且提交成功。与同设备保存的首版覆盖报告相比，旧 381 条的目标候选名次在 1,143 项中都没有变化。通用引擎回归另外通过 702 个词例和 44 项检查。
- **模拟器折叠 UI（Debug）：** 1080×2340／440 dpi，默认浅色皮肤、竖屏、1× 字号，合成编辑器。对「琅琊榜」「艾尔登法环」「浪浪山小妖怪」「鸣潮」和原有的「芙宁娜」「钟离」「那维莱特」各跑三种方案，21 次都在不滚动、不展开的候选条上直接点选并提交。「芙宁娜」仍是首选；「钟离」第 4 且「中立」仍是首选；「鸣潮」第 3 且「明朝」仍是首选。芙宁娜的 `Furina` 英文提交也通过。首次 UI 运行未打开输入法，以上结论来自唤醒模拟器并在测试编辑器预先打开输入法后的复测，不是冷启动验收。
- **签名 Release APK：** 已生成；签名与 381 条开发 Release APK 相同，双 ABI／原生依赖和 ZIP 对齐检查通过。182 个版本化文件逐一校验摘要，生成资源与实测 Debug APK 内容相同，未声明 `android.permission.INTERNET`。未在此次 Release APK 重跑点选矩阵。
- **暂未验证：** 实体手机、arm64 设备、其他屏宽或皮肤，以及实际有学习历史的用户跨版本升级。没有声称所有 420 条都能在折叠首屏点到。

| 项目 | 值 |
| --- | --- |
| 381 条资源版本 | `7feb4ef9bf4241e80d54` |
| 420 条资源版本 | `fd2dd9ded3195aa5a597` |
| 420 条 TSV SHA-256 | `5f5e85be849d6211c7259445d0738b415cb3af0043619be604bf292d644848be` |
| 开发签名 Release APK SHA-256 | `878592e4cb8986374622a42c24c85980777c074730b04d60edd39689f446b530` |

在隔离测试设备上用 `tools/android/build.py` 构建，安装后运行 `tools/android/run_device_checks.py offline-names-work-titles --serial <序列号>` 可复测同一份备选清单；比较旧包时使用保留的 381 条 APK 和与其签名匹配的测试 APK，不传 `--names-baseline`（该开关用于没有任何专名的旧基线）。正式补录另外复测 `offline-names-engine`、`offline-names-coverage`、`offline-names-ui` 和 `native`。本机原始前后 JSON、UI 截图及安装/验证摘要在 `.cache/android/evidence/offline-names/work-title-update/`。
