# -*- coding: utf-8 -*-
"""PDF 文本提取（按版式自动重组），处理期刊 PDF 的三种常见坑。

**什么时候用**：`page.get_text()` 读出来"没法看"的时候。三类典型症状：

  1. 每个词单独成行（LaTeX 排版，每词是独立文本对象）
  2. 页边距的下载水印混进正文，出现 "Introduction Agricultural" 这种串词
     （水印是**旋转 90°** 的文字，被按 y 聚类误并进正文行）
  3. 双栏排版被读成一句 —— 同一 y 上的左右栏文字并进了一行

用法：
  python pdf_text.py <输入.pdf> <输出.txt>

输出带 `===== PAGE N =====` 分隔；双栏页先输出左栏（按 y），再输出右栏。

★ 核心顺序（反了就会出 3 号症状）：
    ① 用 span 的 line["dir"] 过滤掉旋转文字（水印）
    ② 按 y 聚类成"视觉行"
    ③ 行内找最宽空隙；若空隙横跨页面中线 → 把这条行切成左右两段
    ④ 先输出左栏全部行，再输出右栏全部行
"""
import io
import sys

import pymupdf

Y_TOL = 4.0        # 同一行内 y 的容差（pt）
GAP_MIN = 12.0     # 判定"栏间空隙"的最小水平间隙（pt）


def horizontal_spans(page):
    """只收水平方向的文字片段 → [(x0, y0, x1, text)]，旋转水印被丢弃。"""
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:                 # 0 = 文本块
            continue
        for line in blk.get("lines", []):
            dx, dy = line.get("dir", (1.0, 0.0))
            if abs(dx - 1.0) > 0.01 or abs(dy) > 0.01:
                continue                         # ★ 旋转文字（水印），丢弃
            for sp in line.get("spans", []):
                t = sp["text"].strip()
                if t:
                    x0, y0, x1, _y1 = sp["bbox"]
                    out.append((x0, y0, x1, t))
    return out


def visual_lines(spans):
    """按 y 聚类成视觉行 → [[(x0, x1, text), ...]]"""
    spans = sorted(spans, key=lambda w: (round(w[1], 1), w[0]))
    lines, cur, cy = [], [], None
    for x0, y0, x1, t in spans:
        if cy is None or abs(y0 - cy) <= Y_TOL:
            cur.append((x0, x1, t))
            cy = y0 if cy is None else cy
        else:
            lines.append(cur)
            cur = [(x0, x1, t)]
            cy = y0
    if cur:
        lines.append(cur)
    return lines


def split_line(items, split_x):
    """把一条视觉行切成 (左段, 右段)；跨栏行按中线断开。"""
    items = sorted(items, key=lambda p: p[0])
    best_gap, best_i = 0.0, -1
    for i in range(len(items) - 1):
        gap = items[i + 1][0] - items[i][1]
        if gap > best_gap:
            best_gap, best_i = gap, i
    if best_i >= 0 and best_gap >= GAP_MIN and items[best_i][1] <= split_x <= items[best_i + 1][0]:
        a = " ".join(p[2] for p in items[:best_i + 1])
        b = " ".join(p[2] for p in items[best_i + 1:])
        return a, b
    text = " ".join(p[2] for p in items)
    return ("", text) if items[0][0] >= split_x else (text, "")


def extract(pdf_path, out_path):
    doc = pymupdf.open(pdf_path)
    buf = []
    for pno, page in enumerate(doc):
        split_x = page.rect.width * 0.5
        left, right = [], []
        for ln in visual_lines(horizontal_spans(page)):
            a, b = split_line(ln, split_x)
            if a:
                left.append(a)
            if b:
                right.append(b)
        buf.append(f"\n\n===== PAGE {pno+1} =====\n")
        if len(left) > 8 and len(right) > 8:      # 判定为双栏
            buf.extend(s + "\n" for s in left)
            buf.append("\n")
            buf.extend(s + "\n" for s in right)
        else:                                      # 单栏
            buf.extend(s + "\n" for s in left + right)
    io.open(out_path, "w", encoding="utf-8").write("".join(buf))
    doc.close()
    print("written", out_path)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    extract(sys.argv[1], sys.argv[2])
