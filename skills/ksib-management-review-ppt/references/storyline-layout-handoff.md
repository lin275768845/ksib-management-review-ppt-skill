# Storyline到Layout的交接合同

## 1. 真相源优先级

新建或重构Deck按以下优先级执行：

1. 用户明确指令与锁定内容；
2. `storyline/storyline.json`中的页序、Action Title、Proof Question和证据含义；
3. 用户提供的品牌／母版与现有宏观Layout；
4. KSIB视觉系统；
5. Mck与BCG增强Layout合同。

低优先级不得改变高优先级。格式美化不能改变故事线。

## 2. 必须交接的逐页字段

| Storyline字段 | 制作阶段用途 | 不允许的变化 |
|---|---|---|
| `id` | 写入内容页`storylineId` | 不得重用或丢失 |
| `slideRole` | 锁定页面在论证中的角色与豁免边界 | Content必须逐页完全一致，不得自标methodology／closing |
| `actionTitle` | 页面主标题 | 不得为了适配版式改写 |
| `proofQuestion` | 判断页面内容是否足够 | 不得被第二个问题稀释 |
| `evidence[].claimId`／`claimIds[]` | 绑定Evidence Contract中的主张 | 不得换成另一组证据 |
| `implication` | 锁定管理含义；仅在允许的Layout中可渲染为Takeaway | 不得变成证据复述 |
| `visualLogic` | 选择Layout | 不得用装饰风格替代 |
| `continuityFrom/To` | 检查翻页关系 | 不得用Navigator掩盖断点 |
| `audienceObjection` | 决定是否需要边界／风险 | 详细回应可进入Notes |

制作阶段的结构化内容必须逐页回写`slideRole`、`proofQuestion`、`claimIds[]`、`implication`、`visualLogic`、`continuityFrom`、`continuityTo`和`audienceObjection`；使用`proofShape`时必须与锁定的`visualLogic`一致。交接门禁对上述字段逐项核对并纳入逐页语义哈希；只保持Action Title不变不足以通过。

`claimIds[]`只能引用已通过`validate_evidence.mjs`的Evidence Contract。Storyline证据必须显式填写`evidence[].claimId`；通用`evidence[].id`不被识别为Claim引用。不得把商品名、图表标题或任意来源字符串临时当作claim ID。

### Role×Layout豁免合同

| Layout | 唯一允许的`slideRole` | 可获得的结构豁免 |
|---|---|---|
| `cover` | `cover` | 语义、Evidence、Argument Tree |
| `toc`、`agenda`、`section`、`sectionDivider` | `navigator` | 语义、Evidence、Argument Tree |
| `appendixDivider` | `appendix` | 语义、Evidence、Argument Tree |
| `appendixProject` | `appendix` | Argument Tree |
| `appendixTable` | `appendix`、`methodology`或`scope_boundary` | Argument Tree；Evidence显式豁免另按角色、类型和理由合同 |
| `appendixQA` | `appendix`、`methodology`、`scope_boundary`或`legal_disclaimer` | Argument Tree；Evidence显式豁免另按角色、类型和理由合同 |
| `styleboardSystem`、`styleboardDensity` | `navigator` | 语义、Evidence、Argument Tree |
| 其他实质Layout | `context`、`diagnosis`、`evidence`、`recommendation`、`plan`、`organization`、`reflection`、`closing`、`executive_summary`、`methodology`、`scope_boundary`或`legal_disclaimer` | 无默认豁免 |

豁免必须同时满足Layout和Role。把`slideRole=evidence`的页面改成`cover`，或把实质页改名为章节页，Content、Evidence、Handoff与Argument Tree四层门禁都会阻断；不能只看Layout名称决定豁免。

## 3. Deck级论证树

新建或重构的正式Deck在用户锁定前必须补齐`argumentTree`：

```json
{
  "argumentTree": {
    "rootStatement": "与governingThought完全一致",
    "pillars": [
      {
        "id": "P1",
        "statement": "支撑论点",
        "supportLogic": "为什么该论点支持根结论",
        "slideIds": ["S3", "S4"],
        "claimIds": ["CLM_01", "CLM_02"]
      }
    ]
  }
}
```

