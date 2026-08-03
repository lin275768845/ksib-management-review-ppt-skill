#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUTPUT_DIR = path.resolve(process.argv[2] ?? "output");
const PX_PER_INCH = 96;
const PX_PER_POINT = 96 / 72;
const FONT = "PingFang SC";
const C = {
  orange: "#FF4906",
  deepOrange: "#D83D00",
  paleOrange: "#FFF7F3",
  paleOrangeLine: "#FFDBCD",
  ink: "#1F2329",
  gray: "#646A73",
  darkGray: "#3B4048",
  midGray: "#AEB2BA",
  barGray: "#D9DCE1",
  softGray: "#F5F6F7",
  line: "#E5E6EB",
  white: "#FFFFFF",
};

const inch = (value) => value * PX_PER_INCH;
const pt = (value) => value * PX_PER_POINT;

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function addText(slide, {
  name,
  text,
  x,
  y,
  w,
  h,
  fontPt,
  color = C.ink,
  bold = false,
  align = "left",
  vertical = "top",
  fill = "none",
  line = { style: "solid", fill: "none", width: 0 },
}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position: {
      left: inch(x),
      top: inch(y),
      width: inch(w),
      height: inch(h),
    },
    fill,
    line,
  });
  shape.text = text;
  shape.text.style = {
    fontSize: pt(fontPt),
    typeface: FONT,
    color,
    bold,
    alignment: align,
    verticalAlignment: vertical,
    autoFit: "none",
    wrap: "square",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function addRect(slide, {
  name,
  x,
  y,
  w,
  h,
  fill,
  line = { style: "solid", fill: "none", width: 0 },
}) {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position: {
      left: inch(x),
      top: inch(y),
      width: inch(w),
      height: inch(h),
    },
    fill,
    line,
  });
}

function addLine(slide, {
  name,
  x,
  y,
  w,
  color,
  width = 1,
}) {
  return slide.shapes.add({
    geometry: "line",
    name,
    position: {
      left: inch(x),
      top: inch(y),
      width: inch(w),
      height: 0,
    },
    fill: "none",
    line: { style: "solid", fill: color, width },
  });
}

function addHeader(slide, {
  header,
  title,
  mode,
  subtitle,
  source,
  page,
}) {
  addRect(slide, {
    name: "header-accent",
    x: 0.8,
    y: 0.15,
    w: 0.03,
    h: 0.2,
    fill: C.orange,
  });
  addText(slide, {
    name: "header-text",
    text: header,
    x: 0.92,
    y: 0.15,
    w: 11.61,
    h: 0.2,
    fontPt: 10,
    color: C.gray,
    bold: true,
    vertical: "middle",
  });
  const titleHeight = mode === "title-two-line" ? 0.72 : 0.4;
  addText(slide, {
    name: "action-title",
    text: title,
    x: 0.8,
    y: 0.55,
    w: 11.733,
    h: titleHeight,
    fontPt: 22,
    bold: true,
  });
  let dividerY = 1.1;
  if (mode === "title-subtitle") {
    addText(slide, {
      name: "subtitle",
      text: subtitle,
      x: 0.8,
      y: 0.99,
      w: 11.733,
      h: 0.24,
      fontPt: 14,
      color: C.gray,
    });
    dividerY = 1.3;
  } else if (mode === "title-two-line") {
    dividerY = 1.38;
  }
  addRect(slide, {
    name: "title-divider",
    x: 0.8,
    y: dividerY,
    w: 11.733,
    h: 0.01,
    fill: C.line,
  });
  addLine(slide, {
    name: "footer-divider",
    x: 0.8,
    y: 6.95,
    w: 11.733,
    color: C.line,
    width: 1,
  });
  addText(slide, {
    name: "source-footnote",
    text: source,
    x: 0.8,
    y: 7.05,
    w: 10.8,
    h: 0.2,
    fontPt: 9,
    color: C.gray,
  });
  addText(slide, {
    name: "page-number",
    text: String(page),
    x: 12.2,
    y: 7.1,
    w: 1.0,
    h: 0.3,
    fontPt: 9,
    color: C.gray,
    align: "right",
  });
}

