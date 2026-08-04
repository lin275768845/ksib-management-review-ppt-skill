# KSIB PPT 交付可追溯合同

本合同解决两个问题：

1. 纯格式修改是否误改了文字、数字、页序、颜色或加粗语义；
2. 客户交付文件是否能追溯到输入文件、锁定Storyline、门禁报告、Renderer版本和人工PowerPoint检查。

脚本只读输入PPTX和JSON；除显式指定的JSON输出外，不修改PPTX，不发送、不发布文件。

## 1. 语义指纹

`pptx_semantic_fingerprint.py`仅使用Python标准库读取PPTX ZIP／XML。指纹不依赖PowerPoint、LibreOffice或第三方Python包。

指纹覆盖：

- 按演示文稿关系解析的真实页序；
- 逐页可见文本段落及排序后的文本清单；
- 逐页数字、金额、比例、日期等数字Token；
- 与页面关联的原生Chart／SmartArt文本及缓存数据；
- 文字、数字、Chart／SmartArt缓存数据与原生对象ID的绑定关系；
- 同一文本对象内逐段文字与颜色的有序绑定关系；
- 同一文本对象内逐段文字与有效加粗状态的有序绑定关系；
- 关联Chart／Diagram文本与有效颜色、加粗状态及具体part的绑定关系；
- Chart／Diagram中series、point index、标签、数值与公式路径的绑定关系；
- 逐页非文本直接色、主题色引用、颜色角色及颜色变换；文本颜色按最终有效显示值绑定，不把冗余run覆盖当成业务语义；
- 颜色与字体在原生对象之间的绑定关系，防止两个文本框互换内容／颜色后被聚合清单漏过；
- 逐页直接字体族、字号和主题字体引用；
- 页面经Layout／Master继承的主题绑定与Color Map；
- 全部主题色槽位及色值；
- 全部主题字体槽位及字体值；
- 原始PPTX SHA256和上述语义字段的整体Hash。

创建内容冻结指纹：

```bash
python3 scripts/pptx_semantic_fingerprint.py create \
  --pptx inputs/locked-client-deck.pptx \
  --output work/delivery/input-semantic-fingerprint.json
```

纯格式修改完成后比较：

```bash
python3 scripts/pptx_semantic_fingerprint.py compare \
  --baseline work/delivery/input-semantic-fingerprint.json \
  --pptx outputs/client-delivery.pptx \
  --mode format-only \
  --font-policy preserve \
  --style-policy preserve \
  --report work/delivery/format-only-semantic-gate.json
```

`format-only`模式将以下任一变化视为阻断错误并返回非0退出码：

- 增页、删页或页序变化；
- 任一页可见文本变化；
- 任一页数字、金额或比例变化；
- 任一页有效可见颜色、非文本直接色／主题色引用／颜色角色／颜色变换变化；
- 文字、数字、图表缓存、颜色或字体在原生对象之间交换或重绑定；
- 同一对象内文字与颜色或加粗状态互换，或图表点值、点标签、系列标签互换；
- 主题色槽位或主题色值变化。
- `--font-policy preserve`时，任一页字体族、字号、主题字体引用或主题字体槽位变化。

指纹使用`ksib-pptx-semantic-fingerprint/3.2`与`ksib-pptx-semantic-compare/3.2`。语义优先绑定到唯一且明确的原生对象名称；没有唯一名称时回退到OOXML对象ID。这样既允许PowerPoint或兼容工具在无损保存时重排内部ID，又能阻断对象之间的文字、数字、颜色、字号和加粗关系被交换。格式专修必须先为受控对象赋予唯一角色名，不得用整页重建伪装成格式调整。字体是否冻结由`--font-policy preserve|allow`显式决定；颜色、填充、边框边侧、线宽、线型、端点和加粗是否冻结由`--style-policy preserve|allow`显式决定。只有用户授权字体归一化或按KSIB／MBB规范重新定样时，才能分别使用对应的`allow`；允许重新定样仍冻结文字、数字、页序、图表数据与对象内容绑定。它不验证缓存背后的Excel公式、图片中的OCR文本、音视频内容、Speaker Notes、动画时序或肉眼渲染一致性，这些仍需由数据门禁、OOXML门禁、视觉门禁和人工PowerPoint检查覆盖。

