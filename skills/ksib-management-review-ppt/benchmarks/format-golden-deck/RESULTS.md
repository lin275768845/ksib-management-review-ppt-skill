# Golden Deck验证结果

验证日期：2026-08-03

## 已自动验证

| 项目 | 结果 |
|---|---|
| 6页页数、页序、13.333 × 7.5 in画布 | 通过 |
| Header、Title、Subtitle、Footer、页码角色与几何 | 通过 |
| 内容页Action Title | P2–P6全部单行；多个段落、显式换行、超过38个加权字符均由门禁阻断；P1封面主标题不属于此门禁 |
| 开放式Header | P2–P6无默认`title-divider`；Title-only正文锚点不早于1.52 in，Title＋Subtitle不早于1.66 in |
| 固定Chrome跨页绝对对齐 | 2组、0 EMU容差通过；P2–P6共用页眉／页脚无漂移，P3–P6的Title-only Action Title无漂移；P2的Title＋Subtitle单例按设计Token和视觉门禁验收 |
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
| Artifact-tool回读再导出 | 当前v4.3基准的OOXML格式合同、6/6全页Visual Gate与语义指纹均为0错误、0警告；原始与回读PNG逐页规范化像素SHA完全相同 |
| Microsoft PowerPoint保存往返 | 当前v4.3尚未重跑；包内记录仅是v4.1历史证据，不计入本次发布门禁 |
| PowerPoint交互检查 | 当前v4.3尚未重跑；文字、格式、组合、表格、图表数据和连接器仍需在与当前PPTX SHA一致的副本中复核 |
| 自动回归 | 278项通过：原266项基线之外，新增Content合同3项、PowerPoint Render合成Golden Deck 8项和Release阻断1项；后者覆盖分类／数值重复标签、整数百分比、非平滑折线与真实`phasePlaybook`字段渲染 |

当前v4.3机器基准绑定如下：

| 证据 | SHA256／结果 |
|---|---|
| 原始Golden PPTX | `9f2064af8fab5719ec18ed038e0d05faf451ce09b1a387703823a893ff55813d` |
| Artifact-tool回读PPTX | `ad22ee097723f2600587abe4ec5502235e97dfbb5b1cd13388b3cb40aae508e8` |
| 格式合同 | `0fbc1ff9e727eea7b0a4abc2eab6b73a1adae91c8250f788828c7cb43418ec9d` |
| OOXML QA | 原始与回读均0错误、0警告 |
| 视觉渲染集合 | 两版均为`fc9f9f5432f33fb1ad3ae3abf8a9592c2362e5bea91a086e632a41c28f0b4038` |
| 语义指纹 | 两版均为`596a69d3f8fa6820360c91218223b08a2bfc0757d02b6acb75f6a92e8ffd5e91` |

## 历史PowerPoint验收说明

包内`powerpoint-*`文件记录v4.1基准的历史人工验收。PowerPoint保存曾额外写入Office／Calibri主题部件；未清理的`save-only`文件因此被OOXML门禁阻断14项、语义指纹阻断1项。经过受控Sanitizer归一化后，v4.1的OOXML格式合同和语义指纹恢复为0错误、0警告，六页视觉除第4页极小文本run渲染差异外保持一致。

第3页总计规则线在v4.1已由表格单元格顶边改为独立原生Shape `table-total-rule`，并通过当时的PowerPoint保存往返。

v4.1人工验收使用两个与当时基准SHA一致的独立副本：

- `save-only`副本只执行保存、关闭、重开和重新门禁；
- `interaction`副本完成局部编辑、撤销和连接器检查后不保存关闭，关闭后SHA仍与基准一致。

这种分工仍是v4.3重跑时的正确方法，但历史副本不能证明当前新增的单行Action Title、无默认标题下划线、正文起点、跨页0 EMU合同、对象类型／垂直对齐门禁和Header重叠门禁已在Microsoft PowerPoint中通过。

## 明确能力边界

- Chart数据模式仍为`nativeLiteral`，不是内嵌Excel工作簿；v4.1历史验收曾在PowerPoint中打开“编辑数据”，把B2由18改为99并撤销回18。当前v4.3仍需重新执行该操作。正式客户Deck若要求稳定的工作簿维护能力，仍必须使用`embedded-workbook-required`合同。
- 页码是静态文本，不是`slidenum`字段。正式多页客户Deck应优先使用动态字段或母版页码占位符。
- 本夹具不含SmartArt，因此没有把`smartArtTextFormatUndo`记为已验证；含SmartArt的客户Deck仍须单独执行该项。

当前机器门禁证明v4.3 Golden Deck及其Artifact-tool回读文件符合本次自动化合同；Microsoft PowerPoint人工保存往返和交互验收尚待重跑。任何基准通过都不自动替代未来客户Deck、Windows PowerPoint或其他Office版本的逐文件验收。
