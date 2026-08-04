---
name: ksib-management-review-ppt
description: Build, revise, evidence-check, format, and QA serious, editable Chinese consulting and management decks for KSIB/Kuaishou/Kwai overseas e-commerce. Use for management appointment reviews, market and competitor studies, channel or price analysis, consumer research, strategy recommendations, locked-storyline production, or formatting-only PowerPoint work that must preserve content. Covers evidence and calculation traceability, storyline handoff, layout contracts, theme normalization, native editability, semantic fingerprints, and release manifests.
---

# KSIB 咨询与管理汇报 PPT

## 目标

把经确认的研究、策略或管理内容转换为严肃、克制、高信息密度且可编辑的 PowerPoint。保持人对最终故事线、业务事实、计算口径、管理承诺和品牌资产的控制；`linzhe-mbb-storyline`负责上游论证与锁定，本Skill负责证据链、视觉系统、版式工程、内容承载和交付门禁。

## 先读与边界

1. 先读仓库 `AGENTS.md`、用户提供的述职内容和约束。
2. 使用系统 `Presentations` skill 与 `@oai/artifact-tool`；不要用全页图片模拟 PPT，也不要引入 `python-pptx` 或 PptxGenJS。
3. 若当前工作区存在`ppt/content.example.json`、`ppt/theme.js`、`ppt/components.js`和`ppt/layouts.js`，把它们视为本项目的内容与视觉接口；其他工作区使用系统`Presentations` skill建立项目本地源文件，不假设固定仓库结构。
4. 不替用户决定最终故事线，不补写未经提供的业务事实、数字、排名、归因或承诺。新建／重构Deck必须先使用`linzhe-mbb-storyline`；只改格式时必须跳过Storyline重构，并用语义指纹证明文字、数字、页序、颜色和加粗语义未漂移。
5. 示例内容统一显式标记 `[占位]`；模板内容统一显式标记 `[替换]`。
6. 外部发布、发送、提交、品牌 Logo 使用和不可逆修改仍需人工确认。
7. 接到任务先完整读取`references/intake-contract.md`与`references/intake-contract.json`并通过Intake Gate；正式制作或交付前，完整读取 `references/production-standard.md`、`references/design-tokens.json`、`references/theme-color-contract.md`、`references/theme-color-contract.json`、`references/layout-system.md`、`references/bcg-layout-patterns.md`、`references/format-engineering-contract.md`、`references/chrome-alignment-contract.md`与`references/powerpoint-render-contract.md`；页面包含图表或表格时还必须读取`references/mbb-exhibit-style-contract.md`；需要选择或研发Waterfall、Mekko、Gantt、自动标签避让等高级组件时读取`references/think-cell-open-source-landscape.md`；含外部事实、数据、市场或竞品判断时读取`references/evidence-contract.md`，交付前读取`references/delivery-contract.md`。
8. 在选Layout和填内容前读取本地已安装的`mck-ppt-design` skill及其`references/layout-matrix.yaml`；只吸收其咨询版式方法和容量边界，不调用其`python-pptx`生产路径。本 skill 的`references/layout-matrix.json`补充KSIB页面别名、增强Layout与机读容量，不得凭感觉决定栏目数、节点数或字符容量。
9. 新建或重构Deck时读取`references/storyline-layout-handoff.md`，并以已通过门禁且由用户锁定的`storyline.json`作为Governing Thought、2–4个支撑论点、页面顺序、Action Title和证据含义的真相源。
10. 使用参考Deck时，先抽取页面功能类型、内容Schema、标题节奏和几何合同，再选择性复用；不得只按截图逐页模仿，也不得把参考Deck的业务结论带入当前材料。
11. 任何客户可见数字和外部事实必须映射到`claimIds[]`；任何派生指标必须登记公式、时期、单位、分母和数据版本。自然语言脚注不能代替Evidence Contract。
12. 本Skill提供Layout与Renderer合同，但不声称自带完整渲染引擎。实际构建使用系统`Presentations` skill与`@oai/artifact-tool`，或项目中已验证的原生构建器；缺少renderer时只能使用合同声明的fallback并记录到release manifest。

## 默认视觉系统

设计、结构、留白、页面体例、容量和门禁以本地安装的`mck-ppt-design` skill为基础规范；只吸收其咨询版式方法，不采用其`python-pptx`实现。在此基础上吸收用户提供的BCG管理者任命模板中可复用的标题纵向节奏与证据型Layout。只保留三项品牌覆盖：KSIB配色、苹方-简字体、客户Deck正文16／14／12 pt；原生可编辑性和主题色板归一化属于工程增强。

`references/design-tokens.json`是画布、字体、字号、主题色、Header/Footer几何与基础间距的机读真相源；文档、Renderer、Sanitizer、OOXML QA、格式合同和Release Manifest不得各自维护另一套无校验数值。修改这些值时必须同步通过`test_design_tokens.py`。

