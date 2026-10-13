#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把成品 HTML 一键推进微信公众号草稿箱。

自动完成：
  ① 读取凭据（AppID / AppSecret）→ 换取 access_token
  ② 扫描 HTML 中的本地图片 → 逐张上传到微信 → 把 src 换成微信 URL
  ③ 上传封面图 → 拿 thumb_media_id
  ④ 调 draft/add 建草稿 → 返回草稿链接

────────────────────────────────────────────────────────
凭据获取顺序（先命中先用）：
  1) 命令行 --env <文件路径>
  2) 环境变量 WX_APPID / WX_APPSECRET
  3) 环境变量 WX_ENV_FILE 指向的文件
  4) 依次搜索常见位置：./.env、~/.wechat.env、~/.workbuddy/wechat.env、~/wechat.env

凭据文件格式（键名大小写不敏感，中英文冒号均可）：
    AppID：wx1234567890abcdef
    AppSecret: 0123456789abcdef0123456789abcdef

────────────────────────────────────────────────────────
用法：
  python publish.py <成品.html>
  python publish.py <成品.html> --env ~/my.env
  python publish.py <成品.html> --title "自定义标题" --digest "自定义摘要"
  python publish.py <成品.html> --cover path/to/cover.png
  python publish.py --list                  # 列出草稿箱
  python publish.py --delete <media_id>     # 删除某条草稿
  python publish.py --update <media_id> --title "新标题"   # ★ 原地改标题/摘要，不重传图片
  python publish.py --check                 # 只做凭据与连通性自检

★ 前置条件：
  - 本机出口 IP 必须在公众号后台「设置与开发 → 开发 → 基本配置 → IP 白名单」中。
    家庭宽带出口 IP 通常是动态的，会漂移；报 40164 时按提示把新 IP 加入白名单。
  - 调 API 时须绕开本机 HTTP 代理（脚本已内置空 ProxyHandler）。
