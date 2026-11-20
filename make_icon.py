# -*- coding: utf-8 -*-
"""生成小凡智能体桌面图标：深色底 + 金色光晕 + 「凡」字 + ✦ 星标"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角方形深色底（对角微渐变模拟高级质感）
bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bd = ImageDraw.Draw(bg)
for y in range(S):
    t = y / S
    r = int(18 + 10 * t); g = int(17 + 9 * t); b = int(21 + 10 * t)
    bd.line([(0, y), (S, y)], fill=(r, g, b, 255))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([8, 8, S-8, S-8], radius=110, fill=255)
img.paste(bg, (0, 0), mask)

# 金色内发光边框
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S-8, S-8], radius=110, outline=(226, 184, 87, 220), width=6)
d.rounded_rectangle([22, 22, S-22, S-22], radius=96, outline=(226, 184, 87, 60), width=2)

# 金色光晕（左上）
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([-120, -120, 260, 260], fill=(232, 197, 106, 70))
glow = glow.filter(ImageFilter.GaussianBlur(80))
img.alpha_composite(glow)

# 「凡」字（金色，楷体系）
font = None
for fp in [r"C:\Windows\Fonts\STKAITI.TTF", r"C:\Windows\Fonts\simkai.ttf",
           r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"]:
    try:
        font = ImageFont.truetype(fp, 300)
        break
    except Exception:
        pass
d = ImageDraw.Draw(img)
bbox = d.textbbox((0, 0), "凡", font=font)
w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
# 文字微渐变金
txt = Image.new("RGBA", (S, S), (0, 0, 0, 0))
td = ImageDraw.Draw(txt)
td.text((S/2 - w/2 - bbox[0], S/2 - h/2 - bbox[1] + 10), "凡", font=font, fill=(240, 214, 146, 255))
gold_mask = txt.split()[3]
grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd2 = ImageDraw.Draw(grad)
for y in range(S):
    t = y / S
    gd2.line([(0, y), (S, y)], fill=(int(242 - 40*t), int(212 - 45*t), int(146 - 50*t), 255))
img.alpha_composite(Image.composite(grad, Image.new("RGBA",(S,S),(0,0,0,0)), gold_mask), (0,0))

# 右上角 ✦ 四角星
def star4(cx, cy, r, color):
    pts = []
    for i in range(8):
        ang = math.pi/2 * (i/2) - math.pi/2
        rad = r if i % 2 == 0 else r*0.32
        pts.append((cx + rad*math.cos(ang), cy + rad*math.sin(ang)))
    d.polygon(pts, fill=color)
star4(408, 96, 34, (242, 212, 146, 235))
star4(448, 148, 16, (226, 184, 87, 180))

img.save(r"D:\桌面版agent\icon.png")
img.resize((256, 256), Image.LANCZOS).save(r"D:\桌面版agent\icon.ico",
    sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("icon OK")