格式专修执行OOXML兼容性归一化时必须使用`ooxml_sanitize.py --preserve-theme`。该模式保留主题色板，同时在slide、notes、表格单元格及关联Chart／Diagram的DrawingML文本中清理与段落默认色完全相同的冗余run颜色覆盖，并将段落默认加粗等价物化到字符run；语义指纹按最终有效文字颜色与加粗状态核对，因此允许存储方式清理，但任何实际视觉语义变化仍会阻断。新建Deck或用户已授权品牌归一化时才使用默认KSIB主题模式。

任何format-only任务在Sanitizer或编辑器打开前，先用`prepare_revision.py`创建Source副本、Working副本和`ksib-pptx-revision/1.0`清单。后续写操作只能发生在Working副本或新的最终输出路径；用户原文件与Source副本不得被覆盖。

## 2. Release Manifest

`build_release_manifest.mjs`输出`ksib-release-manifest/3.2`，为最终交付建立单一、可审计的发布记录。3.2要求format-only使用`ksib-pptx-semantic-compare/3.2`，把填充和边框结构纳入`stylePolicy`；同时保留3.1引入的`parentArtifactSha256`与Design Tokens哈希。既有3.0／3.1清单可作为历史记录保留，但新交付必须重新生成，不能把旧报告直接复用。它收集：

- 输入PPTX、冻结Content、Evidence及最终PPTX的文件名、字节数和SHA256；输入同时记录为`parentArtifactSha256`，证明本次修订源自哪一个父版本；
- Storyline Lock文件的SHA256、锁定状态和页数；
- 每个Gate JSON的SHA256、`passed`、错误数、警告数、Schema版本及当前Validator SHA256；
- Storyline包装器与上游MBB Storyline Validator的SHA256；
- 当前Layout Matrix与`design-tokens.json`的SHA256；
- 逐页Storyline ID、canonical／fallback Renderer合同和实际使用记录；
- 人工PowerPoint检查人、检查时间、总状态和逐项状态；
- 阻断原因和Manifest自身Hash。

人工PowerPoint检查JSON示例：

```json
{
  "passed": true,
  "checkedBy": "Reviewer Name",
  "checkedAt": "2026-07-20T16:30:00+08:00",
  "pptxSha256": "<最终PPTX的SHA256>",
  "checks": {
    "noRepairPrompt": true,
    "textEditUndo": true,
    "textColorChangeUndo": true,
    "boldToggleUndo": true,
    "fontFamilyChangeUndo": true,
    "shapeFillChangeUndo": true,
    "groupUngroup": true,
    "fontDisplay": true,
    "finalSlideAndPageNumber": true,
    "tableCellFormatUndo": true,
    "chartTextFormatUndo": true,
    "chartDataEditUndo": true,
    "smartArtTextFormatUndo": true
  },
  "notes": "Final client-delivery file opened in Microsoft PowerPoint for macOS."
}
```

前9项为所有Deck必检；后4项由最终PPTX的原生对象清单自动触发：存在表格时必须提供`tableCellFormatUndo`，存在图表时必须同时提供`chartTextFormatUndo`和`chartDataEditUndo`，存在SmartArt时必须提供`smartArtTextFormatUndo`。不含对应对象时无需伪填。

人工交互应在测试前与最终PPTX逐字节一致的`interaction`副本上完成，并在不保存的情况下关闭；这样检查记录仍可绑定最终文件的SHA256。另建`save-only`副本验证PowerPoint保存与重开，保存后必须重新运行Sanitizer、语义指纹、OOXML和视觉门禁。不得把已经执行并保存过临时交互改动的副本用作最终文件或无损往返证据。

生成Release Manifest：

