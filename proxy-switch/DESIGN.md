# FlowSwitch 3.3 界面设计

## 方向

以深色网络工作台呈现连接状态：固定左侧导航承载程序分流、代理管理、诊断与工具；内容区域依次放置页面说明、当前状态、明确的切换操作和详细列表。保留原品牌图标；正文界面使用中性炭灰与低饱和灰蓝，减少大面积强调色。

## 设计规范与应用

- [Fluent 2 布局](https://fluent2.microsoft.design/layout)：通过间距区分相关内容，主要间距为 8、12、16、24 像素。导航与内容分区，卡片使用一致的内边距。
- [Fluent 2 排版](https://fluent2.microsoft.design/typography)：标题、数值、正文与说明分级；中文使用系统 Microsoft YaHei UI，字段与数据左对齐。
- [Fluent 2 颜色](https://fluent2.microsoft.design/color)：中性色承担背景与层级；灰蓝色用于主要操作和当前选中项，警告与错误保留文字及独立颜色。
- [Windows 导航](https://learn.microsoft.com/en-us/windows/apps/design/controls/navigationview)：采用稳定的侧边导航位置，页面标题与导航选中项同步。实现继续使用 WinForms，不新增 WinUI 运行依赖。

## 视觉参数

| 角色 | 颜色 / 尺寸 |
| --- | --- |
| 背景 | `#14171C` |
| 面板 | `#1C2027` |
| 输入与次级按钮 | `#282E38` |
| 边框 | `#39424F` |
| 正文 | `#EDF0F5` |
| 次级文字 | `#ADB6C4` |
| 操作强调 | `#ACC8F0` |
| 警告 / 错误 | `#DEC395` / `#E5A6A2` |
| 卡片 / 按钮圆角 | 12 / 8 像素 |
| 程序列表行高 | 36 像素 |

按钮有悬停、按下、选中、禁用和键盘焦点状态。列表使用交替底色、选择标记和单行省略；原右键、搜索、拖放和程序分流事件继续使用。

表格保留滚动条空间，仅在控件外部宽度改变时调整列宽，避免滚动条出现后反复计算尺寸。页面顶部的网络状态仍来自实际读取，不通过装饰颜色假定连接成功。

## 验证

`Test-VisualTheme.ps1` 使用隔离配置及 120 行演示数据，检查导航与标题、三个窗口尺寸、滚动列表和输入控件样式。`Test-SwitchInteraction.ps1` 检查手动切换和界面状态；`Test-WindowsPackage.ps1` 检查编译包与真实 UI 启动。

公开图片只使用演示数据。系统文件选择器和信息提示保留 Windows 原生行为。

## 3.3.1 滚动与缩放

滚动容器保留 ListView / TextBox 的原生内容和滚动范围，将原生滚动条置于裁切区域之外，使用独立灰色滑块。通过 Windows GetScrollInfo 读取真实范围；列表拖动使用 LVM_SCROLL，日志使用 WM_VSCROLL。原生键盘导航、鼠标滚轮、选择与右键菜单继续生效。公开预览的 WM_PRINT 额外绘制同一滑块控件，避免 Windows 打印控件时忽略裁切区域。

布局只保留一套列宽分配，固定预留滚动轨道；单列工作区使用百分比宽度，根布局使用百分比高度。自动刷新不能修改用户网络选择。

参考：[Microsoft GetScrollInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getscrollinfo)。测试使用隔离数据；1.25 / 1.5 倍为控件布局缩放模拟，不修改系统 DPI。

## 3.3.2 绘制时序

列宽以实际 ClientSize 与父视口的较小值为上限；ScaleControl 完成以及 WM_PAINT / WM_NCPAINT / WM_PRINT 之前再次收敛，避免原生列宽在尺寸事件之后变化造成白色横条。回归测试先人为重现这个原生事件顺序，再逐帧调整尺寸和滚动，并读取 WS_HSCROLL 验证。卡片开启 ResizeRedraw，以清除缩放边缘残影。
