# KSIB Cross-slide Chrome Contract

本合同约束跨页重复出现的页面框架元素，解决“单页看起来接近、翻页时仍发生跳动”的问题。`Chrome`只指页眉、标题区、分隔线、来源与页码等跨页固定结构，不包含图表、表格或正文内容。

## 1. 适用对象

KSIB默认固定Chrome角色包括：

- `header-accent`
- `header-text`
- `action-title`
- `subtitle`
- `footer-divider`
- `source-footnote`
- `page-number`

`title-divider`只作为遗留Deck或用户明确批准的特殊模板兼容角色；KSIB默认正文Profile禁用。封面、目录、章节分隔、标准正文、标题＋Subtitle和附录可以使用不同Profile；同一Profile内的固定角色必须绝对一致。不得把合法的页面类型差异误判为漂移，也不得用“页面类型不同”掩盖同类页面之间的手工偏移。

## 2. 绝对一致的含义

固定Chrome不使用普通版式容差。合同必须按PowerPoint底层EMU整数比较，默认`geometryToleranceEmu: 0`。同组同角色逐项比较：

- `x`、`y`、`cx`、`cy`与旋转角度；
- 填充类型、颜色、透明度；
- 线条颜色、宽度、虚实、端点；
- 文本框四边内边距与垂直对齐；
- 字体族、字号、粗细、颜色；
- 段落对齐、段前、段后、行距；
- 对象类型与稳定角色名。

任何1 EMU几何差异或受控样式差异均阻断交付。正文对象仍按常规版式与视觉门禁检查，不强制逐对象跨页相同。

## 3. 基准Profile

新建Deck以`design-tokens.json`和Slide Master／Layout中的固定对象为基准。修改既有Deck时：

1. 先从用户认可的参考页抽取Profile；
2. 明确Profile名称、参考页、目标页和受控角色；
3. 为遗留对象名建立别名映射；
4. 只在授权范围内复制几何与格式，保留目标页文字；
5. 修改后同时运行语义指纹、Chrome审计和OOXML QA。

Profile名称只能使用`design-tokens.json.crossSlideChrome.profileIds[]`中的枚举。标准内容页至少区分：

- `content-title-only`
- `content-title-subtitle`
- `appendix-title-only`
- `appendix-title-subtitle`

封面、目录、章节和附录分隔页也要登记各自Profile；同类页面只有一页时只按设计Token和视觉门禁验收，不建立“只有一页”的跨页相等组。同类页面达到两页时必须建立独立相等组。

## 4. 既有PPT归一

使用`scripts/pptx_chrome_normalizer.py`先审计、后写入。默认只读；只有显式`--apply`才生成新PPTX，且不得覆盖输入文件。`--scope geometry`只同步几何与旋转，`--scope style`只同步受控样式，`--scope all`同步两者；用户没有授权颜色、字体或段落样式变化时必须使用`geometry`。归一时必须：

- 唯一识别参考页和目标页的每个受控角色；
- 验证参考对象和目标对象属于同一PresentationML对象类型；
- 精确复制参考对象的几何与受控格式；
- 保留目标页可见文字、数字和字段；
- 不改变页序、正文、图表数据或对象内容绑定；
- 无法唯一识别、角色缺失或对象类型不一致时立即阻断；
- 二次执行结果为零改动。

遗留对象名可通过别名映射迁移，例如：

```json
{
  "header-accent": [
    "header-accent",
    "v283-header-accent",
    "v284-header-accent",
    "v285-header-accent"
  ],
  "header-text": [
    "header-text",
    "v283-header",
    "v284-header",
    "v285-header"
  ]
}
```

归一化默认保留既有对象名，避免破坏对象引用或用户维护习惯；最终格式合同必须用`roleAliases`把遗留名映射到canonical角色。角色迁移需要单独授权、碰撞检查和语义指纹，不由本脚本静默完成。

## 5. 门禁与可视化复核

最终格式合同必须声明跨页一致性组。每组至少包含：

- 唯一`id`；
- `referenceSlide`；
- 显式`slides[]`或Header模式选择器；
- `roles[]`；
- `geometryToleranceEmu`；
- 可选`compareFields[]`，用于只授权geometry或style子集的任务；
- 需要比较的样式属性；
- 必需角色策略与别名映射。

OOXML QA拒绝空角色组、不存在的显式页码、参考页不在组内，以及实际覆盖少于两页的“空通过”。输出每组的参考签名、覆盖页、对象类型、有效垂直对齐、缺失角色和差异清单。任何已纳入`compareFields[]`的固定Chrome差异均为错误，不降级为警告。若同页Action Title与Subtitle发生正面积重叠，输出`format_header_role_overlap`并阻断；若遗留合同显式保留`title-divider`，仍检查其不得进入Subtitle框。

自动门禁之后，仍需生成跨页叠图或快速翻页复核，重点检查：

- 小矩形是否发生宽高或颜色跳动；
- 页眉、标题和Subtitle基线是否跳动；
- 主体起点是否跳动，正文是否至少从1.52／1.66 in开始；
- Source和页码是否漂移；
- Action Title是否保持单行，是否出现字体渲染造成的软换行；
- 默认正文是否误带标题下横线，或遗留横线是否得到明确授权。

自动检查通过不代表光学质量已经通过；但自动检查失败时不得依靠人工“看起来差不多”放行。
