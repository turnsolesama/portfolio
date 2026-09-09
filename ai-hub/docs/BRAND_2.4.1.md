# AI Hub 2.4.1 图标

本轮使用内置图像生成工具产生三枚 AI Hub 候选，并与 Codex Switcher 的三枚候选一起比较。

| 候选 | 概念 | 取舍 |
| --- | --- | --- |
| A | 开放式资产盒 | 有立体感，但内部结构较复杂 |
| B（选用） | 带微光标记的叠层资产卡 | 资料库含义直观，64px 下层叠关系清楚 |
| C | 四片环绕的几何开口 | 轮廓简洁，但容易被理解为摄影工具 |

选用 B 与切换器的双箭头图标搭配。深色圆角底、冰蓝主体、真实透明边缘。没有使用其他软件的商标。

## 生成提示词

使用内置 `image_gen`，未调用 CLI 或第三方图像 API。选定方案提示词：

> Generate ONE finished app icon for AI Hub, local creative asset library. Square canvas 1024x1024, no text letters watermark, no presentation/mockup/grid. Direction B: exceptionally refined, bold minimal three-layer floating archive stack, each layer a thick rounded diamond slab, aligned vertically with clean clear negative gaps. Top slab contains a simple inset four-point glint, large and geometric. Semi-matte porcelain ice-blue with gentle teal edge, graphite rounded-square base with equal 7% transparent margin. Front-on mild isometric elevation, little perspective. Simple vector-like silhouette with subtle tactile bevel, not photoreal metal, no tiny details, no neon bloom. Strong readable shape at Windows 16/24/32px, professional restrained creative tooling identity. Genuine transparent background outside rounded tile. The emblem fills 67% of the tile. Balanced, memorable, clean.

## 文件与接入

- `frontend/brand-2.4.1.png`：256px 的透明 PNG，用于侧栏与 favicon。
- `frontend/brand.ico`：16/24/32/48/64/128/256 多尺寸 Windows ICO，同时嵌入 EXE 与窗体图标资源。
- `frontend/brand-2.4.1.ico`：同内容的版本化图标，用于本机快捷方式避开旧文件名缓存。
- `desktop/Program.cs`：程序集版本统一为 2.4.1.0；后台 API 协议仍沿用 2.3。

仅进行图标尺寸转换与 ICO 编码，保留生成图像及 alpha，不做抠图或重绘。原始候选在本机项目 artwork 目录保留，发行包只包含实际使用的图标，不包含私人图库。

## 验证与限制

已查看选定图标的 64px 实际预览并确认轮廓；ICO 尺寸、透明通道与 EXE 嵌入资源按构建记录校验。桌面构建的 30 项检查通过，包含隔离路径冷启动、复用后台、无控制台启动。沿用本版前端功能检查。

已打开的旧进程仍可能使用旧图标；关闭后重开应用即可加载新图标。不清空系统图标缓存，不重启 Explorer，不关闭其他程序。Windows 任务栏的实际刷新状态未做本轮截图验收。
