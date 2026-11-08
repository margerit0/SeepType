# 拾词输入法产品打包与安装产物

## 2026-11-08 词频工作区状态：暂不生成 dev.3

中文词频、独立开关、逐词遗忘与升级检查已实现并通过定向验证，见 [词频记录](word-frequency.md)。当前 `packaging/product.json` 的 dev.3 编号只用于内部测试构建；用户要求后续加入小鹤双拼，再统一生成 dev.3。本轮没有导出新版运行或源码 ZIP，也没有安装新版本。`dist` 内既有 dev.2 归档保持原状，下面的 dev.2 打包和卸载记录继续有效。

下一项与更高级排序见 [优化待办](optimization-todo.md)。新版构建会包含 Rime 本地学习的暂停判定，以及服务启动时完整的方案内容检查，避免固定归档时间戳导致旧方案未更新。

## 2026-11-08 卸载修订与当前包边界

实际安装、记事本与 VS Code 输入、跨应用焦点、断线恢复、125%/150% 缩放及单屏右下角检查已完成。用户明确要求跳过浏览器测试；多显示器尚无设备验证。详见 [实际安装记录](installed-desktop-acceptance.md)。

已完成本机 profile/CLSID 注销，默认输入法、用户输入法列表及 32/64 位 TIP 注册树恢复至安装前。卸载的占用分支和再次执行均已观察：当前 Codex、资源管理器等仍映射 `StudyIME.TSF.x64.dll`，因此保留该 DLL、卸载支持文件、收据及应用列表项，收据为 `cleanup-pending / registered=false`。**重启 Windows 后还需执行最后清理，不能称全部卸载完成。** 正常用户数据逐文件未变。

本次发现 TSF 的注销 API 会遗留本产品的空目录。卸载脚本现只清理已注销、收据归属匹配、结构已知且完全无值的自有 TIP 目录；含值、仍存在 profile、未知子项或其他 COM 注册时均保留。8 项 Windows PowerShell 5.1 注册表夹具检查通过，同一修复函数已用于本机实际残留清理；没有修改其他输入法的键。

运行 ZIP 与源码 ZIP 通过 [本次增量源码核对](../experiments/phase6/results/source-uninstall-update-20261108/summary.json) 关联。相对于收据修订包，仅改变 `Uninstall.ps1`、`scripts/Common.ps1` 和包清单；产品原生文件、Rime、词库及已验证输入不变。源码归档包含修复与定向验证脚本，原生复建证据沿用已成功的独立目录结果；本次在该目录验证脚本并重新导出运行包，没有重新编译或声称跨机器/全新空缓存构建。以 `dist/SHA256SUMS.txt` 和本次报告为当前摘要。

Windows PowerShell 5.1 的收据修复 `[NullString]::Value` 仍保留。其先前同步结果见 [收据源码核对](../experiments/phase6/results/source-receipt-update-20261108/summary.json)，当时运行 ZIP 为 `c1c429adee39465f0740bf7ac6111dad799d097a83e39019a5975d02acf3648e`。收据修复前与本次卸载修复前的归档分别保存在 `dist/before-receipt-fix-20261108/`、`dist/before-uninstall-fix-20261108/`。以下 2026-11-07 记录保留为原生构建基线。

## 2026-11-07 构建基线

2026-11-07。用户已确定产品名称 **拾词输入法（StudyIME）**，新写代码采用 **GPL-3.0-or-later**，中文基础词库和英文学习数据分别遵循 **CC BY-SA 4.0**。本轮交付 `0.5.0-dev.2` 开发预览，沿用已确认的 v0.5 原生设计。

## 当前产物

输出目录为 `.\.cache\packaging\dist`，包含：

