# sci-wechat-daily

> 把一篇 SCI 论文 PDF 做成一期「每日文献分享」公众号图文，并推进微信公众号草稿箱。
> Turn a paper PDF into a Chinese WeChat article, then push it to the WeChat Official Account drafts box.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**A zero-config pipeline for turning a scientific paper PDF into a publishable Chinese WeChat article** —
figure extraction, caption renumbering, three rotating layout themes, and one-command upload to the
WeChat Official Account drafts box. No account credentials are bundled; bring your own.

---

## 它做什么

```
PDF  →  提图裁切 + 自制配图  →  写中文标准解读  →  生成 B/D/E 三套版式  →  一键进草稿箱（人工点群发）
```

一期文章的成品骨架（顺序固定）：

```
标题            期刊名 ｜ 署名部分 + 一句话核心发现（署名三选一，见下）
 ↓
一段话总述      全文压缩成一段，说清「做了什么 — 发现了什么」
 ↓
封面信息卡      自制图：期刊 + 卷期 + 完整标题 + 作者 + 单位 + DOI + 日期
 ↓
一、研究背景      4 段：基础背景 → 研究现状 → 存在的问题 → 本研究做了什么
 ↓
二、研究思路      一段话讲清实验安排 + 自制「技术路线图」（图1）
 ↓
三、研究结果      按原文 Results 小节逐条：小标题 + 一整段 + 关键结果图 + 图注
 ↓
四、讨论          原文 Discussion 的目的、意义、未来展望
 ↓
五、结论          一段话收束 + 原文机制总结图
 ↓
论文信息         期刊｜日期｜DOI｜第一作者｜通讯作者｜主要单位（全篇只出现一次）
 ↓
AI 声明          一句：搜集整理分析由人工完成，AI 辅助解读，经人工复核
 ↓
欢迎关注         二维码 + 公众号名称
```

**标题署名三选一**（详见 SKILL.md §2.5）：

| 情况 | 判据 | 写法 |
|---|---|---|
| A | 主通讯单位 = 第一作者单位 | 《期刊》｜单位 + 姓名 + 团队 + 核心发现 |
| B | 多位通讯中含院士等知名学者 | 同单位 →「某某院士团队」；不同单位 →「某某教授联合某某院士团队」 |
| C | 通讯不在第一作者单位，且查不到其官方个人介绍 | 《期刊》｜只描述文章内容（不写单位与作者） |

**三套版式轮换**：B 期刊色带（正式）/ D 卡片分区（手机友好）/ E 墨绿纸感（人文）。
文字层与皮肤分离 —— 改文字只动内容文件，重跑生成器，三套同步更新。

---

## 快速开始

```bash
git clone https://github.com/yangyangyh-hub/sci-wechat-daily.git
cd sci-wechat-daily

# 装依赖（装到当前解释器所在的 venv，不要装全局）
python -m pip install pymupdf pillow numpy

# 自检：打印技能根目录 + 解释器 + 依赖状态
python scripts/_env.py
```

### 完整流程

```bash
SK="$(pwd)"   # 本仓库根目录

# 1) PDF 提图 + 面板检测
python "$SK/scripts/figtools.py" detect "<论文.pdf>" "<项目>/.cache/figs"
#    → 打开 .cache/figs/annot_p*.png 人工核对面板编号

# 2) 按 panels.json 写 spec.json 后拼接
python "$SK/scripts/figtools.py" compose "<项目>/.cache/spec.json"

# 3) 自制封面卡 / 技术路线图
python "$SK/scripts/make_figures.py" cover   "<项目>/.cache/cover.json"
python "$SK/scripts/make_figures.py" roadmap "<项目>/.cache/roadmap.json"

# 4) 像素自检（★ 必做）
python "$SK/scripts/figtools.py" verify <项目>/图片/裁切/*.png

# 5) 复制模板、填内容
cp "$SK/assets/content_template.py" "<项目>/content_<篇名>.py"

# 6) 生成三套版式
python "$SK/scripts/build.py" "<项目>/content_<篇名>.py" "<项目>"

# 7) 进草稿箱
python "$SK/scripts/publish.py" "<项目>/版式B_期刊色带.html" --env "<凭据文件>"
```

> **作为 Agent Skill 使用**：把本仓库整个目录放到你的技能目录下即可
> （如 `~/.workbuddy/skills/sci-wechat-daily/`）。`SKILL.md` 是主流程，Agent 会自动读取。