"""
import json
import os
import re
import sys
import uuid
import urllib.error
import urllib.request

API = "https://api.weixin.qq.com/cgi-bin"

# 必须绕开会话代理，否则可能出现 TLS 握手失败
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 凭据文件的候选位置（按顺序找，先命中先用）。
# 全部用 ~ 展开，不含任何机器专属路径。
CANDIDATE_ENV_FILES = [
    os.path.join(os.getcwd(), ".env"),
    os.path.expanduser("~/.wechat.env"),
    os.path.expanduser("~/.workbuddy/wechat.env"),
    os.path.expanduser("~/wechat.env"),
]


def log(msg):
    print(msg, flush=True)


# ───────────────────────── 凭据 ─────────────────────────
def parse_env_file(path):
    if not path or not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8", errors="ignore").read()
    appid = re.search(r"AppID\s*[：:=]\s*(\S+)", text, re.I)
    secret = re.search(r"AppSecret\s*[：:=]\s*(\S+)", text, re.I)
    if appid and secret:
        return appid.group(1).strip().strip('"\''), secret.group(1).strip().strip('"\'')
    return None


def load_credentials(env_arg=None):
    """按优先级顺序找凭据，返回 (appid, secret, 来源描述)。"""
    if env_arg:
        got = parse_env_file(env_arg)
        if got:
            return got[0], got[1], f"文件 {env_arg}"
        raise SystemExit(f"❌ 指定的凭据文件里没找到 AppID/AppSecret：{env_arg}")

    a, s = os.environ.get("WX_APPID"), os.environ.get("WX_APPSECRET")
    if a and s:
        return a.strip(), s.strip(), "环境变量 WX_APPID/WX_APPSECRET"

    pointed = os.environ.get("WX_ENV_FILE")
    if pointed:
        got = parse_env_file(pointed)
        if got:
            return got[0], got[1], f"环境变量 WX_ENV_FILE → {pointed}"

    for cand in CANDIDATE_ENV_FILES:
        got = parse_env_file(cand)
        if got:
            return got[0], got[1], f"文件 {cand}"

    raise SystemExit(
        "❌ 没找到公众号凭据。请用以下任一方式提供：\n"
        "   1) 命令行：--env <凭据文件路径>\n"
        "   2) 环境变量：WX_APPID / WX_APPSECRET\n"
        "   3) 在下列位置之一放一个 .env 文件：\n"
        + "\n".join(f"        {p}" for p in CANDIDATE_ENV_FILES)
        + "\n\n   凭据文件格式：\n"
        "        AppID：wx1234567890abcdef\n"
        "        AppSecret: 0123456789abcdef0123456789abcdef\n\n"
        "   获取方式：公众号后台 → 设置与开发 → 开发 → 基本配置\n"
        "   （个人未认证订阅号亦可生成 AppSecret；需同时配置 IP 白名单）"
    )


# ───────────────────────── HTTP ─────────────────────────
def http_json(url, data=None, method=None):
    if data is not None and not isinstance(data, bytes):
        data = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with OPENER.open(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            raise SystemExit(f"❌ 请求失败（HTTP {e.code}）：{url.split('?')[0]}")


def get_token(appid, secret):
    r = http_json(f"{API}/token?grant_type=client_credential&appid={appid}&secret={secret}")
    if "access_token" not in r:
        if r.get("errcode") == 40164:
            raise SystemExit(
                "❌ IP 不在白名单。\n"
                f"   微信返回：{r.get('errmsg')}\n"
                "   → 把上面提示的 IP 加进「公众号后台 → 设置与开发 → 开发 → 基本配置 → IP 白名单」后重试。\n"
                "   注意：家庭宽带出口 IP 通常是动态的，会不定时变化。"
            )
        if r.get("errcode") == 40125:
            raise SystemExit("❌ AppSecret 不正确（40125）。请核对凭据文件中的 AppSecret。")
        if r.get("errcode") == 40013:
            raise SystemExit("❌ AppID 不正确（40013）。请核对凭据文件中的 AppID。")
        raise SystemExit(f"❌ 换取 access_token 失败：{r}")
    return r["access_token"]


# ───────────────────── 素材上传 ─────────────────────
def _post_file(url, filepath, field="media"):
    boundary = "----wb" + uuid.uuid4().hex
    fname = os.path.basename(filepath)
    with open(filepath, "rb") as fh:
        body = fh.read()
    ext = os.path.splitext(fname)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png" if ext == ".png" else "image/gif"
    payload = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field}"; filename="{fname}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        body,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(url, data=payload)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with OPENER.open(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def upload_body_image(token, path):
    """上传正文插图，返回微信 URL（统一转 https）。"""
    r = _post_file(f"{API}/media/uploadimg?access_token={token}", path)
    if "url" not in r:
        raise RuntimeError(f"正文图上传失败：{r}")
    return r["url"].replace("http://", "https://", 1)


def upload_cover(token, path):
    """上传封面素材，返回 thumb_media_id。"""
    r = _post_file(f"{API}/material/add_material?access_token={token}&type=image", path)
    if "media_id" not in r:
        raise RuntimeError(f"封面上传失败：{r}")
    return r["media_id"]


# ───────────────────── HTML 处理 ─────────────────────
def inline_images(token, html_path):
    """把 HTML 里的本地图片全部上传到微信并替换 src。返回 (新HTML, {原路径: 微信URL})。"""
    html = open(html_path, encoding="utf-8").read()
    base = os.path.dirname(os.path.abspath(html_path))
    srcs = re.findall(r'<img[^>]+src="([^"]+)"', html)
    seen, ordered = set(), []
    for s in srcs:
        if s.startswith(("http://", "https://", "data:")):
            continue
        if s not in seen:
            seen.add(s)
            ordered.append(s)

    mapping = {}
    for i, rel in enumerate(ordered, 1):
        local = rel if os.path.isabs(rel) else os.path.join(base, rel)
        local = os.path.normpath(local)
        if not os.path.exists(local):
            raise SystemExit(f"❌ 图片不存在：{local}\n   （HTML 里的引用是「{rel}」，请检查相对路径）")
        url = upload_body_image(token, local)
        mapping[rel] = url
        log(f"   [{i}/{len(ordered)}] {os.path.basename(rel)}  → 上传成功")

    for rel, url in mapping.items():
        html = html.replace(f'src="{rel}"', f'src="{url}"')
    return html, mapping


def strip_outer(html):
    """只取注释标记之间的正文，去掉 <!DOCTYPE>/<head>/<body> 外壳。"""
    m = re.search(r"<!--\s*=+\s*正文开始.*?=+\s*-->(.*?)<!--\s*=+\s*正文结束", html, re.S)
    return m.group(1).strip() if m else html


def meta(html, name):
    m = re.search(rf'<meta\s+name="{re.escape(name)}"\s+content="(.*?)"\s*/?>', html, re.S)
    if not m:
        m = re.search(rf"<meta\s+name=\"{re.escape(name)}\"\s+content='(.*?)'\s*/?>", html, re.S)
    return m.group(1).strip() if m else ""


def extract_title(html_path, html):
    t = meta(html, "wx-title")
    if t:
        return t
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return os.path.splitext(os.path.basename(html_path))[0]


def make_digest(html, limit=120):
    """摘要：优先读 build 阶段写入的 wx-digest（= 总述纯文本）。"""
    d = meta(html, "wx-digest")
    if d:
        return d.replace("&quot;", '"')[:limit]
    for block in re.split(r"</section>", html):
        text = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", block))
        if len(text) >= 60:
            return text[:limit]
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", html))[:limit]


# ───────────────────── 草稿操作 ─────────────────────
def list_drafts(token, count=20):
    r = http_json(f"{API}/draft/batchget?access_token={token}",
                  {"offset": 0, "count": count, "no_content": 1})
    items = r.get("item", [])
    if not items:
        log("（草稿箱为空）")
        return []
    log(f"共 {r.get('total_count', len(items))} 条草稿：\n")
    for i, it in enumerate(items, 1):
        ni = it["content"]["news_item"][0]
        log(f" {i:2d}. {ni['title']}")
        log(f"     media_id: {it['media_id']}")
    return items


def delete_draft(token, media_id):
    r = http_json(f"{API}/draft/delete?access_token={token}", {"media_id": media_id})
    log("✅ 已删除草稿 " + media_id if r.get("errcode") == 0 else f"❌ 删除失败：{r}")


def add_draft(token, article):
    r = http_json(f"{API}/draft/add?access_token={token}", {"articles": [article]})
    if "media_id" not in r:
        hint = ""
        if r.get("errcode") == 40007:
            hint = "\n   提示：40007 通常是封面 media_id 无效或缺失（本脚本会自动上传封面）。"
        raise SystemExit(f"❌ 建草稿失败：{r}{hint}")
    return r["media_id"]


def draft_url(token, media_id):
    r = http_json(f"{API}/draft/batchget?access_token={token}",
                  {"offset": 0, "count": 20, "no_content": 1})
    for it in r.get("item", []):
        if it["media_id"] == media_id:
            return it["content"]["news_item"][0].get("url", "")
    return ""


def get_article(token, media_id):
    """取回草稿的完整 article（含正文），用于原地更新。"""
    r = http_json(f"{API}/draft/batchget?access_token={token}",
                  {"offset": 0, "count": 20, "no_content": 0})
    for it in r.get("item", []):
        if it["media_id"] == media_id:
            return it["content"]["news_item"][0]
    raise SystemExit(f"❌ 草稿箱里找不到 media_id：{media_id}\n   （可用 --list 查看现有草稿）")


def update_draft_meta(token, media_id, **fields):
    """原地更新草稿的元信息（标题/摘要/作者/原文链接），不动正文与图片。

    ★ 为什么要单独做这个：只改一个标题时，没必要把 17 张图重新上传一遍。
      正文里的图片已经是微信托管 URL，直接原样回传即可。
    """
    art = get_article(token, media_id)
    # draft/update 要求带回完整 article；只覆盖指定字段
    # 注意：不能用 fields.get(k, 默认值) —— key 存在但值为 None 时不会回落到默认值
    article = {
        "title": fields.get("title") or art.get("title", ""),
        "author": fields.get("author") or art.get("author", "") or "",
        "digest": fields.get("digest") or art.get("digest", ""),
        "content": art.get("content", ""),
        "content_source_url": fields.get("source_url") or art.get("content_source_url", "") or "",
        "thumb_media_id": art.get("thumb_media_id", ""),
        "need_open_comment": art.get("need_open_comment", 0),
        "only_fans_can_comment": art.get("only_fans_can_comment", 0),
    }
    r = http_json(f"{API}/draft/update?access_token={token}",
                  {"media_id": media_id, "index": 0, "articles": article})
    if r.get("errcode") != 0:
        raise SystemExit(f"❌ 更新草稿失败：{r}")
    log(f"✅ 已更新草稿 {media_id}")
    log(f"   标题：{article['title']}")
    if fields.get("digest"):
        log(f"   摘要：{article['digest'][:50]}…")
    return article


# ───────────────────── 主流程 ─────────────────────
# 取值型选项：后面必须跟一个值，不是"子命令"
VALUE_OPTS = ("--env", "--title", "--digest", "--cover", "--author", "--source-url", "--update")


def split_args(args):
    """把命令行拆成 (子命令, 位置参数, 选项表)。

    为什么不能直接用 args[0]：用户常写成
        publish.py --env <文件> --check
        publish.py --env <文件> --list
    此时 args[0] 是 --env，会被误判成 HTML 路径。必须先剔除选项对。
    """
    sub, positional, opts = None, [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a in VALUE_OPTS:
            if i + 1 >= len(args):
                raise SystemExit(f"❌ {a} 后面缺少值")
            opts[a] = args[i + 1]
            i += 2
            continue
        if a in ("--check", "--list") and sub is None:
            sub = a
            i += 1
            continue
        if a == "--delete" and sub is None:
            sub = a
            i += 1
            continue
        positional.append(a)
        i += 1
    # --update 是"带值的子命令"
    if "--update" in opts and sub is None:
        sub = "--update"
    return sub, positional, opts


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    sub, positional, opts = split_args(args)

    appid, secret, origin = load_credentials(opts.get("--env"))
    log(f"凭据来源：{origin}")
    token = get_token(appid, secret)
    log("✅ access_token 获取成功")

    if sub == "--check":
        r = http_json(f"{API}/draft/batchget?access_token={token}",
                      {"offset": 0, "count": 1, "no_content": 1})
        log("✅ 接口连通，草稿箱可访问" if "item" in r else f"❌ 接口异常：{r}")
        return

    if sub == "--list":
        list_drafts(token)
        return

    if sub == "--delete":
        if not positional:
            raise SystemExit("用法：publish.py --delete <media_id>")
        delete_draft(token, positional[0])
        return

    if sub == "--update":
        mid = opts["--update"]
        if not any(opts.get(k) for k in ("--title", "--digest", "--author", "--source-url")):
            raise SystemExit(
                "用法：publish.py --update <media_id> --title \"新标题\" [--digest \"新摘要\"]\n"
                "   只改元信息，不重传图片。要换正文请重新跑一次普通推送。"
            )
        update_draft_meta(token, mid,
                          title=opts.get("--title"), digest=opts.get("--digest"),
                          author=opts.get("--author"), source_url=opts.get("--source-url"))
        return

    if not positional:
        print(__doc__)
        raise SystemExit("❌ 缺少成品 HTML 路径。用法：publish.py <成品.html> [--env <凭据文件>]")

    html_path = os.path.abspath(positional[0])
    if not os.path.exists(html_path):
        raise SystemExit(f"❌ 找不到 HTML：{html_path}")

    html = open(html_path, encoding="utf-8").read()
    title = opts.get("--title") or extract_title(html_path, html)

    log("① 上传正文图片…")
    body_html, mapping = inline_images(token, html_path)
    body_inner = strip_outer(body_html)
    if not mapping:
        log("   （HTML 中没有本地图片，跳过）")

    log("② 上传封面…")
    cover_arg = opts.get("--cover")
    if cover_arg:
        cover_path = os.path.abspath(cover_arg)
    elif mapping:
        first = next(iter(mapping))
        cover_path = first if os.path.isabs(first) else os.path.normpath(os.path.join(os.path.dirname(html_path), first))
    else:
        raise SystemExit("❌ 没有可用封面。请用 --cover <图片路径> 指定。")
    cover_mid = upload_cover(token, cover_path)
    log(f"   封面 media_id: {cover_mid}")

    log("③ 建草稿…")
    article = {
        "title": title,
        "author": opts.get("--author", "") or "",
        "digest": opts.get("--digest") or make_digest(body_html),
        "content": body_inner,
        "content_source_url": opts.get("--source-url", "") or "",
        "thumb_media_id": cover_mid,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    mid = add_draft(token, article)
    log(f"   ✅ 草稿 media_id: {mid}")

    url = draft_url(token, mid)
    log("\n" + "=" * 62)
    log("草稿已建立。请到公众号后台「草稿箱」打开、预览、点群发：")
    log(url or "（未能取到草稿链接，请手动进后台草稿箱查看）")
    log("=" * 62)
    log("注意：该链接带临时签名，过期后直接在后台草稿箱打开即可。")


if __name__ == "__main__":
    main()
