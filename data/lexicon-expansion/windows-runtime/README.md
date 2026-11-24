# Windows 扩展词库 · 开发快照

`runtime-model.json` 保存 Windows 开发快照的运行义项及默认值选择。`snapshot.json` 锁定模型和[共享运行快照清单](../android-runtime/snapshot.json)。Windows 和 Android 读取同一份 `lexicon.lua` 和 `cedict_study.dict.yaml`。

- 共享清单记录源提交、词库数量和原快照通过的全拼、自然码双拼与小鹤双拼引擎检查数。此处的验证入口使用公版随附的默认义抽样用例，在当前方案上检查标注及中英文提交。
- 扩词批次通过源仓库的引擎验证后，按[共享快照的同步步骤](../android-runtime/README.md)更新公版模型和词库。
- 这是开发快照，不等同于人工批准的词库、Windows 安装包或发行记录。正式打包的审核门槛不变。词库与模型沿用[来源、署名及许可声明](../android-runtime/NOTICE.txt)；原逐条审校、来源证据和 API 回执在原始开发归档中，不随公版仓库分发。

从仓库根目录运行，不引用旧 Git 历史：

```powershell
# 验证锁文件、共享词库和 Lua 的确定性重建；无需联网或 Windows 工具链。
python -B -X utf8 -m tools.lexicon_expand.windows_snapshot

# 按 Windows 打包说明准备锁定依赖及 x64 Rime/探针后，跑隔离引擎回归。
python -B -X utf8 -m tools.lexicon_expand.windows_snapshot --engine
```

引擎回归在本工作树的 `.cache/lexicon-expansion/windows-snapshot/` 新建独立用户目录和报告，不安装输入法。也可以用 `--probe`、`--rime` 显式指定已构建的本地探针和 DLL。Windows 构建工具链见[打包说明](../../../docs/packaging.md#可重复构建与打包)。
