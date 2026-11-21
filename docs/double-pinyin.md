# 全拼、自然码双拼与小鹤双拼

2026-11-08：按用户确认的“自然码双拼＋小鹤双拼”完成开发，保留全拼为默认方案。当前是 `0.5.0-dev.3` 内部构建；本轮完成原生构建、隔离运行和设置窗口检查，没有导出新版运行／源码 ZIP 或安装新版。

## 使用

打开拾词设置，在“输入方案”选择全拼、自然码双拼或小鹤双拼后保存。安装版可从 `StudyIME.Settings.exe` 打开，也可在没有正在输入的内容时使用 `Ctrl+Shift+F12`。新会话直接使用保存的方案；已经开始的输入继续按原方案完成，下一次输入再切换。取消设置不会改变保存的方案。

| 中文 | 全拼 | 自然码双拼 | 小鹤双拼 |
| --- | --- | --- | --- |
| 你好 | `nihao` | `nihk` | `nihc` |
| 中国 | `zhongguo` | `vsgo` | `vsgo` |
| 学习 | `xuexi` | `xtxi` | `xtxi` |
| 学校 | `xuexiao` | `xtxc` | `xtxn` |
| 朋友 | `pengyou` | `pgyb` | `pgyz` |
| 现在 | `xianzai` | `xmzl` | `xmzd` |

两套双拼的单字母零声母用 `aa`、`ee`、`oo`；两字母音节可直接输入 `ai`、`an`、`ao`、`ou`、`en`、`er`；`ang` 用 `ah`，`eng` 用 `eg`。`女`／`绿`用 `nv`／`lv`，`虐`／`略`用 `nt`／`lt`。保留上游合法的替代编码，例如自然码的 `al` 和小鹤的 `ad` 都可输入“爱”。可用单引号明确分隔音节，例如 `ni'hc`。

自然码和小鹤都支持首键简拼。例如输入 `xz`，可在候选中选「现在」；也可以用 `x'z` 明确分隔。若按键已组成完整双拼音节（例如 `xs` 对应 `xiong`），优先按完整音节匹配。

三种方案使用同一个中文词库和本机学习记录。选词学习、暂停学习、分段造词及“忘记此词的学习记录”均共享；切换方案不清空已学词频。英文释义和英文快捷键沿用原有行为：空格、数字、普通点击提交中文；只有明确的英文操作提交英文。候选只覆盖部分输入时，英文提交会被拒绝并保留后面的输入。

## 实现与兼容

- `packaging/data/study.schema.yaml` 为共同基础；`study_double_pinyin.schema.yaml` 与 `study_flypy.schema.yaml` 继承相同处理器、过滤器及词库，各自使用独立拼写索引。三者的用户词典均为 `cedict_study.userdb`。
- `settings.ini` 保持 `version=1`，新增 `input_scheme=study`、`study_double_pinyin` 或 `study_flypy`。旧文件没有该字段或字段值未知时使用全拼，其他有效设置保留。
- `ProductRime.cpp` 在创建会话和新按键到达时读取设置；非空组合串不换方案。模式切换保留中英文状态、标点和英语显示开关，不读取或清空应用尚未领取的提交。
- 全拼方案声明两套双拼为部署依赖，因此旧版原厂 `default.custom.yaml` 只有全拼时仍能编译新索引。升级测试保留该用户文件、旧偏好、无关文件与已学词频。
- 方案统一通过拾词设置选择，产品预设关闭 Rime 自带方案菜单快捷键。翻页测试发现上游 IPC 丢弃成功返回值；产品补丁现在返回真实的翻页结果，首尾边界继续返回失败。

键位规则与预编辑格式来自 Rime `rime-double-pinyin` 的固定提交 `01a13287cbd27819be1c34fa1ddc1b3643d5001b`。原始方案、署名、README、GPLv3 许可证和文件摘要保存在 [来源锁定](../licensing/double-pinyin.lock.json) 中，构建导出会核对它们；派生方案标明修改。

## 验证

运行入口：

```powershell
.\tools\packaging\build.cmd
python tools/packaging/verify_double_pinyin.py --section engine
python tools/packaging/verify_double_pinyin.py --section ipc
python tools/packaging/verify_frequency.py
python tools/packaging/verify_renderer.py
```

- [引擎结果](../experiments/phase6/results/double-pinyin-engine.json)：79 项检查及三种方案各 200 条、共 600 条词义回归通过；每条验证英文注释、完整英文提交和普通中文提交。覆盖零声母、ü、合法别码、音节分隔、退格、分段造词和跨方案遗忘。服务翻页返回值修复后，[摘要核对](../experiments/phase6/results/double-pinyin-engine-binding.json)确认引擎、探针与全部运行时数据字节相同，沿用已完成的引擎检查。
- [产品会话结果](../experiments/phase6/results/double-pinyin-ipc.json)：69 项检查通过，覆盖已有／新建／并发会话、中途改设置、待取提交、翻页及边界、分段输入、重复／过期动作、学习开关、跨方案词频、服务重启与真实 dev.2 用户目录升级。
- [词频回归](../experiments/phase6/results/word-frequency.json)：60 项通过。[候选窗回归](../experiments/phase6/results/product-renderer.json)：18 项组件检查及 9 组像素比对通过，180ms 翻页和 240ms 学习开关动画保持。
- [设置窗口观察](../experiments/phase6/results/double-pinyin-settings.json)：10 项通过；在独立用户目录中实际选择两套双拼、保存并重开，验证取消及其他设置保持；[界面截图](../experiments/phase6/results/double-pinyin-settings/flypy-selected.png)来自真实原生窗口。

[最终构建核对](../experiments/phase6/results/double-pinyin-final-build.json)确认提交前格式整理后的四个产品文件、四个验证程序和全部引擎／方案／词库／Lua 数据与测试版本相同。

这些检查使用隔离数据和服务，除设置窗口外均为程序输入；不等同于安装后的外部应用 TSF 验收。原 dev.2 待重启清理、多显示器及英文人工审核事项仍按 [交接记录](handoff.md) 跟进。
