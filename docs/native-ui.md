# v0.5 原生候选界面与 x64 整合

2026-11-07。沿用已确认的 v0.5 设计，接续真实 TSF 文本宿主。所有实现保存在 `src/study/windows` 与覆盖层生成器中；原 Weasel checkout 不改动。

## 实现

- `CandidateUi` 由真正的 `CCandidateList` 持有。使用 Weasel 的 DirectWrite 资源和从阶段 3 迁入的 `StudyLayout`，常规五项及工具区为 600×55 DIP，学习关闭后为 600×38 DIP。中英文共用候选命中区域，保留圆角和浅/深色主题，不画左侧深色条。
- 工具区提供上一页、下一页、学习开关和更多。普通点击及无障碍默认动作始终调用中文选词；右键/更多菜单及配置的快捷键才触发经过服务版本验证的英文提交。
- F2 或悬停显示独立完整释义浮层，文本换行，极长释义可滚动；Esc、关闭按钮、候选失效、关闭学习、失焦和断线使浮层关闭。浮层不改变候选条尺寸，也不直接提交英文。
- `StudyMotion` 用实际时钟计算 180ms 翻页和 240ms 学习高度过渡，英文透明度在 160ms 内切换。连续操作替换过渡，开关从当前尺寸反向移动。当前候选立即更新，旧页只参与绘制，不进入命中或无障碍树。系统“减少动画”偏好或应用内减少动态效果会直接完成过渡。
- 同一输入的翻页保留候选视口宽度，工具区不随末页缩短。新拼音可以重新计算短条。后续页或屏幕边缘的候选总宽度超过视口时保留原字号和单行，键盘选中项自动滚入视口，鼠标滚轮可横向查看；不会偷偷改变 Rime 的分页大小。实际多显示器边缘体验仍待桌面验收。
- 当前候选与四个工具按钮提供 MSAA 名称、角色、状态、位置与动作。学习关闭立即移除英文读出；旧页不存在于无障碍树。对象保留期间持有 DLL 引用，窗口销毁后旧对象不能操作新窗口。

## 设置

原生设置窗口提供学习默认状态、18/20px 中文字号、跟随系统/浅色/深色、Ctrl+Shift+Enter 或 Alt+Enter、减少动态效果，以及当前测试词库和许可说明。独立入口为 `study_settings_x64.exe`；组合结束后也可按 Ctrl+Shift+F12 打开。组合期间打开设置会被阻止，保留待输入内容。

偏好为有版本且有长度限制的本地文件，只接受已知字段，以临时文件原子替换。隔离构建必须显式指定设置文件位置；没有位置时不写入用户配置目录。交互宿主与设置启动器共用 `experiments/phase4/runtime/interactive-settings.ini`。其他设置进程的修改在下一次按键处理前同步到已有服务会话，无需重建 Rime 引擎。

## 本轮发现并修复的问题

1. 旧 `SelectCandidateOnCurrentPage` 只修改 Rime 状态，没有返回候选/commit 响应。前端此前移除模拟 VK_SELECT 后无法取得提交文本。现在普通选择在同一次响应内交付中文、状态与 capability，拒绝的选择不消耗待取 commit。
2. Rime 切换过滤器选项会刷新菜单并重置选中项。学习开关现在记录原页和选中项，通过不提交文本的绝对高亮 API 恢复；原拼音、光标和所选中文须保持一致，不能恢复时拒绝此次切换。
3. TSF UI element 的 SetSelection/Finalize 原先只改本地显示或关闭窗口，现在接到同一中文选择路径；候选 BSTR 不再多包含一个结尾 NUL。
4. 普通命中直接使用按下/抬起位置及当前候选版本，不依赖异步更新后的高亮矩形；英文行不会变成英文提交入口。

## 清晰度与高 DPI 修正

2026-11-07 用户附图中的上方候选条，是此前 600×55 像素的预览放大至约 900×82 像素。未遮挡区域与旧图经过双线性放大的结果吻合，平均通道误差仅为 0.068/255；文字已经栅格化后再被插值放大，因此比同屏系统输入法模糊。分析记录见 [截图诊断](../experiments/phase4/results/dpi-preview-diagnosis.json)。

同时修复了真实宿主的 DPI 缺口：文本宿主、原生组件检查程序和设置程序现在通过嵌入的 Per Monitor V2 清单，在创建窗口前确定 DPI 感知。宿主的字号、文档区域和 TSF 光标坐标随 DPI 缩放；收到 DPI 变化时调整窗口和文档布局。候选窗在创建时取得自身 DPI，更新位置时也不再因缺少 owner 而退回 96 DPI。TSF DLL 不修改加载它的应用的进程 DPI 设置。

