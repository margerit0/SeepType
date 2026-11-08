# 产品化开发预览

主入口：[产品打包与安装产物](../../docs/packaging.md)、[软件许可汇总](../../docs/software-licenses.md)。

本阶段在 `.cache/packaging` 构建 StudyIME 产品运行目录，保存独立 GUID、运行路径、源码材料、确定性打包和默认只预演的安装/卸载脚本。保留 v0.5，使用原有 200 条审核预览；没有自动批准词义。

`results` 是本阶段的验证记录，不覆盖旧阶段报告。只有相关修改时才运行对应新检查：

```powershell
python tools/packaging/verify.py --section archive
python tools/packaging/verify.py --section installer
python tools/packaging/verify.py --section runtime
python tools/packaging/bind_evidence.py
.\tools\packaging\verify-registration.cmd
python tools/packaging/verify_sources.py --build
python tools/packaging/bind_source_evidence.py
```

`runtime` 只做无注册 DLL 身份检查及专用用户数据目录中的真实 Rime IPC。它不注册 TIP、不注入物理按键、不修改正常用户数据或系统输入设置。`bind_evidence` 仅核对之前测试的原生/数据摘要是否仍然适用，不伪装成新的运行验收。

注册恢复验证让生产流程调用内存模拟对象，覆盖部分写入、清理失败和再次清理。`verify_sources --build` 从源码 ZIP 在含中文和空格的新目录恢复空缓存；四个产品二进制及记录输入必须全部相同才成功。源码包最后只调整说明时，使用 `bind_source_evidence` 校验原生输入和其余归档成员未变，不重复已通过的完整构建。

2026-11-08 已获安装、应用测试后卸载恢复授权。修复收据文件替换后实际安装成功，记事本 5 项观察通过；Chrome 状态读取被 Computer Use URL 识别保护中断，已注册产品尚未卸载。最新状态见 [实际安装验收](../../docs/installed-desktop-acceptance.md)。

`capture-installed-state.py` 只读记录安装状态；`run-approved-install-step.ps1` 包装已授权的安装/卸载并记录结果，不自行提权；`start-installed-app.py` 使用独立 StudyIME 数据启动真实应用，不选输入法或合成按键。`tools/packaging/verify-receipt.ps1` 仅在缓存目录验证真实收据创建、原子替换、占用失败与重试，不修改系统注册。