- `StudyIME-0.5.0-dev.2-windows-x64-preview.zip`：完整运行目录，含四个产品二进制、从源码构建的 Rime/Lua、121,505 条中文词形/读音记录、原有 200 条审核预览、许可与逐文件摘要，以及安装/卸载脚本。
- `StudyIME-0.5.0-dev.2-source-materials.zip`：已验证的项目源码、10 份选择后的固定上游材料、Weasel Git bundle、Boost、固定 CMake、词库原始数据及离线恢复脚本，增量包含 2026-11-08 的收据与卸载脚本修复。并行词库扩充草稿不在此归档中。
- `SHA256SUMS.txt`、`package-report.json`：实际产物摘要与大小。SHA256 用于完整性核对，不是代码签名；当前产物未签名。

供审阅的展开目录：`.\.cache\packaging\stage\StudyIME-0.5.0-dev.2`。开发预览不代表正式发布条件已满足；人工审核仍为 **0/200**，原三项许可/来源阻止项已处理，剩余产品验收边界见 [许可与来源说明](software-licenses.md)。

## 标识与运行目录

唯一配置入口为 [product.json](../packaging/product.json)，图标为本项目原创的 [SVG](../packaging/artwork/StudyIME.svg)，生成 16/20/24/32/40/48/64/128/256 像素 ICO。四个 PE 文件均带拾词名称、版本与贡献者信息。

| 项目 | 值 |
| --- | --- |
| 稳定产品 ID | `StudyIME.InputMethod` |
| 安装/应用列表 ID | `{D89859C5-5A51-53E6-8199-DF3407D2908B}` |
| TSF CLSID | `{FEB10355-3C08-5342-B75C-5873F1CA04DF}` |
| 简体中文 profile | `{C126F14A-E78D-57FF-910F-205A393AE9D9}`，`0x0804` |
| 安装目录 | `%ProgramFiles%\StudyIME\0.5.0-dev.2` |
| 用户数据与偏好 | `%LocalAppData%\StudyIME` |
| IPC | `StudyIME-v1` + 用户 SID + Windows 会话；开发验证额外加入独立标记 |

产品用自身模块位置寻找 `bin/rime.dll` 和 `data/shared`，不需要当前仓库或 `.cache` 路径。配置模板只复制到拾词自己的用户目录；现有文件不覆盖。管道拒绝远程客户端，访问控制限定当前用户和 SYSTEM，客户端核对服务器用户 SID 与 Windows 会话。

产品覆盖层单独输出到 `.cache/packaging/weasel`；原 v0.5 隔离宿主仍使用原覆盖层和 21 条测试数据。产品启用真实 TSF 键盘事件入口，使用独立注册实现，不启用上游更新器或托盘程序。2026-11-08 已在本机实际注册，后续验收状态见页首。

## 可重复构建与打包

```powershell
# 复用已安装的 VS2019 / ATL / SDK 与固定缓存；不安装任何系统组件
.\tools\packaging\build.cmd

# 离线打包；保留原有人工审核状态
python tools/packaging/package.py --mode preview --with-sources `
  --stage .cache/packaging/stage/StudyIME-0.5.0-dev.2

