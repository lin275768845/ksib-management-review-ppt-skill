# KSIB Format Engineering Contract

本合同把“看起来统一”和“对象可选中”改造成可验证的PowerPoint工程要求。它不替代逐页视觉复核，也不改写Storyline；它只验证最终`.pptx`中的角色对象、几何、层级和原生对象类型。

## 1. 何时使用

- 新建或重制Deck：必须在构建前建立`ksib-format-contract/1.0`，最终OOXML QA用同一合同验收。
- `format-only`：必须先保留输入语义指纹，再建立只覆盖授权范围的格式合同；合同可以只覆盖页眉、标题、Subtitle、分隔线、来源和页码，不得借合同改变文字、颜色或加粗语义。
- 用户提供原生模板：合同坐标从模板抽取，不能强行套用KSIB默认坐标；但对象角色命名、层级去重和原生可编辑性仍适用。

参考模板见`golden-deck-format-contract.json`。

## 2. 对象角色命名

需要被机器验收的对象必须在PowerPoint选择窗格中使用稳定英文角色名：

| 角色 | 含义 |
|---|---|
| `header-accent` | 页眉橙色竖线 |
| `header-text` | 单一页眉文本框 |
| `action-title` | 本页唯一主结论 |
| `subtitle` | 范围、时期、方法、定义、边界或比较框架 |
| `title-divider` | 标题区分隔线 |
| `footer-divider` | 页脚区分隔线 |
| `takeaway` | 标题之外的行动、风险、决策含义或跨证据综合 |
| `source-footnote` | 数据来源或脚注 |
| `page-number` | 右下角页码 |
| `chart-main` | 主原生图表 |
| `table-main` | 主原生表格 |

允许数字后缀，例如`page-number-2`；同一页的单例角色不得重复。流程节点、标签和普通正文可以使用项目自定义名称，但应保持稳定、可读且不含业务隐私。

## 3. 合同结构

```json
{
  "schemaVersion": "ksib-format-contract/1.0",
  "deck": {
    "widthIn": 13.333,
    "heightIn": 7.5,
    "toleranceIn": 0.03,
    "requireAllSlides": true
  },
  "roleGeometry": {},
  "headerModes": {},
  "nativeEditability": {
    "allowFullSlideRaster": false,
    "fullSlideRasterCoverageThreshold": 0.9,
    "chartDataPolicy": "native-data-required",
    "slideNumberPolicy": "field-required"
  },
  "hierarchy": {
    "roles": ["action-title", "subtitle", "takeaway"],
    "similarityThreshold": 0.72
  },
  "takeawayPolicy": {
    "maxContentSlideRatio": 0.25,
    "maxConsecutive": 1,
    "requireNamedBottomTextBlocks": true,
    "bottomBandYIn": 6.2,
    "allowedBottomRoles": ["takeaway", "source-footnote", "page-number"]
  },
  "crossSlideEqualityGroups": [],
  "slides": []
}
```

### `roleGeometry`

定义跨页稳定角色的对象类型、坐标和文本框边距。例如：

```json
{
  "header-text": {
    "objectTypes": ["textBoxes"],
    "geometry": {"x": 0.92, "y": 0.15, "w": 11.61, "h": 0.2},
    "zeroTextMargins": true
  }
}
```

实际`x/y/w/h`任一偏差超过`toleranceIn`即失败。该容差只用于单页对象相对设计Token的常规几何校验；固定Chrome的跨页一致性必须使用`crossSlideEqualityGroups.geometryToleranceEmu: 0`。`zeroTextMargins`按DrawingML有效值判断；属性缺失时使用Office默认非零边距，因此不能通过。

### `crossSlideEqualityGroups`

定义同类页面之间必须绝对一致的固定Chrome。示例：