function setCellRules(cell, {
  topFill = null,
  topWidth = 0,
  bottomFill = null,
  bottomWidth = 0,
} = {}) {
  for (const side of ["left", "right", "top", "bottom"]) {
    cell.borders[side].visible = false;
  }
  if (topFill && topWidth > 0) {
    cell.borders.top.visible = true;
    cell.borders.top.fill = topFill;
    cell.borders.top.width = topWidth;
  }
  if (bottomFill && bottomWidth > 0) {
    cell.borders.bottom.visible = true;
    cell.borders.bottom.fill = bottomFill;
    cell.borders.bottom.width = bottomWidth;
  }
}

function applyTableBase(table, {
  rows,
  columns,
  headerFontPt,
  bodyFontPt,
  variant = "analysis",
  numericColumns = [],
  centerColumns = [],
}) {
  const allCells = table.cells.block({
    row: 0,
    column: 0,
    rowCount: rows,
    columnCount: columns,
  });
  allCells.fill = C.white;
  allCells.textStyle.fontSize = pt(bodyFontPt);
  allCells.textStyle.color = C.ink;
  const header = table.cells.block({
    row: 0,
    column: 0,
    rowCount: 1,
    columnCount: columns,
  });
  header.fill = variant === "appendix" ? C.softGray : C.white;
  header.textStyle.fontSize = pt(headerFontPt);
  header.textStyle.color = C.ink;
  header.textStyle.bold = true;
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const cell = table.getCell(row, column);
      cell.text.typeface = FONT;
      cell.textStyle.alignment = centerColumns.includes(column)
        ? "center"
        : numericColumns.includes(column)
          ? "right"
          : "left";
      cell.margins = {
        top: inch(0.08),
        right: inch(0.1),
        bottom: inch(0.08),
        left: inch(0.1),
      };
      cell.anchor = "middle";
      const isHeader = row === 0;
      const showBodyRule = variant === "appendix" && row > 0 && row < rows - 1;
      setCellRules(cell, {
        topFill: isHeader ? C.orange : null,
        topWidth: isHeader ? 2 : 0,
        bottomFill: isHeader ? C.midGray : showBodyRule ? C.line : null,
        bottomWidth: isHeader ? 1 : showBodyRule ? 0.5 : 0,
      });
      if (
        variant === "appendix"
        && rows > 10
        && row > 0
        && row % 2 === 0
      ) {
        cell.fill = "#FAFAFA";
      }
    }
  }
}

function buildCover(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addRect(slide, {
    name: "cover-accent-line",
    x: 0.8,
    y: 1.05,
    w: 0.06,
    h: 1.75,
    fill: C.orange,
  });
  addText(slide, {
    name: "cover-wordmark",
    text: "KSIB FORMAT ENGINEERING",
    x: 0.98,
    y: 0.94,
    w: 3,
    h: 0.3,
    fontPt: 12,
    color: C.orange,
    bold: true,
  });
  addText(slide, {
    name: "cover-title",
    text: "KSIB / MBB FORMAT\nGOLDEN DECK",
    x: 0.98,
    y: 2,
    w: 10.6,
    h: 1.15,
    fontPt: 44,
    bold: true,
  });
  addText(slide, {
    name: "cover-subtitle",
    text: "咨询型PowerPoint格式与原生可编辑性基准",
    x: 0.98,
    y: 3.45,
    w: 10.5,
    h: 0.55,
    fontPt: 24,
  });
  addText(slide, {
    name: "cover-statement",
    text: "固定6页、固定对象、固定样式；仅评估格式与编辑性，不评估内容生成",
    x: 0.98,
    y: 4.25,
    w: 10.5,
    h: 0.5,
    fontPt: 16,
    color: C.gray,
  });
  addText(slide, {
    name: "cover-meta",
    text: "Benchmark v1.0｜2026-07-30",
    x: 0.98,
    y: 6.55,
    w: 5,
    h: 0.28,
    fontPt: 14,
    color: C.gray,
  });
}

