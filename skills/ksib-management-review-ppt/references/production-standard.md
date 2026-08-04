# KSIB 咨询与管理汇报 PPT 产出标准

## 1. 适用范围

适用于快手／Kwai海外电商管理者任命述职、工作回顾、市场与竞争研究、渠道与价格分析、消费者洞察、战略建议及客户沟通页面。默认场景严肃、信息密度高、受众快速扫读，且交付物必须在Microsoft PowerPoint中原生可编辑。

新建、合并、删页、重构或改写论证时，必须先取得`linzhe-mbb-storyline`输出的锁定Storyline合同；只改格式时冻结内容，不触发故事线改写。

含事实、数据或外部判断时，必须同时建立`evidence/evidence.json`：Source经过核验，派生指标登记Calculation，客户可见结论登记Claim，页面只通过`claimIds[]`引用。品牌份额和品牌集中度的分母必须包含未识别品牌成交额。

正式多页Deck在锁定前必须建立Deck级`argumentTree`：`governingThought`拆为2–4个支撑论点，每张核心内容页及其Claim必须且只能归入一个Pillar。逐页顺畅不能替代完整的金字塔支撑关系。

## 2. 视觉系统

- 画布：Mck标准宽屏 `13.333 × 7.5 in`，16:9，白底。
- 主字体：macOS使用 `PingFang SC`，PowerPoint显示“苹方-简”；Windows使用 `Microsoft YaHei`。中文、英文和数字使用同一字体族。
- Mck字号层级：封面44 pt；章节／目录28 pt；封面副标题24 pt；内容页Action Title 22 pt；Sub-header 18 pt；Takeaway 16 pt；来源和页码9 pt。
- KSIB正文覆盖：客户Deck正文使用16／14／12 pt。16 pt用于少量高层正文，14 pt用于主要正文与内容页Subtitle，12 pt用于密集正文；10 pt只用于来源、脚注或经批准的高密度附录。
- 内容页Action Title：22 pt、粗体、结论句，只允许一行；超出单行容量时必须改写标题或拆页，不得缩字号或启用两行Profile。该门禁不限制封面主标题或章节名称的自然断行，但这些页面仍须通过视觉复核。
- 主色：Kwai Orange `#FF4906`；深橙 `#D83D00`；浅橙 `#FFF7F3`；浅橙分隔线 `#FFDBCD`。
- 对比辅色：`#006B8F`；浅色面为`#E6F3F7`。只用于真正的对照、反例或第二关键证据，不用于装饰。
- 正文：`#1F2329`；次级文字：`#646A73`；分隔线：`#E5E6EB`；白色：`#FFFFFF`。
- 橙色只用于Action、关键结论、主数字、当前节点和结构锚点，不做随意highlight。

### 2.1 Theme Color Contract

颜色的机读真相源为`theme-color-contract.json`，执行说明为`theme-color-contract.md`。Renderer只能按Token用色：主色阶负责同一语义家族的层级与顺序；对比辅色负责真正对照；浅灰`#D9DCE1`只表示“其他”、基线、参考、弱化或较差对比；深灰只用于文字与必要线条，不得作为默认图表填充。正向、负向和预警色只有在内容本身存在对应状态语义时才可使用。

每页必须生成`ksib-theme-usage/1.1`登记。最终PPTX完成最后一次保存后，必须用`extract_pptx_theme_colors.py`生成`ksib-pptx-color-inventory/1.0`，并把每个可见实际颜色绑定到一个语义元素和Token。对象名不稳定、主题色无法解析、实际色未登记／重复登记、声明Token与成片Hex不同、清单与当前PPTX哈希不同，均阻断交付。`single-focus`、`sequential`、`two-way-comparison`、`status-diverging`与`categorical-limited`必须选择其一；无数据页使用`no-data`。Format-only未获样式授权时只审计并保留原颜色，不得自动套用新色板。

## 3. Header、标题与Subtitle合同

Mck原规范没有定义内容页Subtitle，BCG参考模板也主要使用Title-only页面。BCG模板的内容页标题基线约为y=0.68 in，明显低于本skill旧版y=0.40 in；本skill因此将Action Title统一下移至y=0.55 in，同时保留页眉与Mck 0.8 in安全边距。内容页标题下默认不使用横向分隔线，主体进一步下移，形成更开放的咨询页Header。每页只能选择以下两种Header模式，不得逐页微调：

