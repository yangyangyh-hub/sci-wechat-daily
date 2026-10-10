# -*- coding: utf-8 -*-
"""文献图处理工具（本项目「每日 SCI 分享」专用，可复用）

用法：
  # 1) 从 PDF 抽出每页大图，并自动识别各面板包围盒，输出带编号的标注图
  python figtools.py detect <pdf路径> <输出目录>

  # 2) 按包围盒表拼接结果图（面板先单独裁，再按行拼接，保证每个面板完整）
  python figtools.py compose <spec.json>

spec.json 格式：
{
  "figures": { "F1": "路径/Fig1.png", ... },
  "boxes":   { "F1_A": [x0,y0,x1,y1], ... },
  "jobs":    [ ["R1_Fig1_A-G", [["F1_A","F1_B"],["F1_C"]]], ... ],
  "width":   1200
}

依赖：pymupdf、Pillow、numpy
  装法：python -m pip install pymupdf pillow numpy
  （缺依赖时脚本会给出可复制的安装命令，不会直接抛栈）
"""
import json
import os
import sys

import numpy as np

# 允许脚本直接运行（python tools/figtools.py ...）时也能 import 同目录的 _env
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _env
except ImportError:  # 极端情况下退化为不检查
    _env = None


# ---------------- 面板检测 ----------------
def _dilate(b, r, axis):
    out = b.copy()
    for _ in range(r):
        if axis == 1:
            out[:, 1:] |= out[:, :-1]
            out[:, :-1] |= out[:, 1:]
        else:
            out[1:, :] |= out[:-1, :]
            out[:-1, :] |= out[1:, :]
    return out


def _label_boxes(mask, min_w=60, min_h=40, min_area=6000):
    h, _ = mask.shape
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    runs = []
    for y in range(h):
        row = mask[y]
        if not row.any():
            runs.append([])
            continue
        idx = np.flatnonzero(np.diff(np.r_[False, row, False].astype(np.int8)))
        rr = []
        for k in range(0, len(idx), 2):
            s, e = int(idx[k]), int(idx[k + 1])
            lab = len(parent)
            parent[lab] = lab
            rr.append((s, e, lab))
        runs.append(rr)
    for y in range(h - 1):
        for s, e, lab in runs[y]:
            for s2, e2, lab2 in runs[y + 1]:
                if s2 <= e and s <= e2:
                    union(lab, lab2)
    box = {}
    for y in range(h):
        for s, e, lab in runs[y]:
            r = find(lab)
            if r not in box:
                box[r] = [s, y, e, y]
            else:
                b = box[r]
                b[0] = min(b[0], s); b[1] = min(b[1], y)
                b[2] = max(b[2], e); b[3] = max(b[3], y)
    out = [(s, y0, e + 1, y1 + 1) for s, y0, e, y1 in box.values()
           if (e - s) >= min_w and (y1 - y0) >= min_h and (e - s) * (y1 - y0) >= min_area]
    return sorted(out, key=lambda t: (t[1], t[0]))


COLORS = [(220, 40, 40), (30, 110, 200), (20, 150, 80), (200, 120, 0), (150, 40, 190), (0, 150, 160)]

# 标注图上的面板编号字体（跨平台候选，找不到就用 PIL 默认字体）
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\msyhbd.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _pick_font(size):
    """按候选列表找一个可用字体；都没有就返回 None（调用方用默认字体）。"""
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


