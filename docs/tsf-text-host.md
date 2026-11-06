# 未注册的真实 TSF 文本宿主

2026-11-06。接续 `08d5733`，固定 Weasel 0.17.4 源码和已验证 x86 隔离服务。

## 实现与验证边界

新增 `experiments/phase4/tsf_text_host.cpp` 和 `text_store.h`：可见双文本区，应用侧实现纯文本 `ITextStoreACP`，Windows 自身创建 `ITfThreadMgr`、`ITfDocumentMgr`、`ITfContext`、range、composition 和 edit cookie。宿主没有自己实现/模拟这些 TSF 对象，也没有用 `SetWindowText` 替代上屏；实际 `ITfRange::SetText` 写入文本存储后由宿主绘制。

DLL 通过 `LoadLibrary` → `DllGetClassObject` → `ITfTextInputProcessor::Activate` 在宿主进程内创建。线程使用 `TF_TMAE_NOACTIVATETIP`，没有选择或登记系统输入法 profile。宿主取得进程内 TIP client ID，并显式转发按键、焦点通知到生产 `ITfKeyEventSink` / `ITfThreadMgrEventSink`。**不验证 Windows 对已安装 TIP 的自动按键/焦点路由。** 隔离 DLL 跳过系统按键 sink 注册、语言栏与输入模式设置；注册/注销入口仍被禁用。

候选窗和菜单均由实际 DLL 中的 WeaselUI / EnglishMenu 创建。菜单测试进入真实 `TrackPopupMenuEx` 模态循环，枚举本线程可见的系统菜单窗口并核对文本存储没有持锁，随后验证取消、失焦与服务关闭。2.5 秒宿主兜底定时器若触发，整次测试失败；不能把兜底关闭算作前端成功。

按键和焦点采用程序调用，菜单取消/焦点切换由宿主定时器触发，**这些不是物理键鼠桌面观察，也不是记事本、浏览器或 VS Code 的兼容性结果**。本轮没有验证用真实键鼠点击菜单“输入英文”；宿主投递普通键消息没有驱动系统菜单选择，未将其记为通过。英文上屏通过实际快捷键处理接口验证。

## 实际修复

- 文档焦点切换结束旧组合并使响应失效。旧组合的结束任务持有自己的 composition/range，排队后立即从前端脱离；晚到的结束或 `OnCompositionTerminated` 不会清除新文档组合。
- `OnEndEdit` 忽略不属于当前编辑文档的通知，避免旧文档的 range 与新文档 edit cookie 混用。
- 停用先结束组合，解绑 thread-focus sink，结束候选 UI element、释放候选和编辑 context。候选对象的初始引用使用 `Attach` 接管，打断前端与候选之间的 COM 引用环；验证 `DllCanUnloadNow` 为 `S_OK` 后实际卸载 DLL。
- 所有上游修改保存在 `prepare-tsf.py`，生成可审阅补丁；未只改 `.cache/study-weasel`。

## 定向证据

```powershell
./experiments/phase4/build-tsf.cmd
python experiments/phase4/verify-text-host.py
```

产物：`experiments/phase4/build/tsf_text_host_x64.exe`。报告：`experiments/phase4/results/tsf-text-host.json`，包含宿主、DLL、原 x86 服务与源码/生成器 SHA256。

16 项覆盖激活双 context、同步写锁与真实 composition、可见候选窗、空格中文提交、明确英文提交、重复动作不重复写入、应用延迟写锁、后续 IPC 覆盖后仍提交原快照、焦点切换丢弃旧 commit、旧文档结束任务不影响新文档提交、菜单写锁外打开与取消、菜单失焦关闭、250ms watchdog 检测断线、断线不回放、全程写锁约束，以及停用后 COM 生命周期释放。

`--preview` 额外停留候选与上屏阶段，便于人工查看；外部焦点变化会真实取消组合，因此观察运行受桌面操作影响，应以不受干扰的普通验证作为自动检查证据。旧 `tsf-frontend.json`、菜单、IPC、调度及阶段 3 报告保持原样。

## 下一步

继续将阶段 3 双行布局移入正式前端，开发右侧工具区、独立完整释义浮层、设置、同组合翻页定宽、180ms 翻页动画及 240ms 学习切换动画。随后整合 x64 服务、正式词库、许可和完整产品构建。当前仍不是可安装输入法；真实应用、物理菜单选择、系统自动路由与安装标识仍须后续验证。
