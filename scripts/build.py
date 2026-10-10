# -*- coding: utf-8 -*-
"""每日 SCI 文献分享 · 三套版式生成器（B / D / E 轮换使用）

用法：
    python build.py <内容文件.py> [项目目录]

  例：
    python build.py content_某某论文.py .
        → 在项目目录下生成三套 HTML：
           版式B_期刊色带.html / 版式D_卡片分区.html / 版式E_墨绿纸感.html

内容文件需定义（见 assets/content_template.py）：
    TITLE          标题
    SUBLINE        版式 B 标题下副行（期刊 ｜ 日期 ｜ DOI）
    SUBLINE_E      版式 E 标题下副行（同上，用 ／ 与中文日期）
    COVER_IMG      封面信息卡图片路径（相对项目目录）
    ROADMAP_IMG    研究思路配图路径
    CONCLUSION_IMG 结论配图路径（原文无机制图则写 ""）
    LEAD           一段话总述
    BG             研究背景，4 段（基础背景→研究现状→存在的问题→本研究做了什么）
    THINK          研究思路，一段
    RESULTS        研究结果，[{no, title, body, figs:[(图片路径, 图注文字)]}]
    DISCUSS        讨论，通常 2 段
    CONCLUSION     结论，一段
    INFO           论文信息 [(标签, 值)]
    ACCOUNT        公众号名称

设计原则：**文字层与皮肤分离**。
  - 改文字 → 只动内容文件，重跑本脚本，三套同步更新
  - 改版式 → 改本文件里对应主题字典
  - 加第四套 → 在 THEMES 里加一个主题字典（需实现下面列出的 10 个渲染函数）
  - **不要手改生成出来的 HTML**（下次重跑会覆盖）

图注编号由本脚本自动生成：正文从「图1」起顺序编号（图1 = 技术路线图，
其后为各结果图，末图为结论机制图），内容文件里只写图注文字、不用写编号。

版式预览：assets/版式预览.html（在浏览器打开可对比三套效果）
"""
import importlib.util
import io
import os
import re
import sys

FONT = ("-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif")


def load_content(path):
    if not os.path.exists(path):
        raise SystemExit(f"❌ 找不到内容文件：{path}")
    spec = importlib.util.spec_from_file_location("content", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 缺省字段兜底
    mod.SUBLINE = getattr(mod, "SUBLINE", "")
    mod.SUBLINE_E = getattr(mod, "SUBLINE_E", mod.SUBLINE)
    mod.COVER_IMG = getattr(mod, "COVER_IMG", "图片/裁切/封面_论文信息卡.png")
    mod.ROADMAP_IMG = getattr(mod, "ROADMAP_IMG", "图片/裁切/技术路线图.png")
    mod.CONCLUSION_IMG = getattr(mod, "CONCLUSION_IMG", "")
    mod.ACCOUNT = getattr(mod, "ACCOUNT", "")
    # 二维码：支持 QR_IMG，也兼容旧字段名 QR
    mod.QR_IMG = getattr(mod, "QR_IMG", None) or getattr(mod, "QR", None) \
        or "图片/裁切/关注二维码_订阅号.jpg"
    return mod


def _num(n):
    """图注前缀：图N + 全角空格。"""
    return f"图{n}　"


def _strip_num(text):
    """剥掉图注里手写的「图N　」前缀（含「图N 」半角空格、纯「图N」）。

    为什么要剥：编号由本脚本统一递增生成，内容文件里不该再写。
    但历史内容文件（或用户手抄模板）常常带编号，直接拼会出现「图2 图2 …」。
    这里做成幂等处理，两种写法都能正确输出。
    """
    return re.sub(r"^图\s*\d+\s*[　\s]*", "", text)


def build_theme(theme, C):
    """把内容层套进一套皮肤，返回完整 HTML 字符串。"""
    def p(x):
        return theme["p"](x)

    counter = {"n": 0}

    def cap_text(text):
        counter["n"] += 1
        return _num(counter["n"]) + _strip_num(text)

    # 一、研究背景
    bg = "\n".join(p(x) for x in C.BG)

    # 二、研究思路（图1）
    fig1 = (f'<section style="margin:26px 0 0;"><img src="{C.ROADMAP_IMG}" '
            f'style="width:100%;height:auto;display:block;" /></section>'
            f'{theme["cap"](cap_text("研究思路与技术路线"), True)}')

    # 三、研究结果（图2 起）
    res = []
    for sec in C.RESULTS:
        res.append(theme["h3"](sec["no"], sec["title"]))
        res.append(p(sec["body"]))
        for i, (src, cap) in enumerate(sec["figs"]):
            last = (i == len(sec["figs"]) - 1)
            res.append(f'<section style="margin:24px 0 0;"><img src="{src}" '
                       f'style="width:100%;height:auto;display:block;{theme["img"]}" /></section>')
            res.append(theme["cap"](cap_text(cap), last))
    res = "\n".join(res)

    # 四、讨论
    disc = "\n".join(p(x) for x in C.DISCUSS)

    # 五、结论（末图 = 机制总结图）
    conc = p(C.CONCLUSION)
    if C.CONCLUSION_IMG:
        conc += (f'<section style="margin:24px 0 0;"><img src="{C.CONCLUSION_IMG}" '
                 f'style="width:100%;height:auto;display:block;{theme["img"]}" /></section>'
                 f'{theme["cap"](cap_text(getattr(C, "CONCLUSION_CAPTION", "机制总结图"), 
                                          ), True)}')

    # 摘要（供 publish.py 读取）
    plain = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", C.LEAD))[:120].replace('"', "&quot;")

    subline = C.SUBLINE_E if theme["name"] == E["name"] else C.SUBLINE

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{C.TITLE}</title>
<meta name="wx-title" content="{C.TITLE.replace('"', '&quot;')}">
<meta name="wx-digest" content="{plain}">
<style>
  body{{margin:0;padding:0;background:{theme["pagebg"]};}}
