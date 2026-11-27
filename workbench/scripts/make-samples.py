"""生成工作台预览用的示例文件（docx / pptx / pdf / png / xlsx / diff / md）。

只用于本地演示；输出到 workbench/public/samples/。
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor as PptxRGB
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt as PptPt

OUT = Path(__file__).resolve().parents[1] / "public" / "samples"
OUT.mkdir(parents=True, exist_ok=True)

FONT_CN = r"C:\Windows\Fonts\msyh.ttc"
FONT_CN_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
GOLD = (226, 184, 87)
TXT = (236, 232, 223)
DIM = (152, 147, 138)
BG = (13, 14, 17)
PANEL = (23, 24, 29)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_CN_BOLD if bold else FONT_CN
    return ImageFont.truetype(path, size)


def vertical_gradient(w: int, h: int, top=(19, 20, 25), bottom=(9, 10, 13)) -> Image.Image:
    img = Image.new("RGB", (w, h), top)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def draw_glow(img: Image.Image, center, radius, color, alpha=70):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    steps = 24
    for i in range(steps, 0, -1):
        r = radius * i / steps
        a = int(alpha * (1 - i / steps) ** 1.8)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
    img.alpha_composite(layer) if img.mode == "RGBA" else img.paste(
        Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0)
    )


def make_png():
    w, h = 1440, 900
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    base = vertical_gradient(w, h).convert("RGBA")
    img = Image.alpha_composite(img, base)
    draw_glow(img, (250, 150), 380, (226, 184, 87), 85)
    draw_glow(img, (1180, 720), 420, (126, 106, 248), 55)
    d = ImageDraw.Draw(img)

    # 顶部装饰线
    d.rounded_rectangle([72, 70, 1368, 830], radius=28, outline=(255, 255, 255, 26), width=1)

    d.text((110, 112), "小凡智能体 · 工作台视觉稿", font=font(42, True), fill=TXT)
    d.text((112, 176), "Workbench concept / dark gold system", font=font(22), fill=GOLD)

    # 三分栏示意
    panels = [
        (110, 248, 360, 730, "导航树"),
        (388, 248, 1000, 730, "对话中枢"),
        (1028, 248, 1300, 730, "预览停靠"),
    ]
    for x1, y1, x2, y2, label in panels:
        d.rounded_rectangle([x1, y1, x2, y2], radius=18, fill=(255, 255, 255, 10), outline=(255, 255, 255, 28))
        d.text((x1 + 22, y1 + 18), label, font=font(20, True), fill=(242, 212, 146))

    # 左侧树
    rows = ["小凡工作区", "  ◇ 会话 · 需求梳理", "  ◇ 会话 · 代码评审", "  ◆ 智能体 · 写作", "  ◆ API · DeepSeek", "  文件 · product-spec.docx"]
    for i, text in enumerate(rows):
        y = 306 + i * 44
        if i == 1:
            d.rounded_rectangle([126, y - 6, 342, y + 30], radius=10, fill=(226, 184, 87, 34))
        d.text((140, y), text, font=font(17), fill=TXT if i != 5 else DIM)

    # 中间对话气泡
    d.rounded_rectangle([416, 300, 972, 372], radius=16, fill=(30, 31, 36), outline=(255, 255, 255, 18))
    d.text((438, 318), "帮我把这份需求整理成可执行的开发任务。", font=font(18), fill=TXT)
    d.rounded_rectangle([416, 392, 972, 520], radius=16, fill=(255, 255, 255, 8), outline=(255, 255, 255, 20))
    d.text((438, 410), "已拆分为 6 个任务，并生成任务清单：", font=font(18), fill=TXT)
    for i, t in enumerate(["梳理工作台三栏状态", "接入旧聊天 iframe", "封装 dockview 预览 API", "统一预览样式"]):
        d.ellipse([442, 452 + i * 22, 450, 460 + i * 22], fill=GOLD)
        d.text((462, 444 + i * 22), t, font=font(15), fill=DIM)
    d.rounded_rectangle([416, 620, 972, 706], radius=22, fill=(23, 24, 29), outline=(226, 184, 87, 90))
    d.text((440, 646), "继续追问，或拖入文件让我直接看…", font=font(17), fill=(130, 126, 118))
    d.rounded_rectangle([922, 630, 960, 668], radius=14, fill=GOLD)
    d.line([(934, 656), (948, 642)], fill=BG, width=3)
    d.line([(948, 642), (948, 656)], fill=BG, width=3)
    d.line([(948, 656), (934, 642)], fill=BG, width=3)

    # 右侧预览 tab
    d.rounded_rectangle([1050, 288, 1278, 330], radius=10, fill=(226, 184, 87, 40))
    d.text((1066, 297), "product-spec.docx", font=font(15, True), fill=(242, 212, 146))
    d.rounded_rectangle([1034, 344, 1294, 714], radius=12, fill=(255, 255, 255, 6))
    for i in range(7):
        y = 380 + i * 42
        width = 220 - (i % 3) * 40
        d.rounded_rectangle([1054, y, 1054 + width, y + 12], radius=6, fill=(255, 255, 255, 32 if i else 90))
    d.text((1054, 680), "docx-preview · 自定义皮肤", font=font(14), fill=DIM)

    d.text((110, 790), "布局：react-resizable-panels  ·  树：react-arborist  ·  停靠：dockview-react", font=font(16), fill=(103, 99, 89))

    img = img.convert("RGB")
    img.save(OUT / "design.png", quality=92)
    print("png ok")


def make_pdf():
    w, h = 1240, 1754
    img = vertical_gradient(w, h, (18, 19, 24), (10, 11, 14))
    d = ImageDraw.Draw(img)
    d.text((90, 90), "技术方案 · AI 智能体工作台", font=font(46, True), fill=TXT)
    d.text((92, 158), "React + TypeScript + zustand · 三栏式桌面工作台", font=font(22), fill=GOLD)

    d.rounded_rectangle([90, 230, 1150, 236], radius=3, fill=(226, 184, 87, 120))

    sections = [
        ("01 / 目标", "把原有聊天 HTML 作为独立内核嵌入中间栏，工作台只负责外壳、布局与文件预览。"),
        ("02 / 边界", "不引入 assistant-ui，不接管 LLM 与工具调用；聊天 sendMsg / SSE / 分支逻辑留在旧页。"),
        ("03 / 结构", "左：react-arborist 导航树；中：旧页 iframe 插槽；右：dockview 预览停靠区。"),
        ("04 / 预览", "docx / pptx / pdf / image / xlsx / diff / terminal 七类预览，按扩展名自动匹配。"),
    ]
    y = 290
    for title, body in sections:
        d.text((92, y), title, font=font(26, True), fill=(242, 212, 146))
        y += 46
        # 中文自动换行
        line, lines = "", []
        for ch in body:
            if d.textlength(line + ch, font=font(20)) > 980:
                lines.append(line)
                line = ch
            else:
                line += ch
        if line:
            lines.append(line)
        for ln in lines:
            d.text((94, y), ln, font=font(20), fill=(210, 205, 195))
            y += 34
        y += 26

    # 简单的指标条
    d.text((92, y + 10), "组件依赖覆盖率", font=font(24, True), fill=TXT)
    y += 60
    metrics = [("react-arborist", 0.95), ("dockview-react", 0.88), ("docx-preview", 0.8), ("react-pdf", 0.72)]
    for name, pct in metrics:
        d.text((94, y), name, font=font(18), fill=DIM)
        d.rounded_rectangle([360, y + 3, 1040, y + 25], radius=11, fill=(255, 255, 255, 20))
        d.rounded_rectangle([360, y + 3, 360 + int(680 * pct), y + 25], radius=11, fill=GOLD)
        d.text((1052, y), f"{int(pct * 100)}%", font=font(18), fill=(242, 212, 146))
        y += 48

    d.text((92, 1640), "小凡智能体 · 仅供内部方案评审", font=font(16), fill=(103, 99, 89))
    img.save(OUT / "tech-plan.pdf", resolution=150.0)
    print("pdf ok")


def make_docx():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)

    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(10.5)
    style.font.color.rgb = RGBColor(0x2B, 0x26, 0x20)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = title.add_run("AI 智能体工作台\n产品需求说明")
    run.font.size = Pt(24)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x8F, 0x6A, 0x24)
    run.font.name = "微软雅黑"

    p = doc.add_paragraph()
    r = p.add_run("版本 v0.1 · 2026-11-26 · 工作台外壳与文件预览交互")
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x71, 0x6B, 0x60)

    doc.add_paragraph()
    doc.add_heading("1. 背景与目标", level=1)
    doc.add_paragraph(
        "现有聊天页已经具备 sendMsg、SSE 流式输出、会话分支等自研能力。"
        "本次不重写聊天内核，只新增一层桌面工作台外壳，把导航、聊天、文件预览整合到同一窗口。"
    )

    doc.add_heading("2. 三分栏结构", level=1)
    for text in [
        "左侧：react-arborist 导航树，节点包含工作区、会话、自定义 Agent、API 配置、文件。",
        "中间：聊天插槽，嵌入原有聊天 HTML 模板，保留全部自研逻辑。",
        "右侧：dockview 停靠面板，支持 Tab、拖拽拆分、关闭与布局持久化。",
    ]:
        p = doc.add_paragraph(text, style="List Bullet")
        p.paragraph_format.space_after = Pt(4)

    doc.add_heading("3. 预览类型", level=1)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, text in enumerate(["文件类型", "扩展名", "预览组件"]):
        hdr[i].text = text
        for run in hdr[i].paragraphs[0].runs:
            run.font.bold = True
            run.font.size = Pt(10)
    rows = [
        ("Word", ".docx / .doc", "docx-preview"),
        ("PowerPoint", ".pptx / .ppt", "pptx-react-viewer"),
        ("PDF", ".pdf", "react-pdf"),
        ("图片", ".png / .jpg / .webp / .gif", "react-photo-view"),
        ("表格", ".xlsx / .xls / .csv", "SheetJS"),
        ("代码对比", ".diff / .patch", "diff2html"),
        ("终端", "-", "@xterm/xterm"),
    ]
    for row in rows:
        cells = table.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = text
            for run in cells[i].paragraphs[0].runs:
                run.font.size = Pt(9)

    doc.add_heading("4. 验收标准", level=1)
    for text in [
        "点击左侧文件节点，右侧自动新建对应预览 Tab，同一文件重复点击只聚焦不重复创建。",
        "所有预览组件不加载库自带主题，颜色与间距由工作台 CSS 变量统一控制。",
        "聊天 iframe 的 sendMsg / SSE / 会话分支完全沿用旧页，工作台不实现聊天逻辑。",
        "刷新页面后 dockview 布局与打开的文件 Tab 自动恢复。",
    ]:
        p = doc.add_paragraph(text, style="List Number")

    doc.save(OUT / "product-spec.docx")
    print("docx ok")


def make_pptx():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    bg = prs.slides.add_slide(prs.slide_layouts[6])
    # 背景
    fill = bg.background.fill
    fill.solid()
    fill.fore_color.rgb = PptxRGB(0x0D, 0x0E, 0x11)

    def textbox(slide, x, y, w, h, text, size=28, color=PptxRGB(0xEC, 0xE8, 0xDF), bold=False):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = PptPt(size)
        p.font.color.rgb = color
        p.font.bold = bold
        p.font.name = "微软雅黑"
        return box

    # 封面
    accent = bg.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.08))
    accent.fill.solid()
    accent.fill.fore_color.rgb = PptxRGB(0xE2, 0xB8, 0x57)
    accent.line.fill.background()
    textbox(bg, 0.9, 1.7, 11.5, 1.1, "AI 智能体工作台", 54, PptxRGB(0xF2, 0xD4, 0x92), True)
    textbox(bg, 0.95, 2.9, 11.5, 0.7, "三栏式外壳 · 旧聊天内核 · 可停靠文件预览", 24, PptxRGB(0x98, 0x93, 0x8A))
    textbox(bg, 0.95, 6.2, 11.5, 0.5, "小凡智能体 · 2026 内部方案", 14, PptxRGB(0x67, 0x63, 0x59))

    # 结构页
    s2 = prs.slides.add_slide(prs.slide_layouts[6])
    s2.background.fill.solid()
    s2.background.fill.fore_color.rgb = PptxRGB(0x0D, 0x0E, 0x11)
    textbox(s2, 0.8, 0.6, 11.5, 0.8, "三分栏布局", 36, PptxRGB(0xF2, 0xD4, 0x92), True)
    cols = [
        ("左栏", "react-arborist\n工作区 / 会话 / Agent / API / 文件"),
        ("中栏", "聊天插槽\n旧 HTML iframe · sendMsg / SSE / 分支"),
        ("右栏", "dockview-react\n七类预览 · 拖拽拆分 · 布局持久化"),
    ]
    for i, (head, body) in enumerate(cols):
        x = 0.75 + i * 4.15
        card = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.8), Inches(3.7), Inches(4.2))
        card.fill.solid()
        card.fill.fore_color.rgb = PptxRGB(0x17, 0x18, 0x1D)
        card.line.color.rgb = PptxRGB(0x2C, 0x2D, 0x33)
        textbox(s2, x + 0.25, 2.1, 3.2, 0.5, head, 20, PptxRGB(0xE2, 0xB8, 0x57), True)
        textbox(s2, x + 0.25, 2.8, 3.2, 2.4, body, 15, PptxRGB(0xD5, 0xD0, 0xC6))

    # 数据页（原生图表，可编辑）
    s3 = prs.slides.add_slide(prs.slide_layouts[6])
    s3.background.fill.solid()
    s3.background.fill.fore_color.rgb = PptxRGB(0x0D, 0x0E, 0x11)
    textbox(s3, 0.8, 0.5, 11.5, 0.8, "预览能力覆盖", 36, PptxRGB(0xF2, 0xD4, 0x92), True)
    chart_data = CategoryChartData()
    chart_data.categories = ["docx", "pptx", "pdf", "image", "xlsx", "diff", "xterm"]
    chart_data.add_series("组件接入", (100, 100, 100, 100, 100, 100, 100))
    chart = s3.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.9), Inches(1.6), Inches(11.4), Inches(4.8), chart_data
    ).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.has_title = False
    plot = chart.plots[0]
    plot.gap_width = 80
    series = plot.series[0]
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = PptxRGB(0xE2, 0xB8, 0x57)
    textbox(s3, 0.9, 6.55, 11.5, 0.4, "所有 Tab 均由扩展名自动匹配，样式统一由工作台 CSS 控制", 14, PptxRGB(0x98, 0x93, 0x8A))

    prs.save(OUT / "quarterly-review.pptx")
    print("pptx ok")


def make_xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "销售数据"

    gold = "E2B857"
    dark = "17181D"
    light = "F5F0E6"
    border = Border(
        left=Side(style="thin", color="D9D2C3"),
        right=Side(style="thin", color="D9D2C3"),
        top=Side(style="thin", color="D9D2C3"),
        bottom=Side(style="thin", color="D9D2C3"),
    )

    ws.merge_cells("A1:F1")
    ws["A1"] = "2026 Q4 销售数据总览"
    ws["A1"].font = Font(name="微软雅黑", size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor=dark)
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 34

    headers = ["区域", "Q4 目标", "Q4 实际", "完成率", "同比增长", "负责人"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=c, value=h)
        cell.font = Font(name="微软雅黑", size=10.5, bold=True, color="2B2620")
        cell.fill = PatternFill("solid", fgColor=gold)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
    ws.row_dimensions[3].height = 24

    data = [
        ("华东", 1200000, 1286000, 1.12, 0.072, "林晚"),
        ("华南", 980000, 902000, 0.995, -0.021, "陈屿"),
        ("华北", 760000, 813000, 1.005, 0.018, "赵一鸣"),
        ("西南", 540000, 498000, 0.795, -0.062, "周梨"),
        ("海外", 1500000, 1635000, 1.09, 0.245, "Mia"),
    ]
    for r, row in enumerate(data, 4):
        for c, val in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = Font(name="微软雅黑", size=10)
            cell.border = border
            cell.alignment = Alignment(horizontal="center" if c > 1 else "left", vertical="center")
            cell.fill = PatternFill("solid", fgColor=light if r % 2 == 0 else "FFFFFF")
        ws.cell(row=r, column=2).number_format = '¥#,##0'
        ws.cell(row=r, column=3).number_format = '¥#,##0'
        ws.cell(row=r, column=4).number_format = '0.0%'
        ws.cell(row=r, column=5).number_format = '0.0%;[Red]-0.0%'

    ws.cell(row=9, column=1, value="合计").font = Font(name="微软雅黑", size=10.5, bold=True)
    ws.cell(row=9, column=2, value=4980000).number_format = '¥#,##0'
    ws.cell(row=9, column=3, value=5137000).number_format = '¥#,##0'
    ws.cell(row=9, column=4, value=1.0315).number_format = '0.0%'
    for c in range(1, 7):
        cell = ws.cell(row=9, column=c)
        cell.fill = PatternFill("solid", fgColor="EFE7D6")
        cell.border = border
        cell.font = Font(name="微软雅黑", size=10.5, bold=True)

    widths = [12, 14, 14, 12, 12, 10]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # 第二个 sheet：明细
    ws2 = wb.create_sheet("月度明细")
    months = ["7月", "8月", "9月", "10月", "11月", "12月"]
    values = [182, 206, 214, 238, 251, 260]
    ws2["A1"] = "月度营收（万元）"
    ws2["A1"].font = Font(name="微软雅黑", size=14, bold=True)
    ws2.append([])
    for i, (m, v) in enumerate(zip(months, values), 1):
        ws2.cell(row=3, column=i, value=m)
        ws2.cell(row=4, column=i, value=v)
        ws2.cell(row=4, column=i).number_format = '0.0'
    for c in range(1, 7):
        ws2.cell(row=3, column=c).font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        ws2.cell(row=3, column=c).fill = PatternFill("solid", fgColor="8F6A24")
        ws2.cell(row=3, column=c).alignment = Alignment(horizontal="center")
        ws2.cell(row=4, column=c).alignment = Alignment(horizontal="center")
    for i in range(1, 7):
        ws2.column_dimensions[get_column_letter(i)].width = 11

    wb.save(OUT / "sales-data.xlsx")
    print("xlsx ok")


def make_diff():
    diff = """diff --git a/src/preview/registry.ts b/src/preview/registry.ts
