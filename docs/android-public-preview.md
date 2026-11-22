# Android 公开预览：构建、签名与复验

这是维护者流程。`build.py apk` 及 `package_preview.py` 交付的是使用本地开发签名的 APK，不可用于 GitHub 公开预览。

## 同一源码提交、独立发行签名

1. 先按[首次公开发布](releases.md#维护者首次公开发布)核对运行和分发范围。记录公开 `main` 候选的完整 commit SHA；构建后若改动源码，重新构建和复验。开发签名不能用于发行；发行密钥应由维护者控制、在仓库外存放并备份，后续更新使用同一签名身份。不要把密码放入命令参数、环境配置文件或日志。
2. 在已准备 SDK、JDK 和原生输入的 Windows 构建环境执行以下命令。签名由 SDK 工具交互读取密码。每一步必须成功，签名证书 SHA-256 必须和维护者确认的发行证书一致。

```powershell
if (git status --porcelain) { throw '请在干净的公开候选检出中构建' }
$source = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw '没有可绑定的源码提交' }
python -X utf8 tools/android/build.py apk --unsigned-release
if ($LASTEXITCODE -ne 0) { throw '无签名构建失败' }
$tools = (Resolve-Path -LiteralPath '.cache/android/sdk/build-tools/35.0.0').Path
$unsigned = (Resolve-Path -LiteralPath 'android/app/build/outputs/apk/release/app-release-unsigned.apk').Path
$signed = Join-Path (Get-Location).Path '.cache/StudyIME-0.1.0-preview.3-arm64-x86_64.apk'
if (Test-Path -LiteralPath $signed) { throw '签名输出已存在；使用新的输出文件' }
$keyStore = Read-Host '请输入仓库之外的发行密钥库路径'
$alias = Read-Host '请输入发行密钥别名'

& "$tools/zipalign.exe" -c -P 16 4 $unsigned
if ($LASTEXITCODE -ne 0) { throw '无签名 APK 对齐检查失败' }
& "$tools/apksigner.bat" sign --ks $keyStore --ks-key-alias $alias --out $signed $unsigned
if ($LASTEXITCODE -ne 0) { throw '发行签名失败' }
& "$tools/apksigner.bat" verify --verbose --print-certs $signed
if ($LASTEXITCODE -ne 0) { throw 'APK 签名验证失败' }
python -X utf8 tools/android/verify_artifact.py --apk $signed
if ($LASTEXITCODE -ne 0) { throw 'APK 原生库或对齐验证失败' }
"源码提交：$source"
Get-FileHash -Algorithm SHA256 -LiteralPath $signed
```

`apksigner.bat` 需要环境中可找到已准备的 Java。先检查对齐再签名，签完后不再修改 APK。不同签名的版本不能直接覆盖已有本地开发包；不要建议为了升级而直接卸载带词频数据的版本。

## 交付前复验

使用独立项目模拟器安装最终发行签名的 APK。设备若留有开发签名的同包名版本，应换干净的项目模拟器，不能在真机上为了测试卸载用户数据。准备合成编辑器和 Debug 测试运行器，再运行以下检查（`$serial` 指核验后的项目模拟器，`$signed` 是上一步同一文件）：

```powershell
python -X utf8 tools/android/build.py apk --debug
if ($LASTEXITCODE -ne 0) { throw '合成编辑器构建失败' }
python -X utf8 tools/android/build.py tests
if ($LASTEXITCODE -ne 0) { throw '测试运行器构建失败' }
python -X utf8 tools/android/run_device_checks.py install --serial $serial
if ($LASTEXITCODE -ne 0) { throw '专用模拟器核验或测试包安装失败' }
python -X utf8 tools/android/device.py --serial $serial install -r $signed
if ($LASTEXITCODE -ne 0) { throw '最终签名 APK 安装失败' }
foreach ($step in 'preview-input', 'reopen', 'clipboard-privacy') {
    python -X utf8 tools/android/run_device_checks.py $step --serial $serial --ime-package org.studyime.android --release-apk $signed --runtime-evidence
    if ($LASTEXITCODE -ne 0) { throw "发行复验失败：$step" }
}
```

以与最终 APK 摘要绑定的结果为准。源码用指向同一个提交的 `android-v<versionName>` 标签；原生依赖源码与当前构建的锁定输入、原始来源摘要和 Android 补丁一并核对。只把经核对的源码、发行 APK、摘要和发布说明对外提供，不附带签名私钥或本地原始验证 ZIP。
