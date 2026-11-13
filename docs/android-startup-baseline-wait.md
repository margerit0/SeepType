# 拾词 Android：启动基线对照与首次绘制等待定位

2026-11-14（北京时间）。本报告完成新一轮任务 1、2：启动基线与诊断开销对照，以及首次绘制具体等待点定位。没有实施产品优化，没有执行最终全套 Release 回归、API 30 补测或磁盘准备。

**80 次无追踪对照未建立诊断代码导致可复验延迟惩罚的因果结论；首次绘制的大段等待已关联到 RenderThread 队列中的表面初始化和首次渲染。** 主线程具体阻塞函数仍缺直接调用栈，源码推断与实测证据在下文分列。不能据此声称零诊断开销、启动达标或 P4 完成。

## 输入、设备与证据

开工实时 HEAD 是 `6c246520b1700b83bb905af508dd40977066dcb8`，分支 `codex/android-dev`，工作区干净。检查点 `9be4dea` 之后的皮肤及剪贴板合入提交完整保留。本次使用历史冻结 APK，未构建当前合入版，不能将结果当作 `6c24652` 产品的 Release 验收。

工作树为 `.`。新证据根目录：

`.cache/android/release-stability-worktree/evidence/startup-baseline-wait-20261113T1923433697860Z`

下文路径均相对该目录；目录名使用 UTC。独立入口是专用缓存中的 `startup-baseline-wait-latest.json`。前轮 `continuation-1235-20261113T152157390451Z`、正式性能目录及 `release-stability-latest.json` 保留原版本含义。

| 角色 | 冻结源码 | APK SHA-256 |
| --- | --- | --- |
| A Release | `0fc9993` | `f62e302a49a0918bcbd1133c1ed68c727175c5afd1a5674c2ba0bc48db850506` |
| B Release | `9be4dea` | `31ab41223ce5a0a438f6e07ef0b1d869ebb07e904b48eca25674e159aedc2e60` |
| 固定 Debug 编辑器 | B | `05694011be29147c7adcb699b809f45b7e8df76e1a81722b05dfa8c1a4c55d64` |
| 固定测试 APK | B | `59c8013ef1b817f5cdde003e2f231cc0f6a72eb62cf03d5ec9216a78651a8987` |

四份摘要在运行前重新核验。A 的 95 个、B 的 99 个受版本控制构建输入逐项与各自 Git 提交及 assembly 收据核对一致；每版另有 7 个准备输入由冻结收据绑定。当前宿主 harness 的源码副本与摘要单独记录在 `protocol.json`、`harness`，未将旧 APK 说成新源码产物。

设备为 `StudyIME_Stability_API35_20261113`，API 35 x86_64，serial `127.0.0.1:5581`，独立 ADB server `5041`，console `5580`。复用原 AVD 数据和 `swiftshader_indirect / skiagl`，本次 guest boot 为 `44d6f09e-c0a7-44f1-a75f-ae4483be66b9`。四批之间未重启、清数据或文件缓存、强制 AOT、切 renderer；本窗口没有并行 Gradle 或其他 instrumentation。

## 任务 1：A → B → B → A

固定编辑器和测试 APK 只在准备阶段正常 `install -r -t`。每批均执行同样的 Release `install -r`，包括相邻的两批 B。每批从安装前开始 `RuntimeCapture`，保留运行标记、命令、APK 前后身份、编译状态、boot/uptime、Windows/WSL 和退出原因记录。四批均为 `verify / reason=install`，追踪关闭。

计时仍是**首次 `onStartInputView` 请求到真实就绪 Compose 绘制**，不含此前进程创建和物理呈现。80 个 PID 均不同；每个进程恰好一次 show、首次 draw 和 ready draw，两个 pending 均为 false，绘制 epoch 相符。覆盖结果和 500 ms 目标分开核对。

| 顺序 | 版本 | 样本 | p50（ms） | p95（ms） | 最大值（ms） |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | A | 20 | 794.783 | 1454.675 | 1972.797 |
| 2 | B | 20 | 818.163 | 1956.101 | 2253.590 |
| 3 | B，重新覆盖安装 | 20 | 658.347 | 748.025 | 756.546 |
| 4 | A，重新覆盖安装 | 20 | 636.018 | 760.992 | 774.551 |

`coverageComplete=true`，四批 p95 均超出 500 ms，`timingTargetsMet=false`。原始逐样本和有序批次见 `abba-samples.csv`、`batch-*`、`abba-summary.json`。

