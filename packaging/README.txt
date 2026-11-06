拾词输入法（StudyIME）0.5.0-dev.1
Windows 11 x64 开发预览包

本包保留已确认的 v0.5 候选界面，包含独立前端、服务与设置程序。
200 条英文数据仍待人工审核；本包不是正式发布版。

检查安装计划：
  Install.cmd
检查卸载计划：
  Uninstall.cmd
这两个默认命令不安装、不注册、不卸载。

实际安装必须在明确授权后，由 64 位管理员 PowerShell 执行：
  .\Install.ps1 -Apply -AllowDevelopment
实际卸载从安装目录执行：
  .\Uninstall.ps1 -Apply -AllowDevelopment
也可以在“已安装的应用”中使用该卸载入口。
脚本不会修改执行策略；请遵循本机现有脚本策略。

安装位置：Program Files\StudyIME\0.5.0-dev.1
数据位置：当前用户 LocalAppData\StudyIME
只注册拾词自己的简体中文 TSF 标识，不设为默认输入法，不立即激活。
服务在选用拾词时按用户和登录会话启动，不是 Windows 系统服务。
设置可以从 bin\StudyIME.Settings.exe 打开，也保留已有设置快捷键。
此版本只包含 x64 前端；32 位应用支持尚未提供。

卸载保留用户数据；使用中的或修改过的程序文件会保留并报告，
关闭相关应用后可重试。当前不支持原地升级，请先审阅并卸载旧预览。

许可与来源：COPYING.md、LICENSE、docs/software-licenses.md、licensing。
词库预览、原文、署名与许可：data\lexicon。
该版本附有单独的 source-materials.zip 和 SHA256 清单，供源码审阅与构建。
当前源码/许可核验的未决项见 package-manifest.json 的 release_blockers。

安装/卸载、系统自动输入路由及真实桌面兼容性尚未验收。
现有检查不替代人工词义审核或真实键鼠验收。
