# -*- coding: utf-8 -*-
"""自制配图工具：封面信息卡 + 技术路线图 + 二维码处理。

这三张图不能用原文位图（封面卡和路线图是自制的，二维码来自用户），
但和正文图一样要过像素自检。全部用 Pillow 手绘，**不重绘数据图**。

用法：
  # 1) 封面信息卡（取论文首页信息）
  python make_figures.py cover <spec.json>

  # 2) 技术路线图（横向流程）
  python make_figures.py roadmap <spec.json>

  # 3) 二维码处理（裁白边 + 补静默区 + 放到 900×900）
  python make_figures.py qr <源图> <输出图>

── 封面卡 spec.json ──────────────────────────────
{
  "out": "图片/裁切/封面_论文信息卡.png",
  "journal": "Advanced Science",
  "meta": "Volume 12, Issue 3 | 2025",
  "title_en": "Original English title",
  "title_zh": "中文标题",
  "authors": "Author A, Author B, ...",
  "affils": "1. 单位一；2. 单位二",
  "doi": "10.1002/advs.202400001",
  "date": "2025-01-15",
  "width": 1400
}

── 路线图 spec.json ──────────────────────────────
{
  "out": "图片/裁切/技术路线图.png",
  "title": "研究思路与技术路线",
  "steps": ["第一步做什么", "第二步做什么", "第三步做什么", "第四步做什么"],
  "width": 1400
}

★ 上标写法：用 {^...} 包裹，脚本会判断字号并上移绘制。
  例："10{^9} CFU/mL"、"mg kg{^-1}"
  原因：微软雅黑没有 U+2079（⁹）等上标字形，直接写会渲染成方框。
"""
import json
import os
import re
import sys

# 中文（含全角标点、破折号、引号、省略号）按字折行；其余按词折行
CJK = r"\u3000-\u303f\u4e00-\u9fff\uff00-\uffef\u2014\u2018\u2019\u201c\u201d\u2026"
TOKEN_RE = re.compile(f"[{CJK}]|[^{CJK}\\s]+")