| Header模式 | Action Title | Subtitle | 标题分隔线 | 主体起点 |
|---|---|---|---:|---:|
| 一行标题 | x=0.80, y=0.55, w=11.733, h=0.40 in；22 pt | 不使用 | 不使用 | y=1.52 in |
| 一行标题＋Subtitle | x=0.80, y=0.55, w=11.733, h=0.40 in；22 pt | x=0.80, y=0.99, w=11.733, h=0.24 in；14 pt | 不使用 | y=1.66 in |

三种模式共用的页眉与页脚坐标：

| 元素 | x | y | w | h | 字体与段落 |
|---|---:|---:|---:|---:|---|
| 页眉橙色竖线 | 0.80 in | 0.15 in | 0.03 in | 0.20 in | `#FF4906`，无边框 |
| 页眉文字 | 0.92 in | 0.15 in | 11.61 in | 0.20 in | 10 pt，苹方-简，Semibold，`#646A73`，垂直居中 |
| 页脚分隔线 | 0.80 in | 6.95 in | 11.733 in | 0 in | `#E5E6EB`，细线 |
| Source | 0.80 in | 7.05 in | 10.80 in | 0.20 in | 9 pt，苹方-简，`#646A73` |
| 页码 | 12.20 in | 7.10 in | 1.00 in | 0.30 in | 9 pt，右对齐 |

以上坐标不是“建议范围”。页眉橙色竖线、页眉文字、Action Title、Subtitle、页脚分隔线、Source和页码属于固定Chrome；同一Header Profile内必须按底层EMU与受控样式完全一致，几何容差为0 EMU。`title-divider`只作为遗留Deck或用户明确批准的特殊模板兼容角色，不属于KSIB正文默认Profile。普通正文对象仍可使用常规Layout容差。详细规则见`chrome-alignment-contract.md`。

强制格式：

- 页眉格式统一为“`III-2｜页面名称`”；罗马章节号、短横线、数字、分隔符和页面名称不得拆成多个漂移文本框。
- 页眉文字框、Action Title和Subtitle的内部边距全部为0；段前、段后为0；行距为单倍；不使用PowerPoint默认文本框边距。
- 页眉文字框使用垂直居中；Action Title和Subtitle使用顶端对齐。
- Action Title与Subtitle的标准净距为0.04 in，约4 px；不得把Subtitle放到标题下方20–40 px之外。
- Subtitle是可选解释层，不是每页必备元素；确需使用时固定14 pt，不得使用12 pt，且不得重复标题。
- Action Title不得包含硬换行、多个文本段落或渲染后的软换行。Content Gate先检查文本换行与单行容量，OOXML Gate检查`a:p`／`a:br`结构，最终全尺寸PNG检查字体渲染造成的软换行。
- 标题超长时按“删限定词→把口径移入Subtitle→把解释移入主体→必要时拆页”的顺序处理；不得缩小22 pt字号或恢复两行标题格式。
- 同一连续页面组优先共享相同Header模式；若Title-only与Title＋Subtitle混用，必须分别严格使用上表坐标，不能靠手工移动制造“看起来差不多”。
- Chrome Profile名称以`design-tokens.json.crossSlideChrome.profileIds[]`为唯一枚举。单例封面、目录或章节页可以只登记Profile、不建立跨页相等组；出现两页及以上时必须建立独立相等组。同一Profile内不得存在第二套小矩形宽高、颜色、标题基线、主体起点或页脚坐标。
- Header区域不得放置状态标签以外的附加结论；状态标签如确需保留，应固定在右上角，不改变标题、Subtitle和主体基线。

### 3.1 Title、Subtitle与Takeaway语义合同

| 元素 | 唯一职责 | 允许内容 | 禁止内容 |
|---|---|---|---|
| Action Title | 回答本页核心问题 | 一个可验证的结论或判断 | 主题标签、空泛口号 |
| Subtitle | 补充阅读边界 | 范围、时期、方法、定义、边界、比较框架 | 同义改写Action Title |
| Takeaway | 提供标题之外的决策含义 | 行动、风险、决策含义、跨证据综合 | 复述Title、Subtitle、图表或主体洞察 |

页面默认采用`Title-only`。需要边界时采用`Title＋Subtitle`；需要新增决策含义时采用`Title＋Takeaway`。`Title＋Subtitle＋Takeaway`默认禁止，确有必要时必须声明`hierarchyJustification`，并证明三者职责不同。

结构化内容必须声明：

- `subtitlePurpose`：`scope`、`period`、`method`、`definition`、`boundary`或`comparison_frame`；
- `takeawayPurpose`：`decision_implication`、`action`、`risk`或`cross_evidence_synthesis`。

