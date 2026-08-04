---
name: linzhe-mbb-storyline
description: Build, review, and lock decision-led MBB-style storylines before slide production. Use for Chinese or English management reviews, appointment reviews, strategy decks, board prereads, business recommendations, transformation plans, and any request involving SCQA/SCR, Pyramid Principle, Ghost Decks, action titles, horizontal logic, vertical proof, evidence traceability, audience objections, or speaker narrative. Also use when an existing deck feels fragmented, repetitive, descriptive rather than decisive, or visually polished but logically weak. Do not use for formatting-only work where the user has frozen all content.
---

# 林哲 MBB Storyline

## 目标

先把演示文稿变成一条可验证的决策论证，再交给PPT制作Skill。输出不是“内容大纲”，而是经受众、Ghost Deck、证据和异议门禁检验的Storyline合同。

保持以下边界：

- 人拥有最终故事线、业务事实、承诺和取舍。
- 本Skill可以诊断、提出备选和重写建议；未经授权，不把建议当成最终结论。
- 不补造事实、数字、归因或管理承诺。缺失内容标记为`[TBD]`、`[假设]`或`[待验证]`。
- 用户明确要求“只改格式／不改内容”时，不触发故事线重构。
- 故事线锁定后，PPT制作Skill不得擅自改变Action Title、页面顺序或证据含义。

## 开始前读取

1. 读取仓库`AGENTS.md`及用户给出的内容、证据和边界。
2. 完整读取`references/frameworks-and-rubric.md`，选择适合任务的论证架构和评分规则。
3. 需要创建可交接文件时读取`references/storyline-contract.md`。
4. 需要说明方法来源或更新本Skill时读取`references/source-provenance.md`。
5. 若上游已提供`ksib-intake-gate/1.0`报告或项目级Intake任务JSON，先读取并复用已确认的受众、场合、决策、时长、页数、证据范围和禁区；只补缺失或冲突项，不重复提问。Intake原始答案仍按隐私边界处理，不复制到无关日志。

## 工作模式

先判断任务属于哪一种：

- `build`：从材料建立新故事线。
- `review`：审阅既有目录、Action Titles或完整Deck。
- `repair`：保留事实和核心结论，修复断裂、重复、缺证据或错位页面。
- `lock`：用户已确认故事线，只补齐证据合同、口播和交接字段。
- `format-only`：不改任何内容；停止本Skill，转交PPT制作Skill。

## 六阶段工作流

### S1 决策简报

优先从已通过的KSIB Intake Gate读取，只有缺失或冲突时再明确：

- 受众是谁、拥有何种决策权；
- 演示结束后希望受众相信、决定或授权什么；
- 最关键的决策问题是什么；
- 时长、页数、必须回答的问题与禁区；
- 已知事实、假设、观点和未确认项。

输出`storyline/brief.md`。把“汇报主题”改写为一个能被回答的决策问题。

### S2 Governing Thought与故事弧

先写一句Governing Thought，再选择一种主架构：

- 推荐／决策：Situation → Complication → Resolution → Ask。
- 诊断／复盘：Context → Evidence → Root Cause → Implication → Action。
- 管理者述职：Role Mandate → Accumulated Evidence → Business Judgement → Future Plan → Organization Fit。
- 转型规划：Why Change → Where to Play → How to Win → Enablers → Roadmap。

只选一个主弧。章节可以使用子SCQA，但不得同时并列多套主框架。

### S3 Ghost Deck

先只写页面Action Titles，不写正文。逐页记录：

- 页面在论证中的职责；
- Action Title；
- 与前页的逻辑关系；
- 本页要回答的Proof Question；
- 下一页为何自然发生。

把全部标题连读成3–5句Narrative Read-through。若只读标题不能理解完整故事，先修标题和顺序，不进入内容扩写。

Action Title必须：

