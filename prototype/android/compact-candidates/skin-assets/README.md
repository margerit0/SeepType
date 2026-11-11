# 轻彩皮肤的矢量图形

- reference.jpg：用户在样稿迭代中提供的参考图。
- [soft-pop-vectors.svg](soft-pop-vectors.svg)：本轮独立绘制的 33 个 SVG symbol，包括 10 个数字、16 个符号、删除、回车、大小写键装饰与工具栏图标。`ime-v-shift-art` 将两颗星芒和两条弧线组合在一个可缩放图层中，替代原先的独立星芒与 CSS 椭圆。

数字和符号采用手工定义的几何路径、圆头笔触和少量断笔，未从参考图描边或提取像素。使用 `currentColor` 适配浅深色；大小写键的亮弧线使用 `--ime-mint-line` 主题变量。字母为真实字体文本，字体候选及许可证见 [fonts/README.md](../fonts/README.md)。

SVG 内容内嵌于 `concept.html`，每个按键用 `<use>` 引用所需 symbol；不加载图片、不依赖位图遮罩。修改 SVG 后需同步源稿中的同名节点、重新生成 `index.html` 并更新截图。根 SVG 是符号定义容器，单独打开不直接显示所有图形，可在交互样稿中查看。

之前截图提取的 `reference-key-ink.png` 图集及映射已移除，`reference.jpg` 仅保留为设计参照。本文件夹仍为网页样稿资源，尚未接入 Android；移植需要根据选定设计转换或绘制原生矢量资源并验证触摸与显示效果。
