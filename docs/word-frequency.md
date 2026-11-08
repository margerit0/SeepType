# 中文选词学习

2026-11-08，词频功能已在工作区完成。内部测试构建标记为 `0.5.0-dev.3`；按用户最新要求，暂不生成新版运行或源码压缩包，后续小鹤双拼完成后再统一打包 dev.3。启用 Rime 原生用户词典，补充独立设置与单词记录清理。下一项及高级排序见 [优化待办](optimization-todo.md)。

## 使用行为

- 默认启用“记住中文选词习惯”。空格、数字键和普通点击提交中文后，Rime 更新词频；分段选出的词组也可进入用户词典。
- 设置中的“英语学习：显示英文释义”只控制英语功能。关闭英语显示不会关闭中文选词学习。
- 关闭“记住中文选词习惯”后停止记录新选择，已有记录继续参与排序。保存设置后，服务在下一次选词或提交前读取该设置；不要求重启服务，也不清除当前组合。
- 右键候选 → “忘记此词的学习记录”。操作对应当前候选的读音：内置词恢复基础排序，已学的自造词可被移除。再次选用可以重新学习。不会提交文字或修改已经输入到应用中的正文。
- 英文提交只提交词表中的英文值，不把对应中文候选计为一次中文选择。Esc 取消和仅浏览候选不应学习。
- 本轮提供逐词清理；批量清理、置顶和降权列入后续优化。

## 保存与升级

用户数据目录为 `%LocalAppData%\StudyIME`：

- `settings.ini` 增加 `user_learning=1/0`，保持 `version=1` 的兼容读取。旧文件缺少该键时默认启用，原英语、字号、主题等设置保留。
- `rime\cedict_study.userdb` 保存 Rime 的中文词形、读音、使用统计与造词记录。这些内容可能包含用户输入的词组，仅保存在本机，不上传。
- 产品包的共享方案启用 `translator/enable_user_dict`。方案重新部署会更新编译数据；用户词典和已有设置不会由模板覆盖。
- 每次启动检查方案内容，复用未变化的词典。旧的仅按文件修改时间判断方式会漏掉固定 ZIP 时间戳的版本升级，本轮已修正。
- 安装器仍要求先卸载旧预览，再安装新版本；卸载保留用户数据。用户数据兼容性验证与系统安装升级是两种不同的检查。

## 实现边界

排序公式、用户词典格式、自动造词和候选删除继续使用原生 Rime。自建 Rime 中仅在 `Memory::OnCommit` 增加三行属性检查：当前会话的 `study_user_learning=0` 时跳过新增学习。该属性由产品服务在键盘、普通点击、显式组合提交前更新，不触发候选重排，也不与英语 `learning_mode` 混用。

“忘记此词”经过现有 `study.v1` IPC，携带服务、会话、版本和候选索引。服务重新核对当时查看的候选，再调用 `delete_candidate_on_current_page`；重复请求、失焦和候选变化会让旧请求失效。此操作不领取应用待取的提交文本。

设置页修正了旧的“不保存输入内容”说明。词频与造词会保存中文记录；英语释义模块仍只查询本地审核词表。

## 验证入口

```powershell
tools\packaging\build.cmd
python tools\packaging\verify_frequency.py
python tools\packaging\verify_engine.py
python tools\packaging\verify_renderer.py
```

`verify_frequency.py` 使用每次新建的隔离目录，验证真实 Rime 和产品服务 IPC、暂停/恢复、遗忘、分段输入、翻页、英文动作、重启，以及 dev.2 用户数据的迁移。

本轮验证结果：

- [60 项词频与升级检查](../experiments/phase6/results/word-frequency.json)全部通过，包括输入途中关闭学习、多会话共享记录、重复/过期遗忘请求和保留待取提交。
- [200 条原有英文释义及中英文提交](../experiments/phase6/results/source-built-engine.json)全部通过。
- [17 项原生组件检查及 9 组像素比对](../experiments/phase6/results/product-renderer.json)通过，既有候选条布局保持一致；外部修改词频设置后，英语工具开关不会覆盖它。
- [7 项真实设置窗口观察](../experiments/phase6/results/word-frequency-settings.json)通过：独立开关、保存、重开持久化、取消及文字布局。

以上使用隔离用户目录；没有安装新版本或进行新版已注册 TSF 的外部应用验收。原 dev.2 的卸载最后清理仍等待重启，参见 [已安装版本记录](installed-desktop-acceptance.md)。

迁移检查默认使用 `.cache/packaging/stage/StudyIME-0.5.0-dev.2` 中保留的旧包；新源码目录可通过 `--legacy-package <旧包展开目录>` 指定。旧词频先由真实 dev.2 引擎生成，再恢复其默认的“关闭用户词典”编译方案，最后由新服务部署并读取旧记录。
