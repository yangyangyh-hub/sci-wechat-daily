# -*- coding: utf-8 -*-
"""定位论文里的图：哪一页是哪张图、图注从哪个 y 坐标开始、正文页是位图还是矢量。

为什么需要它：
  `figtools.detect` 只认「内嵌位图且宽度 ≥ 页面宽 50%」的图。
  Nature / Science / Cell 一类期刊的主图常是**矢量绘图 + 若干小块位图**，
  detect 会整页跳过，看起来像"这篇论文没有图"。先用本脚本摸清版式，再决定走哪条路线。

用法：
    python find_figs.py "<论文.pdf>"                # 列出图注所在页 + 每页图/绘图数
    python find_figs.py "<论文.pdf>" --counts-only   # 只看每页位图数与绘图数

输出示例：
    p  2 | Fig. 1 | LPDs induce browning in a microbiota-dependent manner.
    p 20 | Extended Data Fig. 1 | See next page for caption.

判据（配合看 image/drawing 两列）：
    位图数 ≥1 且绘图数少      → 位图主图，走 figtools detect
    位图数 0~2 但绘图数上千   → 矢量主图，走「渲染页面 + 按图注 y 裁剪」（见 图片处理.md §一之补 C）
    两者都接近 0              → Accepted Manuscript，正文图排在文末
"""
import argparse
import re
import sys

CAP_RE = re.compile(r"(Extended Data )?Fig(?:ure)?\.?\s*(\d+)\s*[|｜]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--counts-only", action="store_true")
    args = ap.parse_args()

    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            sys.exit("缺少 PyMuPDF，请先 pip install pymupdf")

    doc = pymupdf.open(args.pdf)
    if args.counts_only:
        for i, pg in enumerate(doc):
            print(i + 1, len(pg.get_images(full=True)), len(pg.get_drawings()))
        return

    print("=== 图注定位（页号 | 图号 | 图注开头）===")
    hits = {}
    for i, pg in enumerate(doc):
        text = pg.get_text()
        for m in CAP_RE.finditer(text):
            # 图注标题可能跨页重复出现，取每页最后一次出现的 y（页内正文引用的 y 通常更大）
            box = pg.search_for(m.group(0).replace("｜", "|")) or []
            y = box[-1].y0 if box else -1
            tag = ("Extended Data Fig. " if m.group(1) else "Fig. ") + m.group(2)
            head = text[m.start():m.start() + 90].replace("\n", " ")
            print(f"p{i+1:>3} | {tag:<20} | caption_y={y:>7.1f} | {head}")
            hits.setdefault((tag, m.group(2)), []).append((i + 1, y))

    print("\n=== 每页 位图数 / 绘图数 ===")
    for i, pg in enumerate(doc):
        print(f"p{i+1:>3}  images={len(pg.get_images(full=True)):<4} drawings={len(pg.get_drawings())}")


if __name__ == "__main__":
    main()