- 画布：Mck宽屏 `13.333 × 7.5 in`（16:9；等效1280 × 720）。
- 颜色：以`ksib-theme-color-contract/1.0`为唯一语义合同。主色采用深／主／浅／极浅四级橙色阶，对比辅色默认`#006B8F`；浅灰只承担“其他”、基线、参考、弱化或较差对比，深灰只用于文字与必要线条。Renderer不得直接使用任意Hex或把辅色、功能色当装饰。
- 字体：macOS统一使用 PingFang SC（PowerPoint显示“苹方-简”），Windows回退 Microsoft YaHei；不继承Georgia、Arial或楷体。
- 字号：继承Mck层级中的44／28／24／22／18／16／9 pt；客户Deck正文使用16／14／12 pt，内部高密度页可使用14／12 pt。10 pt只用于来源、脚注或经批准的高密度附录，9 pt只用于来源／页脚；内容页Action Title固定22 pt，不得用缩字号掩盖超载。
- 内容层级：Action Title负责本页唯一主结论；默认按页面类型生成结论型标题，人物／产品／业务单元等明确对象页优先使用“对象：核心结论”，其他页面使用完整结论句。Subtitle只负责范围、时期、方法、定义、边界或比较框架；Takeaway只负责标题之外的决策含义、行动、风险或跨证据综合。页面默认只使用Action Title。
- Subtitle：Mck和BCG参考模板都没有要求每页固定使用内容页Subtitle；本skill将其定义为可选边界层。确需使用时设置`subtitlePurpose`，使用苹方-简14 pt，并遵守 `layout-system.md` 的坐标、净距和零内边距合同；不得改写或复述Action Title。
- Header：必须从 `layout-system.md` 的固定Header合同中选择一种：一行标题或一行标题＋Subtitle。内容页标题下默认不使用横向分隔线；`title-divider`只兼容遗留Deck或经用户批准的特殊模板。页眉、Action Title、Subtitle和主体起点不得逐页漂移；开放文本框边距为0。
- 跨页Chrome：同一页面Profile中的页眉橙色竖线、页眉文字、Action Title、Subtitle、页脚分隔线、Source与页码必须按底层EMU和受控样式绝对一致；固定Chrome容差为0 EMU，不能沿用普通Layout的0.03 in容差。Profile使用`design-tokens.json`唯一枚举；同类页面达到两页时必须建立相等组，单例页面只按设计Token和视觉门禁验收。
- 标题：结论型Action Title只能一行；Content Gate拒绝硬换行和超出单行容量，OOXML Gate拒绝多个段落或显式换行，最终PNG检查软换行。标题与Subtitle之间标准净距为0.04 in。
- 布局：使用Mck Layout目录及选择逻辑，包括左右对比、表格洞见、流程、时间轴、垂直步骤、漏斗、价值链、图表和图文版式；不再全局禁止纵向Layout。页面级明确要求仍优先。
- 留白：使用Mck `0.8 in`左右边距、`0.35 in`动态多栏间距和`0.15 in`实体框内边距；主体与底栏净距硬下限0.15 in、默认0.30 in，高视觉重量模块可在逐页视觉复核中提高到0.35–0.40 in。Title-only主体起点固定为1.52 in，Title＋Subtitle固定为1.66 in，并以`bodyStartRoles[]`进行机器校验，不得逐页手调。
- 风格：白底、黑灰正文、平面化、无阴影、无3D、无渐变；通过对齐、细线和留白建立层级。
- 表格：默认使用`minimal-rule`，即白底表头、无外框、无竖线、数字右对齐、仅保留表头规则线和必要的总计／分组横线。黑色或深灰实心表头不是咨询风默认值，只有客户模板或高密附录明确需要时才允许使用。
- 图表：默认使用`direct-label-spotlight`，删除无意义的边框、图例、坐标轴和网格线；直接标注数据，只使用一个橙色视觉焦点。“其他”置于末位并保持中性灰。Waterfall、Mekko、Gantt及CAGR／差异标注按`mbb-exhibit-style-contract.md`执行。
- 底部信息：Takeaway默认不设置；只有新增决策含义、行动、风险或跨证据综合时才允许设置一条，并声明`takeawayPurpose`。不得因页面留白而添加，不得复述Title、Subtitle、图表标注或主体洞察区，也不得与洞察侧栏、Owner、未解问题或第二结论带共存。
- 密度：按Mck逐Layout字符预算、Max Items和内容区利用率门禁执行；超限先删减，不得任意缩小字号。
- 品牌资产：没有经批准的Logo文件时只使用品牌色与文字标识，不重绘、不改色、不伪造Logo。

## 页面类型

优先使用Mck Layout目录，而不是临时堆叠文本框。以下KSIB名称是对Mck Layout的业务语义别名：

