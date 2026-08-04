# Certified Core Layout Golden Library

本夹具覆盖12个高频咨询正文Layout，每类固定生成稀疏、标准和最大容量三页，共36页。所有可见内容均显式标记为`[占位]`，不包含真实业务事实，也不是客户模板。

构建顺序固定为：生成Render Plan输入与结构化内容 → 解析锁定几何 → Artifact Tool原生PPTX构建 → OOXML归一与QA → Layout Fidelity Gate。构建输出写入`output/`并由Git忽略。

```bash
PYTHON="$BUNDLED_PYTHON" node build.mjs output
```

每次变更Renderer、Registry、Component或Typography后都必须重建，并逐页检查36张辅助渲染图。辅助PNG不能替代Microsoft PowerPoint真机截图；正式客户交付仍需完成PowerPoint保存、重开与交互门禁。
