# Certified Layout System：从语义Layout到确定性成片

## 1. 目的

现有Storyline、Proof Shape和Layout Matrix解决“这一页应采用什么证明结构”，但不能单独决定正文对象的精确坐标、组件、字号和溢出行为。Certified Layout System补齐以下执行链：

```text
Storyline Lock
  → canonical Layout
  → certified variant
  → content-to-slot binding
  → resolved render plan
  → deterministic builder
  → final PPTX layout fidelity gate
```

正式PowerPoint母版`templates/KSIB_MBB_Master_v1.0.potx`负责Theme、Chrome、标题、页脚和基础Placeholder；复杂正文由Certified Layout Registry负责。两者读取同一份Design Tokens，不能互相替代。

母版包含8个基础Profile：Cover、Navigator、Section Divider、Content Title Only、Content Title＋Subtitle、Appendix Divider、Appendix Title Only、Appendix Title＋Subtitle。母版不把12类复杂正文Layout伪装成PowerPoint Placeholder；复杂正文继续由Variant、Slot与确定性Renderer落地。

## 2. 当前认证范围

当前Certified Core覆盖12类MBB高频正文版式、18个固定Variant：

| Layout | 已认证Variant | 典型用途 |
| --- | --- | --- |
| `executiveSummary` | `three-pillar-standard` | 决策摘要、3项支柱、明确Ask |
| `singleExhibit` | `full-width-chart`、`full-width-table` | 单一主证据全宽展示 |
| `evidenceInsight` | `right-panel-standard`、`right-panel-subtitle`、`bottom-panel-standard` | 证据与管理含义一一对应 |
| `tableInsight` | `right-panel-standard` | 原生表格＋右侧洞察 |
| `sideBySide` | `balanced` | 两方案取舍 |
| `structuredComparison` | `three-column`、`four-column` | 三／四对象同构比较 |
| `matrix2x2` | `quadrant-standard` | 价值×可行性等双维判断 |
| `issueTree` | `three-branch` | 三个MECE分支 |
| `problemSolutionMap` | `three-row` | 问题—行动—结果逐行对应 |
| `processValueChain` | `four-stage`、`five-stage` | 端到端流程／价值链 |
| `phasePlaybook` | `three-stage`、`four-stage` | 共同逻辑、判断标准、行动递进 |
| `recommendationRoadmap` | `four-phase` | 建议、里程碑、Owner／条件 |

Render Plan直接驱动Artifact Tool生成原生图表、原生表格、可编辑复合面板和附着连接线。只有注册表中的Layout／Variant可以使用“Certified Layout”表述；其他Layout仍按`layout-matrix.json`和现有Renderer合同执行，并如实标记为非Certified。

## 3. 四份真相源

- `powerpoint-master-contract.json`：基础Profile、母版与Renderer职责边界、模板版本；
- `certified-layout-registry.json`：页面Region、Slot、Variant、容量和模式相关Overflow Policy；
- `component-registry.json`：每个Slot允许的原生组件类型；
- `typography-roles.json`：组件可使用的字体角色，Renderer不能自由输入字号。

以上合同共同引用`design-tokens.json`。任何构建器都必须读取这些机读文件，不得把坐标复制到Prompt后再由LLM解释；Renderer输出必须记录`templateVersion`和`designTokensVersion`。

母版构建与结构门禁：

```bash
node scripts/build_powerpoint_master.mjs
python3 scripts/validate_powerpoint_master.py --report templates/master-gate.json
```

`.potx`必须包含0张样张、8个KSIB基础Profile和动态页码字段；样板库必须包含8张可编辑样张。两者的Theme Font、固定Chrome原始EMU几何和Profile清单必须与合同一致。

## 4. Render Plan Lock

Storyline锁定后、PPTX构建前，创建`ksib-render-plan-input/1.0`：

```json
{
  "schemaVersion": "ksib-render-plan-input/1.0",
  "executionMode": "story-change",
  "slides": [
    {
      "slide": 7,
      "storylineId": "S07",
      "layoutId": "evidenceInsight",
      "variantId": "right-panel-standard",
      "headerProfile": "content-title-only",
      "slotBindings": {
        "mainExhibit": { "componentId": "native-chart", "objectName": "S07-main-exhibit" },
        "insightPanel": { "componentId": "insight-panel", "objectName": "S07-insight-panel" },
        "insightTitle": { "componentId": "insight-title", "objectName": "S07-insight-title" },
        "insightLead": { "componentId": "insight-lead", "objectName": "S07-insight-lead" },
        "insightItems": { "componentId": "insight-list", "objectName": "S07-insight-items", "itemCount": 3 }
      }
    }
  ]
}
```