def detect(pdf_path, outdir, shrink=3, radius=4, out_w=1500, dpi=400):
    """抽出 PDF 中的大图（一页一图的期刊排版），逐张识别面板并输出标注图。"""
    if _env:
        if _env.check_pymupdf() is None:
            raise SystemExit(1)
        _env.require("PIL", "numpy")
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(outdir, exist_ok=True)
    doc = fitz.open(pdf_path)
    made = []
    for pno, page in enumerate(doc):
        for xref, *_ in page.get_images(full=True):
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            r = rects[0]
            if r.width < page.rect.width * 0.5:      # 跳过 logo / 页眉
                continue
            info = doc.extract_image(xref)
            raw = os.path.join(outdir, f"p{pno+1}_x{xref}.{info['ext']}")
            with open(raw, "wb") as fh:
                fh.write(info["image"])
            im = Image.open(raw).convert("RGB")
            W, H = im.size
            a = np.asarray(im.convert("L").resize((W // shrink, H // shrink), Image.BILINEAR))
            boxes = _label_boxes(_dilate(_dilate(a < 244, radius, 0), radius, 1))
            boxes = [(x0 * shrink, y0 * shrink, x1 * shrink, y1 * shrink) for x0, y0, x1, y1 in boxes]
            sc = out_w / W
            vis = im.resize((out_w, int(H * sc)), Image.LANCZOS)
            dr = ImageDraw.Draw(vis)
            font = _pick_font(max(20, int(30 * sc * 1.6))) or ImageFont.load_default()
            has_size = hasattr(font, "size")
            box_h = (font.size if has_size else 18) + 10
            for i, (x0, y0, x1, y1) in enumerate(boxes):
                c = COLORS[i % len(COLORS)]
                dr.rectangle([x0 * sc, y0 * sc, x1 * sc, y1 * sc], outline=c, width=3)
                t = str(i)
                dr.rectangle([x0 * sc, y0 * sc, x0 * sc + dr.textlength(t, font=font) + 14, y0 * sc + box_h], fill=c)
                dr.text((x0 * sc + 7, y0 * sc + 3), t, font=font, fill=(255, 255, 255))
            ann = os.path.join(outdir, f"annot_p{pno+1}.png")
            vis.save(ann)
            made.append({"page": pno + 1, "image": raw, "annot": ann,
                         "size": [W, H], "boxes": boxes})
    doc.close()
    with open(os.path.join(outdir, "panels.json"), "w", encoding="utf-8") as fh:
        json.dump(made, fh, ensure_ascii=False, indent=1)
    for m in made:
        print(f"page {m['page']}: {m['size'][0]}x{m['size'][1]}  {len(m['boxes'])} panels -> {m['annot']}")
    print("面板坐标已写入 panels.json")


# ---------------- 拼接 ----------------
def compose(spec_path):
    from PIL import Image
    spec = json.load(open(spec_path, encoding="utf-8"))
    width = spec.get("width", 1200)
    gap = spec.get("gap", 22)
    margin = spec.get("margin", 10)
    src = {k: Image.open(v).convert("RGB") for k, v in spec["figures"].items()}
    boxes, outdir = spec["boxes"], spec.get("outdir", ".")
    os.makedirs(outdir, exist_ok=True)

    def cut(key):
        fam, name = key.split("_", 1)
        return src[fam].crop(tuple(boxes[key]))

    for name, rows in spec["jobs"]:
        rows = [[k for k in r if k] for r in rows]
        rows = [r for r in rows if r]
        row_imgs = []
        for r in rows:
            ims = [cut(k) for k in r]
            h = max(i.height for i in ims)
            w = sum(i.width for i in ims) + gap * (len(ims) - 1)
            cv = Image.new("RGB", (w, h), (255, 255, 255))
            x = 0
            for i in ims:
                cv.paste(i, (x, 0))
                x += i.width + gap
            row_imgs.append(cv)
        tw = max(r.width for r in row_imgs) + margin * 2
        th = sum(r.height for r in row_imgs) + gap * (len(row_imgs) - 1) + margin * 2
        out = Image.new("RGB", (tw, th), (255, 255, 255))
        y = margin
        for r in row_imgs:
            out.paste(r, (margin, y))
            y += r.height + gap
        if out.width > width:
            out = out.resize((width, round(out.height * width / out.width)), Image.LANCZOS)
        p = os.path.join(outdir, name + ".png")
        out.save(p, optimize=True)
        print(f"{name:24s} {out.size[0]}x{out.size[1]:<5d} {round(os.path.getsize(p)/1024,1):>7.1f} KB")


def verify_image(path):
    """★ 必须调用：图片生成后做像素级自检（曾因画布高度写错产出全黑图而只靠肉眼看图没发现）。"""
    from PIL import Image
    a = np.asarray(Image.open(path).convert("L"))
    light = float((a > 200).mean())
    print(f"{os.path.basename(path)}: {a.shape[1]}x{a.shape[0]} 亮像素 {light:.1%} "
          f"{'OK' if light > 0.5 else '★异常（疑似全黑/空图）'}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "detect":
        detect(sys.argv[2], sys.argv[3])
    elif cmd == "compose":
        compose(sys.argv[2])
    elif cmd == "verify":
        for p in sys.argv[2:]:
            verify_image(p)
    else:
        print(__doc__)