若Takeaway比Action Title更像本页结论，将Takeaway提升为Action Title并删除原Takeaway。若删除Title、Subtitle、Takeaway中的任意两个后，剩余文本仍能完整表达同一信息，则判定为层级重复。

### 3.2 页面意图合同

新建与重构任务的每张实质内容页必须先声明`pageIntent`，再选择Layout。合同至少包含：

- `questionToAnswer`：本页必须回答的唯一问题；
- `actionTitlePolicy`：`auto-conclusion`、`subject-colon-conclusion`、`conclusion-sentence`或`preserve`；
- `requiredContent[]`：缺失即不能完成本页证明的内容；
- `primaryEvidence`：最强证据及其Claim绑定；
- `visualHierarchy`：主证据、解释与次级信息的优先级；
- `acceptanceChecks[]`：本页可以被逐项验证的完成条件。

`subject-colon-conclusion`适用于人物、产品、业务单元等明确对象页，使用“对象：核心结论”；其他页面默认使用`auto-conclusion`，由页面角色选择完整结论句。冒号结构不是全Deck强制模板。Subtitle默认`boundary-only`：只有范围、时期、方法、定义、边界或比较框架确实增加信息时才生成，否则使用Title-only。

## 4. 信息与布局

- 每页只证明一个核心判断；Action Title 必须能够独立概括页面答案。
- Ghost Deck、Proof Question和证据含义先于Layout；不因某个版式“好看”而改变页面职责。
- 结果页原则上一页一个主证据，并在证据附近直接标注关键发现；多个证据必须共同证明同一个Action Title。
- 优先保留用户原有主 Layout，尤其是既有左右结构、三列结构、矩阵和漏斗。只有用户明确要求重构时才改变主结构。
- Layout选择、页面结构、动态尺寸和容量默认采用Mck Layout Matrix；允许Mck定义的垂直步骤、时间轴、流程、图表和图文结构。
- Takeaway是例外组件，不是页面标配。仅当页面需要表达Action Title之外的行动、风险、决策含义或跨证据综合时，主体之外才允许设置一条；不得因留白、版式习惯或“每页都应有总结”而添加。
- Takeaway不得用于封面、章节页、目录、附录、单一证据且标题已完整表达结论的页面，或已经设置主体洞察区／Implication Panel的页面。除标准来源和页码外，禁止在Takeaway附近堆叠Owner、未解问题、角色说明、补充结论、第二条总结或其他内容带。
- Owner 价值必须在主体的“我的角色／我的判断／我的决策／责任对象”等信息中体现；未解问题必须并入主体因果链、唯一 Takeaway 或 Speaker Notes，不得另起底部模块。
- Mck的0.8 in安全边距、动态多栏、底栏间距和逐Layout容量是强制结构基准；Title-only主体起点固定为1.52 in，Title＋Subtitle主体起点固定为1.66 in。标题与主体、Subtitle与主体的最小净距分别为0.50／0.35 in；主体与底栏净距硬下限0.15 in，默认0.30 in，高视觉重量模块可提高到0.35–0.40 in。
- BCG增强Layout只使用其信息架构，不继承字体、绿色、顶部进度条、阴影、纹理、剪贴画或小字号。具体合同见 `bcg-layout-patterns.md`。
- 所有新建或重制页面必须使用 `layout-system.md` 的Mck英寸坐标；既有PPT的页眉、标题、Subtitle、分隔线、主体起点、来源和页码也必须归一。
- 每页先按Mck `layout-matrix.yaml` 选择Layout，再用KSIB `layout-matrix.json` 校验业务别名。
- 视觉分组优先使用对齐、留白和细线；除表格单元格、组织节点和必要流程节点外，实体框建议不超过4个，浅橙Highlight Box最多1个。
- 信息放不下时，处理顺序固定为：删次要信息 → 短句化 → 合并重复表达 → 调整局部间距 → 最后才降一级字号。
- 客户Deck正文只使用12／14／16 pt，不使用11、13、15 pt等任意中间字号；内部高密度页可使用14／12 pt。10 pt不得成为正文默认值。
- 单页最多一个主视觉、四个重点数字、一种强调色。
- 每页最多一个实体 Highlight Box。橙色编号、细线和小号标签可以作为结构锚点，但不能形成多个并列高亮框。
- 继承Mck版式多样性：相邻页面原则上不使用同一Layout；含时间／日期和数值的分析优先使用图表；8页以上的完整Deck至少安排一个图文版式。用户明确禁止图片或要求连续页面同构时，以用户要求为准。
- 不使用Emoji、机器人／芯片图标、渐变、玻璃拟态、3D或大面积阴影。