function buildChartSlide(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, {
    header: "I-1｜原生图表",
    title: "类别D达到57，形成唯一视觉焦点；其余三项保持中性呈现",
    subtitle: "基准测试虚构数据｜单系列、4个类别、单位：指数",
    mode: "title-subtitle",
    source: "数据来源：KSIB Golden Deck 基准测试虚构数据；仅用于格式与编辑性测试",
    page: 2,
  });
  const chart = slide.charts.add("bar", {
    position: {
      left: inch(0.8),
      top: inch(1.52),
      width: inch(8.6),
      height: inch(5.2),
    },
    categories: ["A", "B", "C", "D"],
    series: [{
      name: "类别指数",
      values: [18, 32, 41, 57],
      valuesFormatCode: "0",
      fill: C.barGray,
      points: [{ idx: 3, fill: C.orange }],
      dataLabelOverrides: [0, 1, 2, 3].map((idx) => ({
        idx,
        showValue: true,
        position: "outEnd",
        textStyle: {
          fill: idx === 3 ? C.orange : C.gray,
          fontSize: pt(idx === 3 ? 14 : 12),
          bold: true,
        },
      })),
    }],
    hasLegend: false,
    barOptions: {
      direction: "bar",
      grouping: "clustered",
      gapWidth: 88,
    },
    chartFill: C.white,
    chartLine: { style: "solid", fill: "none", width: 0 },
    plotAreaFill: C.white,
    plotAreaLine: { style: "solid", fill: "none", width: 0 },
    xAxis: {
      visible: true,
      tickLabelPosition: "nextTo",
      textStyle: { fill: C.gray, fontSize: pt(12) },
      line: { style: "solid", fill: "none", width: 0 },
      majorGridlines: null,
    },
    yAxis: {
      visible: false,
      tickLabelPosition: "none",
      line: { style: "solid", fill: "none", width: 0 },
      majorGridlines: null,
    },
    dataLabels: {
      showValue: true,
      position: "outEnd",
      textStyle: { fill: C.gray, fontSize: pt(12), bold: true },
    },
  });
  chart.data.name = "chart-main";
  addText(slide, {
    name: "metric-1",
    text: "57",
    x: 9.75,
    y: 1.75,
    w: 2.78,
    h: 0.48,
    fontPt: 24,
    color: C.orange,
    bold: true,
  });
  addText(slide, {
    name: "metric-label-1",
    text: "最高值｜类别D",
    x: 9.75,
    y: 2.28,
    w: 2.78,
    h: 0.35,
    fontPt: 14,
    color: C.gray,
  });
  addText(slide, {
    name: "metric-2",
    text: "+39",
    x: 9.75,
    y: 3.05,
    w: 2.78,
    h: 0.48,
    fontPt: 24,
    color: C.ink,
    bold: true,
  });
  addText(slide, {
    name: "metric-label-2",
    text: "较类别A的差值",
    x: 9.75,
    y: 3.58,
    w: 2.78,
    h: 0.35,
    fontPt: 14,
    color: C.gray,
  });
  addText(slide, {
    name: "chart-reading-note",
    text: "强调色只服务于唯一主证据；其余类别使用中性色，避免制造多个视觉中心。",
    x: 9.75,
    y: 4.55,
    w: 2.78,
    h: 1.25,
    fontPt: 14,
    color: C.ink,
  });
}