# 字体候选（跨平台；优先带中文的字体，否则中文会渲染成方框）
FONT_REGULAR = [
    r"C:\Windows\Fonts\msyh.ttc",              # Windows 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",            # Windows 黑体
    "/System/Library/Fonts/PingFang.ttc",      # macOS 苹方
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",   # Linux
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
FONT_BOLD = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def _font(size, bold=False, path=None):
    from PIL import ImageFont
    if path:
        return ImageFont.truetype(path, size)
    for c in (FONT_BOLD if bold else FONT_REGULAR):
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    # 兜底：找不到中文字体时仍能出图（中文会变方框，但结构完整）
    return ImageFont.load_default()


def _text_w(draw, text, font):
    """计算文本宽度（不实际绘制）。"""
    return draw.textlength(text, font=font)


def parse_rich(text):
    """把 `a{^b}c` 切成 [('n','a'), ('sup','b'), ('n','c')]，用于手绘上标。"""
    out, buf, i = [], "", 0
    while i < len(text):
        if text.startswith("{^", i):
            j = text.find("}", i)
            if j != -1:
                if buf:
                    out.append(("n", buf)); buf = ""
                out.append(("sup", text[i + 2:j]))
                i = j + 1
                continue
        buf += text[i]; i += 1
    if buf:
        out.append(("n", buf))
    return out


def draw_rich(draw, x, y, text, font, fill, sup_scale=0.68, sup_rise=0.36):
    """绘制含 {^} 上标的文本，返回结束 x。"""
    cx = x
    for kind, seg in parse_rich(text):
        if kind == "n":
            draw.text((cx, y), seg, font=font, fill=fill)
            cx += _text_w(draw, seg, font)
        else:
            sf = _font(max(10, int(font.size * sup_scale)))
            size_px = getattr(font, "size", 16)
            draw.text((cx, y - size_px * sup_rise), seg, font=sf, fill=fill)
            cx += _text_w(draw, seg, sf)
    return cx


def rich_width(draw, text, font, sup_scale=0.68):
    w = 0
    for kind, seg in parse_rich(text):
        f = font if kind == "n" else _font(max(10, int(font.size * sup_scale)))
        w += _text_w(draw, seg, f)
    return w


def wrap_rich(draw, text, font, max_w):
    """按宽度折行（兼容 {^} 标记，标记不占宽度）。

    ★ 必须区分中西文：
      - 中文逐字折行
      - 拉丁词按「词」折行（否则会出现 "si / ngle-cell" 这种从单词中间断开的丑行）
    """
    toks = TOKEN_RE.findall(text)
    lines, cur = [], ""

    def is_cjk(s):
        return bool(re.match(f"[{CJK}]", s))

    for tk in toks:
        # 两个拉丁词之间才补空格
        piece = tk
        if cur and not is_cjk(tk) and not is_cjk(cur[-1]):
            piece = " " + tk
        if not cur or rich_width(draw, cur + piece, font) <= max_w:
            cur += piece
        else:
            lines.append(cur)
            cur = tk
    if cur:
        lines.append(cur)

    # ★ 避头点：标点不能落在行首，否则出现「/ ，锁定…」这种断行
    BAD_HEAD = "，。、；：）】》」』”’％%！？·…"
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in BAD_HEAD:
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
        if not lines[i]:
            lines[i] = ""
    return [ln for ln in lines if ln]


# ─────────────────────── 封面信息卡 ───────────────────────
def make_cover(spec):
    from PIL import Image, ImageDraw
    W = spec.get("width", 1400)
    pad = int(W * 0.055)
    ink = (31, 46, 58)
    muted = (110, 126, 138)
    accent = (31, 78, 107)

    ft_j = _font(int(W * 0.036), bold=True)
    ft_m = _font(int(W * 0.019))
    ft_t = _font(int(W * 0.034), bold=True)
    ft_z = _font(int(W * 0.024))
    ft_b = _font(int(W * 0.017))
    ft_s = _font(int(W * 0.016))

    # 先算高度
    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)
    inner = W - pad * 2

    t_en = ft_t
    t_zh = ft_z
    en_lines = wrap_rich(d, spec.get("title_en", ""), t_en, inner)
    zh_lines = wrap_rich(d, spec.get("title_zh", ""), t_zh, inner)
    # ★ 作者/单位行数必须按实际折行数算高度，否则多作者会把单位行压掉
    au_lines = wrap_rich(d, spec.get("authors", ""), ft_b, inner)[:4]
    af_lines = wrap_rich(d, spec.get("affils", ""), ft_s, inner)[:3]

    h = pad
    h += int(W * 0.052)                      # 期刊行
    h += int(W * 0.020)
    h += int(W * 0.024)                      # 分隔
    h += int(W * 0.028)
    h += len(en_lines) * int(W * 0.048)
    h += int(W * 0.012)
    h += len(zh_lines) * int(W * 0.036)
    h += int(W * 0.030)
    h += len(au_lines) * int(W * 0.023)      # 作者（按实际行数）
    h += int(W * 0.016)                      # 作者与单位之间的留白
    h += len(af_lines) * int(W * 0.031)      # 单位（按实际行数）
    h += int(W * 0.026)
    h += int(W * 0.024)                      # DOI 行
    h += pad

    H = h
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)

    # 顶部色带
    dr.rectangle([0, 0, W, int(W * 0.012)], fill=accent)

    y = pad
    dr.text((pad, y), spec.get("journal", ""), font=ft_j, fill=accent)
    y += int(W * 0.052)
    dr.text((pad, y), spec.get("meta", ""), font=ft_m, fill=muted)
    y += int(W * 0.020)
    dr.line([pad, y, W - pad, y], fill=(224, 229, 233), width=2)
    y += int(W * 0.028)

    for line in en_lines:
        draw_rich(dr, pad, y, line, t_en, ink)
        y += int(W * 0.048)
    y += int(W * 0.012)
    for line in zh_lines:
        dr.text((pad, y), line, font=t_zh, fill=(70, 88, 100))
        y += int(W * 0.036)
    y += int(W * 0.030)

    for line in au_lines:
        dr.text((pad, y), line, font=ft_b, fill=ink)
        y += int(W * 0.023)
    y += int(W * 0.016)
    for line in af_lines:
        dr.text((pad, y), line, font=ft_s, fill=muted)
        y += int(W * 0.031)
    y += int(W * 0.026)

    dr.text((pad, y), f"DOI: {spec.get('doi', '')}", font=ft_s, fill=accent)
    dr.text((W - pad - dr.textlength(spec.get("date", ""), font=ft_s), y),
            spec.get("date", ""), font=ft_s, fill=muted)

    _save(im, spec["out"])


