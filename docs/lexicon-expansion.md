# 英语词库扩充：离线准备与外部 API 流程

## 2026-11-08 接续结果：30 项草稿，服务负载阻塞

已读取原会话并继承用户授权：使用 `https://ai.hybgzs.com/v1`，保留 `gemini-3.8-flash-high`，并行加入 `grok-4.7`（`reasoning_effort=high`）。所有词义来自外部 API，代理未编写或替换译文。凭据仅从用户已提供的会话记录注入当前请求进程，没有写入配置或词库。

接续前已有 20 项。本轮发出 5 次生成请求：Gemini 成功 1 次、新增 10 项，另有 504 和 429“上游负载已饱和”；Grok 两次均为 504。累计完成 **30/300 项、3/40 个请求、59 个义项**，全部待审核，剩余 270 项。当前没有在途请求或不确定结果。

跨旧接口和两个模型累计尝试 14 次，其中 3 次成功、11 次失败；累计输出预留上界 57,344 token。服务对 3 次成功返回的用量合计为 prompt 22,808、completion 6,258、total 29,707 token。这些字段按服务原值独立累计，不强行配平；失败未报告用量，金额未知。

静态审核：48/59 个义项的中文和无调拼音命中固定基础词库；11 个义项缺少中文触发词；4 个义项存在源词表大小写差异（例如专名），合计 14 个义项需优先复核。27/30 项至少有一个基础库读音命中。这不代表译文正确、已导入或通过真实输入法验收。

- 合并草稿：`.cache/lexicon-expansion/pilot-results-combined/drafts.jsonl`
- 审核清单：`.cache/lexicon-expansion/pilot-results-combined/review.md` 与 `review-queue.jsonl`
- 汇总：`.cache/lexicon-expansion/pilot-results-combined/summary.json`、`audit.json`
- 可版本化断点：`experiments/lexicon-expansion/results/pilot-progress-20261108.json`

双模型分工保存于 `allocation.json`，已完成请求不重复发送；各模型保留原始响应和独立收据。并行工具计入旧接口的两次尝试，共享原有 60 次尝试及 245,760 输出 token 预留上限，每个模型遇到失败即结束该轮后续调用。服务恢复后，在两个既有 `STUDYIME_*` 变量已配置的进程中续跑：

```powershell
python -B -X utf8 -m tools.lexicon_expand.parallel_run --retry-failed
python -B -X utf8 -m tools.lexicon_expand.parallel_run --execute --retry-failed
python -B -X utf8 -m tools.lexicon_expand.audit_pilot
```

首行只预演并整理本地汇总，不读取凭据或发送请求。重试仍计入总预算，不能换目录绕过额度。42 项离线测试通过，包含分工、断点复用、high 参数和失败后停止；真实服务结果以请求收据为准。当前仅完成试生成的一部分，未进行人工批准、运行时导入、安装或发布。

## 离线阶段记录

2026-11-08。用户已要求开始执行，并明确「需要调用模型的话我可以提供 api key 和 base url，你不要负责生成词库」；随后选择「先完成离线准备，稍后配置 API」。本轮完成来源词表、覆盖统计、可检查的请求清单和外部 API 工具，未调用模型、未新增英文译词。

## 已完成的离线结果

| 范围 | 不同目标词形 | 已有 200 条中的审核稿命中 | 已人工通过且中文可输入 | CC-CEDICT 精确参考命中 | 参考未命中 |
| --- | ---: | ---: | ---: | ---: | ---: |
| IELTS 工作清单 | 5,040 | 86 | 0 | 4,130 | 910 |
| CEFR A1–C2 | 8,845 | 173 | 0 | 6,634 | 2,211 |
| 合并去重 | 10,625 | 174 | 0 | 7,816 | 2,809 |

IELTS 清单取固定 ECDICT 版本的 `ielts` 标签，来源与使用字段见 [来源说明](../data/lexicon-expansion/README.md)。它是可核对的工作范围，不代表官方全集。CEFR 分级独立保存，不推断 IELTS 归属。

参考匹配只比较 CC-CEDICT 斜杠分隔的完整英文义项，并额外允许去掉动词不定式前缀 `to `。不拆解长解释、不推断近义词、不自动选义。未命中可能源于释义写法或词形差异；命中也不意味着可以直接提交英文。每个目标最多携带 8 个原文参考，完整命中数另记。

中文可输入性依据现有中文词库相同的字形/读音过滤规则计算，复得 121,505 个词形/读音记录、120,786 个不同词形。此检查未操作已安装输入法。当前旧有 200 条仍为待人工审核。

20 个场景主题已配置，英语场景清单尚未生成。默认试生成计划包含 **200 个 IELTS 目标与 100 个场景名额，共 300 项、40 个请求**；100 个场景名额分配给 20 个主题。IELTS 优先选尚无现有释义的高频目标，并纳入参考未命中的目标。每项最多保存 3 个独立词义，300 项不等于最多 300 个义项。

## 离线复现

在仓库根目录运行，无第三方 Python 依赖：

```powershell
python -B -X utf8 tools/lexicon_expand/cli.py verify-sources
python -B -X utf8 tools/lexicon_expand/cli.py prepare
python -B -X utf8 tools/lexicon_expand/cli.py plan
```

输出：

- `.cache/lexicon-expansion/prepared/targets.jsonl`：逐个英文目标、源词形、词性、等级、来源行和现有记录。
- `.cache/lexicon-expansion/prepared/coverage.json` / `coverage.md`：分类覆盖统计。
- `.cache/lexicon-expansion/prepared/manifest.json`：源文件、旧词库及构建输入摘要。
- `.cache/lexicon-expansion/pilot/selected-targets.jsonl`：本次选出的现成 IELTS 目标。
- `.cache/lexicon-expansion/pilot/requests.jsonl`：将发送的完整提示词及公开词典参考；场景槽位没有预填英语。
- `.cache/lexicon-expansion/pilot/plan.json`：300 项上限、请求数和输入哈希。

