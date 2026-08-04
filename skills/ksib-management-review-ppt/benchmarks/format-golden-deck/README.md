# KSIB / MBB Format Golden Deck

这是一个只评估PowerPoint格式、原生对象和编辑性的6页合成回归夹具。全部数据和文字都是基准测试虚构内容，不构成业务事实，也不是客户模板。当前v4.3基准还验证内容页Action Title单行、无默认标题下划线、1.52／1.66 in正文起点和固定Chrome跨页0 EMU一致。

- 固定页面与评分规范：`SPEC.md`
- 当前自动验证结果及未验证边界：`RESULTS.md`

## 运行

先把本Skill根目录记为`$SKILL_ROOT`。使用Codex系统`Presentations` Skill提供的workspace setup脚本，把`@oai/artifact-tool`挂载到一个临时工作区；再从该临时工作区运行本目录的`build.mjs`，并把输出目录作为第一个参数传入。

示例：

```bash
node <presentations-skill>/container_tools/setup_artifact_tool_workspace.mjs \
  --workspace /tmp/ksib-golden-deck

SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/ksib-management-review-ppt"
GOLDEN_DIR="$SKILL_ROOT/benchmarks/format-golden-deck"
cp "$GOLDEN_DIR/build.mjs" "$GOLDEN_DIR/roundtrip.mjs" \
  /tmp/ksib-golden-deck/

cd /tmp/ksib-golden-deck
node build.mjs "$GOLDEN_DIR/output"
```

生成后必须继续运行：

```bash
"$PYTHON" "$SKILL_ROOT/scripts/ooxml_sanitize.py" \
  "$GOLDEN_DIR/output/KSIB_MBB_FORMAT_GOLDEN_DECK_V1.pptx" \
  --in-place

"$PYTHON" "$SKILL_ROOT/scripts/ooxml_qa.py" \
  "$GOLDEN_DIR/output/KSIB_MBB_FORMAT_GOLDEN_DECK_V1.pptx" \
  --format-contract \
  "$SKILL_ROOT/references/golden-deck-format-contract.json"
```

可选的非PowerPoint往返回归：

```bash
node roundtrip.mjs \
  "$GOLDEN_DIR/output/KSIB_MBB_FORMAT_GOLDEN_DECK_V1.pptx" \
  "$GOLDEN_DIR/output/KSIB_MBB_FORMAT_GOLDEN_DECK_V1.roundtrip.pptx"
```

往返文件还要重新运行Sanitizer、格式合同、OOXML QA和全页渲染。这个测试只能证明构建器可重新读取和导出，不替代Microsoft PowerPoint真机交互检查。

生成语义指纹并比较：

```bash
"$PYTHON" "$SKILL_ROOT/scripts/pptx_semantic_fingerprint.py" create \
  --pptx "$GOLDEN_DIR/output/KSIB_MBB_FORMAT_GOLDEN_DECK_V1.pptx" \
  --output "$GOLDEN_DIR/output/golden-semantic-fingerprint.json"

"$PYTHON" "$SKILL_ROOT/scripts/pptx_semantic_fingerprint.py" compare \
  --baseline "$GOLDEN_DIR/output/golden-semantic-fingerprint.json" \
  --pptx "$GOLDEN_DIR/output/KSIB_MBB_FORMAT_GOLDEN_DECK_V1.roundtrip.pptx" \
  --font-policy preserve \
  --style-policy preserve \
  --report "$GOLDEN_DIR/output/roundtrip-semantic-gate.json"
```

当前`build.mjs`生成的Chart属于原生`nativeLiteral`，连接器为双端吸附的原生`p:cxnSp`，页码为静态文本。三者会被OOXML QA分别识别；正式客户Deck若要求工作簿数据维护和自动页码，应把项目合同升级为`embedded-workbook-required`与`field-required`，不能把本夹具的降级能力描述成已经验证。

最后逐页检查PNG，并从原始Golden PPTX复制两个SHA一致的副本：`save-only`副本只做PowerPoint保存与重开，随后重新跑Sanitizer和全部机器门禁；`interaction`副本完成文字、颜色、加粗、字体、形状填充、组合／取消组合、表格单元格、图表数据和连接器吸附操作后不保存直接关闭。不要在同一个副本上同时证明“无损保存”和“交互可编辑”。

`output/`是生成物目录；源文件和格式合同才是回归真相源。
