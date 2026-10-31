# 英文学习动作的 Weasel IPC 接入

2026-11-01。本协议已接入固定版本 Weasel 的客户端、管道服务与 `RimeWithWeaselHandler`，在独立 x86 进程中验证；真实 TSF 候选前端尚未调用这些接口。

## 模块职责

| 模块 | 职责 |
| --- | --- |
| `src/study/RimeSession.*` | 非拥有型 Rime 会话适配器；查询当前页、选中项、光标和 Lua 完整词值；不创建/销毁会话，不读取 commit |
| `src/study/StudyService.*` | 按 IPC 会话保存临时英文目标；管理活动会话、版本、学习状态与服务实例身份 |
| `src/study/StudyProtocol.*` | 请求/响应编码与有界解析；不接收客户端提供的英文文本 |
| `src/study/lua/study_core.lua` | 键盘和菜单共用的词表查询、完整组合判定与实际英文提交 |
| `experiments/phase4/patches/weasel-study-ipc.patch` | 对固定上游的可审阅接入补丁；生成脚本不修改原源码 checkout |

阶段 3 的 `StudyEngine` 是保留历史证据的实验宿主适配器。新的服务模块直接绑定 `RimeWithWeaselHandler` 已有会话，不依赖它，也不共享阶段 3 的运行数据目录。

## 请求与响应

新增 `WEASEL_IPC_STUDY_ACTION` 命令保留旧命令编号。请求体只含 ASCII 字段，以换行和终止行结束：

```text
study.v1=inspect,<service>,<session>,<revision>,<index>,0
.
```

`inspect` 查询并选中当前页候选；`commit` 使用已查询的目标提交完整英文；`learning` 的 index 必须为 0，最后一个字段为目标开关 0/1。服务/会话/版本均为无符号 64 位值；跨语言前端应保留整数精度，不能转为 JavaScript 普通 Number。

请求最多 192 个 UTF-16 单元，字段数、操作名、整数溢出、候选索引与布尔值均检查。不存在接收任意英文文本的字段；未支持版本、额外字段、负数、过长或不完整请求直接拒绝。

普通 Weasel 响应的 action 列表增加 `study`，并附带：

```text
study.v1=<service>,<session>,<revision>,<learning>,<index>,<reason>,<zh-hex>,<en-hex>
```

zh/en 是 UTF-8 字节的十六进制编码，各自最多 2048 字节，避免正文字符被解释为协议分隔符。旧响应解析器会忽略未知 study 字段；新前端通过 `DecodeState` 检查完整终止行与单一有效状态。没有 capability 时不发送学习动作。释义只供显示，不能作为提交参数。

英文提交成功后，文字仍在标准 `commit=` 响应中，状态为 `english-committed`。查询、关闭学习与被拒请求不调用 `get_commit`，不会吃掉应用尚未领取的中文。

## 前端调用顺序

1. 处理正常按键响应时，同时保存对应候选页的 `ActionState`。候选和版本必须来自同一次响应。
2. 打开菜单时，把该状态的 stamp 和候选编号发给 Inspect；用响应中的完整中文、英文及 reason 呈现菜单，并替换为新 stamp。选择非首候选可能改变高亮和显示的组合文本。
3. 用户明确选择输入英文时，用这次 Inspect 的 stamp/index 调用 CommitEnglish；将普通 commit 响应交给既有编辑会话上屏。
4. 学习按钮使用当前 stamp 调用 SetLearning，收到关闭状态后立即禁用英文操作；动画不能延迟这一状态。
5. 失焦、候选变化、翻页或断线时关闭本地菜单。重连必须先取得新会话状态，不缓存或重新播放原英文请求。

服务端仍会独立验证。输入、翻页、选择、选项变化、失焦、活动会话切换和维护使旧目标失效；移除会话会销毁目标。新的会话身份隔离会话重建，新的随机服务身份隔离进程重启。提交前还会重新检查 Rime 实际拼音、光标、页、选中项和 Lua 英文，且在提交前递增版本，避免重复请求再次上屏。这是候选一致性保护，不是本地客户端的身份认证协议。

## 证据与剩余边界

[27 项实际 IPC 结果](../experiments/phase4/results/service-ipc.json)涵盖旧页、返回原页、输入修改、选中变化、开关、分段、待取中文、失焦、会话切换/重建、服务重启、坏报文和两个并发连接。每连接独立缓冲区避免请求/响应混用；每次读取清空旧内容，空消息不会复用上一次动作。

测试仅启动脚本创建的独立服务和客户端，使用固定 Rime DLL、21 条 test-only 词对及隔离数据目录。没有注册输入法，没有向应用注入输入，没有验证可见服务窗口或 TSF 编辑会话。正式候选前端接入、窗口线程调度、x64 TSF 完整构建、断线体验及记事本/浏览器/VS Code 兼容性仍待继续。
