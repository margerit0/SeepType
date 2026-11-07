# 2026-11-07 桌面接续验收

本轮通过当前 `computer-use` 技能的 `node_repl` / `@oai/sky` 正常入口完成。`list_apps`、窗口读取、实际按键与点击均成功，旧审批 404 未复现。没有修改审批配置、安装/注册输入法或重跑历史套件。

## 实际观察与版本边界

[14 项功能观察及二进制摘要](../experiments/phase4/results/desktop-v05-20261107.json) 对应阶段 4 **v0.5 实验 DLL、x64 服务、21 条测试释义**。普通中文行点击、英文显示行普通点击都提交中文；右键“输入英文”、Ctrl+Shift+Enter 提交英文，重复动作不重复写入；F2 显示独立释义而不提交；上一页/下一页、学习开关保持候选；文档切换取消旧组合，第二文档正常空格提交；设置打开/取消、独立设置保存 Alt+Enter 并在宿主生效；菜单取消后数字选词正常。

最终 A 为 `你好你好hellohello`，B 为 `你hello那`，均无剩余组合，文本存储锁违规为零。状态见 [final-state.json](../experiments/phase4/results/desktop-v05-20261107/final-state.json)。设置只写入 `experiments/phase4/runtime/interactive-settings.ini`，本轮结束时保留 `shortcut=alt_enter`；正常产品用户数据未创建。

`sky.type_text('nihao')` 未驱动该宿主的键事件；随后使用 `press_key` 的逐字母按键。内嵌设置窗口的下拉框元素索引及坐标操作遇到工具状态/焦点问题，未计作选择成功；独立设置窗口用键盘选择后保存成功。不能把这个工具操作问题判为设置控件缺陷。

## 修复的验收宿主退出误报

原宿主在 Computer Use 读取候选可访问性后关闭，窗口和进程退出，但返回 1，日志为 `Interactive DLL still referenced`。原始失败保留在 [original-host.log](../experiments/phase4/results/desktop-v05-20261107/original-host.log)，没有改写成通过。

`CandidateAccessible` 持有 DLL 生命周期引用，外部可访问性客户端的 COM 封送引用可以持续到 apartment 断开。交互宿主原先在 `CoUninitialize` 前要求 `DllCanUnloadNow == S_OK`，检查时间过早。本轮仅调整**交互验收宿主**的退出顺序：释放宿主对象、记录断开前状态、断开 COM、记录断开后状态，再要求 `S_OK` 后卸载 DLL。仍被引用时继续返回失败，未放宽检查。原程序测试分支保持原样。

单独编译宿主，在 Computer Use 中输入 `n`、读取真实候选可访问性、Alt+F4 关闭：断开前 `S_FALSE (1)`，断开后 `S_OK (0)`，退出码 0，服务与宿主进程均结束。[定向结果](../experiments/phase4/results/desktop-v05-20261107/shutdown-after-fix.json) 与新宿主摘要在总报告中。没有重复前面的 14 项操作，也没有重建实验 DLL 或产品。

复用修复后宿主的入口：

```powershell
.\experiments\phase6\build-desktop-host.cmd --legacy
python experiments/phase4/start-text-host.py --service-x64 --host .cache/packaging/desktop-host-legacy/StudyIME.DesktopHost.exe
```

旧 `experiments/phase4/build/tsf_text_host_x64.exe` 未覆盖，仍是原有历史二进制；默认旧入口仍会遇到上述退出检查问题。后续使用带 `--host` 的命令，或在确有需要时重新构建原宿主。

## dev.2 产品激活探针

新增独立宿主编译器与 `experiments/phase6/start-desktop-host.py`，用于绑定当前包的真实 CLSID、IPC 和独立 `STUDYIME_DEV_SESSION` / `STUDYIME_DEV_DATA_ROOT`。探针核对运行文件摘要，准备隔离数据并启动服务，直接加载包内 DLL；不执行注册入口。

首次尝试加载的是当前 dev.2 DLL（摘要 `35b8ca6abfbfcac8bbd9164648a2cca8dc739d08fef24bad2a4093f5e45192f5`），`Activate` 返回 **`0x80004005 / E_FAIL`**，未进入键鼠输入。记录见 [desktop-activation-dev2.json](../experiments/phase6/results/desktop-activation-dev2.json)。服务随后停止；注册项与键盘预载项前后相同，正常产品用户目录仍不存在，五个产品二进制未变。

代码中实验 DLL 跳过系统 key-sink 登记，产品 DLL 恢复该路径；这解释了不能直接将旧宿主成功外推到产品的边界。但本次没有插桩定位 `Activate` 内部哪一步失败，不能宣称已经证明具体根因，也不能据此判定安装后产品失败。保留该入口作为激活诊断，**当前不是已经可用的 dev.2 桌面验收入口**。

```powershell
.\experiments\phase6\build-desktop-host.cmd
python experiments/phase6/start-desktop-host.py
```

这两条命令仅供必要时复现激活诊断，不要求接续窗口重复执行。最新编译已包含宿主关闭顺序修复，激活失败报告保留初次编译摘要；没有把后续宿主重编译声称为重新执行过 dev.2 激活。

## 下一断点

- 悬停完整释义、动画期间连续输入、物理服务断线、跨应用失焦、实际缩放切换与多显示器仍待验证。本轮的静态前后截图不能证明动画时间或帧连续性。
- dev.2 安装/注册、卸载恢复、现有小狼毫并存及记事本/浏览器/VS Code 自动路由待单独系统操作授权。已有安装计划：`C:\Program Files\StudyIME\0.5.0-dev.2`，独立 CLSID；现有卸载计划保留用户数据与修改文件。见 [已完成的计划报告](../experiments/phase6/results/installer-plans.json)，不必重跑。
- 原 200 条英文仍为 0 人工通过、200 待审，未添加任何人工审核决定。
- 本轮改动仅为验收工具、报告与文档。dev.2 产品代码、原生构建输入、运行 ZIP 和源码材料 ZIP 未改；现有源码 ZIP 保持其原提交内容，不包含本轮新增 QA 工具。