| 比较，均为 B−A | p50 差（ms） | p95 差（ms） | 最大值差（ms） |
| --- | ---: | ---: | ---: |
| 第 2 批 B 对第 1 批 A | +23.381 | +501.426 | +280.792 |
| 第 3 批 B 对第 4 批 A，顺序交换 | +22.329 | −12.967 | −18.005 |

两个方向的 p50 都出现约 22–23 ms 的 B 偏慢，应保留为小幅同向观察；p95 和最大值的差异没有保持。不能用第四批较快的 A、第三批较快的 B，或合并 40 个样本后的统计量单独下因果结论。

同一版本的时段变化更大：A 后批相对前批 p50 下降 158.765 ms、p95 下降 693.683 ms；B 分别下降 159.817 ms、1208.076 ms。Windows CPU 前后快照依次为 19→63%、31→25%、15→26%、8→19%，可用内存和提交量也变化。WSL boot 与三个模拟器进程身份保持；其他聊天进程只观察、未停止。快照不是逐样本连续 CPU 测量，不能据它确定每个慢样本的宿主原因。

**结论：没有确认诊断导致的可复验尾延迟差异；小幅 p50 偏移仍不能与时段、宿主、缓存和 JIT 等变化充分分离。** 这不是零开销或等效性证明。按预先上限在 80 次结束，没有追加批次挑选较快结果。随后已普通覆盖安装恢复 B，三份最终 APK 摘要核对一致。

## 任务 2：等待链及证据强度

先重新分析旧 A 的三次启动，使用新的 SQL 和输出目录，未改写旧 trace。旧数据已能关联主要睡眠的 RenderThread 唤醒者，但没有 perf 调用栈。恢复 B 后，只补了 3 个新进程启动，统一保存在 `diagnostic-B-3-starts/startup.pftrace`；带追踪数字与任务 1 分开。

### 时钟和三个不同的终点

两条 trace 的 `trace_time_clock_id` 均为 6（BOOTTIME）；A 的 6 次、B 的 7 次 clock snapshot 中，归一化 trace 时间减 BOOTTIME 原值均为 0。B 的 `SystemClock.elapsedRealtimeNanos` 锚点与此对应，首次 draw 和 ready draw 都落在各自实际 `Record View#draw()` 内，再按同一 vsync ID 关联 RenderThread `DrawFrames`。A 仍保留 serviceCreate 末端推算的误差，未升级为精确锚点。

| B 诊断 PID | 首次 traversal（ms） | 主线程 S（ms） | 主线程 Running（ms） | 主线程 R/R+（ms） | ready Compose（ms） | 同帧 RenderThread 结束（ms） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 12287 | 811.562 | 391.054 | 127.144 | 293.364 | 855.643 | 865.445 |
| 12402 | 516.959 | 408.488 | 57.131 | 51.318 | 584.445 | 604.349 |
| 12502 | 516.735 | 404.571 | 61.265 | 50.899 | 562.726 | 590.015 |

末两列均从同一首次显示请求起算。三个首帧都是未就绪帧；ready 属于后续帧。ready 回调之后仍有约 9.802／19.904／27.289 ms 的对应渲染尾部，不能删掉它来声称物理屏幕已显示，也不能将它加进原计时后再改写历史目标。

### 两个 RenderThread 同步等待点

| PID | 绘制命令录制前等待（ms） | 对应 RenderThread 工作 | 录制后等待（ms） | 对应 RenderThread 工作 |
| --- | ---: | --- | ---: | --- |
| 12287 | 81.015 | `setSurface`，含 EGL/表面初始化 | 304.179 | 首次 `DrawFrames`，含 shader 与 swap |
| 12402 | 107.053 | 同上 | 298.135 | 同上 |
| 12502 | 80.793 | 同上 | 308.034 | 同上 |

六段等待均有 `thread_state → runnable state → waker_utid` 链，唤醒者是本进程对应的 RenderThread，唤醒紧随对应工作结束。每个进程两段合计 385.194／405.188／388.827 ms。旧 A 三次也有同样的两段结构，合计约 365.876–401.412 ms。这比仅比较同时出现的长切片更强，但没有提供主线程阻塞函数栈。

源码进一步缩小了同步调用候选：