index 3f2a1c0..b71d9e4 100644
--- a/src/preview/registry.ts
+++ b/src/preview/registry.ts
@@ -1,18 +1,27 @@
 import type { ComponentType } from 'react';
 
-export type PreviewKind = 'docx' | 'pdf' | 'image' | 'sheet';
+export type PreviewKind =
+  | 'docx'
+  | 'pptx'
+  | 'pdf'
+  | 'image'
+  | 'sheet'
+  | 'diff'
+  | 'terminal';
 
 const registry: Record<string, PreviewKind> = {
   docx: 'docx',
   doc: 'docx',
+  pptx: 'pptx',
+  ppt: 'pptx',
   pdf: 'pdf',
   png: 'image',
   jpg: 'image',
+  webp: 'image',
   xlsx: 'sheet',
   xls: 'sheet',
+  csv: 'sheet',
+  diff: 'diff',
+  patch: 'diff',
 };
 
-export function resolvePreview(path: string): PreviewKind {
+export function resolvePreview(path: string): PreviewKind | null {
   const ext = path.split('.').pop()?.toLowerCase() ?? '';
-  return registry[ext] ?? 'docx';
+  return registry[ext] ?? null;
 }
@@ -24,8 +33,10 @@ export function resolvePreview(path: string): PreviewKind {
     case 'docx':
       return import('./DocxPreview');
+    case 'pptx':
+      return import('./PptxPreview');
     case 'pdf':
       return import('./PdfPreview');
     default:
-      return import('./DocxPreview');
+      return import('./TextPreview');
   }
 }
