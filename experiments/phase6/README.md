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

实际 `Install.ps1 -Apply`、`Uninstall.ps1 -Apply` 和输入法注册均待明确授权；Computer Use 继续暂缓。