- `cover`：身份、主题和一句核心主张。
- `toc`、`agenda`：目录／议程导航；必须使用`navigator`角色。
- `section`、`sectionDivider`：章节分隔；必须使用`navigator`角色。
- `appendixDivider`：附录分隔；必须使用`appendix`角色。
- `valueChain`：岗位价值、责任链与经营飞轮。
- `timeline`：阶段成长、代表项目和能力叠加。
- `businessShift`：业务阶段迁移与岗位使命升级。
- `campaign`：目标、难题、关键决策、结果和反思。
- `productCommercialization`：痛点、MVP、收费、产品化、规模化与双边价值。
- `casePortfolio`：案例对照、判断、动作、结果和机制沉淀。
- `orgManagement`：管理转型、目标拆解、授权和复盘机制。
- `scorecard`：任命匹配度、差距、90 天动作和风险承诺。
- `twoColumn`、`threeColumn`、`fourColumn`：左右、三列和四列编辑式布局；以留白和细线分组，不使用卡片墙。
- `horizontalMatrix`、`tableInsight`：高密度矩阵与表格＋洞见布局。
- `funnel`、`horizontalEvolution`：有效供给漏斗、角色演进和阶段迁移。
- `evidenceInsight`：65%–75%主证据区＋25%–35%洞见／管理含义区；适合一页回答“事实说明什么”。
- `phasePlaybook`：3–4个横向阶段共享同一组逻辑行；适合阶段打法、验证标准和递进关系。
- `problemSolutionMap`：问题／卡点与解决动作逐行映射；适合组织补洞、经营诊断和协同机制。
- `processModeMatrix`：同一端到端流程的不同模式或方案横向比较；适合SOP、Managed Service与产品化路径。
- `layeredOperatingModel`：业务链路、横向能力和反馈／承接层组成一张系统图；适合平台能力、经营系统和组织运行模型。
- `strategyEnablers`：一个核心战略判断与3–4项能力支撑；适合Leading Page或战略框架页。
- `reflectionEvolution`：过去／当前／目标三阶段同构演进；适合管理角色、组织成熟度与个人反思。
- `singleExhibit`：一张主图表／表格／事实证据＋直接标注关键发现；适合市场规模、赛道份额、价格带、消费者或渠道数据。
- `issueTree`：把一个决策问题拆成MECE子问题与验证路径；使用Mck Issue／Decision Tree，不把树画成装饰性框架。
- `recommendationRoadmap`：建议、关键条件、里程碑和Owner／判断标准形成一条执行链；按内容选择roadmap、action items或phase playbook。
- `appendixProject`、`appendixTable`、`appendixQA`：证据截图、口径表和委员会问答。
- `styleboardSystem`、`styleboardDensity`：仅用于视觉确认和密度选择，不进入正式述职计时。

## 工作流

### 0. 完成Intake并判断内部执行边界

先按`ksib-intake-contract/1.1`完成两步Intake：第一步只确定`topic-to-deck`、`story-rebuild`或`format-only`；第二步按所选模式一次性处理最多9个问题。`required`缺失即阻断，`visible_optional`必须主动展示默认值，`conditional`只在触发后按必填处理。UI只显示“必填／选填”，不得逐题进行9轮问答。

新建与重构任务必须同时声明`ksib-page-intent-contract/1.0`。每张实质内容页先定义`questionToAnswer`、`actionTitlePolicy`、`requiredContent[]`、`primaryEvidence`、`visualHierarchy`和`acceptanceChecks[]`，再选择Layout。默认`actionTitlePolicy=auto-conclusion`、`subtitlePolicy=boundary-only`、`bodyToBottomBandGapIn=0.30`；Format-only默认保留原标题层级与间距，只有授权归一化时才应用新默认。

若PPT Studio或其他工作台已提供任务JSON／manifest，优先读取已有答案与来源，只询问缺失或冲突项，不重复确认受众、场合、决策、页数、主题或Layout策略。工作台必须声明`intake_contract_version`；版本缺失或不匹配时不能把任务描述为Intake已完成。若上游只粘贴`task.md`，其中还必须提供对应`manifest.json`安全路径或嵌入最小任务JSON；纯自然语言合同不能替代机读门禁。

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_intake.mjs" \
  --task <task-or-manifest.json> \
  --report work/presentations/ksib-management-review/tmp/qa/intake-gate.json
```

只有`passed: true`才进入后续流程。用户任务类型始终只显示“从Topic新建／重构现有PPT／仅调整格式”；`story-change`与`locked-content`只是Storyline锁定后由流程派生的内部制作阶段，不得作为用户任务类型回显。若`story-rebuild`明确提供已锁定故事线或最终内容且不允许改写，则内部派生为`locked-content`，不增加第四个用户任务类型。固定Guardrails不作为问题：不覆盖原文件、不伪造数据、Logo必须获批、新建／重构Storyline必须由用户锁定。

随后按内部执行模式分类：

- `format-only`：用户要求不改内容，只统一Layout／格式／页眉页脚／可编辑性。修改前生成PPTX语义指纹并为受控对象建立唯一角色名、格式合同与跨页Chrome Profile，修改后运行compare。格式合同不得为空；至少覆盖所有重复出现的Header、Title、Divider、Source和Page Number。默认`--style-policy preserve`，任何文字、数字、页序、颜色或加粗语义漂移均阻断交付；只有用户明确授权视觉重排或重新定样时才允许`--style-policy allow`，此时仍冻结文字、数字、页序、图表数据和对象内容绑定。编辑器无损保存导致的内部对象ID重排不视为漂移，唯一角色名才是优先语义键。
- 既有PPT的Chrome归一默认先运行`scripts/pptx_chrome_normalizer.py`只读审计。用户只授权位置／尺寸时使用`--scope geometry`，不得复制颜色、字体或段落样式；授权统一样式但冻结位置时使用`--scope style`；只有两类均获授权才使用`--scope all`。对象类型不一致、角色缺失或重复时立即阻断。
- `locked-content`：用户提供最终版内容并要求制作为PPT。使用`linzhe-mbb-storyline`的`lock`模式补齐最小交接合同，不重新发明故事线；含事实或数据时补齐Evidence Contract。
- `story-change`：用户要求新建、重构、合并、删页或修改论证。先登记Evidence Contract中的Source、Calculation和Claim，再完成`linzhe-mbb-storyline`并取得`productionReady: true`的门禁报告。

研究、策略和数据型Deck的生产顺序固定为：

`Intake完成 → Source核验 → Calculation登记 → Claim登记 → Evidence registry门禁 → Storyline引用claimId并锁定 → Content引用claimIds → Evidence完整门禁 → Storyline交接门禁 → 构建与视觉QA → Release manifest`

`format-only`任务先调用`codex_app__load_workspace_dependencies`设置`$PYTHON`，再在修改前后分别运行：

```bash
"$PYTHON" "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/prepare_revision.py" \
  --input <locked-input.pptx> \
  --workspace work/presentations/ksib-management-review/revisions \
  --label format-only

