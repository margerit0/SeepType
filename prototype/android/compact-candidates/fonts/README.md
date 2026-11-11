# 轻彩皮肤的字体候选

2026-11-12：键帽字母已改为真正的字体文本，移除截图提取的字母位图。字体尚未接入 Android，本轮用于网页样稿对比。

| 字体 | 样稿用途 | 字重 | 设计判断 |
| --- | --- | --- | --- |
| [Nunito](https://fonts.google.com/specimen/Nunito) | 推荐的英文字母候选；英文释义与功能文字 | 400–500 | 圆头、均衡，适合日常输入 |
| [Quicksand](https://fonts.google.com/specimen/Quicksand) | 英文字母对比；大小写键 `ab / AB` | 500；大小写键为 400 | 几何感更强；小写 `a` 为单层结构，贴合大小写键参考 |
| [Fredoka](https://fonts.google.com/specimen/Fredoka) | 轻彩白色“123 / ABC”切换键专用 | 500 | 圆润、厚实；只嵌入 `123ABC` 六字子集，与字母字体选择独立 |
| [Patrick Hand](https://fonts.google.com/specimen/Patrick+Hand) | 英文字母对比 | 400 | 手写感更明显，字形较窄 |
| [Noto Sans SC](https://fonts.google.com/noto/specimen/Noto+Sans+SC) | 简体中文候选与标签 | 400–500 | 优先保证中文辨认和简体字形一致 |

字形判断为本样稿的设计意见，不代表已识别参考图中的原字体。参考图只提供部分字符，不能据此恢复完整字体的小写、字距、字重和完整字符覆盖。

下载的 WOFF2 样稿子集保存在本目录，下载来源、字符集、字重、大小和 SHA-256 见 [manifest.json](manifest.json)。相同字体字节内嵌到 `concept.html` 的 `@font-face`，独立预览由源稿生成，换肤不需要字体网络请求。样例之外的中文字形会回退到系统字体；原生版本仍需选定正式字体文件并验证完整字符覆盖。

五款字体均采用 SIL Open Font License 1.1，原始版权与许可分别见 [nunito-OFL.txt](nunito-OFL.txt)、[quicksand-OFL.txt](quicksand-OFL.txt)、[patrickhand-OFL.txt](patrickhand-OFL.txt)、[notosanssc-OFL.txt](notosanssc-OFL.txt)、[fredoka-OFL.txt](fredoka-OFL.txt)。默认浅绿皮肤继续使用原来的系统字体。

旧稿使用的 Chiron GoRound TC 以繁体中文为主要目标，作者注明不支持简化字，因此本轮将中文换成 Noto Sans SC；Comic Neue 也不再是本轮轻彩的候选。[Chiron GoRound TC 作者说明](https://github.com/chiron-fonts/chiron-go-round-tc#使用須知)。
