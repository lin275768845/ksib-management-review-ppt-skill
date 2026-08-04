# KSIB × Mck 布局与留白系统

本规范以本地已安装的`mck-ppt-design` skill所定义的页面尺寸、固定边距、字号层级、动态多栏、逐版式容量、底栏位置和机读门禁为基础；只吸收其方法与容量合同，不采用其`python-pptx`实现。额外吸收BCG参考模板较低的标题纵向节奏和7种证据主导Layout。KSIB保留Kwai配色、苹方-简、客户Deck正文16／14／12 pt、页眉、可选Subtitle和PowerPoint原生可编辑性工程。

## 目录

1. Storyline到Layout
2. 页面几何与Header
3. Mck间距
4. Mck Layout合同
5. 编辑式视觉规则
6. Takeaway与页脚
7. 既有PPT修改边界

## 1. Storyline到Layout

先读取锁定Storyline中的`proofQuestion`、`evidence`和`visualLogic`，再选择Layout。选择顺序：

1. 这页要证明什么；
2. 最强证据是什么形态；
3. 受众需要比较、观察趋势、理解因果、看到阶段还是作出取舍；
4. 哪个Layout能以最少视觉模块完成证明；
5. 容量是否符合Mck Matrix。

不得从“这页想用三列／想做得丰富”开始。详细映射见`storyline-layout-handoff.md`。

每个canonical Layout都必须解析到Renderer合同。`layout-matrix.json`中的Layout专属`rendererContract`优先；未单独覆盖时继承`global.rendererDefaults`，canonical Renderer名称等于canonical Layout名。内容门禁会逐页输出`storylineId`、provider、canonicalRenderer、允许的fallbackRenderer和原生可编辑要求；任何一项缺失都阻断构建。Release Manifest按`storylineId`绑定实际Renderer；使用fallback必须以版本化usage文件逐页证明该Renderer在合同允许范围内并记录原因。

每个非豁免Layout还必须声明非空`requiredFields[]`，至少包含Action Title与该Layout的主体证据锚点。只写`slideType`和标题、主体为空，或整个`slides[]`为空，均由内容门禁阻断。

Layout不自行决定页面是否可豁免，必须同时满足`slideRole`合同。`cover`只允许`cover`；`toc`、`agenda`、`section`、`sectionDivider`和styleboard只允许`navigator`；`appendixDivider`只允许`appendix`，附录内容Layout除`appendix`外仅接受Matrix登记的`methodology`、`scope_boundary`或`legal_disclaimer`等边界角色；其余Layout只接受Matrix登记的实质内容角色。导航与章节Layout已在Matrix中正式注册，不得用未登记别名或把实质内容塞入导航页以绕过Evidence与语义门禁。

## 2. 页面几何与Header

画布固定为Mck宽屏 `13.333 × 7.5 in`。页面水平几何采用Mck：左边距0.8 in、右边距0.8 in、内容宽度11.733 in。

### 固定Header模式

| 模式 | Action Title | Subtitle | 标题分隔线 | 主体起点 |
|---|---|---|---:|---:|
| 一行标题 | x=0.80, y=0.55, w=11.733, h=0.40 in | 无 | 不使用 | y=1.52 |
| 一行标题＋Subtitle | x=0.80, y=0.55, w=11.733, h=0.40 in | x=0.80, y=0.99, w=11.733, h=0.24 in | 不使用 | y=1.66 |

共用页眉和页脚：页眉橙色竖线x=0.80, y=0.15, w=0.03, h=0.20 in；页眉文字x=0.92, y=0.15, w=11.61, h=0.20 in；页脚分隔线x=0.80, y=6.95, w=11.733 in；Source y=7.05 in；页码x=12.20, y=7.10, w=1.00, h=0.30 in。

上述固定Chrome在同一页面Profile内使用底层EMU精确值，容差为0；颜色、线宽、文本框边距、字体和段落格式同样必须完全一致。Profile唯一枚举见`design-tokens.json.crossSlideChrome.profileIds[]`；合法模式差异不能与同类页面漂移混为一谈。完整合同见`chrome-alignment-contract.md`。

