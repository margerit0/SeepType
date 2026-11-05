# Weasel 服务线程调度

2026-11-05。固定上游仍为 Weasel 0.17.4 / `9cc96e20dc71b80876b12f689bb5863c76c2a7ed`。

## 已实现的边界

此前管道线程持有 `g_api_mutex` 调用 Rime，Rime 又直接调用 `UI::Update/Show/Hide`；服务窗口的设置、主题处理也获取该锁。可见窗口接入后，跨线程同步窗口调用与窗口线程等待此锁可能形成循环等待。

现在所有管道来源的 `RequestHandler` 操作通过 `src/study/windows/WindowDispatcher.*` 排到服务窗口线程。托盘命令、主题和会话操作共用窗口线程，不再使用跨线程的 Rime/UI 互斥锁。初始化与最终清理由宿主在同一个线程完成；`Server::Run()` 返回前已回收管道线程，随后才能销毁 handler/UI。

执行顺序：

1. 每条管道连接有独立接收/响应缓冲区；工作线程读完一个请求后入队。
2. 私有 `WM_APP` 消息仅用于唤醒，不携带任务指针。队列最多 64 项，合并唤醒，避免持续输入堆积冗余消息。
3. 窗口线程每次执行一项：读取请求、调用 Rime、编码同一次候选和 study 状态、更新 UI。执行任务时不持队列锁。
4. 工作线程等任务完成后写回响应；阻塞的客户端不占用窗口线程。响应发送不调用等待对方读完的 `FlushFileBuffers`。
5. 退出消息循环后先关闭队列，取消未执行任务，再取消同步管道 I/O 并 join 监听及连接线程。取消与下一次 I/O 开始的竞态通过重试取消处理；不强制终止线程。

调度器拒绝窗口线程自己调用同步 `Invoke`，并防止嵌套消息循环重入另一项管道任务。任务异常会唤醒等待者并关闭该连接；旧唤醒消息不会执行已取消任务。最多保留 64 个活动连接，已退出连接线程在后续连接进入时回收。

Rime 部署通知可能来自引擎后台线程。`OnNotify` 现在仅在短锁内复制最新通知；窗口线程再读取状态标签、更新展示字段。它保留上游的“最新通知覆盖前一条”语义，不在后台线程调用 Rime 查询或触碰 UI。Finalize 后清空通知。Windows 取消结束会话（`WM_ENDSESSION(FALSE)`）不会清理引擎。

## 源码与产物

- `src/study/windows/WindowDispatcher.*`：任务生命周期、窗口调度和取消。
- `src/study/windows/WeaselPipeServer.inc`：由生成器接入 Weasel 的管道线程实现，拥有并回收所有线程。
- `experiments/phase4/prepare-weasel.py`：服务接入与通知邮箱修改；缓存覆盖层不是正式修改来源。
- `experiments/phase4/patches/weasel-study-ipc.patch`：从固定上游生成的接入差异，配合本项目 `src/study` 构建。

构建命令沿用 `experiments/phase4/build-service.cmd`。新增 `dispatch_test.exe`，所有该脚本生成的 EXE 均嵌入 `asInvoker` 清单，避免测试程序文件名被 Windows 当作安装程序请求提权。

## 本轮验证

运行 `python experiments/phase4/verify-dispatch.py`，**14/14 通过**，证据见 [service-dispatch.json](../experiments/phase4/results/service-dispatch.json)，保留服务、调度测试和真实 Rime 客户端的 SHA256。

- 实际隐藏 Win32 消息窗口：同线程执行、嵌套消息、异常释放、取消排队请求和旧唤醒消息安全性。
- 实际 Weasel 管道：两个健康连接共 200 次请求，逐条核对会话和返回内容；同时处理窗口命令。
- 保留不发送数据的连接，以及不读取响应的连接；确认后者已积满 64KiB 响应且生成第二份响应。健康连接继续工作，服务退出时回收阻塞读、写和监听线程。
- 取消 Windows 结束会话后仍可正常处理请求。
- 独立真实 Rime 进程：同响应候选/capability、完整英文标准 commit、重复动作拒绝、学习开关、失焦后旧动作拒绝。

首轮 13 项通过后合并唤醒消息并补了取消结束会话保护；最终版本重新验证上述受影响路径，共 14 项。原先 27 项 IPC、16 项菜单、引擎及布局报告保持原样，没有重跑。

这些证据仍是 **x86 隔离服务与隐藏消息窗口**，不是可见候选条、真实 TSF 编辑会话或应用兼容性结果。下一步应直接接入真实 TSF 前端的同响应候选/capability、明确英文动作、断线与重连状态；不要重新把本项调度实现当作调查任务。x64 完整构建及 v0.5 工具区、释义浮层、设置、翻页定宽和两种动画仍待实现。
