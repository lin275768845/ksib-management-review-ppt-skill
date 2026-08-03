# KSIB 咨询与管理汇报 PPT Skill

发行日期：2026-07-31
发行版本：v4.2
主 Skill：`ksib-management-review-ppt`

这是一套面向中文咨询报告、管理汇报和市场研究演示文稿的 Codex Skill。它把故事线、证据链、版式合同、原生可编辑性和交付门禁连接成一套工作流，适合：

- 市场、竞争、渠道、价格、人群和消费者研究；
- 战略建议、管理述职、任命评审和经营复盘；
- 根据已锁定内容制作正式客户 PPT；
- 在完全不改文字、数字和页序的前提下统一既有 PPT 格式；
- 检查 PowerPoint 的颜色、加粗、字体、表格、图表和 SmartArt 是否真正可编辑。

v4.2新增“固定Chrome跨页绝对对齐”能力：按版型Profile统一页眉小矩形、页眉文字、标题、Subtitle、标题／页脚分隔线、来源和页码，并以PowerPoint底层EMU整数做零容差门禁。归一化脚本默认只审计，只有显式`--apply`才写入新副本，同时保留目标页可见文字、数字和字段。

## 1. 包内文件

```text
KSIB_PPT_Skill_20260731_v4.2/
├── README.md
├── DISTRIBUTION_NOTICE.md
├── PACKAGE_MANIFEST.json
├── CHECKSUMS.sha256
├── skills/
│   ├── ksib-management-review-ppt/   # 主 Skill，内含Golden Deck回归夹具
│   └── linzhe-mbb-storyline/         # 新建／重构故事线所需依赖
└── third_party/
    └── mck-ppt-design/               # 版式方法参考，Apache-2.0
```

`mck-ppt-design`仅作为咨询版式、容量和页面选择方法的参考依赖。KSIB Skill 不调用其 `python-pptx` 生产路径，本发行包也没有把Mck独立渲染器作为已验证能力；第三方版权和许可证见该目录中的 `LICENSE` 与 `NOTICE`。

## 2. 运行条件

推荐环境：

- Codex Desktop 或支持本地 Skills 的 Codex 环境；
- 内置 `Presentations` Skill、`@oai/artifact-tool`或另行验证的原生PowerPoint构建器；
- Node.js 18或更高版本；
- Python 3.10或更高版本，并安装 `lxml`；
- Microsoft PowerPoint，用于最终真实编辑性验收。

Codex Desktop 用户应优先使用工作区内置的 Node.js 和 Python 运行时，不要默认系统 `python3` 已安装 `lxml`。

字体建议：

- macOS：PingFang SC（PowerPoint中显示为“苹方-简”）；
- Windows：Microsoft YaHei。

## 3. 安装

### macOS / Linux

首次安装前确认目标目录中没有需要保留的同名旧版本。如已有旧版本，请先自行备份，不要直接合并覆盖。三个目录安装后必须位于同一个`skills`目录，且目录名不得修改。

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME/skills"

cp -R skills/ksib-management-review-ppt "$CODEX_HOME/skills/"
cp -R skills/linzhe-mbb-storyline "$CODEX_HOME/skills/"
cp -R third_party/mck-ppt-design "$CODEX_HOME/skills/"
```

### Windows

把以下三个目录完整复制到：

```text
%USERPROFILE%\.codex\skills\
```

需要复制的目录如下。三个目录安装后必须位于同一个`skills`目录，且目录名不得修改：

```text
skills\ksib-management-review-ppt
skills\linzhe-mbb-storyline
third_party\mck-ppt-design
```

复制完成后，新建一个Codex任务，或重启当前客户端，使Skill目录重新载入。

## 4. 如何调用

在提示词中明确写出：

```text
使用 $ksib-management-review-ppt
```

### 模式A：只改格式，不改内容

适合用户已经锁定全部文字、数字和页序，只希望统一字体、页眉、页码、标题高度、对象位置或原生可编辑性。

示例：

```text
使用 $ksib-management-review-ppt，按format-only模式统一这份PPT的页眉、标题、副标题和页码。
不修改任何文字、数字、页序、颜色语义和加粗语义；修改前后必须运行语义指纹比较。
```

此模式不触发故事线重写。任何文字、数字、页序、对象绑定、颜色或加粗语义漂移都应阻断交付。

先审计既有PPT的固定Chrome，不写入文件：

```bash
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/pptx_chrome_normalizer.py" \
  --input input.pptx \
  --canonical-slide 6 \
  --slides 2,3,5,6,8,9 \
  --profile content-title-subtitle \
  --scope all \
  --roles header-accent,header-text,action-title,subtitle,title-divider,footer-divider,source-footnote,page-number