function buildTableSlide(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, {
    header: "I-2｜原生表格",
    title: "原生表格应在高信息密度下保留单元格级格式控制",
    mode: "title-only",
    source: "数据来源：KSIB Golden Deck 基准测试虚构数据；仅用于格式与编辑性测试",
    page: 3,
  });
  const values = [
    ["模块", "基期", "当期", "变化", "说明"],
    ["A", "100", "112", "+12%", "稳定上升"],
    ["B", "100", "104", "+4%", "小幅增长"],
    ["C", "100", "97", "-3%", "轻微回落"],
    ["D", "100", "126", "+26%", "增长最快"],
    ["合计", "400", "439", "+9.8%", "基准汇总"],
  ];
  const tableFrame = {
    x: 0.8,
    y: 1.55,
    w: 8.55,
    h: 4.85,
  };
  const table = slide.tables.add({
    rows: values.length,
    columns: values[0].length,
    left: inch(tableFrame.x),
    top: inch(tableFrame.y),
    width: inch(tableFrame.w),
    height: inch(tableFrame.h),
    columnWidths: [1.4, 1.15, 1.15, 1.15, 3.7].map(inch),
    values,
  });
  table.data.name = "table-main";
  applyTableBase(table, {
    rows: values.length,
    columns: values[0].length,
    headerFontPt: 14,
    bodyFontPt: 12,
    variant: "analysis",
    numericColumns: [1, 2, 3],
  });
  const growthCell = table.cells.block({
    row: 4,
    column: 3,
    rowCount: 1,
    columnCount: 1,
  });
  growthCell.textStyle.fontSize = pt(12);
  growthCell.textStyle.color = C.orange;
  growthCell.textStyle.bold = true;
  const totalRow = table.cells.block({
    row: 5,
    column: 0,
    rowCount: 1,
    columnCount: 5,
  });
  totalRow.fill = C.white;
  totalRow.textStyle.fontSize = pt(12);
  totalRow.textStyle.color = C.ink;
  totalRow.textStyle.bold = true;
  addLine(slide, {
    name: "table-total-rule",
    x: tableFrame.x,
    y: tableFrame.y
      + (tableFrame.h * (values.length - 1)) / values.length,
    w: tableFrame.w,
    color: C.orange,
    width: 1.5,
  });
  addRect(slide, {
    name: "insight-panel-accent",
    x: 9.7,
    y: 1.55,
    w: 0.04,
    h: 2.95,
    fill: C.orange,
  });
  const insight = addText(slide, {
    name: "insight-panel",
    text: "",
    x: 9.94,
    y: 1.55,
    w: 2.59,
    h: 3.4,
    fontPt: 14,
  });
  insight.text.set([
    [{ run: "格式验证重点", textStyle: { bold: true, fontSize: "16pt" } }],
    [{ run: "改单元格填充", textStyle: { bold: true } }, "｜验证局部样式"],
    [{ run: "改字体颜色", textStyle: { bold: true } }, "｜验证文字控制"],
    [{ run: "取消加粗", textStyle: { bold: true } }, "｜验证按钮语义"],
    [{ run: "复制粘贴", textStyle: { bold: true } }, "｜仍为原生表格"],
  ]);
  insight.text.style = {
    fontSize: pt(14),
    typeface: FONT,
    color: C.ink,
    verticalAlignment: "top",
    autoFit: "none",
    wrap: "square",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
}

