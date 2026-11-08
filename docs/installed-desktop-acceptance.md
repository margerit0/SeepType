# 2026-11-08 实际安装与桌面验收

用户明确授权安装、注册、应用测试后卸载恢复，保持现有默认输入法。最新指令为“那就先跳过浏览器测试，进行别的任务”。**dev.2 已注销，输入法配置和注册树已恢复；最后的 DLL 与卸载支持文件需要重启 Windows 后继续清理。浏览器验收本轮跳过。**

初次安装记录保留在 [installed-desktop-20261108](../experiments/phase6/results/installed-desktop-20261108/summary.json)，后续真实桌面观察和卸载证据集中在 [installed-desktop-followup-20261108](../experiments/phase6/results/installed-desktop-followup-20261108/summary.json)。旧快照不改写为本轮成功结果。

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

## 后续桌面验收

后续会话使用 `b000d33a22ad4cacaa60f42122ec789c` 的独立测试目录，输入和鼠标观察通过 Computer Use 的正常原生入口完成。安装目录的程序和词库摘要绑定在 `apps-session.json`，每项观察与实际截图路径见 `observations.jsonl`。

| 范围 | 实际观察 |
| --- | --- |
| VS Code | 悬停和 F2 显示独立完整释义；普通点击英文显示行提交中文；明确英文快捷键提交 `hello`，重复动作不追加。初始保存文本为 `你好hello`。 |
| 跨应用焦点 | VS Code 与记事本切换后旧组合被清除，在另一应用触发英文快捷键没有提交旧候选；新的输入可正常提交。 |
| 服务断线 | 在 VS Code 保持前台时停止隔离服务，组合、候选和释义自动清除，已提交文本保留；旧快捷键不误提交，重新输入自动恢复服务并提交中文。 |
| 实际缩放 | Windows 从 150% 临时切到 125%，候选、释义与点击通过；已恢复原来的 150%、2560 × 1600。 |
| 单屏边缘 | 右侧候选栏向左避让；组合滚到屏幕底部时候选与释义向上避让。移动后的候选点击准确提交中文。 |
| 连续输入 | 连续原生按键及翻页后紧接输入均保留正确组合和候选；翻页与下一按键开始间隔约 122.6 ms。该观察不构成逐帧动画时序证明。 |
| Chrome | 浏览器扩展能读取本地 HTTP 测试页；原生窗口读取仍被网址识别保护中止，包括用户手动将正确页面置于前台之后。没有浏览器原生输入通过结论，按用户指令跳过。 |
| 多显示器 | 设备仅连接一台显示器，跨屏移动尚未验证。 |

最终记事本测试文件为 `你好`。VS Code 第一行为 `你好hello你好你好`，最后一行保留边缘点击产生的 `你好`，中间空行和缩进用于屏幕定位。原初始保存证据和最终保存副本分别保留，不把测试定位空白算成输入错误。

## 已注册产品的卸载与恢复

本地时间 18:12 首次执行已授权卸载。原生注销成功，服务停止；脚本因正在映射的 `bin/StudyIME.TSF.x64.dll` 进入 `cleanup-pending / registered=false`，保留 DLL、收据和支持文件，未强制结束其他应用。这验证了真实占用处理，不沿用先前注册前的复制失败清理作为替代。

对比快照发现 Windows TSF 的注销 API 在 32/64 位视图留下本产品 GUID 下的空 `Category`、`LanguageProfile` 容器。新增卸载函数先验证收据归属与已注销状态，确认 COM 类已不存在，然后仅清理结构已知且没有任何值的自有空键。含值、未知分支、有效 profile 或仍存在 COM 类时拒绝清理；逐键删除前再次检查，未使用递归删除生产 TIP 树。

修复在 Windows PowerShell 5.1 下通过 8 项隔离 HKCU 夹具检查，包括邻接产品保留、有效 profile/未知分支保留、写入失败及重试。18:23 使用同一生产函数清理本机残留，之后 **32/64 位完整 TIP 树、拾词 CLSID/用户 TIP、键盘配置及小狼毫相关记录与安装前一致**。正常用户数据文件和摘要也完全一致。

再次运行原安装目录的卸载脚本仍正确保留占用中的 DLL。当前映射它的进程为 ApplicationFrameHost、Codex（进程名 ChatGPT）、Chrome、资源管理器和记事本。已关闭独立 VS Code 测试窗口、记事本项目测试标签，并停止两个隔离会话及正常拾词服务；记事本其他文档保留。本地 HTTP 测试服务也已停止。

**未完成的最后一步：保存工作并重启 Windows，再执行清理重试。** 此前保留的应用列表项负责提供卸载重试入口，不代表 profile 仍注册。安装目录目前仅余一个 DLL 和六个卸载支持/记录文件。不要强制结束当前 Codex 或用户文档进程来释放 DLL。

重启后，使用已授权的 64 位管理员 PowerShell 执行：

```powershell
& '.\experiments\phase6\run-approved-install-step.ps1' `
  -Action uninstall `
  -ResultDirectory '.\experiments\phase6\results\installed-desktop-followup-20261108\uninstall-after-restart'
```

随后重新运行 `capture-installed-state.py` 保存最终快照，要求安装目录、应用列表项和所有拾词注册均不存在，原输入设置及其他 TIP 树仍与安装前相同，再更新最新汇总。未完成这一步前不报告“完整卸载通过”。

## 包与审核状态

本机实际安装和桌面观察对应的收据修订运行 ZIP 为 `c1c429adee39465f0740bf7ac6111dad799d097a83e39019a5975d02acf3648e`（23,800,624 字节），清单为 `be847600406f9ad3ba53657a20ca33b60f4cb632e47da15e69fd34c405ab4605`。与最初包相比只改变 `scripts/Common.ps1` 和 `package-manifest.json`。其源码更新已经完成，独立源码目录重导出的运行 ZIP 逐字节一致，见 [收据源码同步](../experiments/phase6/results/source-receipt-update-20261108/summary.json)。

本次空 TIP 清理又更新了 `Uninstall.ps1`、`scripts/Common.ps1` 和清单；新的源码/运行归档及定向检查见 [卸载修订源码同步](../experiments/phase6/results/source-uninstall-update-20261108/summary.json)。原生程序、Rime 及词库与已观察版本相同，按文件摘要复用桌面证据；新脚本包未重新完整安装，不宣称进行了新的空缓存原生构建。两次修订之前的归档均已另存。

原有 200 条英文仍为 0 人工通过、200 待审；其他聊天的词库扩充草稿未进入运行包或本次源码归档，开发预览和人工审核边界保持不变。