"$PYTHON" "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/pptx_semantic_fingerprint.py" create \
  --pptx <revision/source/locked-input.pptx> \
  --output work/presentations/ksib-management-review/tmp/qa/input-semantic-fingerprint.json

"$PYTHON" "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/pptx_semantic_fingerprint.py" compare \
  --baseline work/presentations/ksib-management-review/tmp/qa/input-semantic-fingerprint.json \
  --pptx <final.pptx> \
  --mode format-only \
  --font-policy preserve \
  --style-policy preserve \
  --report work/presentations/ksib-management-review/tmp/qa/format-only-semantic-gate.json
```

后续所有Sanitizer、构建和人工编辑只作用于`workingCopy`或新的输出路径；不得覆盖用户原文件。`revision-manifest.json`记录输入、Source副本和Working副本的SHA256。

示例默认冻结字体族、字号、主题字体、颜色和加粗。用户明确授权统一字体时，compare改为`--font-policy allow`；用户明确授权按MBB／KSIB视觉规范重新定样时，compare改为`--style-policy allow`。两种授权相互独立，未授权不得把字体或视觉语义调整暗含在“版式优化”中。

新建／重构Deck必须通过KSIB Storyline包装门禁；包装器会调用`linzhe-mbb-storyline`并同时绑定Storyline原文件、包装器版本和上游校验器版本：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_storyline_gate.mjs" \
  --storyline storyline/storyline.json \
  --upstream "${CODEX_HOME:-$HOME/.codex}/skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs" \
  --report storyline/gate.json \
  --require-lock
```

没有机读通过结果时，不得口头宣布故事线已锁定。

### 1. 读取内容、证据与参考Deck

确认受众、场合、时长、必答问题、证据来源和不可扩写边界。把事实与数字绑定到来源；缺失项保留占位，不推断。

含事实、数据、市场或竞品判断时，先建立`evidence/evidence.json`，按`references/evidence-contract.md`登记Source、Calculation和Claim，并在Storyline锁定前运行。当前合同只接受`contractVersion: "1.0"`；公式中的每个变量必须对应显式`inputs[].name`，时期必须是可解释描述或合法日期范围：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_evidence.mjs" \
  --evidence evidence/evidence.json \
  --registry-only \
  --report work/presentations/ksib-management-review/tmp/qa/evidence-registry-gate.json