function buildComparisonSlide(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, {
    header: "I-3｜左右比较",
    title: "左右比较依靠统一基线、等宽列和局部强调建立清晰取舍",
    mode: "title-only",
    source: "数据来源：KSIB Golden Deck 基准测试虚构内容；仅用于格式与编辑性测试",
    page: 4,
  });
  addRect(slide, {
    name: "column-divider",
    x: 6.665,
    y: 1.34,
    w: 0.01,
    h: 5.16,
    fill: C.line,
  });
  const left = addText(slide, {
    name: "column-left",
    text: "",
    x: 0.8,
    y: 1.34,
    w: 5.69,
    h: 5.16,
    fontPt: 14,
  });
  left.text.set([
    [{ run: "方案A｜稳态优化", textStyle: { bold: true, fontSize: "18pt", color: C.ink } }],
    [{ run: "适用条件｜", textStyle: { bold: true } }, "已有流程可复用"],
    [{ run: "核心动作｜", textStyle: { bold: true } }, "缩短交付链路"],
    [{ run: "资源需求｜", textStyle: { bold: true } }, { run: "2", textStyle: { bold: true, color: C.orange } }, "个角色"],
    [{ run: "主要风险｜", textStyle: { bold: true } }, "局部改善有限"],
  ]);
  left.text.style = {
    ...left.text.style,
    fontSize: pt(14),
    typeface: FONT,
    color: C.ink,
    lineSpacing: 1.45,
    insets: { top: 0, right: inch(0.18), bottom: 0, left: 0 },
  };
  const right = addText(slide, {
    name: "column-right",
    text: "",
    x: 6.84,
    y: 1.34,
    w: 5.69,
    h: 5.16,
    fontPt: 14,
  });
  right.text.set([
    [{ run: "方案B｜结构升级", textStyle: { bold: true, fontSize: "18pt", color: C.orange } }],
    [{ run: "适用条件｜", textStyle: { bold: true } }, "需重构关键接口"],
    [{ run: "核心动作｜", textStyle: { bold: true } }, "建立统一模板"],
    [{ run: "资源需求｜", textStyle: { bold: true } }, { run: "3", textStyle: { bold: true, color: C.orange } }, "个角色"],
    [{ run: "主要风险｜", textStyle: { bold: true } }, "迁移期成本较高"],
  ]);
  right.text.style = {
    ...right.text.style,
    fontSize: pt(14),
    typeface: FONT,
    color: C.ink,
    lineSpacing: 1.45,
    insets: { top: 0, right: 0, bottom: 0, left: inch(0.18) },
  };
}

function buildProcessSlide(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, {
    header: "I-4｜流程与连接器",
    title: "端到端流程通过四个原生节点形成闭环，\n反馈连接器将复核结果重新带回输入端",
    mode: "title-two-line",
    source: "数据来源：KSIB Golden Deck 格式基准规范",
    page: 5,
  });
  const nodeContent = [
    ["接收输入", "读取固定内容与约束"],
    ["选择版式", "匹配结构合同与容量"],
    ["生成页面", "写入原生文本\n图表与表格"],
    ["校验交付", "运行结构、视觉\n与交互检查"],
  ];
  const nodes = nodeContent.map(([heading, body], index) => {
    const shape = addRect(slide, {
      name: `process-node-${index + 1}`,
      x: [0.8, 3.881, 6.962, 10.043][index],
      y: 2.15,
      w: 2.49,
      h: 2.35,
      fill: index === 2 ? C.paleOrange : C.white,
      line: {
        style: "solid",
        fill: index === 2 ? C.paleOrangeLine : C.line,
        width: 1,
      },
    });
    shape.text.set([
      [{ run: `0${index + 1}`, textStyle: { bold: true, color: C.orange, fontSize: "14pt" } }],
      [{ run: heading, textStyle: { bold: true, fontSize: "16pt" } }],
      [{ run: body, textStyle: { fontSize: "12pt" } }],
    ]);
    shape.text.style = {
      fontSize: pt(14),
      typeface: FONT,
      color: C.ink,
      alignment: "left",
      verticalAlignment: "middle",
      autoFit: "none",
      wrap: "square",
      insets: {
        top: inch(0.18),
        right: inch(0.15),
        bottom: inch(0.18),
        left: inch(0.15),
      },
    };
    return shape;
  });
  for (let index = 0; index < 3; index += 1) {
    const connector = slide.shapes.connect(nodes[index], nodes[index + 1], {
      kind: "straight",
      fromSide: "right",
      toSide: "left",
      line: { style: "solid", fill: C.gray, width: 2 },
      tail: { type: "arrow", width: "med", length: "med" },
    });
    connector.data.name = `connector-${index + 1}`;
  }
  const feedback = slide.shapes.connect(nodes[3], nodes[0], {
    kind: "elbow5",
    fromSide: "bottom",
    toSide: "bottom",
    line: { style: "dashed", fill: C.gray, width: 2 },
    tail: { type: "arrow", width: "med", length: "med" },
  });
  feedback.data.name = "feedback-connector";
  addText(slide, {
    name: "feedback-label",
    text: "复核反馈",
    x: 5.65,
    y: 5.55,
    w: 2.03,
    h: 0.3,
    fontPt: 12,
    color: C.gray,
    align: "center",
  });
}