## 5. 原生可编辑标准

- 文本必须是真实文本框，不得把整页或大段文字栅格化成图片。
- 形状、线条、表格和图表必须保持 PowerPoint 原生对象；除明确要求外，不锁定对象。
- 所有普通对象必须支持选择、移动、缩放、多选、组合、取消组合和重新组合；不得保留`noGrp`、`noMove`、`noResize`、`noSelect`或`noTextEdit`锁。
- 所有普通文本框、表格单元格以及Chart／SmartArt中的原生文字必须支持直接修改字体、字号、字体颜色和加粗状态；图表还必须支持编辑原生数据。
- 同一段落的默认颜色只写在段落级默认属性；若字符颜色与段落默认色一致，不再写一层字符级直接颜色。
- 局部橙色强调等有意的混合颜色保留字符级属性，不得被兼容性清理误删。
- 含可见文字的DrawingML段落不得只依赖`defRPr`控制加粗；兼容性清理必须覆盖slide、notes、表格单元格及关联Chart／Diagram，把有效加粗状态物化到字符run并移除默认加粗覆盖，使PowerPoint Bold按钮可以直接取消加粗。
- 中文、英文、数字的 Latin／East Asia／Complex Script 字体槽统一指向主字体，避免局部回退为 Aptos 或其他字体。
- 纯格式任务必须在修改前后生成PPTX语义指纹；文字、数字、页序、颜色或加粗语义不一致即视为内容漂移。

## 6. 强制兼容性归一化

最后一次导出PPTX后执行。新建Deck或用户明确授权KSIB品牌归一化时：

```bash
PYTHON="<codex_app__load_workspace_dependencies 返回的 Python executable>"
OOXML_SANITIZE="<当前项目ppt/ooxml_sanitize.py；不存在则使用本Skill scripts/ooxml_sanitize.py>"
OOXML_QA="<当前项目ppt/ooxml_qa.py；不存在则使用本Skill scripts/ooxml_qa.py>"
FORMAT_CONTRACT="<当前项目最终format-contract.json>"
"$PYTHON" "$OOXML_SANITIZE" <final.pptx> --in-place
"$PYTHON" "$OOXML_QA" <final.pptx> --format-contract "$FORMAT_CONTRACT"
```

归一化必须：

1. 移除普通Shape与GraphicFrame上的`noGrp`、`noMove`、`noResize`、`noSelect`和`noTextEdit`锁，使对象可直接选择、移动、缩放、编辑与组合；
2. 在slide、notes、表格单元格及关联Chart／Diagram的DrawingML文本中，移除与段落默认颜色完全相同的冗余字符级颜色，使整框或对象级改色生效；
3. 保留有意的不同字符颜色；
4. 将上述DrawingML文本的段落默认加粗等价物化到字符run后移除默认覆盖，使Bold按钮可以取消加粗；
5. 修复非视觉对象 ID 和页数元数据；
6. 新建Deck或已授权品牌归一化时，把所有`ppt/theme/theme*.xml`改写为KSIB/Kwai主题色快捷色板；
7. 不改变直接使用品牌色的既有页面渲染结果；使用旧主题色的对象允许随新主题同步更新。

主题色快捷色板顺序固定为：

- 文字／背景：`#1F2329`、`#FFFFFF`、`#646A73`、`#FAFAFA`
- Accent 1–6：`#FF4906`、`#D83D00`、`#FFF7F3`、`#FFDBCD`、`#3B4048`、`#E5E6EB`
- Hyperlink：`#3370FF`；Followed Hyperlink：`#7C3AED`

`ooxml_qa.py` 的 `errors` 必须为空。任何`native_editability_locks`、`redundant_run_text_color`或`paragraph_default_bold_blocks_toggle`都是阻断交付的错误。

`format-only`且用户未授权改变颜色语义时不得重写主题，但仍应清理视觉等价的冗余run颜色覆盖与默认加粗覆盖；语义指纹按最终有效文字颜色和加粗状态比较，不把这种等价存储清理视为颜色漂移：

```bash
"$PYTHON" "$OOXML_SANITIZE" <final.pptx> --in-place --preserve-theme
"$PYTHON" "$OOXML_QA" <final.pptx> \
  --theme-policy preserve \
  --font-policy preserve \
  --format-contract "$FORMAT_CONTRACT"
```