```

Storyline中的每项证据使用`evidence[].claimId`，不得只写无法定位的自然语言`sourceRef`。用户锁定前还必须建立`argumentTree`，把`governingThought`分解为2–4个支撑论点，并把每张实质内容页及其Claim唯一归入一个Pillar。

若用户提供参考Deck，先建立Reference Schema：

- 页面功能类型与章节节奏；
- Header／Title／Subtitle／Body／Footer几何；
- 内容Schema、主证据位置和视觉层级；
- 可复用Layout与不应复制的品牌皮肤。

这一步吸收PPTAgent“先理解参考结构再生成”的工作方式，只复用抽象合同。

### 2. 从证据形态选择承载结构

从Storyline逐页读取`proofQuestion`、`evidence`和`visualLogic`，再从已读取的Mck `references/layout-matrix.yaml`或本Skill的`references/bcg-layout-patterns.md`选择最匹配的单一主Layout；最终写入内容文件的`slideType`必须是`references/layout-matrix.json`中的canonical Layout或其已登记别名。图表类型不是Layout：line／bar／waterfall／bubble等只写入`singleExhibit.exhibit.type`或项目Renderer的图表子型，不能直接写成`slideType`。Layout服务于证明形态，不服务于“版式多样性”本身：

- 比较／取舍 → `twoColumn`、`horizontalMatrix`或`tableInsight`；
- 趋势／时间数列 → `singleExhibit`承载line／bar／waterfall；只有阶段里程碑才用`timeline`；
- 因果／问题映射 → `issueTree`、`problemSolutionMap`或`valueChain`；
- 阶段递进 → `recommendationRoadmap`、`phasePlaybook`、`horizontalEvolution`或`timeline`；
- 系统／闭环 → `layeredOperatingModel`或`valueChain`；
- 单一核心证据 → `singleExhibit`或`evidenceInsight`；
- 组合与优先级 → `horizontalMatrix`或`tableInsight`；2×2／bubble仅作为其中的可编辑视觉子型。

保持Storyline已锁定的页面顺序、Action Title和证据含义；只有用户明确授权时才返回上游修改。既有PPT优先保留宏观结构，但页眉、标题、Subtitle、主体起点、来源和页码必须统一到对应Header模式与页面几何；遗留标题分隔线的删除属于样式授权，format-only不得静默改变。

### 3. 编辑结构化内容

优先只改当前项目约定的结构化内容文件，例如`ppt/content.example.json`或`work/content.json`：

- `slideType` 决定布局。
- 新建与重构内容页填写`pageIntent`：`questionToAnswer`、`actionTitlePolicy`、`requiredContent[]`、`primaryEvidence`、`visualHierarchy`和`acceptanceChecks[]`均不能为空。`subject-colon-conclusion`标题必须是“对象：核心结论”；它只用于对象明确的页面，不强制覆盖所有页面。
- `slideRole` 必须与锁定Storyline逐页一致，并满足`layout-matrix.json.global.roleLayoutPolicy`的Role×Layout合同：`cover`只允许`cover`角色，目录／章节页只允许`navigator`，附录分隔只允许`appendix`；附录内容页除`appendix`外，仅按Matrix允许`methodology`、`scope_boundary`或`legal_disclaimer`等边界角色；其他实质Layout只允许登记的内容角色。不得把实质内容页改用cover／章节Layout，或自标边界角色申请语义、Evidence或Argument Tree豁免。
- `title` 写结论，不写主题标签。
- `source` 写数据口径或材料来源。
- `notes` 写本页时长、目标、讲述顺序和不展开项。
- `proofQuestion`、`implication`、`visualLogic`、`continuityFrom`、`continuityTo`和`audienceObjection`必须与锁定Storyline逐字语义一致；后三项是翻页与反驳合同，不能只留在Storyline而在Content中丢失。
- `implication`是锁定的语义元数据，不代表页面已存在一个可见洞察框；如需显示为Takeaway，另填`takeaway`与`takeawayPurpose`。只有`insight`、`insightPanel`等真实可见主体洞察区才与Takeaway互斥。
- `claimIds[]`只引用Evidence Contract中的客户可见Claim；页面不得重新手写另一版数字。
- Storyline证据只能用`evidence[].claimId`绑定Claim；通用`evidence[].id`、商品ID、图表ID或来源ID不能替代`claimId`。
- 使用`subtitle`时填写`subtitlePurpose`，仅允许`scope`、`period`、`method`、`definition`、`boundary`或`comparison_frame`。
- 使用`takeaway`时填写`takeawayPurpose`，仅允许`decision_implication`、`action`、`risk`或`cross_evidence_synthesis`。
- `Title＋Subtitle`与`Title＋Takeaway`是两种优先层级；三者同时出现默认失败，确有必要时必须提供`hierarchyJustification`。
- 业务事实与指标没有来源时保留 `[占位]`。

填充后运行内容容量门禁：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_content.mjs" \
  --content ppt/content.example.json \
  --require-page-intent \
  --report work/presentations/ksib-management-review/tmp/qa/content-gate.json
```

只有报告中 `passed: true` 才能进入构建。超限时删次要信息或短句化，不得绕过门禁或临时缩小字号。

含事实或数据的Deck还必须运行Evidence完整门禁：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_evidence.mjs" \
  --evidence evidence/evidence.json \
  --content ppt/content.example.json \
  --report work/presentations/ksib-management-review/tmp/qa/evidence-gate.json
```

新建／重构Deck还必须运行Storyline语义交接门禁：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_storyline_handoff.mjs" \
  --storyline storyline/storyline.json \
  --content ppt/content.example.json \
  --report work/presentations/ksib-management-review/tmp/qa/storyline-handoff.json
```

内容文件中的每页使用`storylineId`关联Storyline。门禁核对Governing Thought到支撑论点、页面与Claim的论证树，逐页核对Action Title、Proof Question、claim IDs、Implication、Visual Logic、Continuity From／To、Audience Objection、页序以及Proof Shape与Layout兼容性，并输出逐页语义哈希；任一项变化都必须返回上游重新锁定。

### 4. 构建

默认按系统`Presentations` skill使用`@oai/artifact-tool`生成或编辑PPTX。每页先由内容门禁把canonical Layout解析为`rendererContract`：Layout专属合同优先，其余按`global.rendererDefaults`以canonical Layout名作为Renderer接口。每页必须明确provider、canonicalRenderer与`editableNative: true`；不得把fallback renderer悄悄当作canonical renderer。

构建前创建`ksib-format-contract/1.0`，把页眉、Action Title、Subtitle、来源、页码和主证据对象命名为稳定英文角色，并声明Header模式、单行标题策略、`bodyStartRoles[]`、几何、跨页一致性组、原生对象类型及编辑性策略。默认正文不得创建`title-divider`。固定Chrome使用0 EMU容差逐属性比较；普通正文Layout才可使用常规几何容差。若用户只授权部分格式属性，用`crossSlideEqualityGroups[].compareFields[]`把机器门禁限制到同一授权范围，不得把未比较的颜色或字体描述为“已统一”。图表、表格和流程必须分别保留为原生Chart、Table与吸附节点的Connector；静态文本页码和只含literal数据的Chart只能在合同明确降级且PowerPoint人工验收通过时使用。完整字段与Golden Deck见`references/format-engineering-contract.md`，既有PPT归一流程见`references/chrome-alignment-contract.md`。