DirectWrite 的字体、布局和位图使用物理像素，渲染目标的 96 DPI 设置用于保持 1:1 绘制，不能再额外乘一次缩放。分层窗口继续使用灰度抗锯齿。

预览导出现在记录实际 DPI，并分别绘制 96 / 120 / 144 / 192 DPI；150% 为 900×83 像素，200% 为 1200×110 像素。[同尺寸对比页](../experiments/phase4/results/previews-v05/index.html) 用 srcset 按屏幕密度选图，避免将 96 DPI 图片直接拉大。125% 的逐单元像素取整产生 752 像素宽，页面保留其原生尺寸，不强行重采样成 750 像素。

本次 50/50 原生组件检查通过；29/29 TSF/UI 检查在 x64 服务上通过，实际窗口报告 DPI 144、900×83 物理像素，见 [本次 TSF 结果](../experiments/phase4/results/native-v05-dpi-tsf-x64.json)。旧 x86 服务、选词 IPC 和编辑会话报告保留。多显示器移动、真实键鼠以及 DPI 不感知应用仍待桌面兼容性验收，Computer Use 问题继续暂缓。

## 构建与验证

```powershell
./experiments/phase4/build-tsf.cmd
./experiments/phase4/build-service-x64.cmd
python experiments/phase4/verify-native-ui.py
python experiments/phase4/verify-selection.py --service-x64
python experiments/phase4/verify-text-host.py --v05 --service-x64
```

`build-native-x64.cmd` 顺序构建两部分。x64 服务使用已固定下载缓存中的 `.cache/rime-1.13.1/dist/lib/rime.dll`；旧 x86 服务仍可以通过 `build-service.cmd` 构建，供跨架构检查。没有安装、下载、注册或输入设置修改。

- 原生组件：`results/native-v05.json`，50 项布局、回调、浮层、设置文件、动画和 DPI 检查（包括设置保存失败与仅内存偏好）。预览仅取自身 DirectWrite 绘制缓冲区，不是桌面截图。
- 普通选词 IPC：`results/selection-ipc.json` 与 `selection-ipc-x64.json`，针对选词响应、待取中文保护和学习开关页码保持。
- 真实 TSF 集成：`results/native-v05-tsf.json` 与 `native-v05-tsf-x64.json`，通过实际 Windows TSF 和 MSAA 接口调用，检查普通中文、英文快捷键、F2、学习按钮、设置同步、焦点、断线和 DLL 引用生命周期。
- 高 DPI 修正后的 TSF 集成另存 `results/native-v05-dpi-tsf-x64.json`，包含新增的进程/窗口 DPI 和物理尺寸检查，保留前一轮的 27 项报告。
- 原有 16 项编辑会话回归在 x64 服务上通过，另存 `results/tsf-text-host-v05-x64.json`；旧引擎、布局、桌面菜单、IPC、调度和旧文本宿主报告不覆盖。

x64 Rime 库 SHA256 为 `2d8f1bc3737635a11d9fb1bfca4dc9e70533633930a8a0142a81ca879c39c45b`，来自已固定的 `rime-1c23358-Windows-msvc-x64.7z`（归档哈希在阶段 3 依赖锁中）。包内 `version-info.txt` 标记 librime `1c23358`、librime-lua `e3912a4`；实际 Lua 查询与英文动作已通过新 x64 报告验证。

运行交互宿主与设置：

```powershell
python experiments/phase4/start-text-host.py --service-x64
python experiments/phase4/start-settings.py
```

## 验证边界及后续

上述组件和接口调用不是 Computer Use 的物理键鼠验收。审批服务 404 已按用户要求暂缓处理，详见 [问题记录](computer-use-issue.md)。真实键鼠、动画手感、设置窗口操作、Windows 显示缩放切换、多显示器、记事本/浏览器/VS Code、已安装 TIP 的自动路由仍须验收。

本页的阶段 4 隔离宿主继续使用 21 条 test-only 数据。后续已完成 [拾词产品开发预览、标识与安装/卸载脚本](packaging.md)，并将原有 200 条审核稿以明确预览形式打包；人工审核仍为 0/200。分发许可未决项、实际安装/卸载与真实应用兼容性尚未验收；系统安装与输入法注册需要用户另行授权。