</style>
</head>
<body>

<!-- ===== 正文开始，从这一行往下全选复制到公众号编辑器 ===== -->
<section style="max-width:677px;margin:0 auto;background:{theme["bg"]};padding:{theme["pad"]};font-family:{FONT};font-size:16px;color:{theme["text"]};">

{theme["title"](C.TITLE, subline)}

{theme["lead"](C.LEAD)}

  <section style="margin:0 0 34px;">
    <img src="{C.COVER_IMG}" alt="论文信息" style="width:100%;height:auto;display:block;border:1px solid {theme["border"]};" />
  </section>

{theme["h2"]("一、研究背景")}
{bg}

{theme["h2"]("二、研究思路")}
{p(C.THINK)}
{fig1}

{theme["h2"]("三、研究结果")}
{res}

{theme["h2"]("四、讨论")}
{disc}

{theme["h2"]("五、结论")}
{conc}

{theme["info"](C.INFO)}

{theme["footer"](C.ACCOUNT, C.QR_IMG)}

</section>
<!-- ===== 正文结束 ===== -->

</body>
</html>
'''


# ======================================================================
# 皮肤 B · 期刊色带
# ======================================================================
B = {
    "name": "版式B_期刊色带",
    "pagebg": "#e9ecef", "bg": "#ffffff", "pad": "0 0 34px",
    "text": "#3f4b52", "border": "#e3e6e8", "img": "",
    "title": lambda t, sub: (
        f'  <section style="background:#1f4e6b;padding:26px 22px 22px;">'
        f'<section style="font-size:20px;line-height:1.55;font-weight:700;color:#ffffff;letter-spacing:.4px;">{t}</section>'
        f'<section style="font-size:13px;color:#a9c4d6;margin-top:10px;letter-spacing:.5px;">{sub}</section></section>'),
    "lead": lambda t: (
        f'  <section style="padding:26px 22px 0;"><section style="font-size:15px;line-height:1.95;color:#42525c;'
        f'padding:4px 0 20px;border-bottom:1px solid #dfe5e9;text-align:justify;letter-spacing:.2px;">{t}</section></section>'),
    "h2": lambda t: (
        f'  <section style="margin:34px 22px 20px;background:#1f4e6b;padding:11px 16px;">'
        f'<section style="font-size:16px;font-weight:700;color:#ffffff;letter-spacing:2px;">{t}</section></section>'),
    "h3": lambda no, t: (
        f'  <section style="display:block;background:#1f4e6b;margin:26px 22px 18px;padding:0;">'
        f'<section style="display:inline-block;background:#b8860b;color:#fff;font-size:15px;font-weight:700;padding:9px 16px;letter-spacing:1px;">{no}</section>'
        f'<section style="display:inline-block;color:#fff;font-size:15px;font-weight:700;padding:9px 0 9px 14px;letter-spacing:.5px;">{t}</section></section>'),
    "p": lambda t: (
        f'  <section style="padding:0 22px;"><section style="font-size:16px;line-height:1.9;color:#3f4b52;'
        f'margin:0 0 18px;text-align:justify;letter-spacing:.2px;">{t}</section></section>'),
    "cap": lambda t, last: (
        f'  <section style="padding:0 22px;"><section style="font-size:13px;line-height:1.7;color:#7d8b94;'
        f'margin:12px 0 {"30px" if last else "22px"};padding-left:12px;border-left:3px solid #b8860b;">{t}</section></section>'),
    "info": lambda items: (
        '  <section style="margin:34px 0 0;background:#1f4e6b;padding:18px 22px;">'
        '<section style="font-size:13px;line-height:2;color:#dbe7ee;">'
        + "".join(f'<section><span style="color:#8fb0c4;">{k}</span>{v}</section>' for k, v in items)
        + '</section></section>'),
    "footer": lambda acc, qr: (
        f'  <section style="margin:30px 22px 0;text-align:center;">'
        f'<section style="font-size:15px;line-height:1.8;color:#5c6b74;margin:0 0 14px;letter-spacing:1px;">— 欢迎关注 —</section>'
        f'<img src="{qr}" style="width:58%;max-width:260px;height:auto;display:inline-block;" />'
        f'<section style="font-size:15px;line-height:1.8;color:#1f4e6b;font-weight:700;margin:14px 0 0;letter-spacing:2px;">{acc}</section></section>'),
}

# ======================================================================
# 皮肤 D · 卡片分区
# ======================================================================
D = {
    "name": "版式D_卡片分区",
    "pagebg": "#e9ecef", "bg": "#f7f9fa", "pad": "0 0 34px",
    "text": "#3f4b52", "border": "#e3e6e8", "img": "border-radius:8px;",
    "title": lambda t, sub: (
        f'  <section style="padding:26px 22px 0;"><section style="font-size:21px;line-height:1.55;font-weight:700;'
        f'color:#17394d;letter-spacing:.3px;">{t}</section></section>'),
    "lead": lambda t: (
        f'  <section style="padding:18px 22px 0;"><section style="font-size:15px;line-height:1.9;background:#e8f1f7;'
        f'border-radius:12px;padding:18px;text-align:justify;color:#3d5461;letter-spacing:.2px;">{t}</section></section>'),
    "h2": lambda t: (
        f'  <section style="padding:0 22px;"><section style="margin:32px 0 18px;">'
        f'<section style="display:inline-block;background:#2d6a8f;color:#fff;font-size:16px;font-weight:700;'
        f'padding:8px 18px;border-radius:20px;letter-spacing:.8px;">{t}</section></section></section>'),
    "h3": lambda no, t: (
        f'  <section style="padding:0 22px;"><section style="display:block;margin:24px 0 14px;">'
        f'<section style="display:inline-block;background:#e8f1f7;color:#2d6a8f;font-size:15px;font-weight:700;'
        f'padding:6px 14px;border-radius:20px;letter-spacing:.5px;">{no}　{t}</section></section></section>'),
    "p": lambda t: (
        f'  <section style="padding:0 22px;"><section style="font-size:16px;line-height:1.88;color:#3f4b52;'
        f'margin:0 0 18px;text-align:justify;letter-spacing:.2px;">{t}</section></section>'),
    "cap": lambda t, last: (
        f'  <section style="padding:0 22px;"><section style="font-size:13px;line-height:1.7;color:#8b9aa4;'
        f'margin:10px 0 {"30px" if last else "22px"};text-align:center;">{t}</section></section>'),
    "info": lambda items: (
        '  <section style="padding:0 22px;"><section style="margin:34px 0 0;background:#2d6a8f;border-radius:12px;padding:18px;">'
        '<section style="font-size:13px;line-height:2;color:#dcebf4;">'
        + "".join(f'<section><span style="color:#9dc0d6;">{k}</span>{v}</section>' for k, v in items)
        + '</section></section></section>'),
    "footer": lambda acc, qr: (
        f'  <section style="margin:30px 22px 0;text-align:center;">'
        f'<section style="font-size:15px;line-height:1.8;color:#5c6b74;margin:0 0 14px;letter-spacing:1px;">— 欢迎关注 —</section>'
        f'<img src="{qr}" style="width:58%;max-width:260px;height:auto;display:inline-block;border-radius:10px;" />'
        f'<section style="font-size:15px;line-height:1.8;color:#2d6a8f;font-weight:700;margin:14px 0 0;letter-spacing:2px;">{acc}</section></section>'),
}

# ======================================================================
# 皮肤 E · 墨绿纸感
# ======================================================================
E = {
    "name": "版式E_墨绿纸感",
    "pagebg": "#e9ecef", "bg": "#fbfaf7", "pad": "28px 22px 34px",
    "text": "#4b5751", "border": "#e6e2d8", "img": "",
    "title": lambda t, sub: (
        f'  <section style="font-size:21px;line-height:1.6;font-weight:700;color:#22322c;letter-spacing:.3px;margin:0 0 12px;">{t}</section>\n'
        f'  <section style="font-size:12px;color:#9a988f;letter-spacing:1px;margin:0 0 24px;">{sub}</section>'),
    "lead": lambda t: (
        f'  <section style="font-size:15px;line-height:2;color:#4b5751;background:#f2efe7;padding:18px 20px;'
        f'margin:0 0 28px;text-align:justify;letter-spacing:.2px;">{t}</section>'),
    "h2": lambda t: (
        f'  <section style="margin:36px 0 18px;padding-bottom:10px;border-bottom:2px solid #2f5d50;">'
        f'<section style="font-size:17.5px;font-weight:700;color:#22322c;line-height:1.55;letter-spacing:.5px;">{t}</section></section>'),
    "h3": lambda no, t: (
        f'  <section style="margin:26px 0 14px;">'
        f'<section style="font-size:24px;font-weight:700;color:#c3c9c1;line-height:1;letter-spacing:1px;margin-bottom:6px;">{no.replace(".", " · ")}</section>'
        f'<section style="font-size:16.5px;font-weight:700;color:#22322c;line-height:1.55;">{t}</section></section>'),
    "p": lambda t: (
        f'  <section style="font-size:16px;line-height:1.95;color:#4b5751;margin:0 0 18px;text-align:justify;letter-spacing:.2px;">{t}</section>'),
    "cap": lambda t, last: (
        f'  <section style="font-size:13px;line-height:1.7;color:#9a988f;margin:12px 0 {"32px" if last else "24px"};text-align:center;">{t}</section>'),
    "info": lambda items: (
        '  <section style="background:#f2efe7;padding:16px 18px;border-left:3px solid #2f5d50;margin:34px 0 0;">'
        '<section style="font-size:13px;line-height:2.05;color:#5d6a63;">'
        + "".join(f'<section><span style="color:#a3a79c;">{k}</span>{v}</section>' for k, v in items)
        + '</section></section>'),
    "footer": lambda acc, qr: (
        f'  <section style="margin:30px 0 0;text-align:center;">'
        f'<section style="font-size:15px;line-height:1.8;color:#5c6b74;margin:0 0 14px;letter-spacing:1px;">— 欢迎关注 —</section>'
        f'<img src="{qr}" style="width:58%;max-width:260px;height:auto;display:inline-block;" />'
        f'<section style="font-size:15px;line-height:1.8;color:#22322c;font-weight:700;margin:14px 0 0;letter-spacing:2px;">{acc}</section></section>'),
}

THEMES = [B, D, E]


def collect_images(C):
    """汇总内容文件引用的所有图片路径（去重、保序）。"""
    out = [C.COVER_IMG, C.ROADMAP_IMG, C.CONCLUSION_IMG, C.QR_IMG]
    for sec in C.RESULTS:
        for src, _cap in sec["figs"]:
            out.append(src)
    seen, ordered = set(), []
    for p in out:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def check_images(C, outdir):
    """★ 生成前校验：所有引用的图片都能解析到真实文件。

    缺图是最高频的返工原因（改过命名、换过目录、复用了别的篇的路径）。
    提前报错比在公众号后台发现"图片裂了"便宜得多。
    """
    missing = []
    for rel in collect_images(C):
        if rel.startswith(("http://", "https://", "data:")):
            continue
        local = rel if os.path.isabs(rel) else os.path.join(outdir, rel)
        if not os.path.exists(os.path.normpath(local)):
            missing.append(rel)
    if missing:
        print("★ 以下图片引用不到真实文件：", file=sys.stderr)
        for p in missing:
            print(f"    {p}", file=sys.stderr)
        print(f"  （以内容文件所在目录为基准：{outdir}）", file=sys.stderr)
        print("  → 请修正内容文件里的路径，或用 make_figures.py 生成缺失的图。", file=sys.stderr)
    return missing


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    content_path = os.path.abspath(sys.argv[1])
    outdir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(content_path)
    os.makedirs(outdir, exist_ok=True)
    C = load_content(content_path)

    missing = check_images(C, outdir)

    for theme in THEMES:
        path = os.path.join(outdir, theme["name"] + ".html")
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(build_theme(theme, C))
        print("written:", path)

    n_img = len(collect_images(C))
    print(f"图片引用 {n_img} 张，缺失 {len(missing)} 张；正文已生成 3 套版式。")
    if missing:
        sys.exit(2)


if __name__ == "__main__":
    main()
