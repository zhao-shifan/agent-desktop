# -*- coding: utf-8 -*-
"""从 Anthropic 官方技能库拉取 SKILL.md，生成 official_skills.js"""
import base64, json, subprocess

GH = r"C:\Program Files\GitHub CLI\gh.exe"
SKILLS = ["docx", "pptx", "xlsx", "pdf", "frontend-design"]
CN = {
    "docx": ("📝 Word 文档处理（官方）", "创建/编辑/解析 .docx，含目录、页眉页脚、修订与批注处理"),
    "pptx": ("📊 PPT 演示文稿（官方）", "创建/编辑/拆分合并 .pptx，版式与演讲者备注处理"),
    "xlsx": ("📈 表格数据处理（官方）", "读写/修复 .xlsx/.csv，公式、图表、数据清洗"),
    "pdf":  ("📕 PDF 处理（官方）", "读取/合并/拆分/加水印/表单填写/OCR 识别"),
    "frontend-design": ("🎨 前端视觉设计（官方）", "有辨识度的 UI 设计指导：排版、配色、避免模板感"),
}

out = []
for s in SKILLS:
    r = subprocess.run([GH, "api", f"repos/anthropics/skills/contents/skills/{s}/SKILL.md", "-q", ".content"],
                       capture_output=True)
    raw = base64.b64decode(r.stdout.decode().replace("\n", ""))
    text = raw.decode("utf-8")
    name_cn, desc_cn = CN[s]
    out.append({"id": "official-" + s, "name": name_cn, "desc": desc_cn,
                "prompt": text, "official": True,
                "source": "https://github.com/anthropics/skills"})

with open(r"D:\桌面版agent\official_skills.js", "w", encoding="utf-8") as f:
    f.write("// Anthropic 官方技能（来源: github.com/anthropics/skills，遵循其 LICENSE）\n")
    f.write("window.OFFICIAL_SKILLS = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
print("official_skills.js OK,", sum(len(o["prompt"]) for o in out)//1024, "KB prompts")
