# KSIB Intake Contract

`references/intake-contract.json`是PPT任务入口的机读真相源。当前版本为`ksib-intake-contract/1.1`。它统一PPT Studio与Skill的模式、问题、默认值、触发条件和固定保护规则，避免前端、服务端和Skill各自维护一套含义不同的默认值。

## 1. 两层模式

用户只选择三种互斥任务类型：

| 外部任务类型 | 用户含义 | Skill内部执行模式 |
|---|---|---|
| `topic-to-deck` | 从研究Topic新建Deck | `story-change` |
| `story-rebuild` | 基于现有PPT重构故事线、页序或结构 | 默认`story-change` |
| `format-only` | 冻结内容，只修改格式与Layout | `format-only` |

`locked-content`继续作为内部执行状态，不增加第四个用户选项。若`story-rebuild`任务明确提供已锁定故事线或最终内容，并禁止改写结论、页序和证据含义，Skill在Intake完成后把内部执行模式派生为`locked-content`。

## 2. 两步Clarify

1. 先只确定任务类型。
2. 再按所选模式处理最多9个问题；连同任务类型，总数不超过10个。

`required_level`只有三个合法值：

- `required`：没有显式答案即阻断；不能用默认值自动满足。
- `visible_optional`：与必填项一起主动展示选项和默认值；它不阻断门禁，用户可回复“其余按默认”或只覆盖有异议的项目。Skill仍须在采用前把默认值展示出来。
- `conditional`：触发条件未成立时视为选填；触发后按必填处理且不能由默认值静默满足。

UI只显示“必填／选填”两类标签。激活后的`conditional`显示为“必填”；重要选填直接展示，其他高级项才折叠。

Skill必须一次性输出缺失与冲突清单，不逐题进行9轮问答。字体不单独占用问题：新建和重构默认使用苹方-简，format-only默认保留原字体；提示用户如需其他字体可明确指定。

## 3. 答案来源与去重

答案优先级固定为：

`user → workbench → default`

用户在当前任务中的最新明确回答可以覆盖工作台旧值；其余情况下复用工作台答案，不得重复询问。Skill读取项目级任务JSON、PPT Studio `manifest.json`或用户在当前对话中的明确回答，只对以下两类内容发起Clarify：

- 仍然缺失且会阻断的必填／已触发条件项；
- 与模式保护规则、用户最新指令或其他答案发生冲突的项。

默认值不能替代修改授权。尤其是format-only的冻结确认、字体改变、主题改变和样式授权，必须有显式用户或可信工作台来源。

## 4. 项目级任务JSON

建议PPT Studio在现有`task.md`和`manifest.json`之外生成一个最小任务JSON，或在manifest根部补齐以下字段：

```json
{
  "intake_contract_version": "ksib-intake-contract/1.1",
  "page_intent_contract_version": "ksib-page-intent-contract/1.0",
  "theme_color_contract_version": "ksib-theme-color-contract/1.0",
  "mode": "format-only",
  "answers": {
    "format_source_presentation": "/absolute/path/source.pptx",
    "format_authorized_scope": "geometry-only",
    "format_content_freeze_confirmation": true
  },
  "answer_sources": {
    "format_source_presentation": "workbench",
    "format_authorized_scope": "user",
    "format_content_freeze_confirmation": "user"
  },
  "config": {},
  "inputs": []
}
```

每个问题必须包含以下字段：

```text
question_id
applies_to_modes
question
required_level
default_value
choices
trigger_condition
blocking_when_missing
answer_source
```

固定安全规则存放在`guardrails[]`，不伪装成问题，也不占用10问预算。

## 5. 页面意图合同

新建与重构任务在9个模式问题预算内复用Layout相关问题，不额外增加一轮问答。工作台把以下默认值写入机读任务合同：

```json
{
  "actionTitlePolicy": "auto-conclusion",
  "subtitlePolicy": "boundary-only",
  "bodyToBottomBandGapIn": 0.3
}
```

每张实质内容页必须把用户意图转为`pageIntent`：唯一问题、Action Title表达策略、必需内容、主证据、视觉层级和验收条件。人物、产品、业务单元等对象明确的页面可选择`subject-colon-conclusion`，使用“对象：核心结论”；其他页面默认由页面角色生成完整结论句。Subtitle只有在范围、时期、方法、定义、边界或比较框架增加新信息时才使用。

主题问题必须同时登记主色和对比辅色。默认主色为`#FF4906`、对比辅色为`#006B8F`；自定义主题按`ksib-srgb-mix/1.0`生成深／主／浅／极浅主色阶。这里确认的是色板输入，不是授权Renderer随意用色；生产阶段仍必须遵守`theme-color-contract.json`中的角色、用途和逐页登记规则。

## 6. 运行门禁

```bash
node scripts/validate_intake.mjs \
  --task task.json \
  --report intake-gate.json
```

验证器接受项目级任务JSON，也兼容读取PPT Studio当前`manifest.json`的`mode`、`config`、`inputs`和`references`。报告只输出问题ID、状态、答案来源、默认值使用情况和输入文件哈希；不回显完整用户答案。

只有`passed: true`时才能进入Evidence、Storyline或format-only语义指纹流程。新建与重构固定经过：

`intake complete → evidence registry → storyline draft → user lock → production`

Storyline Skill读取已通过的Intake Gate，只补真正缺失或冲突的信息，不再次询问已确认的受众、决策、时长、页数和禁区。

## 7. 上游兼容性

PPT Studio应声明它支持的`intake_contract_version`。若Intake版本缺失或不等于`ksib-intake-contract/1.1`，或新建／重构任务缺少`ksib-page-intent-contract/1.0`与`ksib-theme-color-contract/1.0`，Skill不得把任务描述为“Intake已完成”；应返回一次性兼容性清单。

若上游仍采用“复制`task.md`后粘贴给Codex”的链路，Markdown至少必须写入`intake_contract_version`，并提供该job的`manifest.json`安全路径或嵌入最小任务JSON。只有自然语言配置、但没有版本和可机读入口时，Skill可以读取其作为上下文，却不能据此宣布Intake Gate已通过。

工作台浏览器样张仍只是配置预览，不是Skill Renderer或Golden Deck的视觉证据。真实视觉验收继续由Golden Deck、最终PPTX、全页PNG和PowerPoint真机门禁承担。
