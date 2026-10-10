# -*- coding: utf-8 -*-
"""环境探测小工具：找 Python 解释器、找技能目录。

为什么需要它：技能会被拷到不同机器上，写死解释器绝对路径必然跑不通。
这里的做法是「先给提示、能自愈就自愈」，不阻断新手用户。

被 build.py / figtools.py / make_figures.py / publish.py 共用。
"""
import os
import sys


def skill_root():
    """技能根目录（本文件在 <技能>/scripts/ 下）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def python_exe():
    """返回当前解释器路径。

    脚本本身就是被 python 跑起来的，所以 sys.executable 永远正确 ——
    不需要探测。这个函数主要是给文档和报错提示用的。
    """
    return sys.executable


def require(*modules):
    """检查依赖是否装齐；缺了给出一条可复制的安装命令（用当前解释器）。"""
    missing = []
    for m in modules:
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if missing:
        pip = "pip"
        cmd = f'"{sys.executable}" -m pip install ' + " ".join(missing)
        print(f"★ 缺少依赖：{', '.join(missing)}", file=sys.stderr)
        print(f"  请运行：{cmd}", file=sys.stderr)
        print("  （注意：装到当前解释器所在的 venv，不要装全局）", file=sys.stderr)
    return missing


def check_pymupdf():
    """PyMuPDF 有两种导入名，新版推荐 pymupdf，旧版是 fitz。"""
    try:
        import pymupdf  # noqa: F401
        return "pymupdf"
    except ImportError:
        pass
    try:
        import fitz  # noqa: F401
        return "fitz"
    except ImportError:
        print("★ 缺少 PyMuPDF。请运行：", file=sys.stderr)
        print(f'  "{sys.executable}" -m pip install pymupdf', file=sys.stderr)
        return None


if __name__ == "__main__":
    print("技能根目录:", skill_root())
    print("Python    :", python_exe())
    print("PyMuPDF   :", check_pymupdf() or "未安装")
