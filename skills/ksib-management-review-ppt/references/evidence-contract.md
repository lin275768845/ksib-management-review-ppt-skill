# Evidence Contract：从来源到账页结论的可追溯合同

## 1. 目的

Evidence Contract用于锁定一条可审计的证据链：

```text
已核验来源 sources[]
  → 可复算计算 calculations[]
    → 客户可见结论 claims[]
      → 页面 slides[].claimIds[]
```

它解决的不是“脚注有没有写”，而是以下四个问题：

1. 每个页面结论来自哪里；
2. 每个数字如何计算、使用什么时期、单位、分母和数据版本；
3. 品牌份额是否把未识别品牌GMV纳入分母；
4. 数据、计算、结论与页面之间是否存在缺失引用或孤儿对象。

Evidence Contract应在生成PPT之前完成，并与锁定的Content JSON一起进入门禁。仅有自然语言脚注不能替代本合同。

## 2. 顶层结构

```json
{
  "contractVersion": "1.0",
  "deckId": "example-market-study",
  "policies": {
    "brandShareDenominator": "all_sample_including_unidentified"
  },
  "sources": [],
  "calculations": [],
  "claims": []
}
```

当前Validator只接受`contractVersion: "1.0"`。`sources[]`、`calculations[]`、`claims[]`必须存在且为数组。三个数组中的所有`id`必须全局唯一，推荐分别使用`SRC_`、`CAL_`、`CLM_`前缀。页面与Storyline只能通过明确的`claimIds[]`或`evidence[].claimId`引用Claim；通用`evidence[].id`不构成Claim引用。

`period`允许两种合同：

- 非空描述字符串，例如`"12周周榜"`；如包含日期，日期必须为真实存在的`YYYY-MM-DD`且起止顺序正确；
- 结构化对象：`{"asOfDate":"2026-07-20"}`，或同时提供`startDate`和`endDate`。

Source的`verifiedAt`必须为真实日期，且不能早于Source期间结束日；Calculation期间不得超出任一输入对象的期间范围。

## 3. Source合同

```json
{
  "id": "SRC_PLATFORM_A_V1",
  "title": "平台A品类与价格带分析",
  "sourceType": "internal_dataset",
  "locator": "platform_a_analysis_v1.xlsx",
  "period": "8周榜单",
  "dataVersion": "V1.0审计版",
  "verificationStatus": "verified",
  "verifiedAt": "2026-07-20",
  "verificationMethod": "与商品汇总底表重算并交叉核对"
}
```

| 字段 | 要求 |
|---|---|
| `id` | 必填；全局唯一 |
| `title` | 必填；读者可理解的来源名称 |
| `sourceType` | 必填；如`internal_dataset`、`external_dataset`、`report`、`webpage`、`interview` |
| `locator` | 必填；文件、URL或可定位的资源地址 |
| `period` | 必填；数据覆盖期或资料对应期 |
| `dataVersion` | 必填；文件版本、发布日期或访问快照 |
| `verificationStatus` | 必须为`verified` |
| `verifiedAt` | 必填；`YYYY-MM-DD` |
| `verificationMethod` | 必填；说明如何核验，而不是只写“已检查” |

来源处于`draft`、`unverified`或其他状态时，客户交付门禁失败。

## 4. Calculation合同

```json
{
  "id": "CAL_PLATFORM_A_CR5",
  "label": "平台A品牌CR5",
  "metricType": "brand_concentration",
  "formula": "top5_gmv / all_sample_gmv",
  "inputs": [
    {
      "name": "top5_gmv",
      "sourceId": "SRC_PLATFORM_A_V1",
      "locator": "商品汇总：按品牌汇总后Top5 GMV之和"
    },
    {
      "name": "all_sample_gmv",
      "sourceId": "SRC_PLATFORM_A_V1",
      "locator": "商品汇总：全量商品GMV之和"
    }
  ],
  "period": "8周榜单周均",
  "unit": "%",
  "denominator": {
    "name": "全样本GMV",
    "scope": "all_sample",
    "includesUnidentified": true,
    "exclusions": []
  },
  "dataVersion": "V1.0审计版"
}
```

| 字段 | 要求 |
|---|---|
| `id`、`label`、`metricType` | 必填 |
| `formula` | 必填；每个变量都必须逐一解析到`inputs[].name`，不得出现未登记变量 |
| `inputs[]` | 至少一个；每项只能引用一个`sourceId`、`claimId`或`calculationId` |
| `inputs[].name` | 必须为唯一的英文字段名，并在`formula`中出现 |
| `inputs[].locator` | 引用Source时必填，精确到工作表、范围、查询或筛选逻辑 |
| `period`、`unit`、`dataVersion` | 必填 |
| `denominator` | 比率、份额、渗透率、转化率、集中度等指标必填 |

Calculation可以引用另一个Calculation或Claim，但该引用仍必须通过一个具名Input进入公式，不得直接把对象ID当成公式变量；依赖不得形成循环。

公式只允许英文字段名、数字、空格、括号、逗号和常见算术符号。支持的函数为：

`abs`、`avg`、`ceil`、`exp`、`floor`、`log`、`max`、`min`、`pow`、`round`、`sqrt`、`sum`。

未登记变量、未使用Input、未支持函数或非合同字符均为阻断错误。

## 5. Claim合同

