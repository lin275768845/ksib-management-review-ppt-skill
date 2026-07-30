# Storyline交接合同

## 最小JSON结构

```json
{
  "version": 1,
  "deckTitle": "管理者任命述职",
  "deckType": "appointment-review",
  "audience": {
    "primary": "任命委员会",
    "decisionRole": "判断候选人是否能承担拟任岗位",
    "knownConcerns": ["业务结果能否复制", "组织能力是否成熟"]
  },
  "decisionQuestion": "候选人是否已具备承担更大业务与组织责任的能力？",
  "desiredOutcome": "委员会认可任命匹配度及未来12个月计划",
  "governingThought": "候选人的责任已从项目结果扩展至经营机制和组织能力。",
  "storyArc": {
    "type": "appointment-review",
    "narrativeReadThrough": [
      "拟任岗位要求同时经营供给、转化、商家投入和组织复制。",
      "过去三阶段工作证明责任对象持续扩大。",
      "未来规划针对尚未解决的问题建立业务和组织闭环。"
    ]
  },
  "slides": [
    {
      "id": "II-2",
      "section": "工作回顾",
      "slideRole": "evidence",
      "purpose": "证明在UE约束下能够通过关键取舍制造峰值",
      "actionTitle": "重构目标、货盘与补贴机制，将有限UE兑换为峰值GMV",
      "proofQuestion": "峰值是否来自可解释的关键决策，而非单纯增加补贴？",
      "evidence": [
        {
          "claim": "峰值GMV达到已确认结果",
          "sourceRef": "source-black-friday-01",
          "status": "verified"
        }
      ],
      "implication": "具备复杂战役中的目标重构和实时决策能力。",
      "visualLogic": "decision-to-impact",
      "layoutHint": "campaign",
      "continuityFrom": "前页提出规模验证阶段的核心命题。",
      "continuityTo": "峰值无法替代日常经营，因此进入经营抓手建设。",
      "audienceObjection": "结果是否主要由补贴驱动？",
      "speakerNotes": ["先讲UE约束，再讲三项关键取舍，最后落到阶段验证。"],
      "sourceRefs": ["source-black-friday-01"],
      "actionTitleScore": 94,
      "verticalLogicScore": 92
    }
  ],
  "review": {
    "horizontalLogicScore": 92,
    "decisionReadinessScore": 88,
    "topObjections": [
      {
        "objection": "单点成功是否可以复制？",
        "responseLocation": "II-7及III部分"
      }
    ],
    "unresolvedCriticalIssues": []
  },
  "lockStatus": "draft"
}
```

## 字段规则

- `slideRole`允许：`cover`、`navigator`、`context`、`diagnosis`、`evidence`、`recommendation`、`plan`、`organization`、`reflection`、`closing`、`appendix`。
- `evidence[].status`允许：`verified`、`assumption`、`tbd`。
- `verified`必须提供`sourceRef`；`assumption`和`tbd`必须在页面或备注中显式标记。
- `visualLogic`描述证据形态，不描述装饰风格。推荐值：`comparison`、`trend`、`causal-chain`、`stages`、`system`、`portfolio`、`decision-to-impact`、`before-after`。
- `layoutHint`只是建议；PPT Skill可在不改变论证职责的前提下选择更合适的Layout。
- `lockStatus`允许：`draft`、`reviewed`、`approved_by_user`。

## 锁定规则

- 用户说“最终版／锁定／按这个制作”，可在完成事实边界检查后标记`approved_by_user`。
- 用户只批准局部章节时，拆分文件或保持全Deck为`reviewed`，不得假装整体已锁定。
- 锁定后若改变页面顺序、Action Title或证据含义，必须回到Storyline审阅并重新锁定。
