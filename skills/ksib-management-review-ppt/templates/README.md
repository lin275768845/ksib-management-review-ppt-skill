# KSIB 可执行母版

本目录包含两个不同用途的文件：

- `KSIB_MBB_Master_v1.0.potx`：PowerPoint 模板。固定主题、字体、页面尺寸、基础 Header／Footer、标题与来源占位符，以及动态页码。
- `KSIB_MBB_Layout_Library_v1.0.pptx`：8 页可编辑样板库。每页对应一个基础 Profile，方便在 PowerPoint 中查看和复制。

母版不承担复杂正文的临场拼版。复杂内容页继续由 `certified-layout-registry.json`、`render-plan.json` 和 `render_certified_layout.mjs`共同控制。

## 8 个基础 Profile

1. Cover
2. Navigator
3. Section Divider
4. Content – Title Only
5. Content – Title + Subtitle
6. Appendix Divider
7. Appendix – Title Only
8. Appendix – Title + Subtitle

## 生成与验证

```bash
node scripts/build_powerpoint_master.mjs
python3 scripts/validate_powerpoint_master.py --report templates/master-gate.json
python3 scripts/test_powerpoint_master.py
```

模板与 Renderer 共用 `references/design-tokens.json`。修改主题色、字体、Chrome 坐标或标题 Profile 时，必须重新生成模板、重建 Golden Deck，并重新运行模板门禁和 Layout Fidelity Gate。
