# 方法来源与吸收边界

观察日期：2026-07-18。Star仅用于判断社区使用信号，不代表方法优劣；具体规则按许可证和任务适配性选择性吸收。

| 公开来源 | 当日信号 | 吸收内容 | 不吸收内容 |
|---|---:|---|---|
| `hugohe3/ppt-master`（MIT） | 39,748 Stars | Strategist与Executor分离、先理解材料再设计、原生可编辑与模板复用边界 | 创意视觉风格、图片生成和动画不作为严肃述职默认 |
| `icip-cas/PPTAgent`（MIT） | 4,831 Stars | 参考Deck先抽取功能类型与内容Schema；Outline先于页面动作；Content／Design／Coherence三维评估 | 不引入其模型、运行时或端到端生成框架 |
| `Gabberflast/academic-pptx-skill`（MIT） | 691 Stars | Action Title、SCR、Ghost Deck、一页一个主证据、直接标注关键发现、communication-first | 学术引用格式、固定结论页规则不直接套用管理述职 |
| `likaku/Mck-ppt-design-skill`（Apache-2.0） | 219 Stars | 需求→结构→内容→渲染→交付分阶段流程；Layout Matrix、字符容量和机读门禁 | Mck颜色、字体、装饰语言与KSIB品牌冲突时不继承 |
| `floflo11/mbb-decks`（MIT） | 14 Stars | Ghost Deck先行、Pyramid／MECE导向、真实PPTX和来源纪律作为交叉验证 | 低社区验证度，不直接作为工程底座 |
| Promptiers AI Presentation Toolkit（公开Gist，未见明确许可证） | 非仓库 | 仅参考公开方法思想：标题评分、标题串读、横向与纵向逻辑分离 | 不复制其文本、模板或专有措辞 |
| 用户提供的BCG参考Deck | 私有参考 | 标题节奏、证据主导页面、阶段与反思类信息架构 | 不复制业务内容、品牌视觉或受版权保护的具体页面 |

本Skill的独立增强：

- 将Ghost Deck、证据合同、异议检查和用户锁定整合为可交接JSON；
- 把语义评分与机读结构门禁分开；
- 为中文Action Title设置18–32字优先、40字上限；
- 增加管理者任命述职专用论证弧和检查表；
- 明确Storyline与PPT生产之间的不可越权边界。
