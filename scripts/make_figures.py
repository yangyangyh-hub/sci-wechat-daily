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

── 路线图 spec.json（2026-10-23 新版：每环节 3–4 条要点分行）────────
{
  "out": "图片/裁切/技术路线图.png",
  "title": "研究思路与技术路线",
  "stages": [
    {"name": "玛咖粉成分分析", "bullets": ["常规营养成分", "总酚、总黄酮", "抗氧化活性", "酚酸与玛咖酰胺"]},
    {"name": "饲养试验",       "bullets": ["40 头后备母猪", "均重 29 kg，随机分两组", "108 天，分两期饲养", "按栏算 DFI、FCR"]},
    {"name": "屠宰与理化检测", "bullets": ["胴体与脏器重量", "背最长肌 pH、嫩度", "血液生化指标", "回肠食糜 pH、氨、SCFAs"]},
    {"name": "肠道微生物分析", "bullets": ["三个时间点采粪样", "16S rRNA 测序", "alpha / beta 多样性", "门、科、属丰度比较"]}
  ],
  "width": 1100
}

★ 旧字段 `steps: ["...", ...]` 仍兼容（每环节一条长句），但**不再推荐**：
一环节一长句会把字挤成一坨，手机上读不动（2026-10-23 用户返工）。

★ 上标写法：用 {^...} 包裹，脚本会判断字号并上移绘制。
  例："10{^9} CFU/mL"、"mg kg{^-1}"
  原因：微软雅黑没有 U+2079（⁹）等上标字形，直接写会渲染成方框。

★ 字号不用手调：脚本按「微信正文显示宽度 677px」反推字号
  （正文字号 = round(width × 12 / 677)），见 make_roadmap 里的 EFF_* 常量。
  判据：图上看着大没用，要看 `字号 × 677 / 画布宽` 换算后的实际值 ≥ 12px。
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
# ★ 字号换算基准（2026-10-23 定）
#   微信正文里图片按约 677px 宽显示 —— 画布再宽也会被缩到这么宽。
#   所以「图上字号」没有意义，要看换算后的实际值：实际字号 = 图上字号 × 677 / 画布宽。
#   经验值（实测）：实际 ≥ 12px 才读得清；旧版 1080px 画布配 14px → 实际 8.6px，被判「字太小」。
#   → 字号一律由下面的 EFF_* 目标值反推，别手填像素字号。
WX_DISPLAY_W = 677
EFF_TITLE = 21      # 大标题的实际字号目标
EFF_BADGE = 16      # 编号数字
EFF_STAGE = 14      # 环节名
EFF_BODY = 12.5     # 要点正文


def _bullets_of(stage):
    """兼容两种写法：新 {name, bullets} / 旧 "一整句"。"""
    if isinstance(stage, dict):
        return str(stage.get("name", "")), list(stage.get("bullets", []))
    return "", [stage]


def _rebalance(draw, lines, font, min_tail=None):
    """★ 孤行回填：末行太短（1–2 字）时，把上一行末尾的字符/词挪下来。
    中文按单字挪；拉丁词整词挪，不把单词拆断。"""
    if min_tail is None:
        min_tail = getattr(font, "size", 16) * 1.3
    latin = r"[A-Za-z0-9/%·+]"
    while len(lines) >= 2 and _text_w(draw, lines[-1], font) < min_tail:
        prev = lines[-2]
        if not prev:
            break
        if re.search(latin + r"$", prev) and re.search(latin + r"$", prev[:-1]):
            m = re.search(r"(" + latin + r"+)\s*$", prev)   # 拉丁词整词回填（注意要带捕获组）
            if not m or m.start() == 0:
                break
            moved, newprev = m.group(1), prev[: m.start()].rstrip()
        else:                                              # 中文单字回填
            moved, newprev = prev[-1], prev[:-1].rstrip()
            if not newprev:
                break
        sep = " " if (re.search(latin + r"$", newprev) and re.match(latin, moved)) else ""
        lines[-2] = newprev
        lines[-1] = moved + sep + lines[-1]
    return [ln for ln in lines if ln]


def wrap_keep(draw, text, font, max_w):
    """按宽度折行并保留原空格；ASCII 词串不断行；末尾孤字回填上一行。"""
    toks = re.findall(r"[A-Za-z0-9/%·+]+|\s+|\S", text)
    lines, cur = [], ""
    for tk in toks:
        if tk.isspace():
            if cur and _text_w(draw, cur + tk, font) <= max_w:
                cur += tk
            continue
        trial = cur + tk
        if not cur or _text_w(draw, trial, font) <= max_w:
            cur = trial
        else:
            lines.append(cur.rstrip())
            cur = tk
    if cur.strip():
        lines.append(cur.rstrip())
    lines = _rebalance(draw, lines, font)
    # ★ 避头点：标点不能落在行首（与 wrap_rich 同规则），否则出现「、 FCR」这种断行
    BAD_HEAD = "，。、；：）】》」』”’％%！？·…"
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in BAD_HEAD:
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
    return [ln for ln in lines if ln]