随后必须以修改前指纹运行format-only compare。主题色、直接色、文字、数字或页序任一漂移均阻断交付。

字体授权必须单独声明：用户未授权改变字体时，语义指纹使用`--font-policy preserve`，OOXML QA使用`--font-policy preserve`；用户明确要求统一字体时，指纹才可使用`allow`，且最终OOXML QA必须使用`--font-policy ksib`。

## 7. 三层 QA 门禁

### 结构门禁

- PPTX ZIP 完整；关系目标存在；对象 ID 唯一；页数与备注页数一致。
- 新建／重构Deck的Storyline包装门禁与语义交接门禁均为`passed: true`；交接核对slideRole、Action Title、Proof Question、claim IDs、Implication、Visual Logic、Continuity From／To、Audience Objection、页序和Proof Shape／Layout兼容性；未知Proof Shape直接阻断。Role×Layout必须同时成立：cover只允许cover角色，目录／章节只允许navigator，附录分隔只允许appendix，附录内容页仅接受Matrix允许的appendix或边界角色；实质内容角色不得借这些Layout获得Evidence、语义或Argument Tree豁免。
- 含事实或数据的Deck，Evidence完整门禁必须为`passed: true`；registry-only报告不能替代最终Evidence门禁。
- 格式专修任务必须有修改前后语义指纹和compare报告，且文字、数字、颜色、加粗状态、字体及其原生对象绑定漂移为0；不得通过两个对象互换内容／样式、同一对象内交换文字颜色／加粗状态，或交换图表点值／标签绕过聚合清单。
- 字体仅使用批准字体；客户Deck正文符合16／14／12 pt层级，内部高密度页使用14／12 pt；10 pt只用于来源、脚注或经批准的高密度附录。内容页Action Title为22 pt，封面和章节页允许更大。
- OOXML字体门禁只允许9／10／12／14／16／18／22／24／28／44 pt这些设计系统字号；11、13、15等任意字号在`font-policy ksib`下阻断，在`preserve`下进入审计警告。9 pt仅用于来源或页脚，10 pt仅用于来源、脚注或经批准的高密度附录，不能成为客户Deck正文默认值。使用9／10 pt的对象必须以完整语义角色命名，例如`source-1`、`source-footnote`、`footer-1`、`pagenumber`、`appendix-1`或中文对应名，或确实位于页面底部脚注区；只因名称包含`page`等片段（例如`page-insight`）不能获得豁免，普通`body`对象使用9／10 pt将被阻断。
- Layout符合Mck能力边界；动态节点、栏目和图表数量不超过Mck Max Items。
- Title、Subtitle和Takeaway通过语义层级门禁：互不包含、不高相似、不承担相同结论职责。
- Takeaway通过用途与稀缺性门禁：声明合法`takeawayPurpose`，不得出现在禁用页面或与主体洞察区共存；4页及以上的内容Deck默认不超过内容页的25%，不足4页时最多1页，连续页面使用需人工复核。
- 主体之外至多一条经门禁允许的底部Takeaway；不存在Owner、未解问题、补充结论或第二总结带与其纵向堆叠。
- 内容容量门禁 `validate_content.mjs` 的 `passed` 必须为 `true`；空Deck、空内容页、未知Layout、缺少Layout必填字段、超栏目数、超节点数或超字符预算均阻断构建。嵌套必填路径必须在每个父节点逐一成立，不能因为另一分支存在同名子字段而放行。所有非豁免Layout必须在Matrix中定义非空`requiredFields[]`。
- canonical Layout必须存在机读合同；`singleExhibit`、`issueTree`、`recommendationRoadmap`必须通过必填字段、容量、Proof Shape和rendererContract门禁。使用fallback renderer时必须以`ksib-renderer-usage/1.0`逐页记录实际Renderer和具体原因。
- Header坐标、字体、文本框边距、标题与Subtitle净距符合第3节；主体遵守0.8 in边距和所选Header模式的固定起点；格式合同以`bodyStartRoles[]`命名主体锚点并阻断上移；实体框内边距不小于0.15 in；主体与底栏硬下限0.15 in、默认0.30 in。
- 跨页Chrome合同必须存在且覆盖所有重复模板页；同组固定角色的几何、旋转、填充、线条、文本边距、字体和段落格式逐项完全一致。任何1 EMU差异或受控样式差异均为阻断错误。
- OOXML QA必须阻断Action Title与Subtitle正面积重叠、Action Title多个段落／显式换行、超出单行容量以及主体锚点高于固定起点；最终PNG继续检查实际字形和软换行。

