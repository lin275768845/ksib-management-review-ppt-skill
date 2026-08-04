# PowerPoint Render Contract

本合同定义最终视觉真相源。Microsoft PowerPoint真机渲染高于PDF、LibreOffice、Artifact Tool和其他辅助渲染器；后者只能用于构建期预览和交叉检查，不能单独证明可交付。

## 1. 两类视觉证据

- `Visual Gate`：绑定辅助全页PNG，帮助尽早发现重叠、裁切和意外换行。
- `PowerPoint Render Gate`：绑定最终PPTX、PowerPoint逐页截图、逐页审阅证据和OOXML实现检查，是Release Manifest的必需阻断门禁。

PowerPoint与辅助渲染器出现明显差异时，页面不得通过。差异必须先修复，再重新截图和复核；不得通过填写`passed: true`覆盖。

## 2. PowerPoint审阅输入

```json
{
  "schemaVersion": "ksib-powerpoint-review/1.0",
  "source": "Microsoft PowerPoint",
  "pptxSha256": "<sha256>",
  "reviewedBy": "reviewer",
  "reviewerRole": "independent",
  "reviewedAt": "2026-08-03T12:00:00Z",
  "slides": [
    {
      "slide": 1,
      "screenshot": "slide-1.png",
      "reviewedAt": "2026-08-03T11:58:00Z",
      "checks": {
        "fullSize100": true,
        "reducedScale": true,
        "noOverlap": true,
        "noClipping": true,
        "noUnexpectedWrap": true,
        "labelOwnership": true,
        "numberDisplay": true,
        "layoutContract": true
      },
      "issues": [],
      "notes": "分类轴、数据标签与外部标注逐项核对完成。"
    }
  ]
}
```

`reviewerRole`为`builder`时，每页`notes`必须记录具体复核内容；同一人构建和审阅不能只提交空白清单。

运行：

```bash
python3 scripts/validate_powerpoint_render.py \
  --pptx outputs/client-delivery.pptx \
  --content work/content.json \
  --format-contract work/format-contract.json \
  --review-json work/qa/powerpoint-review.json \
  --screenshot-dir work/qa/powerpoint-screenshots \
  --output work/qa/powerpoint-render-gate.json
```

## 3. 标签唯一归属

同一个类别名、系列名、图表标题或数值只能由一种对象负责：原生坐标轴／数据标签／图例／图表标题，或外部文本框。原生分类轴仍显示且外部文本框重复同一类别名时直接失败；原生数据标签与外部数值标签重复时同样失败。

若采用外部直接标签，应在图表本身关闭对应原生标签。对象名称不能替代实际状态；Validator读取最终PPTX的Chart XML和页面文本。

## 4. 图表数字合同

含百分号的图表必须在`format-contract.json`声明语义：

```json
{
  "chartSemantics": [
    {
      "slide": 2,
      "chart": "chart1.xml",
      "measureKind": "percent",
      "precision": 0
    },
    {
      "slide": 3,
      "chart": "chart2.xml",
      "measureKind": "percentage-point",
      "precision": 1,
      "precisionReason": "绝对值小于1个百分点，整数化会掩盖方向差异"
    }
  ]
}
```

- 默认`precision: 0`；底层数据和Evidence保留原精度。
- 只有整数化会掩盖关键差异、值小于1%或监管口径要求时才允许`precision: 1`，并必须说明原因。
- 同一图表的坐标轴与数据标签必须使用同一精度。
- `percent`与`percentage-point`必须显式区分。
- 金融时间序列的折线不得设置`smooth=true`。

## 5. Renderer实现合同

Content声明Layout不等于页面已经正确渲染。`phasePlaybook`必须有3–4个阶段，并逐阶段渲染标题、共同逻辑行、判断标准和行动：

```json
{
  "renderValidation": {
    "slides": [
      {
        "slide": 5,
        "layout": "phasePlaybook",
        "rows": [
          { "field": "phases[].title", "objectNames": ["phase-1-title", "phase-2-title", "phase-3-title"] },
          { "field": "phases[].logic", "objectNames": ["phase-1-logic", "phase-2-logic", "phase-3-logic"] },
          { "field": "phases[].successCriterion", "objectNames": ["phase-1-criterion", "phase-2-criterion", "phase-3-criterion"] },
          { "field": "phases[].action", "objectNames": ["phase-1-action", "phase-2-action", "phase-3-action"] }
        ]
      }
    ]
  }
}
```

Validator逐项核对对象名和最终文字。把`phasePlaybook`做成只有三个节点的普通时间线、遗漏判断标准或合并后丢失字段，都会阻断。

## 6. Release约束

`powerpoint-render`必须列入所有交付模式的required gates。它必须绑定当前PPTX哈希、Content哈希、Format Contract哈希和PowerPoint逐页截图集合哈希。任何一个检查项失败，Release Manifest都必须为`blocked`。
