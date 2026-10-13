# -*- coding: utf-8 -*-
"""拼版大图切面板辅助（当 figtools.detect 失败时用）。

**什么时候需要它**：期刊大图是"整张拼版"（一页一张位图，内含 A/B/C… 多个面板），
而 `figtools.py detect` 的连通域检测只认得出 2 个左右的面板 —— 因为面板之间的白缝
不贯通整行或整列，自动切不准。

**正确姿势（别靠"看渲染图猜比例"）**：
  显示器缩放一变，估算的比例尺就不同，猜出来的坐标必然要来回返工。
  用坐标网格读，一次就准。

三个子命令：

  1) 看白缝（先粗定位）
     python panel_guide.py grid <大图>

  2) 叠坐标网格（★ 关键步骤，直接读出像素坐标）
     python panel_guide.py overlay <大图> <输出.png> [间隔=100]

  3) 批量裁 + 拼校对图（一次看完再修正，别一张张看）
     python panel_guide.py crop <boxes.json> <输出目录> <校对图.png>

boxes.json 格式：
  { "<大图路径>": { "面板名": [x0, y0, x1, y1], ... }, ... }
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def _font(size):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ─────────────────── 1) 白缝检测 ───────────────────
def find_gutters(path, thresh=248, frac=0.99, min_len=3):
    """找出"近全白"的行/列区间 —— 面板之间的白缝。

    注意：拼版图的白缝常常**不贯通**整行/整列（相邻面板跨行排布），
    所以这里给出的只是**候选**分割线，必须配合 overlay 人工确认。
    """
    a = np.asarray(Image.open(path).convert("L"))
    h, w = a.shape
    rows = (a > thresh).mean(axis=1) > frac
    cols = (a > thresh).mean(axis=0) > frac

    def runs(mask):
        out, s = [], None
        for i, v in enumerate(mask):
            if v and s is None:
                s = i
            elif not v and s is not None:
                out.append((s, i - 1)); s = None
        if s is not None:
            out.append((s, len(mask) - 1))
        return [(a0, b0) for a0, b0 in out if b0 - a0 + 1 >= min_len]

    return runs(rows), runs(cols), (w, h)


def cmd_grid(path):
    rows, cols, (w, h) = find_gutters(path)
    print(f"{os.path.basename(path)}  {w}x{h}")
    print(f"  水平白缝 {len(rows)} 条（可作 y 分割线）:")
    for a, b in rows:
        print(f"    y {a}-{b}   → 建议 y={(a+b)//2}")
    print(f"  垂直白缝 {len(cols)} 条（可作 x 分割线）:")
    for a, b in cols:
        print(f"    x {a}-{b}   → 建议 x={(a+b)//2}")
    if not rows and not cols:
        print("  ★ 没有贯通的白缝 —— 典型的多面板拼版图，请用 overlay 人工定框")


# ─────────────────── 2) 坐标网格 ───────────────────
def cmd_overlay(src, out, step=100):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    dr = ImageDraw.Draw(im)
    f = _font(18)
    for x in range(0, w, step):
        major = (x % (step * 5) == 0)
        dr.line([(x, 0), (x, h)], fill=(255, 0, 255) if major else (255, 170, 255),
                width=2 if major else 1)
        dr.text((x + 3, 3), str(x), font=f, fill=(200, 0, 200))
        dr.text((x + 3, h - 24), str(x), font=f, fill=(200, 0, 200))
    for y in range(0, h, step):
        major = (y % (step * 5) == 0)
        dr.line([(0, y), (w, y)], fill=(0, 200, 255) if major else (155, 230, 255),
                width=2 if major else 1)
        dr.text((3, y + 3), str(y), font=f, fill=(0, 120, 170))
        dr.text((w - 60, y + 3), str(y), font=f, fill=(0, 120, 170))
    im.save(out, optimize=True)
    print(f"{src}  {w}x{h}  →  {out}   （读网格上的刻度即可定坐标）")


# ─────────────────── 3) 批量裁 + 校对图 ───────────────────
def cmd_crop(spec_path, outdir, sheet_out, cell=400, cols=4):
    spec = json.load(open(spec_path, encoding="utf-8"))
    os.makedirs(outdir, exist_ok=True)
    tiles = []
    for src, panels in spec.items():
        im = Image.open(src).convert("RGB")
        for name, box in panels.items():
            c = im.crop(tuple(box))
            c.save(os.path.join(outdir, name + ".png"), optimize=True)
            tiles.append((name, c))
            print(f"  {name:<20} {c.width}x{c.height}   <= {os.path.basename(src)}{box}")

    f = _font(20)
    rows = math.ceil(len(tiles) / cols)
    W = cols * (cell + 10) + 10
    H = rows * (cell + 40) + 10
    sheet = Image.new("RGB", (W, H), (238, 240, 244))
    dr = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = 10 + c * (cell + 10), 10 + r * (cell + 40)
        t = im.copy(); t.thumbnail((cell, cell), Image.LANCZOS)
        sheet.paste(t, (x + (cell - t.width) // 2, y + 30))
        dr.text((x + 4, y + 4), f"{name} {im.width}x{im.height}", font=f, fill=(20, 60, 100))
        dr.rectangle([x, y, x + cell, y + cell + 30], outline=(180, 190, 200))
    sheet.save(sheet_out, optimize=True)
    print(f"校对图 → {sheet_out}  {sheet.size}   ★ 一次看完再修正，别一张张看")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "grid":
        cmd_grid(sys.argv[2])
    elif cmd == "overlay":
        cmd_overlay(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 100)
    elif cmd == "crop":
        cmd_crop(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(__doc__)