```

确认Profile、参考页和角色别名后，再加`--apply --output normalized.pptx`生成新副本。`--scope geometry`只同步坐标、尺寸和旋转，适合未授权改变颜色／字体的format-only任务；`--scope style`只同步样式；`--scope all`同时同步两者。固定Chrome最终必须通过`crossSlideEqualityGroups`的`geometryToleranceEmu: 0`门禁；普通单页对象的近似容差不能替代跨页绝对一致。

### 模式B：内容已锁定，制作正式PPT

适合已经有完整报告、Word稿或最终页序，只需要补齐最小故事线合同、证据引用、版式和交付门禁。

示例：

```text
使用 $ksib-management-review-ppt，把这份已经定稿的内容制作为中文客户沟通PPT。
主体内容和结论不得重写；补齐来源、口径和可编辑图表，并输出最终PPTX和QA结果。
```

### 模式C：新建或重构故事线

适合从研究材料出发建立新Deck，或修复现有PPT故事线断裂、重复和“只有主题没有结论”的问题。

示例：

```text
先使用 $linzhe-mbb-storyline 建立并锁定Ghost Deck，
再使用 $ksib-management-review-ppt 完成证据、Layout、制作和交付门禁。
```

在用户确认故事线前，不应进入正式排版。

## 5. 核心工作流

研究、数据或策略型Deck采用：

```text
Source核验
→ Calculation登记
→ Claim登记
→ Evidence门禁
→ Storyline引用Claim并由用户锁定
→ Content引用Claim
→ Storyline交接门禁
→ PPT构建与逐页视觉检查
→ OOXML与原生可编辑性检查
→ Release Manifest
```

几个不可绕过的原则：

1. 证据先于叙述，不补造事实、数字、排名或归因。
2. Action Title负责本页唯一主结论。
3. Subtitle只负责范围、时期、方法、定义或比较边界。
4. Takeaway默认不用；只有新增决策含义、行动、风险或跨证据综合时才使用。
5. Title、Subtitle、Takeaway不得高度重复，也不得为了填补留白而新增结论框。
6. 品牌份额和集中度默认使用包括未识别品牌成交额在内的全样本分母。
7. 不用整页截图伪装成PPT；文字、表格、图表和形状应尽量保持PowerPoint原生可编辑。
8. 受控对象必须使用唯一角色名并通过格式合同校验；“视觉上对齐”不能替代坐标、对象类型和编辑性证据。
9. 同一Profile的固定Chrome必须做到0 EMU跨页一致；页眉小矩形、页眉文字、标题区、页脚线、来源和页码不得因手工拖动产生翻页跳动。
10. 表格默认采用白底表头、无外框、无竖线和数字右对齐；黑色表头不是MBB默认风格。
11. 图表默认删除重复的图例、坐标轴和网格线，优先直接标注，并只保留一个重点色焦点。

## 6. “真正可编辑”的含义

对象能够被选中，并不等于对象真的可编辑。Skill会自动检查或清理：

- `noMove`、`noResize`、`noSelect`、`noTextEdit`、`noGrp`等对象锁；
- 重复的字符级颜色覆盖；
- 只写在默认段落层、导致Bold按钮无法直接取消的加粗属性；
- 普通Shape、表格单元格、图表文字、SmartArt和备注页中的DrawingML文本；
- 修改前后文字、数字、对象绑定、颜色、加粗和字体语义漂移。
- Header、Title、Subtitle、来源和页码的角色名、坐标、尺寸与文本框边距；
- 同一Profile内固定Chrome的原始EMU几何、旋转、填充、线条、文本框边距、字体和段落格式；
- 原生Chart的数据模式、原生Connector的起终节点吸附与箭头，以及动态页码字段。

自动检查不能替代Microsoft PowerPoint中的真实操作。最终交付前仍必须实际完成并撤销：

- 文字替换、字体颜色修改、加粗取消／恢复、字体族修改；
- Shape填充色修改；
- 两个对象的组合与取消组合；
- 表格单元格改色和取消加粗；
- 图表标题／标签改色、取消加粗和图表数据编辑；
- SmartArt文字格式修改。

任何一项无法直接完成，都不能把文件描述为“原生可编辑”。

PowerPoint真机验收必须使用两个与最终文件SHA一致的独立副本：`save-only`副本只执行保存、关闭、重开和重新门禁；`interaction`副本只执行局部编辑与撤销，最终不保存关闭。不要在同一个副本上同时证明“保存无损”和“交互可编辑”，也不要用全选操作代替局部对象检查。

## 7. 快速自检

以下命令应在安装后运行。`$CODEX_HOME`未设置时使用`$HOME/.codex`。

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

node "$CODEX_HOME/skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs" --self-test

node "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/validate_storyline_gate.mjs" \
  --self-test \
  --upstream "$CODEX_HOME/skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs"

node "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/validate_evidence.mjs" --self-test
node "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/validate_content.mjs" --self-test
node "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/validate_storyline_handoff.mjs" --self-test
node "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/build_release_manifest.mjs" --self-test

python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/build_visual_review_gate.py" --self-test
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/prepare_revision.py" --self-test
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/test_ooxml_editability.py"
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/test_format_contract.py"
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/test_design_tokens.py"
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/test_exhibit_styles.py"
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/test_chrome_normalizer.py"
```

