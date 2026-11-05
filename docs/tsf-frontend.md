# TSF 学习前端接入与 x64 隔离构建

2026-11-05。固定上游 Weasel 0.17.4 / `9cc96e20dc71b80876b12f689bb5863c76c2a7ed`。

## 本轮交付

已将学习动作接入真实 `WeaselTSF` / `CCandidateList` 源码，并完整编译链接 x64 TSF DLL（包括 IPC、WeaselUI、资源与 COM 导出）。产物为 `experiments/phase4/build/tsf-x64/study_weasel_x64.dll`。它只使用隔离管道，注册及注销入口返回 `E_ACCESSDENIED`；没有执行注册、激活 TSF 或改变输入设置。它不是可安装产品，服务仍沿用上轮通过检查的 x86 二进制。

- `src/study/windows/WeaselResponse.*` 在同一次管道回调中解析普通 commit、候选、状态、样式与 study capability，形成只读、独立拥有的响应。身份与版本始终为 `uint64_t`。样式沿用 Weasel 的增量发送规则；候选和 capability 不从上次响应补齐。缺失或重复 capability 禁用动作。
- `src/study/windows/TsfStudy.inc` 接入实际 TSF 编辑会话。每个 `StudyResponseEditSession` 持有独立响应、COM context、生命周期和响应序号，不再在异步执行时读取共享管道缓冲区。普通 commit 仍经既有 composition/`ITfRange::SetText` 路径交付；响应处理中的子操作使用当前已获准的 edit cookie，避免二次异步排队。代码已编译，真实编辑执行尚未验证。
- 只有最新响应可发布候选与 capability；输入、菜单关闭、候选变化等失效会阻止旧异步响应重新发布 UI。失焦、上下文退出、停用及重连还改变生命周期，旧编辑任务不能向新的上下文应用响应。
- Ctrl+Shift+Enter 通过 Inspect → CommitEnglish 调用服务；Inspect 与提交在编辑会话排队前完成，应用推迟编辑也不需要重发用户动作。右键候选和 Shift+F10/菜单键使用实际候选命中位置，先 Inspect，再显示完整定义与明确英文菜单。F2 没有临时替代独立释义浮层。
- 菜单在 TSF 写锁之外运行。候选变化/失焦关闭菜单并丢弃令牌；菜单期间每 250ms 检查连接，断线结束菜单。提交前仍要求服务重新验证 stamp/index。
- 普通点击（包括英文行所属候选区域）继续走中文选词。移除原先鼠标选词后注入 `VK_SELECT` 的方案，直接捕获标准响应并申请编辑会话。空格与数字没有改为英文提交。
- SetLearning 已有前端动作入口，收到关闭状态后立即禁用英文动作；右侧原生按钮尚未接入。
- 移除上游管道写失败后的自动重连重发，失败时关闭句柄、清空缓冲区与会话身份。重连需要新会话、新响应，不回放英文请求。移除 TSF 后台 detached 线程访问 COM/客户端及启动系统服务的路径；重连在原 apartment 完成。

正式修改保存在 `src/study/windows` 和 `experiments/phase4/prepare-tsf.py`，由 `prepare-weasel.py` 生成覆盖层及同一份 `weasel-study-ipc.patch`。TSF/UI 使用一致的固定源码头文件树，避免原版与覆盖层类定义混用。资源编译使用 Windows SDK `winres.h`，不需要安装 MFC。

## 本轮证据

```powershell
./experiments/phase4/build-tsf.cmd
python experiments/phase4/verify-frontend.py
```

新增报告：`experiments/phase4/results/tsf-frontend.json`，包含前端 EXE、TSF DLL、被测 x86 服务及源码/补丁 SHA256。

16 项定向检查覆盖：x64 架构、DLL 无注册加载、同响应 64 位身份、缓冲区覆盖后独立 commit、缺失/重复 capability、截断响应、菜单令牌不可复活、真实 x64→x86 Rime 候选/动作、候选变更、英文普通 commit、关闭学习、普通空格中文提交、会话重建及断线清空响应。测试使用生产 `WeaselResponse`/`CandidateState` 与真实 Weasel 客户端。

**这些检查没有激活 TSF，没有执行真实 TSF edit session，也没有实际操作 TSF 候选窗口。** DLL 能加载和协议检查通过不能证明文字已在应用上屏、菜单可见/可操作或定时断线关闭行为已实测。上轮 16 项菜单、27 项 IPC、14 项调度及阶段 3 报告保持原样，没有重跑。

## 下一个开发断点

1. 给已接入的真实 TSF 编辑路径增加未注册的隔离文本宿主，验证同步/异步编辑、焦点切换、提交一次、菜单与断线；不能将本轮 parser/IPC 测试表述为已验证上屏。
2. 将阶段 3 已验证的双行布局移入正式前端，接入右侧工具区、独立完整释义浮层与设置；实现同组合翻页定宽、180ms 翻页及 240ms 学习开关动画，继续遵循 v0.5。
3. 当前是完整 x64 TSF DLL 构建，尚不是 x64 服务/完整产品构建。继续整合服务、正式词库、许可与安装标识。准备具体可审阅安装产物后再申请实际系统安装授权。
4. 记事本、浏览器、VS Code 的真实兼容性仍未测试。21 条词对仍为 test-only。
