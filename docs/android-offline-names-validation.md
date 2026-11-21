# Android 离线专名：加词前后设备验证

2026-11-21。由与原会话分离的 `codex/android-offline-names` worktree 完成；基线使用 `2322bca` 加交接文件中的原有未提交快照，不是干净 HEAD。没有提交或合并原会话的改动。

**设备条件：** 独立 WSL2／KVM AOSP Android 11（API 30、x86_64）模拟器，1080×2340、440 dpi。测试期间开飞行模式并关闭 Wi-Fi／移动数据。引擎测试为 Kotlin → JNI → Rust → Rime → Lua，每轮使用独立用户词典并关闭学习；UI 使用 Debug APK、默认浅色皮肤、1× 字号、竖屏折叠候选条和合成 EditText，不预先滚动或展开候选。名次为引擎全局候选顺序，和折叠 UI 可见性分开判定。

| 阶段 | 实际部署资源版本 | 基线样本 |
| --- | --- | --- |
| 加词前（Windows 中文快照 124,066 条） | `96e911430fa2b76448e0` | 36 个引擎探针，9 次折叠候选采集 |
| 12 条小样 | `b7c1380c3a70e79a9578` | 36 次完整提交通过；3 个名称 × 3 个方案折叠 UI 通过 |
| 381 条首版 | `7feb4ef9bf4241e80d54` | 同一组探针复测通过，扩量后关键排序不变 |

## 候选对照

下表列实际前三项（钟离列到第 4 项），键序为**全拼 / 自然码 / 小鹤**。除表内说明外，三种方案在所列名次一致；括号里的名次是**目标词**而非首项的名次。「未见」只指探针的搜索范围。实际完整首张引擎候选页及折叠 UI 内容见 [结构化对照](android-offline-names-comparison.json)。

| 名称 | 三种键序 | 加词前候选 | 381 条首版候选 |
| --- | --- | --- | --- |
| 芙宁娜 | `funingna` / `funyna` / `funkna` | 阜宁那、阜宁、抚宁（未见（最多 8 页）） | 芙宁娜、阜宁、抚宁（第 1 位） |
| 钟离 | `zhongli` / `vsli` / `vsli` | 中立、重力、重利（未见（最多 8 页）） | 中立、重力、重利、钟离（第 4 位） |
| 那维莱特 | `naweilaite` / `nawzllte` / `nawwldte` | 那为莱特、那、拿（未见（最多 8 页）） | 那维莱特、那、拿（第 1 位） |
| 纳西妲 | `naxida` / `naxida` / `naxida` | 纳西大、纳西、纳溪（未见（最多 8 页）） | 纳西妲、纳西、纳溪（第 1 位） |
| 雷电将军 | `leidianjiangjun` / `lzdmjdjp` / `lwdmjljy` | 雷电将军、雷电计、雷电（第 1 位）；第三项以全拼为准 | 雷电将军、雷电计、雷电（第 1 位）；第三项以全拼为准 |
| 原神 | `yuanshen` / `yruf` / `yruf` | 元神、渊深、元（未见（最多 8 页）） | 元神、渊深、原神（第 3 位） |
| 丹恒 | `danheng` / `djhg` / `djhg` | 但哼、但、单（未见（最多 8 页）） | 丹恒、但、单（第 1 位） |
| 三月七 | `sanyueqi` / `sjytqi` / `sjytqi` | 三月其、三月、三（未见（最多 8 页）） | 三月七、三月、三（第 1 位） |
| 流浪地球 | `liulangdiqiu` / `lqlhdiqq` / `lqlhdiqq` | 流浪地球、流浪、六（第 1 位） | 流浪地球、流浪、六（第 1 位） |
| 哪吒之魔童降世 | `nezhazhimotongjiangshi` / `nevavimotsjdui` / `nevavimotsjlui` | 哪吒指模同江市、哪吒、呢（未见（最多 8 页）） | 哪吒之魔童降世、哪吒、呢（第 1 位） |
| 千与千寻 | `qianyuqianxun` / `qmyuqmxp` / `qmyuqmxy` | 谦语谦逊、谦语、前（未见（最多 8 页）） | 千与千寻、谦语、前（第 1 位） |
| 星际穿越 | `xingjichuanyue` / `xyjiiryt` / `xkjiiryt` | 星际穿越、星际、星级（第 1 位） | 星际穿越、星际、星级（第 1 位） |

