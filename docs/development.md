# SeepType 双平台开发

**一条 `main`，两个工作树。** `main` 是 Windows、Android 和共享词库的集成基线。Windows 与 Android 各在自己的工作树里选独立任务分支；不需要复制仓库，也不需要长期维护彼此分叉的两条主线。

1. 在对应平台的工作树，从本地 `main` 开任务分支（例如 `git switch -c codex/windows-candidate-view main` 或 `git switch -c codex/android-settings main`）。两个工作树不要同时检出同一个分支。
2. 在平台工作树中开发、提交及验证。在主工作目录里检查差异后合入 `main`。已有分支不会因 `main` 前进而自动更新；新任务直接从 `main` 开，更老的进行中分支再按需要同步。
3. 两边的 `.cache`、构建产物、设备配置和签名材料保持本地隔离。外部缓存如需使用，按对应工具的配置为各工作树分配，不复用写入中的构建目录。源码合并与平台发版分别处理。

| 范围 | 改动与验证入口 |
| --- | --- |
| Windows | [Windows 打包](packaging.md)、[扩展词库回归](../data/lexicon-expansion/windows-runtime/README.md) |
| Android | [Android 构建与验证](../android/README.md)、[Android 快照](../data/lexicon-expansion/android-runtime/README.md) |
| 共享 | `src/study/lua/study_core.lua`、`packaging/data/study*.schema.yaml` 及两端共用的锁定词库。更新共用运行数据时，同步更新其公版快照与模型校验，并在两平台测试。 |

旧 Windows 源码是从原分支按文件迁移到公版 `main`，不是合并原分支历史。[词库工具](lexicon-expansion.md)与当前开发模型随源码保留；原始参考素材、审校批次、生成回执和完整逐条验收日志留在原归档。依赖这些历史材料的命令是归档重放工具，不是公版构建或引擎验收的前置条件。不要把原仓库分支或历史导入公版仓库。