# 存在词义审核、许可或验收阻止项时，这个命令应失败
python tools/packaging/package.py --mode release
```

构建先从固定源码编译仅含 Lua 插件的 Rime，再复用阶段 4 构建器的 `--product` 模式，输出到独立目录。产品源码树从固定 Weasel Git 提交和正式覆盖层生成，不读取旧实验目录中残留的头文件或上游工作区修改。原开发缓存保留；产品生成目录中的过期文件才会被清理。

VS2019 使用 `/Brepro /experimental:deterministic /pathmap:<project>=.`。仅 `/Brepro` 或仅把命令行改成相对路径仍会留下断言路径、对象路径和匿名命名空间差异；当前编译和资源生成均已消除项目绝对路径。构建记录包含项目源码、完整生成树、实际 Boost/Rime 头文件与源码树摘要、工具链摘要，以及四个二进制的架构、导入和摘要。内容变化会使编译缓存失效；打包也拒绝未重新构建的源文件、生成头文件或依赖变化，即使文件修改时间未变。

ZIP 固定排序、时间、权限，使用不依赖压缩器版本的 `ZIP_STORED`；不同输出位置及反向文件枚举下已验证字节一致。源码包验证入口为 `python tools/packaging/verify_sources.py --build`：在含中文和空格的新目录离线恢复空缓存并构建，要求记录的输入、四个产品原生文件、Rime DLL 和完整运行 ZIP 均逐字节一致，否则返回失败。最终结果见下方证据表。此验证使用同一台机器上已有的 VS2019，不代表跨机器验证，不使用官方 Rime DLL 或其原始 CI 缓存。

本版复建已通过，记录见 `experiments/phase6/results/source-materials.json`。独立目录最初由源码包恢复空缓存，五个原生文件均与原目录一致；随后在同一目录修正 glog 测试路径宏和 RC 头文件记录并续建，Rime 构建记录及完整运行 ZIP 也一致。最终核对 209 份项目文件、16 份恢复材料；未从原目录复制二进制。该结果属于同机工具链、带元数据修正的独立目录验证，未额外声称最终包重新做过全新空缓存构建。最终说明文档调整通过 `source-evidence-binding.json` 关联到已验证输入。

源码材料解包后，在 `project` 中运行：

```powershell
python tools/packaging/bootstrap_sources.py ..
.\tools\packaging\build.cmd
python tools/packaging/package.py --mode preview
```

恢复脚本先校验所有归档摘要，再恢复项目缓存。由 Python 读取固定 ZIP/tar/gzip 数据，使用本地 Weasel bundle 克隆；脚本不会联网、安装编译器、注册输入法或改变系统输入设置。

## 中文基础词库与英文审核

中文基础使用固定 CC-CEDICT 简体词形与读音，加上 wordfreq 3.1.1 中文词频。121,505 条词形/读音记录对应 120,786 个不同词形，原始行摘要和词频许可随包提供。Luna/essay 混合词典不再分发；保留的 Luna 文件只承担方案和拼写规则。比较中，原有 200 个学习词均在第一页，193 个排首位；20 个常用输入样例均排首位。这些样例不能替代实际打字体验验收。

英文数据仍是原来的 200 条审核稿，人工通过 0 条。中文基础词库的扩大不会把其他词条的英文释义自动加入产品。普通点击上下两行仍提交中文，英文只通过明确动作提交。资料见 [中文基础词库](../data/chinese/README.md)。

## 安装与卸载的具体行为

展开目录中直接运行 `Install.cmd` 或 `Uninstall.cmd` **仅输出计划**，不需要管理员权限，也不发生安装/注册。当前已通过 Windows PowerShell 5.1 的实际默认入口预演。

后续在用户明确授权后，才由 64 位管理员 PowerShell 执行：

```powershell
.\Install.ps1 -Apply -AllowDevelopment
# 从实际安装目录中卸载
.\Uninstall.ps1 -Apply -AllowDevelopment
```

安装按固定版本目录复制包、校验复制后的文件、准备当前用户的 Rime 数据，然后调用自己的注册工具注册简中 profile，写入“已安装的应用”条目。不会调用默认输入法设置或 profile 激活接口。首次选用拾词时按用户/会话启动服务，不创建 Windows 系统服务或全局启动任务。

注册使用 Unicode 路径与字符长度，检查现有 CLSID 的产品标记及 DLL 所有权，拒绝覆盖另一位置，也不会把已有的不完整注册直接报告为成功。注册失败时清理可能已写入的 profile 和类别；任一步清理失败都会保留归属记录，供再次注销时核对。注销先查询各项是否仍存在，允许在前一次部分清理后重试；TSF 引用全部清理后才删除自有 COM 类。删除时显式申请所需注册表访问权限。

安装脚本在失败时保留文件和恢复记录，不删除可能仍被注册的 DLL。注册恢复流程已有 28 项内存模拟检查，未调用 Windows 注册 API。实际复制失败、权限异常、Windows TSF 返回行为等仍须授权后的安装验收；有缺失文件时应先从原包恢复，再审阅卸载计划。

卸载要求产品、路径、版本、manifest 摘要匹配的安装记录，停止当前用户/会话的拾词服务，注销自身 profile/CLSID，逐文件删除未修改的已登记内容。用户数据、新增或修改过的文件均保留；被应用锁定的文件会报告并保留可重试的清理记录。不强制结束其他应用，不递归删除用户目录或共享 Rime 目录。当前预览不实现原地升级；只包含 x64 前端，32 位应用支持未提供。

**2026-11-07 构建阶段没有执行 `-Apply`。** 2026-11-08 已执行实际安装、注册、注销、空 TIP 残留清理与占用重试。最后 DLL 删除需要重启 Windows 后继续；浏览器按用户要求跳过，见页首最新记录。

## 本轮针对性验证

| 报告 | 已验证范围 |
| --- | --- |
| [package-validation.json](../experiments/phase6/results/package-validation.json) | 15 项归档一致性、来源明确的中文数据、无 WTL 编译、Rime 源码构建、路径约束、发布阻止及生成头文件漂移检查 |
| [installer-plans.json](../experiments/phase6/results/installer-plans.json) | 12 项真实默认脚本预演、摘要/额外文件/路径校验、PE 标识及系统状态未变检查 |
| [product-runtime-x64.json](../experiments/phase6/results/product-runtime-x64.json) | 8 项独立目录检查，其中包含 22 项真实 Rime IPC 子检查；首次文本词典部署、服务按需启动/停止、产品 GUID、5 个样本的中英文提交 |
| [runtime-evidence-binding.json](../experiments/phase6/results/runtime-evidence-binding.json) | 最终包与已验证的原生程序、Rime 数据、产品标识逐文件相同；脚本/文档调整后复用既有运行证据 |
| [artifact-evidence-binding.json](../experiments/phase6/results/artifact-evidence-binding.json) | 当前构建的绘制探针及头文件、引擎探针及运行数据、中文词库及来源映射均与已通过报告一致；构建元数据修正后保留原行为验证 |
| [product-renderer.json](../experiments/phase6/results/product-renderer.json) | 15 项布局/回调/动画检查，9 张原生预览与既有 v0.5 PNG 逐像素一致 |
| [source-built-engine.json](../experiments/phase6/results/source-built-engine.json) | 当前包的 200 条释义、中英文提交，以及 16 组各 200 次的合成输入耗时 |
| [chinese-source-validation.json](../experiments/phase6/results/chinese-source-validation.json) | 121,505 条中文词条对应 124,551 条源记录，重复导出字节一致 |
| [registration-recovery.json](../experiments/phase6/results/registration-recovery.json) | 28 项生产注册流程的内存失败模拟：部分写入、清理失败保留所有权、重试完成；系统注册未执行 |
| [source-materials.json](../experiments/phase6/results/source-materials.json) | 源码 ZIP 的确定性导出、离线空缓存恢复、同机不同目录构建；四个产品文件、Rime DLL、依赖记录与完整运行 ZIP 的逐字节比较 |
| [source-package-rebuild.json](../experiments/phase6/results/source-package-rebuild.json) | dev.1 历史复建记录；dev.2 的完整 ZIP 比较已并入 source-materials.json |
| [source-evidence-binding.json](../experiments/phase6/results/source-evidence-binding.json) | 最终源码包仅文档调整时，核对所有非文档成员和已验证原生输入，避免重复完整构建 |

程序放在包含中文和空格的独立目录，测试用户数据也在专用缓存子目录。系统产品注册、键盘设置和真实用户数据目录均未改变。修正原生输入和注册代码后只重跑上述阶段 6 相关检查；原有 50/29 项界面、25 项词库流程及旧 IPC/菜单报告均保留；因引擎与中文数据变化，当前 200 条引擎检查已另行验证。程序接口检查和内存模拟不替代物理键鼠、实际安装或 Windows TSF 失败恢复验收。
