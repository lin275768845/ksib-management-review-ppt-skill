# Golden Deck验证结果

验证日期：2026-07-31

## 已自动验证

| 项目 | 结果 |
|---|---|
| 6页页数、页序、13.333 × 7.5 in画布 | 通过 |
| Header、Title、Subtitle、Footer、页码角色与几何 | 通过 |
| 固定Chrome跨页绝对对齐 | 2组Profile、0 EMU容差通过；P2–P6共用页眉／页脚无漂移，P3–P4正文Title-only标题区无漂移；单例Header模式仅按设计Token验收 |
| Title／Subtitle／Takeaway重复与Takeaway稀缺性 | 通过；基准6页均无Takeaway |
| 原生对象 | 1个Chart、2个Table、4个Connector；无Picture |
| 主表样式 | 白底表头、无外框与竖线、数字右对齐、总计上规则线 |
| 附录表样式 | 浅灰表头、极浅横线；当前8行表不启用斑马纹，无外框与竖线 |
| 图表样式 | 横向条形、直接标注、无图例与网格；仅一个橙色视觉焦点 |
| Connector吸附 | 4/4同时绑定起终节点，4/4保留箭头 |
| 字体与字号 | 主题和直接字体均为PingFang SC；字号均在批准集合 |
| 颜色与加粗编辑性存储 | 无冗余run颜色；无仅依赖段落默认值的加粗 |
| 对象锁 | 未发现普通用户对象编辑锁 |
| 全页PNG视觉复核 | 6/6通过，无溢出、裁切或意外换行记录 |
| Artifact-tool回读再导出 | 当前v4.2基准的OOXML格式合同、6/6全页Visual Gate与语义指纹均为0错误、0警告；原始与回读PNG逐页SHA完全相同 |
| Microsoft PowerPoint保存往返 | 当前v4.2尚未重跑；包内记录仅是v4.1历史证据，不计入本次发布门禁 |
| PowerPoint交互检查 | 当前v4.2尚未重跑；文字、格式、组合、表格、图表数据和连接器仍需在与当前PPTX SHA一致的副本中复核 |
| 自动回归 | 228项通过：工作流与合同自测165项，OOXML／编辑性24项，格式合同21项，设计Token 5项，图表／表格样式4项，Chrome归一化9项 |

## 历史PowerPoint验收说明

包内`powerpoint-*`文件记录v4.1基准的历史人工验收。PowerPoint保存曾额外写入Office／Calibri主题部件；未清理的`save-only`文件因此被OOXML门禁阻断14项、语义指纹阻断1项。经过受控Sanitizer归一化后，v4.1的OOXML格式合同和语义指纹恢复为0错误、0警告，六页视觉除第4页极小文本run渲染差异外保持一致。

第3页总计规则线在v4.1已由表格单元格顶边改为独立原生Shape `table-total-rule`，并通过当时的PowerPoint保存往返。

v4.1人工验收使用两个与当时基准SHA一致的独立副本：

- `save-only`副本只执行保存、关闭、重开和重新门禁；
- `interaction`副本完成局部编辑、撤销和连接器检查后不保存关闭，关闭后SHA仍与基准一致。

这种分工仍是v4.2重跑时的正确方法，但历史副本不能证明当前新增的页脚分隔线、跨页0 EMU合同、对象类型／垂直对齐门禁和Header重叠门禁已在Microsoft PowerPoint中通过。

## 明确能力边界

- Chart数据模式仍为`nativeLiteral`，不是内嵌Excel工作簿；v4.1历史验收曾在PowerPoint中打开“编辑数据”，把B2由18改为99并撤销回18。当前v4.2仍需重新执行该操作。正式客户Deck若要求稳定的工作簿维护能力，仍必须使用`embedded-workbook-required`合同。
- 页码是静态文本，不是`slidenum`字段。正式多页客户Deck应优先使用动态字段或母版页码占位符。
- 本夹具不含SmartArt，因此没有把`smartArtTextFormatUndo`记为已验证；含SmartArt的客户Deck仍须单独执行该项。

当前机器门禁证明v4.2 Golden Deck及其Artifact-tool回读文件符合本次自动化合同；Microsoft PowerPoint人工保存往返和交互验收尚待重跑。任何基准通过都不自动替代未来客户Deck、Windows PowerPoint或其他Office版本的逐文件验收。
