# 拾词输入法产品打包与安装产物

2026-11-07。用户已确定产品名称 **拾词输入法（StudyIME）**，新写代码采用 **GPL-3.0-or-later**，英文词库单独遵循 **CC BY-SA 4.0**。本轮交付 `0.5.0-dev.1` 开发预览，沿用已确认的 v0.5 原生设计。

## 当前产物

输出目录为 `.\.cache\packaging\dist`，包含：

- `StudyIME-0.5.0-dev.1-windows-x64-preview.zip`：完整运行目录，含四个产品二进制、固定 x64 Rime、最小中文输入数据、原有 200 条审核预览、许可与逐文件摘要，以及安装/卸载脚本。
- `StudyIME-0.5.0-dev.1-source-materials.zip`：当前项目源码、14 份固定上游源码归档、Weasel Git bundle、Boost 原始归档、Rime 固定构建材料及离线恢复脚本。
- `SHA256SUMS.txt`、`package-report.json`：实际产物摘要与大小。SHA256 用于完整性核对，不是代码签名；当前产物未签名。

供审阅的展开目录：`.\.cache\packaging\stage\StudyIME-0.5.0-dev.1`。开发预览不代表正式发布条件已满足；人工审核仍为 **0/200**，软件许可与来源仍有 [明确的阻止项](software-licenses.md)。

## 标识与运行目录

唯一配置入口为 [product.json](../packaging/product.json)，图标为本项目原创的 [SVG](../packaging/artwork/StudyIME.svg)，生成 16/20/24/32/40/48/64/128/256 像素 ICO。四个 PE 文件均带拾词名称、版本与贡献者信息。

| 项目 | 值 |
| --- | --- |
| 稳定产品 ID | `StudyIME.InputMethod` |
| 安装/应用列表 ID | `{D89859C5-5A51-53E6-8199-DF3407D2908B}` |
| TSF CLSID | `{FEB10355-3C08-5342-B75C-5873F1CA04DF}` |
| 简体中文 profile | `{C126F14A-E78D-57FF-910F-205A393AE9D9}`，`0x0804` |
| 安装目录 | `%ProgramFiles%\StudyIME\0.5.0-dev.1` |
| 用户数据与偏好 | `%LocalAppData%\StudyIME` |
| IPC | `StudyIME-v1` + 用户 SID + Windows 会话；开发验证额外加入独立标记 |

产品用自身模块位置寻找 `bin/rime.dll` 和 `data/shared`，不需要当前仓库或 `.cache` 路径。配置模板只复制到拾词自己的用户目录；现有文件不覆盖。管道拒绝远程客户端，访问控制限定当前用户和 SYSTEM，客户端核对服务器用户 SID 与 Windows 会话。

产品覆盖层单独输出到 `.cache/packaging/weasel`；原 v0.5 隔离宿主仍使用原覆盖层和 21 条测试数据。产品启用真实 TSF 键盘事件入口，使用独立注册实现，不启用上游更新器或托盘程序。已恢复注册能力的 DLL 仍未在本机实际注册。

## 可重复构建与打包

```powershell
# 复用已安装的 VS2019 / ATL / SDK 与固定缓存；不安装任何系统组件
.\tools\packaging\build.cmd

# 离线打包；保留原有人工审核状态
python tools/packaging/package.py --mode preview --with-sources `
  --stage .cache/packaging/stage/StudyIME-0.5.0-dev.1

