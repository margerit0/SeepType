# 阶段 5：词库审核与数据导出

200 条日常词库审核稿、来源快照及审核导出流程已准备，见 [词库接续](../../docs/lexicon.md)。

从项目根目录运行：

    python tools/lexicon/verify.py
    .\experiments\phase5\build-probe.cmd
    python experiments/phase5/verify-lexicon-runtime.py

构建使用已有 VS2019 / x64 工具链及固定 Rime 头文件。探针源代码沿用阶段 3 的通用 C API 程序，单独输出到本阶段 build，不改写旧二进制。运行时建立独立 shared / user 目录，复制固定中文输入数据、正式 study_core.lua 及 200 条开发预览词表；不改动阶段 3/4 目录。

25 项数据流程检查通过。200 条草稿全部通过真实 x64 Rime/Lua 的释义和中英文提交检查，13 条使用非首候选。没有创建候选窗口、注册输入法或操作桌面。本阶段不重跑既有 UI、TSF、IPC 和编辑会话报告。

来源与审核数据位于 data/lexicon；人工作出通过决定的条目目前为 0。审核页面为 docs/lexicon-review.html，预览数据包位于 .cache/lexicon-preview。仅在完成审核后允许正式导出。