如果上述Python测试提示缺少`lxml`，请改用Codex工作区提供的bundled Python，或在独立Python环境中安装`lxml`后重试。

## 8. Golden Deck格式回归

`skills/ksib-management-review-ppt/benchmarks/format-golden-deck`提供固定6页合成Deck，覆盖封面、原生图表、原生表格、左右对比、吸附连接器流程和高密度附录，并将固定Chrome的跨页0 EMU一致性纳入格式合同。它随主Skill安装，用于比较Renderer或OOXML处理链，不是客户模板。

每次改动格式生产链后，至少完成：

```text
重建Golden Deck
→ Sanitizer
→ OOXML与格式合同
→ 全页PNG Visual Gate
→ 回读再导出
→ 语义指纹compare
→ Microsoft PowerPoint人工交互检查
```

当前基准明确区分：

- 原生Chart与“带内嵌工作簿、可直接编辑数据”的Chart；
- 原生Connector与真正吸附起终节点的Connector；
- 静态页码文本与可随页序刷新的`slidenum`字段；
- 对象可选中与颜色、加粗、字体、单元格、图表数据真正可编辑。

高级图表不会因为“像think-cell”就默认接入第三方库。当前开源生态没有一个组件同时覆盖原生PowerPoint、Waterfall／Mekko／Gantt、自动标签避让、Excel联动和模板复用；候选组件、许可证、边界和组合式PoC路径见`skills/ksib-management-review-ppt/references/think-cell-open-source-landscape.md`。本发行包没有安装或捆绑这些候选项目。

## 9. 典型交付物

完整客户PPT项目通常应保留：

- 最终 `.pptx`；
- 锁定的 `storyline.json`；
- `evidence.json`与结构化内容文件；
- Storyline、Evidence、Content和Visual Gate报告；
- 修改前后语义指纹报告（仅format-only）；
- 逐页PNG复核结果；
- `ksib-release-manifest/3.2`；
- Microsoft PowerPoint人工检查记录。

只有全部必需门禁通过，且PowerPoint没有修复提示、图表错误或不可编辑对象，才应交付。

## 10. 常见问题

### Skill没有触发

确认文件位于：

```text
~/.codex/skills/ksib-management-review-ppt/SKILL.md
```

重新打开Codex任务，并在提示词中显式写：

```text
使用 $ksib-management-review-ppt
```

### 新建／重构模式提示缺少上游校验器

确认：

```text
~/.codex/skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs
```

存在且Node.js可运行。

### 选Layout时提示缺少Mck参考Skill

确认：

```text
~/.codex/skills/mck-ppt-design/SKILL.md
```

已经从本发行包的`third_party`目录安装。

### PowerPoint打开时出现修复提示

视为交付失败。不要忽略提示或直接另存为；应先运行OOXML QA并定位损坏的关系、图表、对象或Content Type。

### 字体在Windows发生变化

PingFang SC通常不是Windows系统字体。允许使用Microsoft YaHei回退，或由项目负责人明确批准其他字体；不要静默更换字体。

## 11. 安全、升级与卸载

- 不要把密钥、Token、Cookie、`.env`、未脱敏业务底稿或个人隐私材料放入Skill目录。
- 仅处理可信来源的本地PPTX；不要把未知来源或可能恶意构造的Office压缩包直接交给脚本。
- `ooxml_sanitize.py --in-place`会修改目标文件；始终先保留原始文件，并优先在副本上运行。
- format-only任务先用`prepare_revision.py`生成只读Source副本、Working副本和哈希清单；不得把Working输出写回用户原文件路径。
- 对外发送PPT前，检查宏、外部链接、嵌入对象、媒体和演讲者备注。
- 升级前先备份同名Skill目录，再完整替换；不建议把两个版本的文件直接合并。
- 卸载时删除对应Skill目录，并重新打开Codex任务。
- `mck-ppt-design`为Apache-2.0第三方组件；再次分发时必须保留其`LICENSE`与`NOTICE`。
- KSIB与Storyline自定义Skill未在本发行包中授予公开再分发许可证；接收方可按分享者授权范围使用。
- 完整分发边界见发行包根目录的`DISTRIBUTION_NOTICE.md`；不要把整个发行包笼统标注为Apache-2.0。