### Header文本框格式

- 页眉统一写作“`III-2｜页面名称`”，使用单一文本框；不得把章节号、竖线和名称拆成多个漂移对象。
- 页眉、Action Title、Subtitle文本框的左／右／上／下内边距全部为0。
- 段前=0、段后=0、单倍行距；禁止继承PowerPoint默认文本框边距或默认段落间距。
- 页眉文本框垂直居中；Action Title和Subtitle顶端对齐。
- Action Title与Subtitle的净距固定0.04 in，约4 px；Subtitle不得远离标题形成第二个标题区。
- Subtitle可选；确需使用时固定14 pt，不使用12 pt，只解释Action Title，不重复标题。
- Subtitle只承担范围、时期、方法、定义、边界或比较框架；使用时必须声明`subtitlePurpose`。若Subtitle包含本页主结论，应并入Action Title或移入主体。
- Action Title只允许一行；Content Gate拒绝换行与超出38个加权字符的标题，OOXML Gate拒绝多个非空段落和`a:br`，最终PNG继续检查字体软换行。
- 内容页标题下默认不绘制横向分隔线；`title-divider`只用于遗留Deck或用户明确批准的特殊模板，不得进入KSIB默认正文Profile。
- Title-only主体起点固定为1.52 in，标题下净留白至少0.50 in；Title＋Subtitle主体起点固定为1.66 in，Subtitle下净留白至少0.35 in。格式合同必须用`bodyStartRoles[]`标记最上方主体锚点。
- 一组连续页面必须共享相同Header模式和绝对一致的Chrome签名，不得逐页手工微调；即使误差小于0.03 in，只要固定角色存在1 EMU或样式差异也必须修正。

## 3. Mck间距

- 实体框中的文字必须从框边缘内缩至少0.15 in。
- 水平动态多栏使用至少0.35 in间距；栏宽按 `(content_width - gap × (n - 1)) / n` 计算。
- 主体内容底部与Bottom Bar之间硬下限为0.15 in，默认0.30 in。大面积填色、深色或高视觉重量模块可在逐页视觉复核中提高到0.35–0.40 in；不得把0.30 in机械理解为所有对象的固定值。
- Bottom Bar位于y=6.10–6.40 in。
- 任何主体对象不得越过x=12.533 in或y=6.95 in。
- 不通过压缩栏距、框内边距或任意降字号塞入超量内容；先按Mck容量矩阵删减。

## 4. Mck与BCG增强Layout合同

每页只选择一个主Layout。Mck `references/layout-matrix.yaml` 是通用真相源；`bcg-layout-patterns.md` 提供证据型增强；KSIB `layout-matrix.json` 负责业务别名、增强Layout与机读校验。

若页面需要“证据→洞见”“阶段打法”“问题→解法”“多模式流程”“分层运营模型”“战略与支撑能力”或“角色演进”，可选择 `bcg-layout-patterns.md` 定义的增强Layout。增强Layout仍使用Mck安全边距、动态间距、正文容量和KSIB视觉系统，不复刻BCG视觉皮肤。

### 左右／对比

- 使用Mck `side_by_side`、`before_after`、`pros_cons`、`two_column_text`或图文Layout。
- 两栏之间至少0.35 in，宽度动态计算。
- `two_column_text`全Deck不超过一页。

### 三列／四列

- 列宽根据可用宽度和0.35 in间距动态计算，不使用固定栏宽。
- 同页各列使用相同的信息层级、标题基线和内容起点。
- 非等宽比例只在信息责任明显不同时使用，并由页面要求明确说明。

### 横向矩阵／表格

- 使用Mck `data_table`、`table_insight`、`checklist`、`scorecard`等能力边界。
- 表头、行高、列宽必须统一；表格内部不再嵌套卡片。
- 行数、栏目数和单元格字符量不得超过Mck Layout Matrix。

### 流程、漏斗、时间轴与垂直步骤

- 使用Mck `process_chevron`、`timeline`、`vertical_steps`、`cycle`、`funnel`或`value_chain`。
- 动态计算节点宽高，禁止固定尺寸硬塞可变数量节点。
- 节点数量和字符预算不得超过Mck Layout Matrix。