```bash
node scripts/build_release_manifest.mjs \
  --input-artifact work/content.json \
  --final-pptx outputs/client-delivery.pptx \
  --delivery-mode locked-content \
  --storyline-lock work/storyline-lock.json \
  --content-artifact work/content.json \
  --evidence-artifact work/evidence.json \
  --gate storyline=work/gates/storyline.json \
  --gate evidence=work/gates/evidence.json \
  --gate content=work/gates/content.json \
  --gate handoff=work/gates/storyline-handoff.json \
  --gate ooxml=work/gates/ooxml.json \
  --gate visual=work/gates/visual.json \
  --gate powerpoint-render=work/gates/powerpoint-render.json \
  --validator storyline=scripts/validate_storyline_gate.mjs \
  --validator storyline-upstream="${CODEX_HOME:-$HOME/.codex}/skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs" \
  --validator evidence=scripts/validate_evidence.mjs \
  --validator content=scripts/validate_content.mjs \
  --validator handoff=scripts/validate_storyline_handoff.mjs \
  --validator ooxml=scripts/ooxml_qa.py \
  --validator visual=scripts/build_visual_review_gate.py \
  --validator powerpoint-render=scripts/validate_powerpoint_render.py \
  --required-gates storyline,evidence,content,handoff,ooxml,visual,powerpoint-render \
  --renderer artifact-tool-ksib \
  --renderer-version 1.0.0 \
  --renderer-mode canonical \
  --powerpoint-check work/delivery/powerpoint-check.json \
  --output outputs/client-delivery.release-manifest.json
```

`format-only`不要求Storyline Lock，但必须提供`--input-pptx`。`locked-content`与`story-change`必须提供已批准的Storyline Lock、`--content-artifact`和`--evidence-artifact`。没有输入PPTX的新建Deck可另用`--input-artifact`登记研究简报或上游输入。

各模式的必需Gate固定如下，不能靠删减`--required-gates`绕过：

- `format-only`：`fingerprint,ooxml,visual,powerpoint-render`
- `locked-content`／`story-change`：`storyline,evidence,content,handoff,ooxml,visual,powerpoint-render`

Release Manifest还会检查Gate本身的Schema与生成版本，不能用一个只有`{"passed": true}`的空JSON或旧Validator报告代替：

- 所有Gate都必须有`errorCount: 0`、`errors: []`和与`--validator name=path`实际文件一致的`validatorSha256`；`--validator`路径还必须是本Skill登记的canonical脚本，不能用复制到临时目录的同内容脚本替代；
- `storyline`必须使用`ksib-storyline-gate/1.0`、包含`productionReady: true`，绑定当前Storyline SHA256、包装器SHA256和上游MBB Validator SHA256；
- `evidence`必须使用`ksib-evidence-gate/2.0`、为`mode: "full"`、包含`coverage`，并绑定当前Evidence、Content与Layout Matrix SHA256；
- `content`必须使用`ksib-content-gate/2.0`、包含非空逐页`results[]`；`slide`必须唯一完整覆盖1..N，`storylineId`必须与锁定Storyline完全一致，每页解析到`provider`、`canonicalRenderer`和`editableNative: true`，并绑定当前Content与Layout Matrix SHA256；
- `handoff`必须使用`ksib-storyline-handoff/2.0`、包含唯一完整且逐页一致的`semanticHashes[]`、`argumentTree.passed: true`，并绑定当前Storyline、Content与Layout Matrix SHA256；
- `fingerprint`必须来自format-only语义比较脚本，并显式登记`fontPolicy`与`stylePolicy`；
- `ooxml`必须使用`ksib-ooxml-qa/2.0`，包含`reports[]`并显式登记主题与字体策略；字体报告应列出直接字体族与字号清单；
- OOXML报告中的外部关系只保留协议与主机，必须删除路径、查询参数、片段和用户信息；日志或Manifest不得复制完整外链；
- `visual`必须逐页全尺寸复核并满足下方辅助预览合同；它不是最终视觉真相源。
- `powerpoint-render`必须使用`ksib-powerpoint-render-gate/1.0`，绑定当前PPTX、Content、Format Contract和PowerPoint逐页截图集合，并通过标签唯一归属、图表数字、金融折线和Renderer实际字段检查。

Visual Review输入示例：

