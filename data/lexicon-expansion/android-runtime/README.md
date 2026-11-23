# Android 离线词库快照

来源：Windows 分支 `codex/technical-spike`，提交 `1977d315e0b2de82bcd3bb33950a576f133048ec`（2026-11-17）。`snapshot.json` 记录完整 Git 提交、源目录和核验摘要。Windows 报告中的 39,786 项检查属于 Windows 的 x64 Rime 验证，不是 Android 实测结果。完整审校历史、逐词采用与来源记录保留在该提交的 `windowsSnapshot` 目录。

- `lexicon.lua`、`cedict_study.dict.yaml` 以及共享的 `src/study/lua/study_core.lua` 是上游验证过的原字节文件。以该快照的完整运行词表替换 Android 旧预览，不将 200 条草稿或历次扩充重复叠加。
- 13,137 是英文开发记录数，不是不同中文词形数；10,495 是有英文默认释义的中文／读音入口数。中文 Rime 词典包含 124,066 条词形／读音记录（基础 121,505 条，补充 2,561 条）。
- `engine-cases.json` 从 Windows 实际通过的默认义项用例抽取：保留的旧预览词、新扩充词、新补读音，以及「系」「还」不同读音的释义。用于 Android 上独立验证候选标注及中英文提交。
- `word-details.jsonl` 从同一提交已校验的运行模型、读音入口和英文开发记录抽取。每条以「词形 + Rime 读音」定位，默认义项排第一，保留 `sense_id`、词性和中文用法；只有能确定声调的读音才附带带调拼音。该文件不参与候选注释或英文提交。
- `word-detail-examples.json` 是拾词编写的首批原创搭配与中英例句（以 GPL-3.0-or-later 提供）。按义项 ID 绑定，打包同时核对词形、读音和英文。新增示例只需编辑此文件，无需从 Windows 重新导入；没有示例的义项照常显示已有释义。
- 快照用于离线预览。`humanApproved` 和 `releaseReady` 保留原开发快照的记录，不用作 Android 公开预览门槛，也不改写为人工通过。预览采用 AI 语义审校和自动回归；来源及署名见 [NOTICE.txt](NOTICE.txt)，发布规则见[获取与发布](../../../docs/releases.md#android)。

下面的旧同步命令仅在能访问原 Windows 归档的开发仓库中使用。公版 `main` 不带该旧引用，也不需要获取或合并原历史；[Windows 开发词库](../windows-runtime/README.md)直接复用本目录的已验证运行文件：

```powershell
python -X utf8 tools/android/import_windows_lexicon.py 1977d31
python -X utf8 tools/android/build.py apk
python -X utf8 tools/android/build.py tests
```

后续更新时传入新的已完成引擎验证的 Windows 提交，检查词表／用例差异并重新运行 Android `native` 回归。普通 Android 构建只读取本目录的锁定快照和仓库共享源码，不依赖 Windows Git 引用。

构建时将详情与例句合并为 `word-details-v1/` APK 分片；Rime 启动不部署这些分片，打开详情才在引擎线程读取对应分片。Windows 的共享 Lua 协议和运行词表仍按原摘要校验。