def make_roadmap(spec):
    from PIL import Image, ImageDraw

    W = spec.get("width", 1100)
    stages = spec.get("stages") or spec.get("steps") or []
    if not stages:
        raise SystemExit("❌ roadmap spec 里既没有 stages 也没有 steps")
    n = len(stages)

    # 字号：按 677px 显示宽度反推（见上方 EFF_* 注释）
    ft_t = _font(int(W * EFF_TITLE / WX_DISPLAY_W), bold=True)
    ft_n = _font(int(W * EFF_BADGE / WX_DISPLAY_W), bold=True)
    ft_s = _font(int(W * EFF_STAGE / WX_DISPLAY_W), bold=True)
    ft_b = _font(int(W * EFF_BODY / WX_DISPLAY_W))

    MARGIN = int(W * 0.040)
    GAP = int(W * 0.024)
    box_w = (W - MARGIN * 2 - GAP * (n - 1)) // n
    pad_in = int(W * 0.022)
    if pad_in > box_w * 0.18:                      # 环节多、卡片窄时别让内边距吃掉版面
        pad_in = max(int(W * 0.016), int(box_w * 0.16))
    inner_w = box_w - pad_in * 2

    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)

    # ── 预估布局：先把每个环节的要点折行，"卡片高度由最长那一列决定" ──
    laid, max_rows = [], 1
    line_step = int(ft_b.size * 1.95)
    name_step = int(ft_s.size * 1.5)
    for st in stages:
        name, bullets = _bullets_of(st)
        nm_lines = wrap_keep(d, name, ft_s, inner_w - 2 * int(ft_n.size)) if name else []
        bl = []
        for b in bullets:
            first_w = _text_w(d, "· ", ft_b)
            lines = wrap_keep(d, b, ft_b, inner_w - first_w)
            bl.append(lines)
        total = max(len(nm_lines) * 2, 2) + sum(len(x) for x in bl)   # 环节名至少占 2 行高
        max_rows = max(max_rows, total)
        laid.append((name, nm_lines, bl))

    badge_d = 2 * int(W * 0.018)
    name_h = max(badge_d, max(len(nm) * name_step for _, nm, _ in laid) if laid else badge_d)
    head_h = int(name_h + W * 0.016)               # 编号圆 + 环节名（含下留白）
    top_y = int(W * 0.030) + int(ft_t.size * 1.9)
    box_h = head_h + max_rows * line_step + int(W * 0.026)
    H = top_y + box_h + int(W * 0.038)

    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    dr.text((MARGIN, int(W * 0.030)), spec.get("title", "研究思路与技术路线"),
            font=ft_t, fill=(31, 46, 58))

    accent = (45, 106, 143)
    for i, (name, nm_lines, bullets) in enumerate(laid):
        x = MARGIN + i * (box_w + GAP)
        dr.rounded_rectangle([x, top_y, x + box_w, top_y + box_h], radius=int(W * 0.014),
                             fill=(238, 244, 249), outline=(193, 214, 231), width=2)
        # 编号圆 + 环节名（名字太长时换行，与编号圆左对齐排列）
        r = int(W * 0.018)
        cx, cy = x + pad_in + r, top_y + int(W * 0.016) + r
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
        num = str(i + 1)
        dr.text((cx - dr.textlength(num, font=ft_n) / 2, cy - r * 0.80), num,
                font=ft_n, fill=(255, 255, 255))
        nx = cx + r + int(W * 0.012)
        ny = cy - int(ft_s.size * 0.60)
        for ln in nm_lines or []:
            draw_rich(dr, nx, ny, ln, ft_s, (23, 57, 77))
            ny += name_step
        # 要点分行（首行带圆点，续行缩进对齐圆点文字）
        ty = top_y + head_h
        indent = _text_w(dr, "· ", ft_b)
        for lines in bullets:
            for j, ln in enumerate(lines):
                if j == 0:
                    draw_rich(dr, x + pad_in, ty, "· ", ft_b, (47, 58, 66))
                draw_rich(dr, x + pad_in + indent, ty, ln, ft_b, (47, 58, 66))
                ty += line_step
        # 箭头
        if i < n - 1:
            ax = x + box_w + GAP // 2
            ay = top_y + box_h // 2
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