- **芙宁娜：** 加词前首项是「阜宁那」；首版三种方案都是第 1，折叠首屏不滚动就能直接点选并提交「芙宁娜」。长按打开详情、明确选择「输入 Furina」可提交完整英文；英文不是由 Wikidata 英文标签推断。
- **钟离：** 加词前三种方案均未找到该候选，首选实际为「中立」。首版顺序均为「中立、重力、重利、钟离」，折叠首屏可点选并提交「钟离」；「重力」的原有 `gravity` 释义仍显示。
- **那维莱特：** 加词前首项是「那为莱特」；首版三种方案第 1，首屏可点选提交完整中文，无新增英文。
- **流浪地球、星际穿越、雷电将军：** 加词前就已能在引擎第 1 位提交完整文本，尽管快照缺独立词条；不把静态缺词当作设备缺候选。扩量后保留第 1 位。

## 通过与尚未验证

| 检查 | 证据与范围 |
| --- | --- |
| **模拟器 · 新词引擎覆盖** | 381 个词 × 3 方案 = **1,143 次**，均选中、提交完整中文并清空组合。最靠后名次全拼 36、自然码 11、小鹤 11；不能据此说所有词都在首屏。 |
| **模拟器 · Debug APK UI** | 「芙宁娜」「钟离」「那维莱特」× 三方案都在折叠条实际可点选，完整提交。`Furina` 在三方案都可显示及显式提交。其他词未逐条做 UI 点选。 |
| **模拟器 · 既有行为** | 702 个既有三方案词库用例和 44 项原生保护/学习/资源修复检查通过；Debug APK 的 21 项原生编辑器交互检查通过。Rime 仍共用 `cedict_study` 用户词典，未执行清空操作。 |
| **主机 · 单表刷新** | 在临时生成目录只增一条合成 TSV 行，禁用网络请求，确认无变化时不重建、有变化时生成资源版本 `b7c1380c3a70e79a9578` → `4fcd62f53b4f0e66541e`。Windows 词典原字节和摘要不变；合成条目不在发布词表中。实际模拟器用安装更新加载了小样和首版两个不同摘要。 |
| **模拟器 · Release APK UI** | 安装同证书签名的首版 Release APK，用独立 Debug 编辑器跑了 21 项通用编辑器/候选交互并通过；未在 Release APK 重跑整套专名点选矩阵。 |
| **Release APK 静态** | 构建、签名及 ABI/原生依赖/ZIP 对齐校验通过。182 个版本化文件 SHA-256 与清单相符，且字节与用于设备测量的 Debug APK 一致。Windows 字典与 Lua 原字节保留，无 `android.permission.INTERNET`；与原开发 Release APK 的签名证书一致。 |
| **未覆盖** | 未用实体手机、arm64 设备或其他屏宽/皮肤跑专名 UI；未做全部 55 组同音冲突的旧首选对照；未验证真实既有用户词频跨版本升级或做人审发布审批。 |

Release APK SHA-256：`3bc6da9606f3c107930de707d0b95f316a531c81d780729e6298fa9299b8ec6b`。首版 TSV SHA-256：`57263402ffab47b91f5db6d9a771ccc31cf2677d4bba3f151b61f6610ff0c243`。

## 复测

在独立测试设备上用已配置的工具链构建 Debug APK 和 Android 测试 APK，然后执行（序列号换成自己的测试设备）：

```powershell
python -X utf8 tools/android/build.py apk --debug
python -X utf8 tools/android/build.py tests
python -X utf8 tools/android/run_device_checks.py install --serial 127.0.0.1:5587
python -X utf8 tools/android/run_device_checks.py offline-names-engine --serial 127.0.0.1:5587
python -X utf8 tools/android/run_device_checks.py offline-names-ui --serial 127.0.0.1:5587
python -X utf8 tools/android/run_device_checks.py offline-names-coverage --serial 127.0.0.1:5587
```

`--names-baseline` 仅供未接入专名的基线 APK（测试 APK 可以用相同探针重建）；勿在并行会话的工作区切换/撤销已有改动以复现它。首版 TSV 前 12 条为小样。原始 JSON、截图和 APK 摘要留在当前工作树的 `.cache/android/evidence`。