- 是完整结论，不是主题标签；
- 回答“So what”；
- 使用主动、具体、可证实的表达；
- 中文原则上18–32字，最多38个加权字符；英文原则上不超过15词；内容页标题不得包含硬换行，交接到PPT Skill后必须保持单行；
- 不超出证据强度，不把假设写成事实；
- 同类页面保持平行句式。

### S4 Slide Proof Contract

为每张实质内容页定义一份证据合同：

- `proofQuestion`：本页必须证明什么；
- `evidence`：最强证据、支持证据及其来源；
- `implication`：证据对受众决策意味着什么；
- `visualLogic`：比较、趋势、因果、阶段、系统、组合或取舍；
- `audienceObjection`：最可能的反驳；
- `speakerNotes`：只补充讲述顺序，不新增无来源事实。

每个正文元素必须证明Action Title，而不只是“与标题有关”。结果页原则上一页一个主证据；确需多个证据时，它们必须共同回答同一个Proof Question。

### S5 横向、纵向与决策准备度审阅

按`references/frameworks-and-rubric.md`评分：

- Action Title ≥90；
- Horizontal Logic ≥90；
- 每页Vertical Logic ≥90；
- Decision Readiness ≥85；
- 严重未解问题为0。

执行三次读法：

1. 只读标题：故事是否完整、无断点、无重复；
2. 标题＋证据：每页内容是否让标题成为必然结论；
3. 站在受众立场：是否回答了最大的异议和决策条件。

### S6 锁定与交接

将结果写入`storyline/storyline.json`，运行：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs" \
  --storyline storyline/storyline.json \
  --report storyline/gate.json
```

用户确认后，把`lockStatus`设为`approved_by_user`，再运行：

```bash
node "${CODEX_HOME:-$HOME/.codex}/skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs" \
  --storyline storyline/storyline.json \
  --report storyline/gate.json \
  --require-lock
```

只有`gate.json`中`passed: true`且`productionReady: true`，才交给PPT制作Skill。不得口头宣布门禁通过。

## 输出合同

向用户展示：

1. 一句话Governing Thought；
2. 3–5句Narrative Read-through；
3. Ghost Deck表：页码、Action Title、页面职责、核心证据、置信度；
4. 关键修改：删除、合并、前移、后移及原因；
5. 最大异议和回应；
6. 门禁结果与仍待用户确认的事项。

向制作Skill交付`storyline/storyline.json`，其中每页至少包含：

- `id`、`section`、`slideRole`、`purpose`；
- `actionTitle`、`proofQuestion`、`evidence`、`implication`；
- `visualLogic`、`layoutHint`；
- `continuityFrom`、`continuityTo`；
- `audienceObjection`、`speakerNotes`、`sourceRefs`；
- `actionTitleScore`、`verticalLogicScore`。

## 强制规则

- Ghost Deck先于页面内容和Layout。
- 先锁定“为什么存在这页”，再决定“这页长什么样”。
- 一页只承担一个论证职责；一个证据不得被多页重复使用来证明同一件事。
- 执行摘要必须综合结论，不得成为目录的文字版。
- 章节Navigator只负责切换，不承担新论点。
- 结尾必须回到受众需要做出的判断、授权或记住的结论。
- 任命述职不能只展示战功；必须同时证明业务判断、责任扩张、未解问题、未来计划和组织匹配。
- 用户材料中的事实与建议分开标记；来源不明的数字不得进入`verified`证据。
- 不用“MECE”“Pyramid”“SCQA”等术语替代真实论证。

## 与KSIB PPT Skill的关系

- 新建、重构或大幅改写Deck：先运行本Skill，再运行`ksib-management-review-ppt`。
- 用户提供“最终版／锁定版Storyline”并要求制作为PPT：使用`lock`模式完成最小合同和门禁，不擅自重写。
- 只改Layout、字体、页眉、页码、主题色或可编辑性：跳过本Skill，直接使用`ksib-management-review-ppt`并冻结内容指纹。
