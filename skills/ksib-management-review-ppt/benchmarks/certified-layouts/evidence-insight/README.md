# evidenceInsight Certified Golden Slides

本夹具验证`evidenceInsight`确定性纵切，不是客户模板，也不包含真实业务数据。

覆盖三种状态：

1. `right-panel-standard`稀疏容量；
2. `right-panel-standard`标准容量；
3. `right-panel-subtitle`最大允许容量。

`build.mjs`固定执行：Render Plan解析 → Artifact Tool原生PPTX构建 → 辅助逐页PNG → OOXML兼容性归一与QA → 最终PPTX Layout Fidelity Gate。所有可见示例内容均标为`[占位]`。

```bash
node "$PRESENTATIONS_SKILL/container_tools/setup_artifact_tool_workspace.mjs" --workspace "$TMP_DIR"
PYTHON="$BUNDLED_PYTHON" node build.mjs output
```

门禁必须由`output/ooxml-gate.json.passed=true`和`output/layout-fidelity-gate.json.passed=true`共同证明。夹具会显式启用OOXML QA的benchmark专用占位符豁免；正式交付不得使用该参数。辅助PNG仅用于构建期逐页视觉检查，不能替代Microsoft PowerPoint真机截图与最终交付门禁。
