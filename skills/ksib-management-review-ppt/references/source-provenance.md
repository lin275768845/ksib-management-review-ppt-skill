# 外部方法来源与KSIB吸收边界

观察日期：2026-07-18。Star数据用于判断社区使用信号，不作为方法质量的唯一依据。

| 来源 | 当日公开信号 | KSIB吸收 | 明确不吸收 |
|---|---:|---|---|
| `hugohe3/ppt-master`，MIT | 39,748 Stars | Story／Design／Execution职责分离，模板与原生对象边界 | 创意视觉、动画和图片生成不作为严肃述职默认 |
| `icip-cas/PPTAgent`，MIT | 4,831 Stars | 先抽取参考Deck功能类型与内容Schema，再做Outline；Content／Design／Coherence三维QA | 不引入其运行时、模型和端到端生成框架 |
| `Gabberflast/academic-pptx-skill`，MIT | 691 Stars | Action Title、Ghost Deck、一页一个主证据、关键发现就地标注 | 学术引用格式与固定结尾规则不直接套用 |
| `likaku/Mck-ppt-design-skill`，Apache-2.0 | 219 Stars | 画布、边距、动态间距、Layout Matrix、字符预算、五阶段门禁 | Mck品牌颜色、字体和装饰皮肤 |
| 用户提供的BCG参考Deck | 私有参考 | 标题纵向节奏、证据型页面、七类信息架构 | 具体业务内容、品牌皮肤和低字号做法 |

Storyline方法由`linzhe-mbb-storyline`独立管理；本Skill只消费锁定合同，不重复内置一套故事线生成器。
