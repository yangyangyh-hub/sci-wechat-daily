# -*- coding: utf-8 -*-
"""信息密度自检 —— 替代「字数」指标（CANON 第 6 条的执行者）。

为什么换指标：字数管的是长度，「概括性」管的是信息层级。同一段 400 字，
写 3 个结论句是概括，写 12 个参数就是流水账。所以查三件事：

  ① 数字密度 = 结果性数字个数 ÷ 每百字（不用绝对个数，长短节才可比）
     LEAD ≤ 0.8 ｜ 背景 ≤ 1.0 ｜ 研究思路 ≤ 1.0 ｜ 结果 ≤ 1.2（工艺型小节 ≤ 3.0）
     讨论 ≤ 0.5 ｜ 结论 ≤ 0.2
  ② 并列词堆砌：同时/此外/另外/并且，每个小节 ≤ 1
     （并列词一多，段落就从「推进」退化成「清单」）
  ③ 研究思路必须四层齐全：首先 → 随后 → 其次 → 最后
     （比查「句数」有效：中文长句靠分号推进，数句号会把一段连写误判成一句）

数字只算「结果性数字」：紧贴字母的编号（16S、C57BL/6J、L9）与年份不计。

判据冲突时以 CANON 为准：某节密度超标但内容确属 L1（如工艺小节的核心参数），
该节就应放宽阈值档（工艺型小节已单列 3.0），**不要为了通过而删 L1**。

用法：python scripts/density_check.py <content_xxx.py>
"""
import importlib.util
import re
import sys

NUM = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?(?![A-Za-z])")
YEAR = re.compile(r"^(19|20)\d{2}$")   # 年份属结构性信息，不计入密度
PARALLEL = ["同时", "此外", "另外", "并且"]
CAUSAL = ["因此", "据此", "继而", "随后", "在此基础上", "这说明"]


def strip(t):
    return re.sub(r"<[^>]+>", "", t)


def check(name, text, cap, par_cap=1):
    t = strip(text)
    n = len(t)
    nums = len([x for x in NUM.findall(t) if not YEAR.match(x)])
    dens = round(nums * 100 / max(n, 1), 2)
    par = sum(t.count(w) for w in PARALLEL)
    flag = []
    if dens > cap:
        flag.append(f"密度{dens}>{cap}")
    if par > par_cap:
        flag.append(f"并列词{par}")
    print(f"{name:<12}{n:>5}字  数字{nums:>2}  密度{dens:>5}  并列{par}  "
          f"{'OK' if not flag else '★ ' + '，'.join(flag)}")
    return len(flag)


def main(path):
    spec = importlib.util.spec_from_file_location("c", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    total = sum(len(strip(x)) for x in [m.LEAD, m.THINK, m.CONCLUSION])
    total += sum(len(strip(x)) for x in m.BG) + sum(len(strip(x)) for x in m.DISCUSS)
    total += sum(len(strip(r["body"])) for r in m.RESULTS)

    print(f"\n=== {path} ===")
    print(f"正文字数 {total}（只作上限参照：5,000–8,000，不设下限）\n")
    bad = 0
    bad += check("LEAD", m.LEAD, 0.8)
    for i, x in enumerate(m.BG, 1):
        bad += check(f"BG-{i}", x, 1.0)
    bad += check("THINK", m.THINK, 1.0)
    think = strip(m.THINK)
    miss = [w for w in ["首先", "随后", "其次", "最后"] if w not in think]
    print(f"{'THINK-四层':<12}{'':>6}{'':>8}{'':>8}{'':>5}{'':>6}"
          f"{'OK' if not miss else '★ 缺 ' + '、'.join(miss)}")
    bad += len(miss)
    for r in m.RESULTS:
        cap = 3.0 if r["no"].endswith("1") else 1.2     # 工艺型小节：参数即内容
        bad += check(r["no"], r["body"], cap)
    for i, x in enumerate(m.DISCUSS, 1):
        bad += check(f"DISC-{i}", x, 0.5)
    bad += check("CONCLUSION", m.CONCLUSION, 0.2)

    allt = strip("".join([m.LEAD, m.THINK, m.CONCLUSION] + m.BG + m.DISCUSS
                         + [r["body"] for r in m.RESULTS]))
    cau = sum(allt.count(w) for w in CAUSAL)
    par = sum(allt.count(w) for w in PARALLEL)
    print(f"\n全篇衔接：递进/因果词 {cau} 次，并列词 {par} 次"
          f"  {'OK 以递进为主' if cau > par else '★ 并列多于递进'}")
    print(f"越界项合计：{bad}")


if __name__ == "__main__":
    main(sys.argv[1])
