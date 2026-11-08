# 2026-11-08 实际安装与桌面验收

用户明确授权安装、注册、记事本/浏览器/VS Code 测试后卸载恢复，保持现有默认输入法。当前修订的 dev.2 **已经安装，尚未完成最终卸载**。所有阶段记录集中在 [installed-desktop-20261108](../experiments/phase6/results/installed-desktop-20261108/summary.json)。本文件在后续提交整理时补记已有观察，没有重跑桌面操作。

## 安装发现与修复

原运行包首次 `-Apply -AllowDevelopment` 在复制完成后更新收据失败，错误为 `File.Replace` 的路径形式不合法。Windows PowerShell 5.1 将该重载的 `$null` 转成空 `System.String`，并非传入真正的空备份路径。改用 `[NullString]::Value` 保留 .NET null。

原错误在缓存目录中复现：首次创建收据通过，第二次替换失败。修复后 4 项真实文件操作检查通过：中文及空格路径下首次创建、已有收据原子替换、目标被占用时保留上次有效记录、解除占用后的重试。原始失败与修复结果分别保存在 `receipt-original.json`、`receipt-fixed.json`，12 项修订包安装预演也已通过。

首次失败发生在用户数据准备与注册之前。调用原安装目录的卸载脚本清理登记文件后，将唯一剩余、归属已验证的临时收据移入 `original-cleanup/recovered-receipt-pending.json`，只删除空安装目录。`before-install.json`、`after-install.json`、`after-original-cleanup.json` 的注册快照相同，原用户输入配置未变。

Git 中保留拾词相关注册项、输入设置及机器级完整 TIP 树的摘要。机器级其他输入法的完整树已省略，原始快照保存在 `.cache/packaging/installed-evidence/raw-registry-20261108/`；每份投影记录都关联原始文件 SHA256，未改写原始结果。

修订包随后于本地时间 2026-11-08 15:20 安装成功，收据为 `installed / registered=true / failed=false`。安装目录为 `C:\Program Files\StudyIME\0.5.0-dev.2`，独立 CLSID/profile 和应用列表项已注册；安装前后的默认覆盖设置及用户输入法列表一致。安装准备创建了拾词自己的正常用户数据，桌面测试另用隔离数据。

## 已完成的记事本观察

通过当前 Computer Use 技能的 `node_repl` / `@oai/sky` 正常入口操作。该记事本为真实 Windows 应用，进程模块读取确认加载安装目录的 `StudyIME.TSF.x64.dll`，不是隔离宿主。

1. Ctrl+Shift 选择拾词后，逐键 `nihao` 出现 dev.2 双行候选，第一项为“你好 / hello”。安装服务在应用使用时启动，观察到本轮独立会话管道。
2. 空格提交“你好”，候选收起。
3. 再输入 `nih`，F2 显示独立完整释义“hello”，未提交，组合保留。
4. Ctrl+Shift+Enter 明确提交英文，文档变为 `你好hello`。
5. 再次按同一快捷键没有重复上屏或追加字符；Ctrl+S 保存后从本项目测试文件读回相同文本，证据副本为 `notepad-saved.txt`。

二进制、词库及启动参数绑定见 `apps-session.json`。独立会话为 `66bcec7716f24f8297a5a1a818699b33`，数据位于 `.cache/packaging/installed-apps/<session>/user`；原生文件摘要与 2026-11-07 的 dev.2 完全相同。这些结果不改变原未注册宿主的 `E_FAIL` 报告，也没有证明其内部失败点。

## 中断与未完成事项

下一步在记事本输入 `n` 准备检查跨应用失焦，并启动独立 Chrome 用户目录下的本地测试页。窗口列表成功返回目标窗口，但选择/激活/读取窗口时工具报告无法可靠识别当前浏览器 URL，要求结束当轮。已立即停止，原文见 [Computer Use 记录](computer-use-issue.md)。

没有获得 Chrome 输入结果或记事本失焦后状态，VS Code 尚未启动。没有进行悬停、动画中输入、服务断线、实际缩放/多显示器检查，也没有执行**已注册产品**的卸载恢复。先前的复制失败清理不能替代注册后卸载测试。中断后的测试窗口及服务仍需在恢复工作时读取当前状态并处理；记事本恢复了用户已有标签，只操作本项目测试文件。

## 包与审核状态

修订运行 ZIP 为 `c1c429adee39465f0740bf7ac6111dad799d097a83e39019a5975d02acf3648e`（23,800,624 字节），清单为 `be847600406f9ad3ba53657a20ca33b60f4cb632e47da15e69fd34c405ab4605`。与原包逐成员比较只改变 `scripts/Common.ps1` 和 `package-manifest.json`；四个产品文件、Rime DLL、词库数据均未变，没有重建原生程序。

修复前完整运行 ZIP、源码 ZIP、摘要和包报告已保存在 `.cache/packaging/dist/before-receipt-fix-20261108/`。源码 ZIP 及旧源码证据绑定尚未为安装脚本修复更新；不能称当前运行包已经做过完整源码复建。原有 200 条英文仍是 0 人工通过、200 待审，没有新词或自动审核决定。