CEFR 原始 CSV 和 IELTS 摘录已随仓库保存。CC-CEDICT 全量快照沿用旧工具的固定缓存；缺失时运行 `python tools/lexicon/pipeline.py fetch-source`，不会自动换成新版。若要重新取得本次上游完整词表并核对摘录：

```powershell
python -B -X utf8 tools/lexicon_expand/cli.py fetch-sources
python -B -X utf8 tools/lexicon_expand/cli.py verify-sources --full
```

`fetch-sources` 只下载锁定的公开原文件，不调用模型。更新来源、旧词库或制表代码后，旧计划会拒绝执行，应重新 `prepare`、`plan`。

## 后续配置外部 API

需要 base URL、模型名，以及名为 `STUDYIME_LEXICON_API_KEY` 的本机环境变量。先把 `data/lexicon-expansion/api.example.json` 复制到 `.cache/lexicon-expansion/api.local.json`，填写地址和模型；key 不写入 JSON。

工具使用 Chat Completions 兼容协议。带 `/v1` 或其他 API 前缀的 base URL 会追加 `/chat/completions`；已提供完整接口地址时保持原路径；没有路径时默认 `/v1/chat/completions`。只接受不带用户名、密码、查询参数或片段的 HTTPS 地址。

如果服务不接受 JSON 模式，可将 `response_format` 改为 `none`，返回内容仍必须通过相同 JSON 校验。可配置 `max_tokens` 或 `max_completion_tokens` 参数名称；不支持温度参数的模型可将 `temperature` 设为 `null`。兼容性尚未连接实际服务验证。

可在 PowerShell 通过隐藏输入设置当前用户环境变量，避免把 key 写在命令文字中：

```powershell
$studyImeSecret = Read-Host 'StudyIME API key' -AsSecureString
$studyImeCredential = [pscredential]::new('StudyIME', $studyImeSecret)
[Environment]::SetEnvironmentVariable('STUDYIME_LEXICON_API_KEY', $studyImeCredential.GetNetworkCredential().Password, 'User')
Remove-Variable studyImeSecret, studyImeCredential
```

工具先读取进程环境；Windows 上缺失时，只读取当前用户环境中同名的这一项，支持在 Codex 启动后配置。不会枚举其他凭据，也不会输出 key。配置完可检查存在性并预演：

```powershell
python -B -X utf8 tools/lexicon_expand/cli.py config .cache/lexicon-expansion/api.local.json --check-key
python -B -X utf8 tools/lexicon_expand/cli.py generate --config .cache/lexicon-expansion/api.local.json
```

`config` 不连接网络；`generate` 默认只预演，不读取 key、不发送请求。收到用户的后续 API 配置与执行安排后，实际调用使用：

```powershell
python -B -X utf8 tools/lexicon_expand/cli.py generate --config .cache/lexicon-expansion/api.local.json --execute
```

本轮未执行上述实际调用命令。默认最多 300 项、累计 60 次请求尝试、累计预留 245,760 个输出 token；初始 40 个请求按每次 4,096 上限计算，预留输出上界为 163,840 token。这是请求上限，不是实际用量或金额估计，输入 token 也可能计费。实际响应的 token 用量另行累计；没有服务商价格时不估算金额。

## 草稿、失败与续跑

实际生成的输出默认为 `.cache/lexicon-expansion/pilot-results/`：

- `run.json`：计划与非敏感接口配置的绑定信息。
- `attempts/`：每次请求的启动、完成或失败记录；先持久化尝试，再发送请求。
- `responses/`：原始服务返回及摘要；包含 key 的意外回显会被拒绝保存。
- `drafts.jsonl`：通过结构校验的 v2 草稿，全部为 `pending`，没有自动选定主词义。
- `summary.json`：完成、未解决、失败、预留输出上限及服务返回的实际用量。格式不合格或被截断的响应若提供用量，也会记入。

每个草稿保留英文词形、词汇包、CEFR 标签、独立的 `senses`、词性、中文触发词、带调拼音、中文义项说明、来源和模型请求记录。显示/提交英文分别保存，当前要求两者一致。模型无法写入审核者或把状态设成人工通过。遗漏目标、替换目标英文、虚构引用 ID、截断英文或错误结构都会使整个请求不进入草稿文件。

正常续跑使用相同命令与输出目录，已完成且原响应校验一致的请求直接复用。不同计划、模型或接口配置不能混用同一输出。失败后先查看本地记录；有明确需要时以 `--retry-failed` 重试失败请求，崩溃造成无法确认结果时以 `--retry-uncertain` 重试。重试也计入累计次数与输出预算；程序不自动重试收费请求。输出目录有进程锁，防止同时运行导致重复调用。

当前阶段没有提供 v2 的正式发布或自动导入运行时命令。后续应先评估首批实际输出、完成审核与主词义选择，再接入预览包、补充缺失中文触发词，并验证真实候选和英文提交。已有 v1 正式导出的人工审核要求仍有效。

## 验证

```powershell
python -B -X utf8 tools/lexicon_expand/verify.py
```

结果记录在 `experiments/lexicon-expansion/results/offline-checks.json`。检查范围包括来源摘录、真实词表覆盖、确定性请求、目标/引用/拼音校验、多义结构、凭据隔离、失败用量、调用上限、进程锁和断点续跑。外部传输全部使用隔离的模拟响应；测试用词从已有审核数据取，不写入产品数据。它不构成实际服务连通性、译文质量或原生输入法验收。