- 第一次睡眠在 `draw-VRI[InputMethod]` 内、`Record View#draw()` 前。AOSP API 35 的 `ViewRootImpl.draw` 在首次报告绘制时调用 `setStopped(false)`；`RenderProxy::setStopped` 使用 `WorkQueue::runSync`，会排在已提交的 `setSurface` 后面。
- 第二次睡眠已在 `draw-VRI` 结束之后。`ViewRootImpl.performDraw` 的首次绘制报告路径又调用 `setStopped(mStopped)`，再次进入同一同步队列。该位置与等待首次 `DrawFrames` 结束吻合，不能直接把整段约 300 ms 归给位于 draw 内的 `syncAndDrawFrame/postAndWait`。
- **上述具体函数名是源码与切片位置支持的推断，尚未取得该次阻塞的直接栈确认。** 参考代码是 AOSP `android-15.0.0_r1`，没有声称它与该系统镜像的每条指令逐字节相同。源码、下载摘要及实际 profile mapping/build ID 保存在 `references` 和 `B-wait-analysis`。

```mermaid
flowchart LR
    A[主线程首次绘制] --> B[录制前同步等待]
    B --> C[RenderThread setSurface / EGL]
    C --> D[真实未就绪 Compose draw]
    D --> E[录制后同步等待]
    E --> F[RenderThread 首次 DrawFrames]
    F --> G[引擎结果回调得以执行]
    G --> H[后续真实 ready draw]
    H --> I[对应帧剩余渲染]
```

图中的同步函数候选是前后两次 `setStopped → runSync`；图末仍不是物理呈现。

### EGL、shader、虚拟图形通信和调度

三次 B 的 EGL context 创建为 60.596–93.068 ms，包含在 `setSurface` 的 93.530–137.888 ms 中。首次 `DrawFrames` 为 303.263–309.682 ms，其中四个 `shader_compile` 切片合计 202.893–204.989 ms，swap 为 85.920–88.640 ms。这些是嵌套或连续区间，不能再与上表主线程等待相加。

新的 CPU 栈确认：就绪前 RenderThread 的 67 个完整展开样本中，51 个包含 `goldfish_pipe_read_write`；其中 36 个包含 `glCreateProgram_enc`，7 个包含 `rcCreateSyncKHR_enc`，通过 `QemuPipeStream::commitBufferAndReadFully` 和 `qemu_pipe_read` 进入客体驱动。另有 EGL loader / `eglGetDisplay` 调用栈。样本计数不是对应路径的精确 CPU 百分比。

首次 `DrawFrames` 的 RenderThread 在客体调度口径下 Running 为 219.103–257.463 ms，S 仅 0.067–0.165 ms，R/R+ 为 45.635–90.456 ms。它并非整段睡眠等待一个 GPU fence。**`shader_compile` 的墙钟包含模拟器命令/回复通信、驱动执行和调度，不能全部归为应用或 shader 编译器计算。** 本次没有宿主 SwiftShader 的调用栈，无法进一步分离宿主编译、pipe 处理和虚拟 CPU 调度各占多少；客体 Running 也不能直接当作宿主实际执行时间。

### 引擎的实际工作与主线程排队

| PID | 资源核验墙钟 / 线程 CPU（ms） | 其中 R/R+（ms） | Rime 创建墙钟 / 线程 CPU（ms） | 其中 R/R+（ms） | FIRST_MAIN_QUEUE（ms） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12287 | 341.051 / 38.895 | 300.835 | 256.469 / 58.057 | 176.847 | 120.645 |
| 12402 | 75.755 / 36.391 | 36.638 | 260.887 / 63.962 | 173.609 | 246.370 |
| 12502 | 241.195 / 42.646 | 196.937 | 178.423 / 62.897 | 97.711 | 126.783 |

资源核验的 D 等待只有 0–0.880 ms；其长墙钟主要不是磁盘阻塞，实际线程 CPU 是约 36–43 ms。Rime 创建另有约 15.766–22.402 ms 的 D 等待，但仍有明显可运行未调度时间。最慢样本的主线程首次 traversal 也有 293.364 ms 的 R/R+，不能把它全部解释为 EGL 同步睡眠。

三段 `FIRST_MAIN_QUEUE` 分别有 109.837／227.617／115.179 ms 与主线程等待 RenderThread 的睡眠重叠；结果回调在首次 traversal 结束后约 6.736／17.153／7.674 ms 执行。工作线程已经完成结果，主线程尚不能处理该回调。它不是“主线程正在等 Rime 完成”的额外串行开销。上述 CPU 和阶段数据来自当前冻结 B 的本次诊断，不复用已撤回方案的数字。