### 图表与图文

- 含时间／日期和数值的分析优先使用Mck图表Layout，而不是把趋势写成长段文字。
- 8页以上完整Deck默认至少安排一个图文Layout；用户明确禁止图片时覆盖。
- 图例色块与图表颜色必须一致，不使用文字字符模拟图例色块。

## 5. 编辑式视觉规则

- 使用白底文字、细分隔线、编号和对齐建立结构。
- 无阴影、无3D、无渐变、无玻璃拟态；使用纯色和平面化形状。
- 禁止卡片套卡片、每段文字一个容器和大面积圆角卡片墙。
- 同类页面共享所选Header模式的坐标、标题基线、Subtitle基线、主体起点、来源和页码位置。
- 同类页面必须共享同一个机读Chrome Profile；不得在一个Deck中并存两套“几乎一样”的小矩形、页眉文字、标题区或脚注样式。
- 相邻页面原则上不重复同一Layout；连续论证页面需要同构时可由用户指令覆盖。
- 留白不是空洞面积，而是Mck固定边距、0.35 in栏距、0.15 in框内边距、主体与底栏默认0.30 in净距和清晰层级之间的间隔。
- 结果页优先一张主证据；图表、表格或事实区域应直接标注关键发现，不把全部洞见挪到远离证据的底部。
- 参考Deck先抽取功能类型和内容Schema，再复用几何；不以逐页截图模仿替代Layout判断。
- Kwai橙色代替Mck Navy及多Accent色；苹方-简代替Georgia、Arial和楷体。

## 6. Takeaway与页脚

- Takeaway默认不设置；“至多一条”是上限，不是页面标配。
- 仅当页面需要表达Action Title之外的行动、风险、决策含义或跨证据综合时，才允许设置Takeaway，并声明`takeawayPurpose`。
- `Title＋Subtitle`与`Title＋Takeaway`是两种优先结构；`Title＋Subtitle＋Takeaway`默认禁止，例外必须声明`hierarchyJustification`。
- Takeaway不得复述Title、Subtitle、图表标注或主体洞察区；若Takeaway是更强结论，应提升为Action Title并删除Bottom Bar。
- `cover`、章节／目录、附录、`evidenceInsight`、`singleExhibit`、`issueTree`、`recommendationRoadmap`，以及包含`insight`、`insights`或其他可见Implication Panel的页面不得再设置Takeaway。结构化内容中的单数`implication`是锁定的Storyline语义元数据，本身不等于可见洞察框。
- 4页及以上的内容Deck中，Takeaway默认不超过实质内容页的25%；不足4页时最多1页。连续两页均使用时必须人工复核其必要性。
- Bottom Bar位于Mck y=6.10–6.40 in区间，与主体硬下限0.15 in、默认0.30 in；高视觉重量模块由PowerPoint逐页复核决定是否增加。
- Takeaway必须是一个完整判断，不得拆成“结论＋未解问题”两层。
- Owner、未解问题、角色说明或补充结论不得在Takeaway附近另起模块。
- Source固定在y=7.05 in；页码固定在右下角y=7.10 in，不得逐页漂移。

## 7. 既有PPT修改边界

- 用户要求只调Layout时，不改文字或颜色；字体是否允许归一化必须单独确认。未授权时保留字体族和字号并使用`font-policy preserve`，先识别并统一Header模式、主体起点、来源和页码，再在原主Layout内调整。遗留标题分隔线是否删除属于样式授权，不能由geometry scope静默改变；自动归一化不能顺带复制颜色、字体或段落样式。
- 用户要求保留左右、三列、矩阵或漏斗时，保留其宏观结构，但使用Mck边距、动态间距和容量规则。
- 不为追求版式多样性破坏连续页面的一一对应关系。
- 默认继承Mck的图文版式与版式多样性要求；用户明确禁止图片时覆盖。
- 不继承Mck的Georgia、Arial、楷体、Navy或多Accent色；这些是明确的KSIB品牌例外。