"""
    (OUT / "code-review.diff").write_text(diff, encoding="utf-8")
    print("diff ok")


def make_md():
    text = """# 工作台接入说明

## 1. 旧聊天页

把旧 `index.html` 复制到 `public/legacy/chat.html`（`pnpm sync:legacy` 会自动完成），
工作台用 iframe 嵌入中间栏，只通过 bridge 传递会话列表与选中会话。

- `sendMsg` / SSE / 会话分支：保持原样
- 侧栏、旧右侧预览：在嵌入副本里隐藏
- 文件预览：由工作台 dockview 接管

## 2. 旧 Agent / API 配置页

把你的旧 HTML 放到：

- `public/legacy/agent-config.html`
- `public/legacy/api-config.html`

点击左侧对应节点时，中间栏直接加载该文件，不生成任何新表单。

## 3. 外部 API

```ts
window.xiaofanWorkbench.openPreview({ path, url, name });
window.xiaofanWorkbench.openTerminal();
window.xiaofanWorkbench.closeTab(id);
```

## 4. 样式

所有颜色来自 `src/styles/workbench.css` 顶部的 `--wb-*` 变量；
dockview、xterm、diff2html、photo-view 的外观均被覆盖，不加载第三方主题。
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")
    print("md ok")


if __name__ == "__main__":
    make_png()
    make_pdf()
    make_docx()
    make_pptx()
    make_xlsx()
    make_diff()
    make_md()
    print("samples ->", OUT)
