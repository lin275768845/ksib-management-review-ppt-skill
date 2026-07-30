# KSIB 咨询与管理汇报 PPT Skill

发行日期：2026-07-23  
主 Skill：`ksib-management-review-ppt`

这是一套面向中文咨询报告、管理汇报和市场研究演示文稿的 Codex Skill。它把故事线、证据链、版式合同、原生可编辑性和交付门禁连接成一套工作流，适合：

- 市场、竞争、渠道、价格、人群和消费者研究；
- 战略建议、管理述职、任命评审和经营复盘；
- 根据已锁定内容制作正式客户 PPT；
- 在完全不改文字、数字和页序的前提下统一既有 PPT 格式；
- 检查 PowerPoint 的颜色、加粗、字体、表格、图表和 SmartArt 是否真正可编辑。

## 1. 包内文件

```text
KSIB_PPT_Skill_20260723/
├── README.md
├── DISTRIBUTION_NOTICE.md
├── PACKAGE_MANIFEST.json
├── CHECKSUMS.sha256
├── skills/
│   ├── ksib-management-review-ppt/   # 主 Skill
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

## 6. “真正可编辑”的含义

对象能够被选中，并不等于对象真的可编辑。Skill会自动检查或清理：

- `noMove`、`noResize`、`noSelect`、`noTextEdit`、`noGrp`等对象锁；
- 重复的字符级颜色覆盖；
- 只写在默认段落层、导致Bold按钮无法直接取消的加粗属性；
- 普通Shape、表格单元格、图表文字、SmartArt和备注页中的DrawingML文本；
- 修改前后文字、数字、对象绑定、颜色、加粗和字体语义漂移。

自动检查不能替代Microsoft PowerPoint中的真实操作。最终交付前仍必须实际完成并撤销：

- 文字替换、字体颜色修改、加粗取消／恢复、字体族修改；
- Shape填充色修改；
- 两个对象的组合与取消组合；
- 表格单元格改色和取消加粗；
- 图表标题／标签改色、取消加粗和图表数据编辑；
- SmartArt文字格式修改。

任何一项无法直接完成，都不能把文件描述为“原生可编辑”。

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
python3 "$CODEX_HOME/skills/ksib-management-review-ppt/scripts/test_ooxml_editability.py"
```

如果最后一条提示缺少`lxml`，请改用Codex工作区提供的bundled Python，或在独立Python环境中安装`lxml`后重试。

## 8. 典型交付物

完整客户PPT项目通常应保留：

- 最终 `.pptx`；
- 锁定的 `storyline.json`；
- `evidence.json`与结构化内容文件；
- Storyline、Evidence、Content和Visual Gate报告；
- 修改前后语义指纹报告（仅format-only）；
- 逐页PNG复核结果；
- `ksib-release-manifest/3.0`；
- Microsoft PowerPoint人工检查记录。

只有全部必需门禁通过，且PowerPoint没有修复提示、图表错误或不可编辑对象，才应交付。

## 9. 常见问题

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

## 10. 安全、升级与卸载

- 不要把密钥、Token、Cookie、`.env`、未脱敏业务底稿或个人隐私材料放入Skill目录。
- 仅处理可信来源的本地PPTX；不要把未知来源或可能恶意构造的Office压缩包直接交给脚本。
- `ooxml_sanitize.py --in-place`会修改目标文件；始终先保留原始文件，并优先在副本上运行。
- 对外发送PPT前，检查宏、外部链接、嵌入对象、媒体和演讲者备注。
- 升级前先备份同名Skill目录，再完整替换；不建议把两个版本的文件直接合并。
- 卸载时删除对应Skill目录，并重新打开Codex任务。
- `mck-ppt-design`为Apache-2.0第三方组件；再次分发时必须保留其`LICENSE`与`NOTICE`。
- KSIB与Storyline自定义Skill未在本发行包中授予公开再分发许可证；接收方可按分享者授权范围使用。
- 完整分发边界见发行包根目录的`DISTRIBUTION_NOTICE.md`；不要把整个发行包笼统标注为Apache-2.0。
