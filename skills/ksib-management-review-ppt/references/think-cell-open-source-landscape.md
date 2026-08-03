# 类 think-cell 开源组件图谱

核验日期：2026-07-31

本文件用于高级图表组件选型，不是依赖清单。任何候选项目进入KSIB生产链前，都必须单独完成许可证、原生编辑性、PowerPoint往返和Golden Deck验证。

## 1. 结论

当前没有一个开源项目同时覆盖以下能力：

- 原生PowerPoint Chart／Table；
- Waterfall、Mekko、Gantt；
- 自动标签避让与差异／CAGR标注；
- Excel或内嵌工作簿数据联动；
- 客户模板复用；
- macOS与Windows稳定往返。

因此，KSIB不应寻找一个“开源think-cell替代品”，而应采用组件化架构：标准原生图表、特殊图表几何、标签布局、模板继承和OOXML QA各自使用最合适的能力。

## 2. 候选组件

| 项目 | 适合借鉴的能力 | 主要边界 |
|---|---|---|
| [pptx-automizer](https://github.com/singerla/pptx-automizer) | 复用PowerPoint模板中的原生Chart／Table／Master；可基于预制模板修改扩展型Waterfall | 高级图表依赖模板；不提供完整Mekko、Gantt和标签避让 |
| [PptxGenJS](https://github.com/gitbrent/PptxGenJS) | 标准原生图表、表格、组合图和内嵌工作簿 | 不提供完整原生Waterfall、Mekko、Gantt或自动标签避让 |
| [OfficeIMO](https://github.com/EvotecIT/OfficeIMO) | .NET原生图表、数据绑定、组合图和表格 | 项目较新；高级图表和PowerPoint往返需单独PoC |
| [OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) | Office对象读写、批量修改和结构QA | 渲染Waterfall不等于能稳定创建可编辑扩展型Waterfall |
| [Instrumenta](https://github.com/iappyx/Instrumenta) | 咨询式对齐、间距、表格格式、样式表、Slide Grader和Slide Library | VBA／PowerPoint运行时能力，不是跨平台图表引擎 |
| [PPT Master](https://github.com/hugohe3/ppt-master) | 图表模板注册、坐标校准和视觉复核流程 | 默认图表路线偏SVG转DrawingML形状，不等于内嵌工作簿Chart |
| [D3-Labeler](https://github.com/tinker10/D3-Labeler) | 标签／锚点避让、边界与引导线交叉惩罚 | 只输出标签坐标，需映射到原生PowerPoint对象 |
| [Nivo](https://github.com/plouc/nivo) | Marimekko几何和图例布局 | Web图形库；需转换为可编辑Shape并保留生成Spec |
| [Frappe Gantt](https://github.com/frappe/gantt) | 任务、时间轴、依赖、进度和里程碑模型 | Web SVG；需转换为原生Shape／Connector |
| [Open XML SDK](https://github.com/dotnet/Open-XML-SDK) | OOXML底层关系、扩展图表和必要补丁 | 工程成本高，不提供审美和自动布局 |

## 3. KSIB建议架构

1. 标准柱线饼散点与表格：优先使用当前已验证的原生构建器；新增候选前先做数据编辑和往返PoC。
2. Waterfall：使用人工定版的原生PowerPoint模板，再由`pptx-automizer`更新数据与标签。
3. Mekko与Gantt：借用Nivo／Frappe的布局模型，输出分组的原生Shape和Connector；同时保存隐藏的`ChartSpec`，数据变化时整图重生成。
4. 自动标签：借鉴D3-Labeler的目标函数，固定随机种子并输出可复现坐标、锚点和引导线。
5. 咨询审美：吸收Instrumenta的间距、对齐、表格样式和Slide Grader思想；不把其宏直接视为跨平台生产依赖。
6. QA：使用OfficeCLI／ShapeCrawler／Open XML SDK思想检查对象类型、工作簿、关系、Connector和Master；最终仍需Microsoft PowerPoint真机往返。

## 4. 进入生产链的最低门槛

- 许可证允许当前分发与使用方式；
- 输出不是整页或整图栅格图片；
- 标准图表保留PowerPoint“编辑数据”入口，特殊Shape图保留逐元素编辑和可重生成Spec；
- 标签在数据更新后不重叠、不越界且结果可复现；
- 通过Golden Deck的OOXML、Visual、语义指纹和PowerPoint人工往返；
- 新依赖经过用户明确批准，并登记在`PACKAGE_MANIFEST.json`和`DISTRIBUTION_NOTICE.md`。