- 多页实质内容使用2–4个支撑论点；单一实质内容页可使用1个。
- 每张非封面、导航、章节页和附录页必须且只能归入一个Pillar；结尾页默认也是实质内容页，不自动豁免。
- 显式豁免只允许`executive_summary`、`methodology`、`scope_boundary`或`closing`角色，并分别使用`cross_pillar_synthesis`、`method_boundary`、`scope_boundary`或`cross_pillar_synthesis`作为`argumentTreeExemptType`，同时填写至少12个字符的具体`argumentTreeExemptReason`。
- 豁免页不得引入Pillar之外的新Claim；`executive_summary`至少综合两个既有Claim。核心证据页不能靠自由填写理由跳出论证树。
- 每个Pillar的`claimIds[]`必须与其`slideIds[]`中的证据Claim并集完全一致。
- `rootStatement`必须与`governingThought`一致，不能在制作阶段另写一个更方便排版的版本。
- 结构门禁只能证明论点、页面和证据没有断链；MECE程度、因果充分性和商业判断仍需人工评审。

## 4. Proof Shape到Layout

| Proof Shape | Canonical Layout | 可编辑视觉子型／适用条件 |
|---|---|---|
| `comparison` | `twoColumn`、`horizontalMatrix`、`tableInsight`、`businessShift`、`casePortfolio`、`threeColumn`、`fourColumn`、`processModeMatrix`、`reflectionEvolution`、`scorecard`、`appendixTable` | 两组对象或两个时期同口径比较；before-after是视觉子型 |
| `trend` | `singleExhibit`、`timeline`、`evidenceInsight` | line／bar／waterfall是`singleExhibit`图表子型；只有阶段里程碑才使用`timeline` |
| `causal-chain` | `issueTree`、`problemSolutionMap`、`valueChain`、`funnel`、`orgManagement`、`strategyEnablers` | 需要解释为什么或如何传导 |
| `stages` | `recommendationRoadmap`、`phasePlaybook`、`horizontalEvolution`、`timeline`、`businessShift`、`threeColumn`、`fourColumn`、`funnel`、`productCommercialization`、`reflectionEvolution` | 阶段存在顺序、递进或门槛 |
| `system` | `layeredOperatingModel`、`valueChain`、`orgManagement`、`processModeMatrix`、`productCommercialization`、`strategyEnablers` | 多层能力共同驱动结果；cycle是可编辑视觉子型 |
| `portfolio` | `horizontalMatrix`、`tableInsight`、`casePortfolio`、`threeColumn`、`fourColumn`、`scorecard`、`appendixTable` | 多对象需要排序、分组或取舍；2×2／bubble是可编辑视觉子型 |
| `decision-to-impact` | `campaign`、`recommendationRoadmap`、`evidenceInsight`、`casePortfolio`、`productCommercialization`、`scorecard`、`appendixProject` | 关键判断如何传导到结果 |
| `single-exhibit` | `singleExhibit`、`evidenceInsight`、`appendixProject`、`appendixTable`、`appendixQA` | 一张证据、表格或直接回答足以证明标题 |

若同时出现多个Proof Shape，先拆页或确定主次；不得把多个同权主视觉塞在一页。
line、bar、waterfall、bubble、cycle、2×2等不得直接写成`slideType`；它们必须作为canonical Layout中的图表或图形子型，并保留原生可编辑性。
`validate_storyline_handoff.mjs`会按`layout-matrix.json`的`proofShapeToLayouts`检查Visual Logic与Layout兼容性；不存在映射是阻断错误，必须先补合同，不能以自由拼版绕过。

Storyline锁定后先运行`validate_storyline_gate.mjs`；该包装门禁输出`ksib-storyline-gate/1.0`，同时记录Storyline、包装器和上游`linzhe-mbb-storyline` Validator的SHA256。交接报告使用`ksib-storyline-handoff/2.0`，记录Storyline、Content、Layout Matrix与当前Handoff Validator的SHA256；Release Manifest会核对所有报告来自同一冻结快照和当前校验器版本。

## 5. 参考Deck抽象

参考Deck审计先抽取：

- 页面功能类型；
- 内容Schema与阅读顺序；
- 标题和主体几何；
- 证据与洞见的空间关系；
- 可复用的母版资产。

不直接复制：

- 参考Deck的业务结论、数字、来源；
- 未经批准的Logo、图标和图片；
- 与KSIB冲突的颜色、字体和装饰；
- 无法保持原生编辑性的全页截图。

## 6. 三维交付门禁

- `Content`：Action Title、Proof Question、claim IDs、Implication、Visual Logic、Continuity From／To和Audience Objection与锁定Storyline一致；所有claim IDs通过Evidence Contract。
- `Design`：几何、字号、留白、容量、原生编辑性通过。
- `Coherence`：Governing Thought到2–4个支撑论点、页面和Claim的论证树完整；页序、转场、视觉语法和章节节奏与Ghost Deck一致。

任何一维失败都不得用另外两维抵消。
