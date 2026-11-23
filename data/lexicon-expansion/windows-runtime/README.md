# Windows 扩展词库 · 开发快照

此目录保留 Windows 在 2026-11-17 冻结的可运行模型，原始提交为 `1977d315e0b2de82bcd3bb33950a576f133048ec`。`runtime-model.json` 保留全部运行义项及默认值选择；`snapshot.json` 锁定模型和[共享运行快照清单](../android-runtime/snapshot.json)。Windows 和 Android 读取同一份 `lexicon.lua` 和 `cedict_study.dict.yaml`，不复制两套词库。Android 的详情分片及专名资产仍由 Android 自己生成。

- 英文审校开发记录 13,137 条，对应 10,495 个带英文默认值的「中文词形 / 读音」入口；中文 Rime 词典有 124,066 条，其中补读音 2,561 条。记录数不等同于不同词形或不同词义的数量。
- Windows 原快照通过了 39,786 项全拼、自然码双拼和小鹤双拼引擎检查。本目录的验证入口复用其中随公版保存的 702 个默认义用例，并用当前 `main` 的方案验证标注及中英文提交；不是重放全部历史测试。
- 这是开发快照，不等同于人工批准的词库、Windows 安装包或发行记录。正式打包的审核门槛不变。词库与模型沿用[来源、署名及许可声明](../android-runtime/NOTICE.txt)；原逐条审校、来源证据和 API 回执在原始开发归档中，不随公版仓库分发。

从仓库根目录运行，不引用旧 Git 历史：

```powershell
# 验证锁文件、共享词库和 Lua 的确定性重建；无需联网或 Windows 工具链。
python -B -X utf8 -m tools.lexicon_expand.windows_snapshot

# 按 Windows 打包说明准备锁定依赖及 x64 Rime/探针后，跑隔离引擎回归。
python -B -X utf8 -m tools.lexicon_expand.windows_snapshot --engine
```

引擎回归在本工作树的 `.cache/lexicon-expansion/windows-snapshot/` 新建独立用户目录和报告，不安装输入法。也可以用 `--probe`、`--rime` 显式指定已构建的本地探针和 DLL。Windows 构建工具链见[打包说明](../../../docs/packaging.md#可重复构建与打包)。