解析命令：

```bash
node scripts/resolve_render_plan.mjs \
  --input work/render-plan-input.json \
  --output work/render-plan.json
```

输出`ksib-render-plan/1.0`绑定版式、组件与字体注册表的SHA256，并记录母版与Design Tokens版本；再将每个Slot解析为确定的英寸与EMU坐标、组件类型、字体角色和稳定对象名。LLM只能选择合法Variant和填充结构化内容，不得直接生成正文`x/y/w/h`或任意字号。

## 5. 模式相关溢出合同

- `story-change`：先压缩尚未锁定的文案，再切换已批准Variant、拆页，最后阻断；
- `locked-content`：只能切换已批准Variant，经授权后拆页，否则阻断；
- `format-only`：不压缩文案、不改页序、不静默拆页，只能使用保持语义的兼容几何，否则阻断。

任何模式都禁止用临时缩字号、越过Region、新增自由文本框或移动安全边界解决超载。

## 6. 构建器合同

构建器接收：

- `layoutId`；
- `variantId`；
- `slotBindings`；
- 结构化内容；
- Theme Tokens。

构建器负责：

- 坐标与尺寸；
- Padding与Gap；
- 字体角色；
- 原生对象类型；
- 稳定对象名；
- 溢出阻断。

当前Skill仍允许系统Presentations／Artifact Tool或项目内已验证构建器，但只要页面声明为Certified Layout，构建器就必须消费已解析Render Plan并按稳定对象名落地，不能退回自由拼版。

当前已认证入口：

```bash
node scripts/render_certified_layout.mjs \
  --render-plan work/render-plan.json \
  --content work/certified-render-content.json \
  --output work/final.pptx
```

内容必须符合`references/certified-render-content.schema.json`的`ksib-certified-render-content/2.0`封装，并通过Renderer针对每类Layout执行的严格字段、数量和容量校验。图表分类名称由原生分类轴唯一负责，数值由原生数据标签唯一负责；百分比展示固定为整数。`phasePlaybook`必须逐阶段落地共同逻辑、判断标准和行动，`recommendationRoadmap`必须逐阶段落地建议、里程碑和Owner／条件。任何内容数量、Storyline ID、Header Profile或Slot绑定不一致都在写PPTX前阻断。

图表、表格和可编辑图形是复合组件，外层Slot只检查组件类型与几何；其内部标题、标签、表头和正文存在多种合法字号，必须继续运行各自的Chart／Table／Diagram合同，不得把整个复合对象错误地按单一字号验收。只有`insightTitle`、`insightLead`、`insightItems`等明确文字Slot由Layout Fidelity Gate直接核对Typography Role。

## 7. Layout Fidelity Gate

```bash
python3 scripts/validate_layout_fidelity.py \
  --pptx output/final.pptx \
  --render-plan work/render-plan.json \
  --output work/gates/layout-fidelity.json
```

`ksib-layout-fidelity-gate/1.0`检查：

- 当前Registry、Component和Typography Hash是否与Render Plan一致；
- 每个必需对象是否唯一存在；
- 对象类型是否匹配Slot；
- Region和Slot几何是否匹配；
- 字体是否使用登记角色；
- 列表是否真实渲染约定项目数；
- Certified正文区域是否出现计划外自由对象。

固定Region与Slot使用0 EMU；图表内部标签、表格内部行高等组件内部动态对象不作为页面级自由对象展开，但仍需通过对应Chart／Table和PowerPoint视觉门禁。

## 8. Studio Wireframe

PPT Studio通过本地API读取当前安装Skill的`certified-layout-registry.json`并渲染Wireframe。它不维护第二份坐标，也不允许用户编辑x/y/w/h。Registry缺失或版本不可解析时，Studio应明确显示“已认证版式不可用”，不得退回手写样张后继续声称预览来自Skill合同。

## 9. 扩展门槛

新增Certified Layout前至少提供：

1. 稀疏内容；
2. 标准内容；
3. 最大容量；
4. 超容量阻断；
5. Render Plan解析测试；
6. Layout Fidelity回归；
7. PowerPoint真机Golden Slide截图。

`benchmarks/certified-layouts/core-library`提供可重复构建的36页Golden Library：12类Layout分别覆盖稀疏、标准和最大容量状态，并在每次构建后运行OOXML、Layout Fidelity、溢出与逐页视觉门禁。原有`evidence-insight`三页夹具继续作为最小纵切回归。

辅助PNG只用于逐页视觉检查；正式客户交付仍必须补Microsoft PowerPoint逐页截图与交互验收。Golden Library通过辅助渲染器不等于已经取得PowerPoint真机最终证明。