### 视觉门禁

- 全页 PNG 渲染；每页必须是非隔行PNG，并通过结构、CRC、IDAT完整解码长度、逐行filter byte、最低960×540分辨率及PPT纵横比检查，再人工检查溢出、遮挡、断行、视觉失衡和空洞留白。文件SHA256和规范化解码像素SHA256都必须逐页唯一，PNG元数据差异不得绕过同图复用门禁。
- 兼容性处理前后逐像素对比应一致；若不一致，必须人工复核差异。
- 检查页面是否通过“白底＋对齐＋细线＋留白”形成层级；若主要依靠多张等权卡片分组，即使无溢出也不得交付。
- 检查主视觉是否承载本页最强证据；视觉重点不得落在次级说明或装饰模块。
- `theme-color-gate.json`逐页通过；颜色Token、用途和主证据登记必须与最终PPTX提取清单逐绑定一致，不能以Renderer manifest或笼统`passed: true`替代。

### 连贯性门禁

- 只读Action Titles仍能复述完整故事。
- 页面顺序、标题和证据含义与锁定Storyline一致。
- 相邻页在逻辑上存在因果、递进、对比或明确章节切换，不靠页眉编号掩盖跳跃。
- 连续页面需要一一对应时优先同构；版式多样性不得破坏论证连续性。

### PowerPoint 交互门禁

先从最终PPTX制作两个副本：

- `save-only`：只打开、保存、关闭、重开；随后重新运行Sanitizer、语义指纹、OOXML和视觉门禁；
- `interaction`：复制完成时必须与最终PPTX的SHA256相同；只做瞬时编辑测试，完成后不保存直接关闭。若误保存，立即废弃该副本，不把它作为最终PPTX或语义等价证据。

在 Microsoft PowerPoint 中打开`interaction`副本：

1. 确认没有修复提示；
2. 抽查一个原生文本框，替换一段文字后撤销；
3. 在同一文本框修改字体颜色后撤销；
4. 取消加粗、恢复加粗并撤销，确认Bold按钮真实控制所选文字；
5. 临时修改字体族后撤销；
6. 修改一个非文本Shape的填充色后撤销；
7. 抽查两个对象，执行组合与取消组合；
8. 检查字体显示为“苹方-简”（macOS）；
9. 若存在表格，修改一个单元格的颜色并取消／恢复加粗后撤销；
10. 若存在图表，修改标题或标签的颜色／加粗并编辑一次图表数据后撤销；
11. 若存在SmartArt，修改其中一段文字的颜色／加粗后撤销；
12. 跳到末页确认页码、备注和对象均正常。

“能选中对象”不等于“可编辑”。颜色、加粗、字体族、文字内容和组合关系必须分别通过交互检查，不能用一个笼统的`editable=true`或一次文本修改替代。

文字操作必须先形成可见的字符级局部选区；未确认光标位于文本内时不得使用全选快捷键，否则可能误选整页对象并破坏对象结构。人工检查记录仍绑定最终PPTX的SHA256，因为`interaction`副本在测试前必须与最终文件逐字节一致；任何保存后的副本都必须重新绑定哈希并重跑全部门禁。

## 8. 交付命名

- `draft`、`tmp`、`inspect`、测试副本不得作为正式交付。
- 正式文件名应明确版本用途，例如 `完全可编辑版`、`正式版` 或用户指定版本名。
- 交付前保留最终PPTX、视觉预览、机读QA结果和`release-manifest.json`；Manifest v3登记输入与PPTX哈希、Storyline lock、Evidence／Content／Handoff／OOXML／视觉Gate、当前Validator、逐页Renderer及人工PowerPoint检查状态。
- Visual Gate必须由`build_visual_review_gate.py`生成，逐页绑定全尺寸PNG文件SHA256、规范化像素SHA256与复核记录；不同页的像素哈希必须唯一，改文件名或只改PNG元数据不能绕过。所有Gate报告必须绑定canonical Validator的当前SHA256，并且晚于其所绑定输入；fingerprint、OOXML和Visual Gate必须都指向当前最终PPTX的同一SHA256。Release还必须验证根`officeDocument`关系、Presentation Content Type、非空`sldId`、每个slide关系、真实slide part及其Content Type完全一致，旧版本或空壳PPTX不得复用。
- 测试副本放在`work/`，不放在`outputs/`。