# ─────────────────────── 技术路线图 ───────────────────────
def make_roadmap(spec):
    from PIL import Image, ImageDraw
    W = spec.get("width", 1400)
    steps = spec["steps"]
    n = len(steps)
    pad = int(W * 0.045)
    gap = int(W * 0.022)
    box_w = (W - pad * 2 - gap * (n - 1)) // n

    ft_t = _font(int(W * 0.026), bold=True)
    ft_s = _font(int(W * 0.019))
    ft_n = _font(int(W * 0.024), bold=True)

    inner_w = box_w - int(W * 0.028)
    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)

    wrapped = [wrap_rich(d, s, ft_s, inner_w) for s in steps]
    max_lines = max(len(w) for w in wrapped)
    line_h = int(W * 0.030)
    box_h = int(W * 0.052) + max_lines * line_h + int(W * 0.022)

    H = int(W * 0.052) + int(W * 0.030) + box_h + int(W * 0.040)
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)

    dr.text((pad, int(W * 0.030)), spec.get("title", "研究思路与技术路线"),
            font=ft_t, fill=(31, 46, 58))

    top = int(W * 0.052) + int(W * 0.030)
    accent = (45, 106, 143)

    for i, (step, lines) in enumerate(zip(steps, wrapped)):
        x = pad + i * (box_w + gap)
        # 卡片
        dr.rounded_rectangle([x, top, x + box_w, top + box_h], radius=int(W * 0.012),
                             fill=(247, 250, 252), outline=(206, 220, 230), width=2)
        # 编号圆
        r = int(W * 0.021)
        cx, cy = x + int(W * 0.030), top + int(W * 0.032)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
        num = str(i + 1)
        dr.text((cx - dr.textlength(num, font=ft_n) / 2, cy - r * 0.82),
                num, font=ft_n, fill=(255, 255, 255))
        # 文字
        ty = top + int(W * 0.052)
        for ln in lines:
            draw_rich(dr, x + int(W * 0.016), ty, ln, ft_s, (63, 75, 82))
            ty += line_h
        # 箭头
        if i < n - 1:
            ax = x + box_w + gap // 2
            ay = top + box_h // 2
            a = int(W * 0.010)
            dr.polygon([(ax - a, ay - a), (ax + a, ay), (ax - a, ay + a)], fill=accent)

    _save(im, spec["out"])


# ─────────────────────── 二维码处理 ───────────────────────
def make_qr(src, out, size=900, quiet=4):
    """裁掉多余白边、补标准静默区、缩放成正方形。"""
    from PIL import Image, ImageChops
    im = Image.open(src).convert("RGB")

    # 1) 转灰度、二值化，找内容包围盒
    g = im.convert("L")
    mask = g.point(lambda v: 0 if v < 200 else 255)
    bbox = ImageChops.invert(mask).getbbox()
    if bbox:
        im = im.crop(bbox)

    # 2) 补静默区
    w, h = im.size
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    q = int(side * quiet / 100 * 4)  # 约 4 模块的边距
    final = Image.new("RGB", (side + q * 2, side + q * 2), (255, 255, 255))
    final.paste(canvas, (q, q))

    # 3) 缩放
    final = final.resize((size, size), Image.LANCZOS)
    _save(final, out)


def _save(im, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    im.save(out, optimize=True)
    print(f"written: {out}  {im.size[0]}x{im.size[1]}  {round(os.path.getsize(out)/1024,1)} KB")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "cover":
        make_cover(json.load(open(sys.argv[2], encoding="utf-8")))
    elif cmd == "roadmap":
        make_roadmap(json.load(open(sys.argv[2], encoding="utf-8")))
    elif cmd == "qr":
        make_qr(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