同时创建`ksib-theme-usage/1.1`语义草稿并逐页登记所有有色元素的稳定ID、角色、Token和用途。数据页面必须登记`pattern`、`dominantEvidenceObject`与`dominantEvidenceToken`；`slides[]`覆盖全部页面。最终PPTX完成最后一次保存和Sanitizer之后，运行`extract_pptx_theme_colors.py`读取成片真实颜色，再用`slides[].bindings[]`把每个可见`bindingRef`恰好绑定到一个语义元素及Token（或用户批准的例外）。主色阶、对比辅色、浅灰中性色和功能色的适用边界以`references/theme-color-contract.json`为准；Renderer声明不能替代最终PPTX核验。

当前工作区存在且已经通过项目测试的KSIB原生构建器时，可以在项目根目录执行：

```bash
node ppt/build_template.js --mode all
```

只构建样张或空白母版时分别使用 `--mode sample` 或 `--mode template`。只验证单一布局时使用 `--only campaign` 等布局名。

项目构建器不是本Skill自带依赖；不存在时不得引用这些命令或假装构建器可用。无论使用哪条渲染路径，都必须在release manifest记录renderer名称、版本、canonical／fallback状态和最终PPTX哈希。

### 5. 运行质量门禁

先调用 `codex_app__load_workspace_dependencies`，把返回的 bundled Python executable 记为 `$PYTHON`；不要假设系统 `python3` 已安装 `lxml`。OOXML脚本优先使用当前项目的`ppt/`版本；不存在时使用本Skill的`scripts/`版本。

先做语法和 JSON 检查，再做布局检查。以下`ppt/*.js`和`ppt/qa.js`命令只在当前项目确实提供对应文件时运行；不存在时使用系统`Presentations` skill的构建／渲染验证，不能把“文件不存在”当作已通过：

```bash
CONTENT_JSON=ppt/content.example.json
OOXML_SANITIZE="${OOXML_SANITIZE:-${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/ooxml_sanitize.py}"
OOXML_QA="${OOXML_QA:-${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/ooxml_qa.py}"
VISUAL_GATE="${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/build_visual_review_gate.py"
COLOR_EXTRACTOR="${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/extract_pptx_theme_colors.py"
[ ! -f ppt/theme.js ] || node --check ppt/theme.js
[ ! -f ppt/components.js ] || node --check ppt/components.js
[ ! -f ppt/layouts.js ] || node --check ppt/layouts.js
[ ! -f ppt/build_template.js ] || node --check ppt/build_template.js
[ ! -f ppt/qa.js ] || node --check ppt/qa.js
node --check "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_content.mjs"
node --check "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_intake.mjs"
node --check "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_theme_usage.mjs"
node --check "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_evidence.mjs"
node --check "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_storyline_gate.mjs"
node --check "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/build_release_manifest.mjs"
"$PYTHON" -m py_compile "$OOXML_SANITIZE" "$OOXML_QA" "$VISUAL_GATE" "$COLOR_EXTRACTOR"
"$PYTHON" -m json.tool "$CONTENT_JSON" >/dev/null
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_content.mjs" --content "$CONTENT_JSON" --report work/presentations/ksib-management-review/tmp/qa/content-gate.json
[ ! -f ppt/qa.js ] || node ppt/qa.js --layout-root work/presentations/ksib-management-review/tmp/layout --report work/presentations/ksib-management-review/tmp/qa/layout-qa.json
```

随后对最终 PPTX 执行：

```bash
"$PYTHON" "${OOXML_SANITIZE:-ppt/ooxml_sanitize.py}" <final.pptx> --in-place
"$PYTHON" "${OOXML_QA:-ppt/ooxml_qa.py}" <final.pptx> \
  --format-contract <format-contract.json>
```

`format-only`且用户未授权改变颜色语义时改用：

```bash
"$PYTHON" "${OOXML_SANITIZE:-ppt/ooxml_sanitize.py}" <final.pptx> --in-place --preserve-theme
"$PYTHON" "${OOXML_QA:-ppt/ooxml_qa.py}" <final.pptx> \
  --theme-policy preserve \
  --font-policy preserve \
  --format-contract <format-contract.json>
```

无论使用哪种主题策略，都必须在对应的最终Sanitizer和OOXML QA完成后执行成片颜色提取与交叉校验：

```bash
"$PYTHON" "$COLOR_EXTRACTOR" --pptx <final.pptx> \
  --output work/presentations/ksib-management-review/tmp/qa/pptx-color-inventory.json
node "${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/scripts/validate_theme_usage.mjs" \
  --pptx <final.pptx> \
  --python "$PYTHON" \
  --usage work/presentations/ksib-management-review/tmp/qa/theme-usage.json \
  --inventory work/presentations/ksib-management-review/tmp/qa/pptx-color-inventory.json \
  --report work/presentations/ksib-management-review/tmp/qa/theme-color-gate.json
```