# 存在词义审核、许可或验收阻止项时，这个命令应失败
python tools/packaging/package.py --mode release
```

原生构建复用阶段 4 构建器的 `--product` 模式，输出到独立目录。产品源码树从固定 Weasel Git 提交和正式覆盖层生成，不读取旧实验目录中残留的头文件或上游工作区修改。原开发缓存保留；产品生成目录中的过期文件才会被清理。

VS2019 使用 `/Brepro /experimental:deterministic /pathmap:<project>=.`。仅 `/Brepro` 或仅把命令行改成相对路径仍会留下断言路径、对象路径和匿名命名空间差异；当前编译和资源生成均已消除项目绝对路径。构建记录包含项目源码、完整生成树、实际 Boost/Rime 头文件与源码树摘要、工具链摘要，以及四个二进制的架构、导入和摘要。内容变化会使编译缓存失效；打包也拒绝未重新构建的源文件、生成头文件或依赖变化，即使文件修改时间未变。

ZIP 固定排序、时间、权限，使用不依赖压缩器版本的 `ZIP_STORED`；不同输出位置及反向文件枚举下已验证字节一致。源码包验证入口为 `python tools/packaging/verify_sources.py --build`：在含中文和空格的新目录离线恢复空缓存并构建，要求记录的输入及四个原生程序均逐字节一致，否则返回失败。最终结果见下方证据表。此验证使用同一台机器上已有的 VS2019，不代表跨机器验证，也没有重现官方 Rime DLL 的原始 CI 环境。

**2026-11-07 已通过完整复建：** 从源码 ZIP 恢复空缓存后，四个原生程序及记录输入全部一致；继续在该新目录运行 `package.py --mode preview`，生成的完整运行 ZIP 也逐字节一致。本次恢复与编译约 390 秒，全程离线。最终仅更新交付说明，再用归档成员摘要绑定这份已完成的构建证据。

源码材料解包后，在 `project` 中运行：

```powershell
python tools/packaging/bootstrap_sources.py ..
.\tools\packaging\build.cmd
python tools/packaging/package.py --mode preview
```

恢复脚本先校验所有归档摘要，再恢复项目缓存。Windows 自带 `tar.exe` 的固定 7z 读取及本地 Weasel bundle 克隆已核对；脚本不会联网、安装编译器、注册输入法或改变系统输入设置。

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

**本轮没有执行任何 `-Apply` 路径，没有实际安装、卸载或注册输入法。** 这些行为的真实回滚、占用恢复、已注册 TIP 的自动路由和外部应用兼容性仍待明确授权后验收。Computer Use 按用户要求继续暂缓。

## 本轮针对性验证

| 报告 | 已验证范围 |
| --- | --- |
| [package-validation.json](../experiments/phase6/results/package-validation.json) | 12 项归档一致性、路径约束、发布阻止、x64、路径映射及生成头文件漂移检查 |
| [installer-plans.json](../experiments/phase6/results/installer-plans.json) | 12 项真实默认脚本预演、摘要/额外文件/路径校验、PE 标识及系统状态未变检查 |
| [product-runtime-x64.json](../experiments/phase6/results/product-runtime-x64.json) | 8 项独立目录检查，其中包含 22 项真实 Rime IPC 子检查；首次文本词典部署、服务按需启动/停止、产品 GUID、5 个样本的中英文提交 |
| [runtime-evidence-binding.json](../experiments/phase6/results/runtime-evidence-binding.json) | 最终包与已验证的原生程序、Rime 数据、产品标识逐文件相同；脚本/文档调整后复用既有运行证据 |
| [registration-recovery.json](../experiments/phase6/results/registration-recovery.json) | 28 项生产注册流程的内存失败模拟：部分写入、清理失败保留所有权、重试完成；系统注册未执行 |
| [source-materials.json](../experiments/phase6/results/source-materials.json) | 源码 ZIP 的确定性导出、离线空缓存恢复、同机不同目录原生构建及四个程序的逐字节比较 |
| [source-package-rebuild.json](../experiments/phase6/results/source-package-rebuild.json) | 在上述恢复目录继续打包，完整运行 ZIP 与原产物逐字节相同 |
| [source-evidence-binding.json](../experiments/phase6/results/source-evidence-binding.json) | 最终源码包仅文档调整时，核对所有非文档成员和已验证原生输入，避免重复完整构建 |

程序放在包含中文和空格的独立目录，测试用户数据也在专用缓存子目录。系统产品注册、键盘设置和真实用户数据目录均未改变。修正原生输入和注册代码后只重跑上述阶段 6 相关检查；原有 50/29 项界面、25 项词库流程、200 条引擎、旧 IPC/菜单等报告均保留。程序接口检查和内存模拟不替代物理键鼠、实际安装或 Windows TSF 失败恢复验收。
