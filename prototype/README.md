# 阶段 2 原型：轻量候选条 v0.5

2026-10-31，尺寸修订待确认。用户反馈旧版太大，当前改为接近日常 Windows 输入法密度的横向双行条。旧紧凑型/学习型已保存于 archive/v0.2，不删除已有工作。

## 打开与修改

浏览器直接打开 index.html，无需服务器或安装。ime-candidates.html 为可编辑源；修改后执行 ./build-preview.ps1 重新生成 index.html。生成依赖 Python 和 visualize 1.0.66 的 scripts/render.py，其他机器可用 -Renderer 指定位置；现有生成页仍可直接打开。预览工具不属于正式输入法依赖。

可选本地服务：在此目录运行 python -m http.server 8765 --bind 127.0.0.1，仅服务本机。

## 操作

- 上方选择普通/长英文/无释义/多义词/分段场景，或在拼音框输入内置拼音。
- 箭头选候选，PageUp/Down 或右侧翻页按钮换页，带 180ms / 10px 定向滑动与淡入淡出。同一组合保持条宽，连续翻页不排队。空格、数字、点击候选均输入中文。
- Ctrl+Shift+Enter 输入完整英文；右键候选或右侧更多菜单也可输入英文。
- F2、悬停或菜单查看完整释义。详情为浮层，Esc 或 × 收起，不撑大候选条。
- 右侧“学/关”控制学习模式。立即以 240ms 过渡收起/展开英文空间，标准高度 55px ↔ 38px；英文同时淡出/淡入。拼音、页码和选中项保留，关闭时立即停用英文提交。减少动态效果偏好下不播放动画。
- 提交或 Esc 取消后打开设置，可调字号和英文快捷键。

原型常规五项条约 599×55 CSS px，单行约 38px；窄容器减少页内项数，仍保持一排。原型响应式分页尚未映射为原生功能。外层场景/主题/练习区是测试工具，不属于实际候选窗。

场景：shishi（十项及翻页）、zhishichanquan（完整英文 intellectual property rights）、zhangxiaoming（无释义）、da（打仅选 hit 这一义）、pingguoyinhang（部分组合禁英文，中文后保留 yinhang）。排序为模拟，全部 test-only。

重试只重置当前组合；刷新清空练习文字。偏好可本地保存，练习文字不写入偏好状态。原型回车提交原始拼音，真实输入法行为仍待核验。

## 验证

翻页动画结果：qa-paging.json；学习模式动画记录：qa-motion.json。尺寸与交互在内置浏览器实际操作核查。qa-slim.json 与 previews/slim-* 是 v0.3 历史记录，其中“本轮保持高度”不再适用。

旧 qa-observations.json 与旧 comparison.png 属于 v0.2。不要将原型的浏览器结果当作原生 Rime、Lua、Weasel、TSF、Windows DPI、应用兼容性、安装/卸载或性能测试；这些均未测试。