```json
{
  "reviewedBy": "Reviewer Name",
  "reviewedAt": "2026-07-20T18:00:00+08:00",
  "checks": {
    "fullSizeReview": true,
    "noOverlap": true,
    "noClipping": true,
    "noUnexpectedWrap": true,
    "footerAndPageNumber": true,
    "chartDataAndSources": true
  },
  "slideReviews": [
    {
      "slide": 1,
      "renderFile": "slide-1.png",
      "passed": true,
      "issues": [],
      "notes": "全尺寸检查通过"
    }
  ]
}
```

先用系统`Presentations` skill渲染全部页面PNG，再生成机读Visual Gate。该结果只用于辅助预览：

```bash
python3 scripts/build_visual_review_gate.py \
  --pptx outputs/client-delivery.pptx \
  --render-dir work/render \
  --review-json work/delivery/visual-review-input.json \
  --output work/gates/visual.json
```

脚本核对PPT页数与逐页复核记录，验证每页PNG结构、CRC、IDAT完整解码长度、逐行filter byte、尺寸、纵横比、文件SHA256及规范化解码像素SHA256唯一性，最低分辨率为960×540；当前只接受非隔行PNG。Visual Gate必须使用`ksib-visual-review/2.0`并记录当前Validator SHA256；只有PNG文件头、短解码载荷、隔行PNG、只手写全局`passed: true`、遗漏某页、同名复用、改名后复用，或仅增加`tEXt`等元数据后的同像素复用均会失败。

随后必须在Microsoft PowerPoint中保存最终PPTX的逐页截图，并按`references/powerpoint-render-contract.md`生成最终视觉门禁：

```bash
python3 scripts/validate_powerpoint_render.py \
  --pptx outputs/client-delivery.pptx \
  --content work/content.json \
  --format-contract work/format-contract.json \
  --review-json work/delivery/powerpoint-review.json \
  --screenshot-dir work/delivery/powerpoint-screenshots \
  --output work/gates/powerpoint-render.json
```

PowerPoint截图必须逐页完成100%视图与缩小视图检查。辅助渲染和PowerPoint明显不一致、分类标签由坐标轴与外部文本重复承担、百分比精度不合规、金融时间序列使用平滑曲线，或`phasePlaybook`漏渲染共同逻辑／判断标准／行动时，均直接阻断。

最终PPTX完成最后一次保存后，必须从成片提取对象颜色并交叉核对Theme Usage：

```bash
python3 scripts/extract_pptx_theme_colors.py \
  --pptx outputs/client-delivery.pptx \
  --output work/gates/pptx-color-inventory.json
node scripts/validate_theme_usage.mjs \
  --pptx outputs/client-delivery.pptx \
  --python "$PYTHON" \
  --usage work/delivery/theme-usage.json \
  --inventory work/gates/pptx-color-inventory.json \
  --report work/gates/theme-color.json
```

提取清单绑定最终PPTX SHA256、当前提取器SHA256、页码、唯一对象名与OOXML属性路径。Validator会在临时目录对同一最终PPTX现场重提取并比较语义哈希，因此手改inventory同样不能通过。每个可见颜色必须可解析并在Theme Usage中恰好登记一次；Renderer声明与最终成片不一致时，以最终PPTX为准并阻断。

纯格式任务示例：

```bash
node scripts/build_release_manifest.mjs \
  --input-pptx inputs/locked-client-deck.pptx \
  --final-pptx outputs/client-delivery.pptx \
  --delivery-mode format-only \
  --gate fingerprint=work/delivery/format-only-semantic-gate.json \
  --gate ooxml=work/gates/ooxml.json \
  --gate visual=work/gates/visual.json \
  --gate theme-color=work/gates/theme-color.json \
  --gate powerpoint-render=work/gates/powerpoint-render.json \
  --validator fingerprint=scripts/pptx_semantic_fingerprint.py \
  --validator ooxml=scripts/ooxml_qa.py \
  --validator visual=scripts/build_visual_review_gate.py \
  --validator theme-color=scripts/validate_theme_usage.mjs \
  --validator powerpoint-render=scripts/validate_powerpoint_render.py \
  --required-gates fingerprint,ooxml,visual,theme-color,powerpoint-render \
  --renderer artifact-tool-template-following \
  --renderer-version 1.0.0 \
  --renderer-mode canonical \
  --powerpoint-check work/delivery/powerpoint-check.json \
  --output outputs/client-delivery.release-manifest.json
```

