# Android 离线词库快照

词库来自 Windows 分支 `codex/technical-spike`。[`snapshot.json`](snapshot.json) 记录当前的源提交、核验摘要、词库数量和 x64 Rime 检查数。完整审校历史、逐词采用与来源记录保留在源提交的 `windowsSnapshot` 目录中。

- `lexicon.lua`、`cedict_study.dict.yaml` 以及共享的 `src/study/lua/study_core.lua` 是上游验证过的原字节文件。以该快照的完整运行词表替换 Android 旧预览，不将 200 条草稿或历次扩充重复叠加。
- 快照分别记录英文开发义项数、有英文默认释义的中文／读音入口数、中文 Rime 词典行数和补充读音数。
- `engine-cases.json` 从 Windows 实际通过的默认义项用例抽取：保留的旧预览词、新扩充词、新补读音，以及「系」「还」不同读音的释义。用于 Android 上独立验证候选标注及中英文提交。
- `word-details.jsonl` 从同一提交已校验的运行模型、读音入口和英文开发记录抽取。每条以「词形 + Rime 读音」定位，默认义项排第一，保留 `sense_id`、词性和中文用法；只有能确定声调的读音才附带带调拼音。该文件不参与候选注释或英文提交。
- `word-detail-examples.json` 包含拾词编写的原创搭配与中英例句（以 GPL-3.0-or-later 提供）。例句按义项 ID 绑定，导入和打包均核对词形、读音和英文。也可以直接在此文件新增例句。
- 快照用于离线预览。`humanApproved` 和 `releaseReady` 保留原开发快照的记录，不用作 Android 公开预览门槛，也不改写为人工通过。预览采用 AI 语义审校和自动回归；来源及署名见 [NOTICE.txt](NOTICE.txt)，发布规则见[获取与发布](../../../docs/releases.md#android)。

每批从公版 `main` 开同步分支，在公版目录运行下面的命令。把 `--source-repo` 指向原开发仓库或它的工作树，把最后一个参数换成本批已完成引擎验证的提交。导入器读取源提交并同步 [Windows 模型及摘要](../windows-runtime/README.md)、共用运行文件、Android 详情和本批例句。

```powershell
python -B -X utf8 tools/android/import_windows_lexicon.py --source-repo D:\inputting 1092118
python -B -X utf8 -m tools.lexicon_expand.windows_snapshot
python -B -X utf8 -m unittest tools.lexicon_expand.test_windows_snapshot tools.android.test_word_details
git diff --check
```

检查词库、例句和用例差异。准备好 Android 构建环境后，按 [Android 验证入口](../../../android/README.md)运行 `native` 回归。常规构建直接读取公版锁定的快照和共享源码。

构建时将详情与例句合并为 `word-details-v1/` APK 分片；Rime 启动不部署这些分片，打开详情才在引擎线程读取对应分片。Windows 的共享 Lua 协议和运行词表仍按原摘要校验。