```json
{
  "id": "content-common-chrome",
  "referenceSlide": 6,
  "slides": [2, 3, 5, 6, 8, 9],
  "roles": [
    "header-accent",
    "header-text",
    "source-footnote",
    "page-number"
  ],
  "geometryToleranceEmu": 0,
  "compareFields": [
    "geometry",
    "rotation",
    "objectType",
    "fill",
    "line",
    "textMargins",
    "verticalAlignment",
    "font",
    "paragraph"
  ],
  "groupByHeaderMode": false,
  "roleAliases": {
    "header-accent": [
      "v283-header-accent",
      "v284-header-accent",
      "v285-header-accent"
    ],
    "header-text": [
      "v283-header",
      "v284-header",
      "v285-header"
    ]
  }
}
```

字段规则：

- `id`与`roles[]`必填；
- 使用显式`slides[]`，或使用`slideSelector.headerModes[]`／`slideRoles[]`选择页面；
- `referenceSlide`指定基准页；如果基准页不在某个Header Mode分区，则使用该分区第一张页；
- `geometryToleranceEmu`默认0；固定Chrome不得改回英寸级宽松容差；
- `compareFields[]`可选；默认比较全部字段。仅获授权改位置时可写`["geometry","rotation","objectType"]`，不能借此宣称颜色或字体也已统一；
- `groupByHeaderMode`默认`true`，防止一行标题、标题＋Subtitle和两行标题互相误比；只有页眉小矩形、页眉文字、Source和页码等确实跨模式共用的角色才设为`false`；
- `roleAliases`中的值是遗留对象的完整角色名，不是模糊片段；每页每个canonical角色必须唯一命中。

跨页签名使用原始EMU比较`x/y/w/h`，并比较PresentationML对象类型、旋转、填充、线条、文本框边距、有效垂直对齐、字体和段落格式。任一差异分别输出`format_cross_slide_geometry_drift`、`format_cross_slide_object_type_drift`或`format_cross_slide_style_drift`；角色缺失或重复输出`format_cross_slide_role_count_invalid`。空角色、缺页、参考页不在组内或有效覆盖少于两页直接判为合同错误，不能“无比较即通过”。Inventory同时登记每组覆盖页、基准页、角色对象和签名哈希。

修改既有PPT前先使用`pptx_chrome_normalizer.py`进行只读审计。只有用户授权统一格式后才使用`--apply`写入新副本；完整流程见`chrome-alignment-contract.md`。

### `headerModes`

每张内容页只能选择一个固定Header模式。模式声明必需角色、禁用角色和覆盖几何：

- `title-only`：Action Title，无Subtitle；
- `title-subtitle`：Action Title＋Subtitle；
- `title-two-line`：两行Action Title，默认无Subtitle；
- `none`：封面或纯分隔页。

### `slides[]`

逐页声明：

- `slide`：从1开始的实际演示顺序；
- `slideRole`：`cover`、`navigator`、`content`、`appendix`等；
- `headerMode`；
- `requiredRoles[]`、`forbiddenRoles[]`；
- `nativeObjectMinimums`／`nativeObjectMaximums`。
- 流程页可声明`connectorPolicy.requireAttachedBothEnds`和`requireArrowhead`，避免把普通直线或未吸附连接器误当成可编辑流程。

原生对象类型包括：

- `textBoxes`
- `shapes`
- `connectors`
- `pictures`
- `tables`
- `charts`
- `smartArt`
- `groups`
- `graphicFrames`

如果一页的证明形态是图表，合同应写`"charts": 1`；如果是表格，应写`"tables": 1`。这样即使页面截图“看起来一样”，把原生图表或表格替换成图片也会失败。

### 原生编辑性策略

- `chartDataPolicy: "embedded-workbook-required"`：所有Chart必须绑定内嵌Excel工作簿；适合需要通过PowerPoint“编辑数据”维护的客户交付。
- `chartDataPolicy: "native-data-required"`：允许内嵌工作簿、原生literal数据或带缓存的数据引用，但拒绝没有数据语义的空Chart。只适合构建器PoC或明确接受手工复核的场景。
- `slideNumberPolicy: "field-required"`：名为`page-number`的对象必须包含`slidenum`字段；`"static-allowed"`只用于构建器能力验证，正式多页客户Deck应优先动态页码或母版页码占位符。