使用合同中的fallback renderer时，先建立逐页实际使用记录：

```json
{
  "schemaVersion": "ksib-renderer-usage/1.0",
  "slides": [
    {
      "storylineId": "S1",
      "rendererName": "evidenceInsight",
      "mode": "fallback",
      "reason": "canonical renderer在目标环境不可用"
    }
  ]
}
```

文件必须完整覆盖全部Storyline页面；未使用fallback的页面填写其canonical Renderer、`mode: "canonical"`和`reason: null`。命令增加：

```bash
--renderer-mode fallback \
--renderer-usage work/delivery/renderer-usage.json
```

未逐页登记、使用未获Layout合同允许的fallback、或没有具体原因都会阻断交付。

以下任一情况都会生成`status: "blocked"`并返回非0退出码：

- Storyline未达到`lockStatus: "approved_by_user"`或没有`slides[]`；
- 任一`--required-gates`未提供；
- 任一必需Gate的`passed`不为`true`、`errorCount`不严格等于0、`errors[]`缺失或非空；
- 任一Gate的`validatorSha256`与当前`--validator`脚本不一致；
- `--validator`不指向本Skill登记的canonical脚本，或Gate报告早于其绑定输入／时间戳晚于本次Release启动；
- Evidence／Content／Handoff报告的输入SHA256不对应本次Storyline、Content、Evidence或当前Layout Matrix，或三者不是基于同一Matrix运行；
- Storyline、Content、Evidence、Handoff和Visual页数不一致，或逐页ID／页码有缺失、重复；
- Renderer实际使用记录与Content逐页canonical／fallback合同不一致；
- fingerprint、OOXML、Visual Gate、Theme Color Gate或PowerPoint Render Gate记录的PPTX SHA256与当前最终文件不一致；
- Theme Color Gate没有逐项核对最终PPTX全部可见颜色，或存在不稳定对象名、未解析颜色、未登记／重复登记颜色、虚假绑定、Token与成片Hex不一致；
- PowerPoint Render Gate缺少逐页PowerPoint截图、逐页审阅时间或任一P0检查未通过；
- 最终文件不是`.pptx`、不是合法ZIP，或根`officeDocument`关系、Presentation Content Type、非空`sldId`、Presentation→Slide关系、真实slide part与Slide Content Type未完全对应；
- format-only指纹的baseline SHA256不对应本次输入PPTX；
- 人工PowerPoint检查的`passed`不为`true`；
- 人工PowerPoint检查记录的`pptxSha256`与当前最终文件不一致；
- 人工检查缺少`checkedBy`、`checkedAt`；
- `noRepairPrompt`、`textEditUndo`、`textColorChangeUndo`、`boldToggleUndo`、`fontFamilyChangeUndo`、`shapeFillChangeUndo`、`groupUngroup`、`fontDisplay`、`finalSlideAndPageNumber`任一人工逐项检查缺失或不为`true`；
- 最终文件存在表格、图表或SmartArt时，其条件人工检查`tableCellFormatUndo`、`chartTextFormatUndo`、`chartDataEditUndo`或`smartArtTextFormatUndo`缺失或不为`true`。

脚本自测：

```bash
node scripts/build_release_manifest.mjs --self-test
```

## 3. 交付边界

- Release Manifest记录的是“哪些输入、门禁和人工检查支持本次交付”，不是对业务结论正确性的替代。
- Gate报告必须来自对应最终文件；不得复用旧版本PPT的通过报告。
- `required-gates`由当前任务合同明确。不得通过从列表中删除失败Gate来绕过阻断。
- 最终PPTX发生任何重存、清理或人工编辑后，必须重新运行语义指纹、OOXML、最终颜色提取与交叉校验、视觉和Release Manifest步骤。
- Manifest只记录文件名和Hash，不写入本机绝对路径，避免在客户交付包中暴露本地目录。
- `generatedAt`默认使用当前UTC时间；需要可重复测试时可显式传入`--generated-at`。
