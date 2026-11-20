# -*- coding: utf-8 -*-
"""小凡智能体图标生成器 v2

一次产出全套图标（桌面快捷方式 / exe / PWA / APK / 网页 favicon）：
  icon.png                  1024 主图
  icon.ico                  多尺寸（16/20/24/32/40/48/64/128/256）
  icons/icon-192.png        PWA
  icons/icon-512.png        PWA
  icons/icon-maskable-512.png  PWA（安卓自适应，满幅底图 + 安全区）
  icons/apple-touch-icon-180.png  iOS 主屏
  icons/favicon.ico         网页

设计：深墨底 + 鎏金内框 + 光晕 +「凡」字 + ✦ 星标。
4 倍超采样渲染，缩到目标尺寸后边缘干净。
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SS = 4                    # 超采样倍数
BASE = 1024               # 主图边长
S = BASE * SS             # 渲染尺寸

GOLD_HI = (246, 222, 160)
GOLD = (226, 184, 87)
GOLD_LO = (186, 138, 58)


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def radial_bg(size):
    """暖色径向渐变：左上微亮，右下更深。低分辨率算完再放大，避免百万级逐像素循环。"""
    small = 384
    bg = Image.new("RGB", (small, small), (0, 0, 0))
    px = bg.load()
    cx, cy = small * 0.32, small * 0.26
    maxd = math.hypot(small, small) * 0.9
    for y in range(small):
        for x in range(small):
            t = min(1.0, math.hypot(x - cx, y - cy) / maxd)
            px[x, y] = (
                int(28 - 16 * t),
                int(25 - 15 * t),
                int(26 - 14 * t),
            )
    return bg.resize((size, size), Image.BICUBIC)


def star_points(cx, cy, r, ratio=0.30):
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = r if i % 2 == 0 else r * ratio
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def pick_font(size):
    for fp in [
        r"C:\Windows\Fonts\STKAITI.TTF",
        r"C:\Windows\Fonts\simkai.ttf",
        r"C:\Windows\Fonts\STSONG.TTF",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
    ]:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_art(canvas, inset, corner_radius, glyph_scale=1.0):
    """在 canvas（RGBA, 边长 S）上画圆角图标主体，inset 为四周留白。"""
    box = [inset, inset, S - inset - 1, S - inset - 1]
    w = box[2] - box[0] + 1
    radius = int(corner_radius * (w / float(S)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)

    bg = radial_bg(S).convert("RGBA")
    canvas.paste(bg, (0, 0), mask)

    # 内发光边框（外圈亮、内圈淡）
    d = ImageDraw.Draw(canvas)
    stroke = max(2, int(w * 0.012))
    d.rounded_rectangle(box, radius=radius, outline=GOLD + (235,), width=stroke)
    inner = [box[0] + stroke * 2, box[1] + stroke * 2, box[2] - stroke * 2, box[3] - stroke * 2]
    d.rounded_rectangle(inner, radius=int(radius * 0.86), outline=GOLD + (70,), width=max(1, stroke // 3))

    # 左上光晕
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [inset - w * 0.18, inset - w * 0.18, inset + w * 0.52, inset + w * 0.52],
        fill=(238, 205, 120, 78),
    )
    g = glow.filter(ImageFilter.GaussianBlur(w * 0.10))
    g.putalpha(ImageChops.multiply(g.split()[3], mask))  # 光晕裁到圆角内，避免方形硬边
    canvas.alpha_composite(g)

    # 「凡」字：金色竖向渐变 + 柔和投影
    font = pick_font(int(w * 0.62 * glyph_scale))
    tmp = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    bbox = td.textbbox((0, 0), "凡", font=font)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = S / 2 - gw / 2 - bbox[0]
    ty = S / 2 - gh / 2 - bbox[1] + w * 0.015
    td.text((tx, ty), "凡", font=font, fill=(255, 255, 255, 255))
    glyph_mask = tmp.split()[3]

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(glyph_mask.filter(ImageFilter.GaussianBlur(w * 0.018)))
    shadow = Image.composite(
        Image.new("RGBA", (S, S), (0, 0, 0, 150)), Image.new("RGBA", (S, S), (0, 0, 0, 0)), shadow.split()[3]
    )
    canvas.alpha_composite(shadow, (0, int(w * 0.012)))

    grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    top, bot = ty + bbox[1], ty + bbox[3]
    for y in range(S):
        t = min(1.0, max(0.0, (y - top) / max(1.0, bot - top)))
        gd.line(
            [(0, y), (S, y)],
            fill=(
                int(GOLD_HI[0] + (GOLD_LO[0] - GOLD_HI[0]) * t),
                int(GOLD_HI[1] + (GOLD_LO[1] - GOLD_HI[1]) * t),
                int(GOLD_HI[2] + (GOLD_LO[2] - GOLD_HI[2]) * t),
                255,
            ),
        )
    canvas.alpha_composite(Image.composite(grad, Image.new("RGBA", (S, S), (0, 0, 0, 0)), glyph_mask), (0, 0))

    # ✦ 星标
    d = ImageDraw.Draw(canvas)
    sx, sy = inset + w * 0.80, inset + w * 0.19
    d.polygon(star_points(sx, sy, w * 0.075), fill=GOLD_HI + (240,))
    d.polygon(star_points(sx + w * 0.085, sy + w * 0.10, w * 0.036), fill=GOLD + (185,))


def build(size, full_bleed=False, glyph_scale=1.0):
    """生成指定边长的最终图标。full_bleed=True 用于 maskable（满幅、无圆角）。"""
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if full_bleed:
        # 满幅底 + 安全区内画主体（主体缩到 72%，不会被安卓裁掉）
        canvas.paste(radial_bg(S).convert("RGBA"), (0, 0))
        art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw_art(art, inset=int(S * 0.135), corner_radius=110 * S / 512.0, glyph_scale=glyph_scale * 0.86)
        canvas.alpha_composite(art)
    else:
        draw_art(canvas, inset=int(S * 0.035), corner_radius=110 * S / 512.0, glyph_scale=glyph_scale)
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(os.path.join(HERE, "icons"), exist_ok=True)

    master = build(BASE)
    master.save(os.path.join(HERE, "icon.png"))

    icos = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    master_ico = build(256)
    master_ico.save(
        os.path.join(HERE, "icon.ico"),
        sizes=[(n, n) for n in icos],
    )
    master_ico.save(os.path.join(HERE, "icons", "favicon.ico"), sizes=[(n, n) for n in icos])

    build(192).save(os.path.join(HERE, "icons", "icon-192.png"))
    build(512).save(os.path.join(HERE, "icons", "icon-512.png"))
    build(512, full_bleed=True).save(os.path.join(HERE, "icons", "icon-maskable-512.png"))
    build(180).save(os.path.join(HERE, "icons", "apple-touch-icon-180.png"))

    for f in ["icon.png", "icon.ico", "icons/icon-192.png", "icons/icon-512.png",
              "icons/icon-maskable-512.png", "icons/apple-touch-icon-180.png", "icons/favicon.ico"]:
        p = os.path.join(HERE, f)
        print(f"{f:34s} {os.path.getsize(p):>7,d} bytes")


if __name__ == "__main__":
    main()
