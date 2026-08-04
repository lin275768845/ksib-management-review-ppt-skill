# Theme Color Contract 1.0

本合同把颜色从“审美偏好”改成可登记、可验证、可阻断的页面语义。正式制作不得直接挑选任意色值；Renderer只能使用`theme-color-contract.json`中的Token，或使用已记录用户批准的例外。

## 1. 色板角色

- 主色阶：`primary.dark/base/light/pale`。用于同一语义家族的层级、顺序和主证据；四个色阶不是四个彼此无关的分类色。
- 对比辅色：`contrast.base/pale`。只用于真正的对照、反例或第二个关键证据，不得作为装饰，也不得与主色在每页平均分配视觉重量。
- 浅灰中性色：`neutral.series`只表示“其他”、基线、参考、弱化或较差对比；`neutral.surface/divider/baselineStroke`分别用于背景、分隔线和坐标轴。深灰只用于文字，不得作为默认的大面积图表填充。
- 功能色：`status.positive/negative/warning`只在内容明确表达正向、负向、风险或预警时使用，不属于品牌装饰色。

## 2. 图表配色模式

- `single-focus`：一个主证据用`primary.base`或`primary.dark`，其余系列使用浅灰中性色。
- `sequential`：只使用主色阶，并按浅到深表达有序强度、时间或优先级；不得随机打乱色阶。
- `two-way-comparison`：主对象用`primary.base`，真正的对照对象用`contrast.base`；若对照只是“其他／基线”，改用`neutral.series`。
- `status-diverging`：仅在正负、好坏或风险语义真实存在时使用功能色。
- `categorical-limited`：无序分类最多使用三个有彩色语义组；更多类别优先采用排序、直接标签、小多图或浅灰弱化，禁止彩虹色。

无数据页面使用`no-data`。最强视觉重量必须落在该页的核心证据或行动节点上，不使用机械的全页色彩占比指标。

## 3. 每页登记与阻断

Renderer先生成颜色语义草稿；最终PPTX完成全部保存与清理后，必须运行`extract_pptx_theme_colors.py`生成`ksib-pptx-color-inventory/1.0`。提取器直接读取最终OOXML中的每个原生对象、Chart／Diagram关联part、颜色属性、主题引用与颜色变换，并把结果绑定到`页码／唯一对象名／属性路径`。随后生成`ksib-theme-usage/1.1`：逐页登记图表模式、主证据对象、每个有色元素的角色、Token和用途，并用`bindings[]`把最终清单中的每个可见`bindingRef`恰好绑定一次。

`pptxArtifactSha256`必须等于最终PPTX哈希；有色对象必须使用页内唯一且明确的对象名，不能依赖PowerPoint可能重排的内部ID。Renderer自己的颜色声明不是交付证据，只有最终PPTX清单与Theme Usage一一核对通过才算合规。

以下情况阻断交付：

- 出现合同外的原始Hex值，且没有用户批准的例外记录；
- 对比辅色或功能色被标为装饰用途；
- 深灰用于数据填充，或浅灰被用作主证据；
- `neutral.series`用于“其他／基线／弱化／参考／较差”之外的含义；
- 同页有彩色数据语义组超过三个；
- 页面未登记、主证据未登记，或登记内容与Renderer实际实现不一致；
- 最终PPTX存在未解析的可见颜色、有色对象名称不稳定、实际颜色未登记或被重复登记；
- 声明Token的Hex与最终PPTX解析值不同，或Theme Usage声明了成片中不存在的虚假绑定；
- 颜色清单、Theme Usage或门禁报告绑定的PPTX SHA256不是当前最终文件；
- 普通文字对背景对比度低于4.5:1，或大号／粗体文字低于3:1。

例外必须同时包含原始色值、业务原因、`approvalRef`和`user-approved`状态；“更好看”“更丰富”“装饰”不是有效理由。

## 4. 模式边界

- 新建／故事线重构：默认使用本合同；自定义主题色时按`ksib-srgb-mix/1.0`生成主色阶，并保留独立对比辅色。
- Format-only：用户未授权改变样式时保留原主题，本合同只做审计，不得借颜色归一化改变原有颜色语义；获明确授权后才可按本合同重新定样。

最终导出、Sanitizer和任何人工重存全部结束后执行：

```bash
python3 scripts/extract_pptx_theme_colors.py \
  --pptx outputs/final.pptx \
  --output work/presentations/ksib-management-review/tmp/qa/pptx-color-inventory.json

# 根据最终清单补齐theme-usage.json中的slides[].bindings[]，不得凭Renderer预声明伪造bindingRef。
node scripts/validate_theme_usage.mjs \
  --pptx outputs/final.pptx \
  --python python3 \
  --usage work/presentations/ksib-management-review/tmp/qa/theme-usage.json \
  --inventory work/presentations/ksib-management-review/tmp/qa/pptx-color-inventory.json \
  --report work/presentations/ksib-management-review/tmp/qa/theme-color-gate.json
```