`--preserve-theme`保留主题色板，但仍会清理与段落默认色完全相同的冗余run颜色覆盖并规范化默认加粗；清理范围覆盖slide、notes、表格单元格以及关联Chart／Diagram中的DrawingML文本。语义指纹比较最终有效颜色与加粗状态，并把Chart／Diagram文本样式绑定到关联part，因此存储方式清理不会被误判为内容漂移。
若用户已明确授权字体归一化，语义指纹使用`--font-policy allow`，OOXML QA使用`--font-policy ksib`；主题仍按用户是否授权改变颜色决定`preserve`或`ksib`。

以上最终Sanitizer、OOXML QA、颜色提取与交叉校验必须在最后一次 PPTX 导出之后执行。不得把未经过兼容性归一化或成片颜色核验的中间文件直接交付。

完成辅助全页PNG渲染与逐页复核后，用复核输入生成绑定最终PPTX和每页PNG哈希的Visual Gate。它只用于构建期预览，不能替代PowerPoint最终视觉门禁：

```bash
"$PYTHON" "$VISUAL_GATE" \
  --pptx <final.pptx> \
  --render-dir work/presentations/ksib-management-review/tmp/render \
  --review-json work/presentations/ksib-management-review/tmp/qa/visual-review-input.json \
  --output work/presentations/ksib-management-review/tmp/qa/visual-gate.json
```

`visual-review-input.json`必须逐页登记`slide`、`renderFile`、`passed`和`issues[]`；PNG必须为非隔行、结构／CRC／IDAT／完整解码行均有效的全页渲染，最低960×540且纵横比与PPT一致。门禁同时计算文件SHA256与规范化解码像素SHA256；只有PNG文件头、短解码载荷、隔行PNG、只写全局`passed: true`、同名复用、改文件名复用，或只增加`tEXt`等元数据伪装成不同文件的同像素跨页复用均不能通过。最终还必须按`references/powerpoint-render-contract.md`保存PowerPoint逐页截图并运行`validate_powerpoint_render.py`；辅助渲染与PowerPoint明显不一致时直接阻断。

- ZIP 完整性检查。
- OOXML 语义检查：关系目标存在、非视觉对象ID唯一、DrawingML尺寸非负、页数元数据一致。新建Deck或用户授权品牌归一化时使用KSIB主题；纯格式任务默认保留原主题，并由语义指纹证明颜色未漂移。
- 最终成片颜色检查：`theme-color-gate.json.passed`必须为`true`且逐页覆盖。最终PPTX每个可见颜色绑定必须可解析、对象名稳定、在Theme Usage中恰好登记一次，并与声明Token的真实Hex一致；任意未登记实际色、虚假Renderer绑定、原始Hex、深灰数据填充、浅灰主证据、无语义辅色、装饰性功能色或未获用户批准的例外均阻断交付。
- 安全与完整性检查：宏为阻断错误；外部关系、嵌入对象和媒体形成可审计清单；未解决的`[占位]`、`[替换]`、`[TBD]`或`[待验证]`阻断交付；直接字体不得漂移到未批准字体。
- 原生编辑性检查：任何普通Shape或GraphicFrame不得保留`noGrp`、`noMove`、`noResize`、`noSelect`或`noTextEdit`锁；slide、notes、表格单元格和关联Chart／Diagram中的普通同色文本不得同时保留段落级与字符级重复颜色覆盖；有意的局部强调色必须保留。含可见文字的DrawingML段落不得把加粗仅留在`defRPr`默认层，必须在保持视觉结果不变的前提下物化到字符run并删除默认加粗覆盖，使PowerPoint的Bold按钮能直接取消加粗。流程Connector必须同时吸附起终节点并保留箭头；图表数据模式必须满足合同；正式Deck页码应使用`slidenum`字段或母版占位符。
- PowerPoint 文件回读和逐页真机截图；100%视图与缩小视图均需逐页复核。
- 全页 PNG 渲染与逐页视觉检查。
- 过小字号与基础OOXML尺寸使用自动检查；重叠、裁切、意外换行和标题实际行数先由辅助PNG发现，再以PowerPoint逐页截图为最终视觉真相，不得描述成自动几何证明。
- 页面层级检查：Title、Subtitle与Takeaway不得存在包含关系或高相似复述；相似度达到硬门禁阈值时必须删减或重新分工。
- Takeaway稀缺性检查：默认无Takeaway；不得用于封面、附录或已有洞察区的页面；全Deck使用量不得超过内容页预算，连续使用需人工复核。
- 页面底部结构检查：主体之外至多一条经门禁允许的Takeaway；不存在Owner、未解问题或第二结论带与Takeaway纵向堆叠。
- Storyline一致性检查：Ghost Deck页序和Action Title未漂移；每页主证据仍回答原Proof Question。
- 三维交付检查：Content、Design、Coherence分别通过；视觉无误不能抵消内容或连贯性缺陷。
- 留白检查：左右边距0.8 in；Title-only主体起点为1.52 in，Title＋Subtitle主体起点为1.66 in；格式合同用`bodyStartRoles[]`阻断主体上移；多栏最小间距0.35 in；实体框内边距至少0.15 in；底栏与主体硬下限0.15 in、默认0.30 in，高视觉重量模块逐页检查是否需要0.35–0.40 in。
- 跨页绝对对齐检查：同一Chrome Profile中的固定角色按EMU、旋转、填充、线条、文本边距、字体和段落格式逐项完全一致；任何1 EMU或受控样式差异均阻断交付。合法的封面、章节页和Header模式差异必须拆分为不同Profile，不能放宽容差。
- Header与标题检查：OOXML QA必须阻断Action Title与Subtitle的对象框正面积重叠、Action Title多个段落／显式换行、超出单行容量、未经批准的默认`title-divider`以及主体锚点上移；最终PNG逐页确认没有字体软换行，画布溢出测试通过不能替代这项检查。
- 原生文本、形状、表格、可编辑矢量图表和演讲者备注检查。
- 媒体、外部链接、嵌入字体和敏感内容检查。
- Microsoft PowerPoint真机门禁拆成两个彼此独立的副本。`save-only`副本只执行打开、保存、关闭和重开，不做任何交互改动；保存后重新运行Sanitizer、语义指纹、OOXML和视觉门禁。`interaction`副本在打开前必须与最终PPTX的SHA256完全相同，只用于文字、格式、组合、表格和图表等瞬时交互，完成后不保存直接关闭。若人工确实保存了任何交互改动，该副本不得再冒充最终文件，除非重新运行全部门禁并更新Release Manifest。
- 在`interaction`副本中跳到末页，确认没有修复提示或图表错误。抽查原生文本框，依次完成文字替换、字体颜色修改、加粗取消／恢复、字体族修改并逐项撤销；抽查形状填充色并撤销；再选中两个对象完成组合与取消组合。若文件包含表格、图表或SmartArt，还必须分别抽查表格单元格改色／取消加粗、图表标题或标签改色／取消加粗、图表数据编辑，以及SmartArt文字格式修改并撤销。选择文字时应局部拖选并确认字符级选区，未确认光标位于文本内时禁止使用全选快捷键，避免误选整页对象。任何一项不能直接操作，都不得以“对象可选中”替代真正可编辑结论。

