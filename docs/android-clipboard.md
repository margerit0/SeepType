# Android 剪贴板历史

- 点待机工具栏的第三个图标打开剪贴板。输入拼音时，长按候选展开按钮进入快捷设置，仍可从上方工具栏打开剪贴板。
- 历史默认关闭。可在面板或应用的「键盘设置 → 剪贴板」中开启。点条目将完整文本粘贴到当前输入框，可置顶或逐条删除。
- 最多保存 50 条、置顶 10 条，重复内容只保留一条。清空或关闭须确认，包含置顶项；这不会清除 Android 系统剪贴板。

历史仅保存在本机应用私有的不备份目录，不上传。密码及禁止个性化的输入框禁用入口并暂停记录；标记为敏感的内容、图片、URI 及超过 4096 UTF-8 字节的文本不记录。只在输入法服务运行且系统允许读取时记录，不承诺补录服务未运行期间的内容。

## 验证

`ClipboardHistoryTest` 使用 Debug 版和合成文本，检查真实输入框粘贴、隐私边界，以及工具栏居中、英译开关与候选显示、浅深色、窄屏大字号和横屏。`ClipboardPersistenceTest` 使用独立的 Release 输入法进程，检查重启后保存的条目与置顶状态。请在专用模拟器上运行，测试会替换模拟器系统剪贴板的内容。

```powershell
python -X utf8 tools/android/build.py apk --debug
python -X utf8 tools/android/build.py tests
python -X utf8 tools/android/run_device_checks.py install --serial 127.0.0.1:5561
python -X utf8 tools/android/run_device_checks.py clipboard --serial 127.0.0.1:5561
python -X utf8 tools/android/collect_device_evidence.py clipboard --serial 127.0.0.1:5561
```

模拟器序列号以 `adb devices -l` 为准，原生截图保存在 `.cache/android/evidence/clipboard/`。