function buildAppendixSlide(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, {
    header: "附录 A-1｜高密度页",
    title: "高密度附录可以使用10pt正文，但不能牺牲可读性和编辑性",
    mode: "title-only",
    source: "数据来源：KSIB Golden Deck 格式基准规范",
    page: 6,
  });
  addText(slide, {
    name: "appendix-note",
    text: "基准对象清单｜仅用于对象类型与交互动作检查",
    x: 0.8,
    y: 1.32,
    w: 11.733,
    h: 0.28,
    fontPt: 12,
    color: C.gray,
  });
  const values = [
    ["#", "对象", "原生类型", "字号", "颜色/样式", "交互动作", "通过标准"],
    ["1", "cover-title", "文本框", "44", "无填充", "改字与撤销", "文本直接编辑"],
    ["2", "chart-main", "原生图表", "12/14", "灰＋橙", "改数据与撤销", "图表更新"],
    ["3", "table-main", "原生表格", "12/14", "白底＋细规则线", "改单元格", "格式保持"],
    ["4", "column-left", "文本框", "14", "混合加粗", "改色及取消加粗", "局部可控"],
    ["5", "connector-1", "原生连接器", "—", "灰色实线", "移动节点", "连线吸附"],
    ["6", "feedback-connector", "原生连接器", "—", "灰色虚线", "改端点", "箭头保持"],
    ["7", "page-number", "页码文本", "9", "无", "调整页序后复核", "位置与格式稳定"],
  ];
  const table = slide.tables.add({
    rows: values.length,
    columns: values[0].length,
    left: inch(0.8),
    top: inch(1.7),
    width: inch(11.733),
    height: inch(5.1),
    columnWidths: [0.65, 1.95, 1.3, 0.9, 1.7, 2.6, 2.633].map(inch),
    values,
  });
  table.data.name = "appendix-table";
  applyTableBase(table, {
    rows: values.length,
    columns: values[0].length,
    headerFontPt: 12,
    bodyFontPt: 10,
    variant: "appendix",
    centerColumns: [0, 3],
  });
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  const presentation = Presentation.create({
    slideSize: { width: 1280, height: 720 },
  });
  presentation.theme.colorScheme = {
    name: "KSIB Management Review Orange",
    themeColors: {
      accent1: C.orange,
      accent2: C.deepOrange,
      accent3: C.paleOrange,
      accent4: C.paleOrangeLine,
      accent5: C.darkGray,
      accent6: C.line,
      bg1: C.white,
      bg2: "#FAFAFA",
      tx1: C.ink,
      tx2: C.gray,
      dk1: C.ink,
      lt1: C.white,
      dk2: C.gray,
      lt2: "#FAFAFA",
      hlink: "#3370FF",
      folHlink: "#7C3AED",
    },
  };

  buildCover(presentation);
  buildChartSlide(presentation);
  buildTableSlide(presentation);
  buildComparisonSlide(presentation);
  buildProcessSlide(presentation);
  buildAppendixSlide(presentation);

  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(
      path.join(OUTPUT_DIR, `${stem}.png`),
      await presentation.export({ slide, format: "png", scale: 1 }),
    );
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(
      path.join(OUTPUT_DIR, `${stem}.layout.json`),
      await layout.text(),
    );
  }
  await writeBlob(
    path.join(OUTPUT_DIR, "deck-montage.webp"),
    await presentation.export({ format: "webp", montage: true, scale: 1 }),
  );
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(path.join(OUTPUT_DIR, "KSIB_MBB_FORMAT_GOLDEN_DECK_V1.pptx"));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