修改Renderer、主题、Sanitizer、OOXML QA、对象命名或格式合同后，必须重建并回归`${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt/benchmarks/format-golden-deck`的6页Golden Deck。原始PPTX和回读再导出的PPTX都要通过格式合同、语义指纹、全页渲染与Visual Gate；基准通过仍不能替代Microsoft PowerPoint真机交互检查。

最后按`references/delivery-contract.md`生成`ksib-release-manifest/3.2`。非format-only任务必须显式提供冻结的Storyline、Content和Evidence文件；每个Gate还必须通过`--validator name=path`绑定本Skill登记的canonical校验脚本，Storyline同时绑定上游MBB校验器。Manifest会先确认最终文件是合法`.pptx` ZIP，并核对根`officeDocument`关系、Presentation Content Type、非空`sldId`、每个slide关系、真实slide part及其Content Type完全一致；再核对父版本SHA256、Design Tokens、Layout Matrix、逐页ID集合、跨门禁页数、逐页Renderer合同、最终PPTX哈希，以及Gate报告是否晚于其绑定输入并在本次Release启动前已经生成。使用fallback时必须提供版本化`renderer-usage`逐页说明实际Renderer和原因。所有模式必须把`powerpoint-render`列为required gate；只写`passed: true`、只有辅助PNG、重复标签、百分比精度不合规、金融折线平滑或Renderer漏字段都不能交付。

## 内容与演讲规则

- 管理者任命述职的10分钟正式讲述控制在600秒；研究报告与客户沟通Deck按用户指定时长，不套用该时长。
- Ghost Deck在上游锁定后才开始排版；制作阶段不得用Layout反向驱动内容。
- 结果页原则上一页一个主证据，直接在图表／表格附近标注关键发现；第二证据只有在共同证明同一标题时才保留。
- Action Title已经完整表达结论时，不再添加同义Subtitle或Takeaway。若Takeaway比Title更像结论，应将其提升为Action Title并删除原Takeaway。
- Action Title默认按页面类型生成：对象明确的档案／人物／产品页可用“对象：核心结论”，其他页面使用完整结论句；不得把冒号结构机械复制到全部页面。
- 关键战役页优先讲判断、取舍与影响，不讲执行流水账。
- 案例页优先讲“共同结论”，再讲差异证据。
- 管理页必须同时呈现目标拆解、过程机制、授权边界和复盘闭环。
- 任命匹配页同时保留优势、差距、风险和 90 天动作，避免只做自我表扬。
- 演讲者备注应能帮助讲述，人工复核时不得保留未出现在Evidence Contract中的新事实；当前语义指纹与Handoff不自动解析或证明Speaker Notes事实一致性。

## 参考原则

Mck仍是页面尺寸、安全边距、字号层级、动态间距、底栏位置、来源页码、容量与机读门禁的基础源。BCG参考模板只贡献较低且更稳定的Action Title纵向基线和7种证据主导Layout。PPTAgent贡献“参考结构抽象优先”和Content／Design／Coherence三维评估；PPT Master贡献Strategist与Executor分离及原生编辑边界；Academic PPTX Skill贡献一页一个主证据和communication-first原则。KSIB额外保留页眉、可选Subtitle、单一底部Takeaway、主题色板和OOXML原生可编辑性工程；只吸收方法，不复制外部项目的代码、模板、字体、颜色、图标、纹理或具体业务内容。完整来源见`references/source-provenance.md`。