OOXML QA会在`chartDataByPart[]`中区分`embeddedWorkbook`、`nativeLiteral`、`cachedReference`与`unknown`。原生Chart不等于数据可维护：如果只有`nativeLiteral`，必须在PowerPoint中实际执行“编辑数据—改单元格—撤销”，未通过前不得宣称图表数据真正可编辑。

## 4. 强制阻断项

以下任一项出现时，不得交付：

1. 必需角色缺失、重复或对象类型错误；
2. 页眉、Action Title、Subtitle、分隔线、来源或页码超出几何容差；
3. 同一Chrome Profile中的固定角色存在1 EMU几何差异，或旋转、填充、线条、文本边距、字体、段落格式不一致；
4. 同页Action Title与Subtitle发生正面积重叠，或标题分隔线进入Subtitle框；
5. Header／Title／Subtitle文本框保留Office默认内边距；
6. Action Title、Subtitle、Takeaway存在包含关系或高相似复述；
7. Takeaway超过内容页预算或连续滥用；
8. 底部结论带未命名为`takeaway`，用通用文本框名称绕过层级与稀缺性检查；
9. 图表页没有原生Chart、表格页没有原生Table、流程页没有原生Connector；
10. 连接器未同时吸附起终节点、箭头端点缺失，或图表数据模式不满足项目策略；
11. 正式Deck要求动态页码但`page-number`不是`slidenum`字段或母版页码占位符；
12. 全页图片覆盖率达到阈值，构成栅格化伪PPT；
13. 普通用户对象保留移动、缩放、选择、文字编辑或组合锁。

标准Notes Placeholder是PowerPoint内部占位对象，不属于客户页面内容；其系统锁不作为普通对象锁报错。用户自行添加到Notes页的普通对象仍必须通过锁检查。

## 5. 命令

```bash
"$PYTHON" scripts/ooxml_qa.py final.pptx \
  --theme-policy ksib \
  --font-policy ksib \
  --format-contract work/format-contract.json
```

`format-only`且用户未授权改变主题或字体时：

```bash
"$PYTHON" scripts/ooxml_qa.py final.pptx \
  --theme-policy preserve \
  --font-policy preserve \
  --format-contract work/format-contract.json
```

OOXML报告的`inventory.formatContractSlides[]`会逐页输出Header模式、原生对象数量、连接器吸附／箭头计数、动态页码字段计数、全页图片数量和实际存在的层级角色；`inventory.crossSlideEqualityGroups[]`输出跨页Profile、基准页、覆盖页、角色对象和签名哈希；`inventory.chartDataByPart[]`输出图表数据模式。合同SHA256同时进入报告，便于发布清单绑定当前检查规则。

## 6. Golden Deck回归

每次修改Renderer、主题、对象命名、OOXML清理或格式门禁后，用同一份6页Golden Deck回归：

1. 封面；
2. 单一原生图表；
3. 原生表格；
4. 左右对比；
5. 原生流程与Connector；
6. 高密度附录表。

基准Deck的六页均不使用Takeaway：这些页面的Action Title已经完整表达结论。Takeaway的合法例外由内容门禁与单元测试覆盖，不为了“测一个框”而在Golden Deck中制造冗余层级。

必须同时通过：

- 结构化合同校验；
- OOXML与格式合同校验；
- 原始PPTX→构建器回读→再导出后的语义指纹比较；
- 全页PNG逐页视觉复核；
- PowerPoint真实文字／颜色／加粗／字体／填充／组合／图表数据／表格编辑操作。

Golden Deck是回归夹具，不是客户模板；不得把其中的示例业务内容带入真实项目。