---

## 目录结构

```
sci-wechat-daily/
├── SKILL.md                       主流程（八步，Agent 读这个）
├── README.md                      本文件
├── LICENSE
├── .env.example                   凭据文件格式示例
├── scripts/
│   ├── _env.py                    环境探测：找解释器、查依赖
│   ├── figtools.py                PDF 提图 / 面板检测 / 拼接 / 像素自检
│   ├── panel_guide.py             拼版大图切面板辅助（白缝检测 / 坐标网格 / 批量裁校对）
│   ├── make_figures.py            封面信息卡 / 技术路线图 / 二维码处理
│   ├── build.py                   内容文件 → 三套版式 HTML
│   └── publish.py                 上传图片 + 建草稿
├── assets/
│   └── content_template.py        内容文件空白模板（每篇复制一份）
└── references/
    ├── 写作规则.md                 写作规范、四步研究背景、数字核验
    ├── 图片处理.md                 提图/拼接/自制图 详细步骤
    └── 发布接口.md                 微信接口链路、错误码、白名单、安全须知
```

---

## 关于凭据（★ 本仓库不含任何账号信息）

使用者需自备公众号 AppID / AppSecret。`publish.py` 按优先级查找：

1. `--env <文件路径>`
2. 环境变量 `WX_APPID` / `WX_APPSECRET`
3. 环境变量 `WX_ENV_FILE` 指向的文件
4. `./.env` → `~/.wechat.env` → `~/.workbuddy/wechat.env` → `~/wechat.env`

凭据文件格式（键名大小写不敏感，中英文冒号都认，见 `.env.example`）：

```
AppID：wx1234567890abcdef
AppSecret: 0123456789abcdef0123456789abcdef
```

**获取位置**：公众号后台 → 设置与开发 → 开发 → 基本配置。
其中 AppSecret 需点「重置」生成，**只显示一次**，当场记下来。

> **★ 必须同时配置 IP 白名单**（同一页面）。
> 家庭宽带出口 IP 是**动态**的，会漂移；报 `40164 not in whitelist` 时，
> 按错误提示里的 IP 去加白名单再重试。**这不是权限问题，别误判。**

### 权限边界

| 接口 | 个人未认证订阅号 | 说明 |
|---|---|---|
| `draft/add`（进草稿箱） | ✅ **可用** | 实测验证；返回 `40007` 而非 `48001` 即为证据 |
| `media/uploadimg`（正文图） | ✅ 可用 | |
| `material/add_material`（封面） | ✅ 可用 | |
| `freepublish`（直接群发） | ❌ 不可用 | 仅企业认证主体 |

**所以本技能做到草稿箱为止，群发必须由账号主手动点**（法规也要求发布者确认）。

---

## 依赖

| 包 | 用途 | 缺了会怎样 |
|---|---|---|
| `pymupdf` | 从 PDF 提取原生位图 | 提图步骤不可用 |
| `pillow` | 裁切 / 拼接 / 自制图 | 全部图片步骤不可用 |
| `numpy` | 面板检测、像素自检 | 同上 |

**跨平台**：字体路径、解释器路径都不写死。
字体按 Windows → macOS → Linux 候选顺序自动挑；找不到中文字体时仍能出图（中文会变方框）。
用什么 python 跑脚本，依赖就装在那个 python 里。

---

## 设计要点

- **文字层与皮肤分离** —— 稿件 = `content_<篇名>.py`（文字），版式 = `build.py`（三套皮肤）。
  改文字只动内容文件；加第四套版式只需在 `build.py` 添一个主题字典。**绝不手改生成的 HTML。**
- **图注编号自动递增** —— 内容文件只写图注文字，不写「图N」。生成器从 1 起编到末图。
- **生成前缺图对账** —— 所有图片引用都会解析一遍，缺哪些直接列出来。
  提前报错比在公众号后台发现"图片裂了"便宜得多。
- **像素级自检** —— 每张生成图都要过亮像素比检查（> 50%），防全黑图。
  **看图 ≠ 验证图**。
- **上标安全** —— 中文字体普遍缺 `⁹`、`⁻` 字形。自制图里写 `{^9}`，脚本按 rich text 手绘。
  PDF 读数用 `get_text("dict")` 按 span 字号判上标（`get_text()` 会把 `10⁹` 读成 `109`）。

---

## License

[MIT](LICENSE) © 2026 yangyangyh-hub