## 采集限制与核验

新增配置请求了阻塞时的 `sched_switch` 调用栈及 99 Hz CPU 栈。阻塞事件源在 `perf_event_open` 返回 `EINVAL` 后被 producer 丢弃；CPU 源成功取得 202 个样本，其中 18 个 `invalid_elf` 展开不完整。主线程等待函数没有命中完整栈，以上推断因此未提升为确认。原始错误在诊断运行的 `runtime/logcat.txt`，独立状态见 `analysis-verification.json`；没有覆盖原失败或再追加新进程。

两条 trace 的必要 sched 数据完整，ftrace overrun、drop、parse error 计数均为 0。36 个 setup notice 对应不存在的物理 GPU 事件，与阻塞 perf 数据源失败分开记录。所有被分析的线程区间都有完整调度状态覆盖；另用独立 SQL 复核了六个首次 traversal 的状态总和及十二条主要唤醒链。metadata 的含引号配置文本使用十六进制导出后解析，规范结果是 `metadata.json`，不依赖初次 CLI CSV 展示的引号处理。

83 次启动的运行边界内均无本次 runtime fatal 或归属崩溃，历史 21 个去重事件仍无根因结论。没有重跑此前 25 分钟循环。结束时 B Release、固定编辑器及测试包摘要一致，`verify / reason=install`；本任务 AVD 已通过实时 PID/命令行/console AVD 名核验后关闭，数据保留，其他两个 AVD 与 WSL boot 未变。

## 留给任务 3 的两个可检验假设

1. **只调整首次引擎准备的调度优先级。** B 的 `StudyRime` 当前从创建起就用 DISPLAY 优先级。资源核验和 Rime 创建实际约百毫秒 CPU，与首次界面工作竞争，而完成后的结果又排队 120–246 ms。可检验首次准备使用普通/较低优先级、完成后恢复 DISPLAY，是否能让主线程更早完成首帧且引擎仍赶上 ready 帧。预期只减少竞争造成的部分等待；也可能推迟引擎就绪。最小验证应同时比较 main 的 R/R+、引擎完成相对首帧的位置、原 ready 边界，并核对后续按键阶段已恢复优先级。它与此前提前创建引擎或门控首帧不同，本轮未实施。
2. **减少静态键盘绘制触发的程序创建和图形通信。** B 的键帽已使用三次 `drawRoundRect` 画接触阴影和底色，不能再把“移除每键 elevation”说成新方案。可试验静态键帽图层合并/缓存或统一绘制路径，保持可见内容及交互，检查能否实际减少首帧 shader/program 类型与 `glCreateProgram` 往返。现有约 203–205 ms shader 区间是待影响区间，不是可承诺节省值；位图上传或新 shader 也可能抵销收益。先对比操作类型、完整 CPU 栈和实际 ready 帧，再做固定安装顺序的无追踪对照；操作类型没减少时不据绘制节点变少宣称收益。

两者都应先在保留皮肤/剪贴板改动的实际当前源码上建立相应基线，继续保留资源核验、R8 和原计时终点。不能用少量带追踪快样本或把渲染移到计时结束之后代替收益复验。

## 复查入口

| 内容 | 新目录中的文件 |
| --- | --- |
| 冻结协议、源码/APK/harness 身份 | `protocol.json`、`inputs`、`harness` |
| 四批全部样本、安装及宿主记录 | `abba-summary.json`、`abba-samples.csv`、`batch-*` |
| 旧 A 的新分析，原 trace 只读 | `old-baseline-analysis/wait-analysis.json` 及 SQL |
| B 的三次诊断及原采集失败 | `diagnostic-B-3-starts` |
| 精确绘制关联、状态、调用栈及校验 | `B-wait-analysis/wait-analysis.json`、`expanded-stacks.json`、`analysis-verification.json` |
| 可重算脚本 | `summarize_abba.py`、`expand_stacks.py`、`analyze_waits.py`、`verify_analysis.py` |
| 关闭与最终设备状态 | `final-device-state.json`、`environment-close-01` |
| 封存索引和逐文件校验 | `evidence-index.json`、`artifact-manifest.json`、`report-verification.json` |

执行入口 `run_abba.py` 和 `trace_waits.py` 都拒绝覆盖已有实验目录。只读重算可按保存的 SQL 调用现有 v59.1 `trace_processor_shell.exe query --format csv -f <SQL> <trace>`，不必再次启动设备。