```json
{
  "id": "CLM_PLATFORM_A_CR5",
  "statement": "平台A品牌CR5为42.0%，市场集中度高于平台B",
  "claimType": "quantitative",
  "metricType": "brand_concentration",
  "sourceIds": [],
  "calculationIds": ["CAL_PLATFORM_A_CR5"],
  "period": "8周榜单周均",
  "unit": "%",
  "denominator": {
    "name": "全样本GMV",
    "scope": "all_sample",
    "includesUnidentified": true,
    "exclusions": []
  },
  "dataVersion": "V1.0审计版"
}
```

| 字段 | 要求 |
|---|---|
| `id`、`statement`、`claimType` | 必填 |
| `claimType` | `quantitative`、`qualitative`、`recommendation`或`methodology` |
| `sourceIds[]`／`calculationIds[]` | 至少一个非空；引用必须存在 |
| `metricType` | Quantitative Claim必填 |
| `period`、`unit`、`dataVersion` | Quantitative Claim必填 |
| `denominator` | 比率类Quantitative Claim必填 |

Claim引用Calculation时，双方的`period`、`unit`、`dataVersion`和分母口径必须一致。不能在PPT中把一个“核心面部护肤”分母的计算结果改写成“全样本”市场份额。

## 6. 分母合同

比率类指标的`denominator`至少包含：

```json
{
  "name": "全样本GMV",
  "scope": "all_sample",
  "includesUnidentified": true,
  "exclusions": []
}
```

硬性规则：

- 所有份额、比率、渗透率、转化率和集中度必须显式声明分母；
- `includesUnidentified`必须为布尔值，不能靠文字推断；
- 品牌份额、品牌CR5／CR10／CR20等品牌集中度必须设置为`true`；
- `exclusions`中不得同时出现`unidentified`、`unknown`或“未识别”；
- 只要存在品牌份额指标，顶层`policies.brandShareDenominator`必须为`all_sample_including_unidentified`。

这意味着品牌份额的分母必须是包括未识别品牌成交额在内的全样本GMV，不能使用“已识别品牌GMV合计”作为分母。

## 7. Content页面引用合同

```json
{
  "slides": [
    {
      "storylineId": "S10",
      "slideType": "evidenceInsight",
      "title": "平台A头部品牌集中度高于平台B",
      "claimIds": ["CLM_PLATFORM_A_CR5", "CLM_PLATFORM_B_CR5"]
    }
  ]
}
```

- 每张实质内容页必须有非空`claimIds[]`；
- `claimIds[]`中的每个ID必须存在于Evidence Contract；
- 封面、目录、章节页等无事实主张的页面可以免除；
- 显式例外必须同时满足角色、类型、Layout和理由四项合同：`methodology + method_boundary`、`scope_boundary + scope_boundary`只允许`appendixTable`或`appendixQA`；`legal_disclaimer + legal_boundary`只允许`appendixQA`；同时设置`evidenceExempt: true`和至少12个字符的具体`evidenceExemptReason`；
- 普通内容页、执行摘要和结尾页不能靠自由填写理由绕过Claim引用；
- Evidence Contract中的Claim、Calculation和Source必须最终可从某张页面的`claimIds[]`追溯到；
- 仅为审计保留的对象可设置`retainedForAudit: true`，但必须给出`retainedReason`。

默认免除的Layout：

`cover`、`toc`、`agenda`、`section`、`sectionDivider`、`section_divider`、`appendixDivider`、`appendix_divider`、`styleboards`、`styleboardSystem`、`styleboardDensity`。

上述默认免除不是只看Layout名称：`cover`必须同时是`slideRole=cover`，目录／议程／章节／styleboard必须是`slideRole=navigator`，附录分隔必须是`slideRole=appendix`。Layout与Role不匹配时既产生`evidence_exempt_layout_role_mismatch`，也仍要求非空`claimIds[]`；实质内容页不能借封面或导航Layout绕过Evidence。

## 8. 门禁命令

```bash
node scripts/validate_evidence.mjs \
  --evidence evidence.json \
  --content content.json \
  --report output/evidence-report.json
```

Content尚未建立时，先校验Source、Calculation和Claim内部合同：

```bash
node scripts/validate_evidence.mjs \
  --evidence evidence.json \
  --registry-only \
  --report output/evidence-registry-report.json
```

`--registry-only`不检查页面引用和孤儿对象；Content完成后必须再运行完整门禁，不能以registry-only报告代替最终交付门禁。

CLI报告使用`ksib-evidence-gate/2.0`，并记录Evidence、Content原文件和当前Validator的SHA256；Release Manifest会据此拒绝旧文件、其他版本或旧Validator生成的门禁报告。

内置自测：

```bash
node scripts/validate_evidence.mjs --self-test
```

门禁通过时退出码为`0`；存在任何错误时退出码为`1`。报告包含：

- 唯一ID与必填字段错误；
- 未核验来源；
- 缺失或无效引用；
- 计算输入、公式、数据版本与分母问题；
- Claim与Calculation口径漂移；
- 页面缺失Claim引用；
- 孤儿Source、Calculation或Claim；
- 覆盖率统计与可追溯对象数。

## 9. 推荐生产顺序

1. 冻结并核验Source；
2. 为所有衍生指标登记Calculation；
3. 把客户可见表述登记为Claim；
4. 在Content JSON中只引用Claim ID，不重复创造数字；
5. 运行Evidence门禁；
6. 门禁通过后才进入PPT构建和视觉QA。
