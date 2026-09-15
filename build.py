#!/usr/bin/env python3
"""Build the vvwbot.com static site from markdown sources."""

import datetime
import html
import json
import re
import shutil
from pathlib import Path

import markdown

SITE = Path(__file__).resolve().parent
OUT = SITE / "dist"
REPORTS = Path.home() / "Automation/tradingroom-digest/exports/daily/digests"
TALKJUN_REPORTS = Path.home() / "Automation/talkjun-video-digest/exports"
WIKI = Path.home() / ".openclaw/wiki/main"

NAV = [("/", "首页"), ("/research/", "研究"), ("/privacy", "隐私")]

# ticker -> (公司名, 一句话摘要). 摘要手写以保证质量和统一语气；
# 每加一批新公司，在这里加一行，跑 build.py 即可上站——不用碰其它代码。
COMPANIES = {
    "fico": ("FICO (Fair Isaac)", "收租型标准，靠涨价而非放量驱动增长；多空在赌那条提价阶梯还剩几格，Mortgage Direct Licensing 是最被低估的变量。"),
    "mu": ("MU (Micron Technology)", "周期型×铲子型混合，卖的是「AI 数据中心带宽缺口的现货租金」；核心矛盾是归一化毛利率会落在 60% 还是 86%，以及供给响应的时点。"),
    "now": ("NOW (ServiceNow)", "订阅型 SaaS，正试图从 workflow 定义者升级成 agent 治理层；反弹主要是板块重定价而非自身基本面加速，DCF 内在价值与现价有约 48% 折价。"),
    "msft": ("MSFT (Microsoft)", "基础设施×订阅混合；与 OpenAI 解绑意外成为看多催化剂（去 OpenAI 化后 Azure 需求仍广谱增长），但自由现金流连续两年下滑是新警号。"),
    "mdb": ("MDB (MongoDB)", "订阅型 Atlas×铲子型 EA 自托管；Q2 财报后 Atlas 增速主动降温到 26%，市场已重新定价，AI 拉动尚未被管理层量化。"),
    "nke": ("NKE (Nike)", "品牌无形资产型护城河，处于「用进废退」式折旧中；标普 100 被剔除带来技术性抛压，长期还要面对人形机器人对轻资产供应链模式的结构性威胁。"),
    "arm": ("ARM (Arm Holdings)", "收租型，护城河是「全球软件都编译成 ARM 指令」的兼容性网络效应；105x PE 由软银的筹码结构和抵押品逻辑托着，基本面撑不起现价但也难以做空。"),
}


def shell(title, body, *, depth=0, noindex=True, desc=""):
    root = "/"
    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if href == root and False else ""}>{label}</a>'
        for href, label in NAV
    )
    robots = '\n<meta name="robots" content="noindex, nofollow">' if noindex else ""
    description = f'\n<meta name="description" content="{html.escape(desc)}">' if desc else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{robots}{description}
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body>
<div class="stars"></div>
<div class="shell">

<header class="topbar">
  <div class="wrap">
    <a class="brand" href="/"><span class="dot"></span>VVW Bot</a>
    <nav>{nav}</nav>
  </div>
</header>

{body}

<footer class="site">
  <div class="wrap">
    <span>VVW Bot · 私人研究站</span>
    <span class="sp"><a href="/privacy">隐私政策</a></span>
  </div>
</footer>

</div>
</body>
</html>
"""


def strip_frontmatter(text):
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return text


def resolve_wikilinks(text):
    def repl(m):
        target, _, label = m.groups()
        label = label or target.rsplit("/", 1)[-1]
        return f"`{label}`"

    return re.sub(r"\[\[([^\]|]+)(\|([^\]]+))?\]\]", repl, text)


def md_to_html(text):
    text = resolve_wikilinks(text)
    out = markdown.markdown(
        text,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )
    # wrap tables so they can scroll on narrow screens
    out = re.sub(r"<table>", '<div class="tablewrap"><table>', out)
    out = re.sub(r"</table>", "</table></div>", out)
    return out


def doc_page(title, lede, body_html, *, back=None, eyebrow=""):
    back_html = f'<a class="backlink" href="{back[0]}">← {html.escape(back[1])}</a>' if back else ""
    eye = f'<div class="eyebrow">{html.escape(eyebrow)}</div>' if eyebrow else ""
    lede_html = f'<p class="lede">{html.escape(lede)}</p>' if lede else ""
    return f"""<main class="doc">
  <div class="wrap">
    <div class="doc-head">
      {back_html}
      {eye}
      <h1>{html.escape(title)}</h1>
      {lede_html}
    </div>
    <article>
{body_html}
    </article>
  </div>
</main>"""


TRADINGROOM_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\.(morning|afternoon|night|day))?\.md$")
TRADINGROOM_BRIEF_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(morning|afternoon|night)\.brief\.md$")
SESSION_TITLE = {
    "morning": "上午盘（06:00–12:00）",
    "afternoon": "下午盘（12:00–18:00）",
    "night": "夜盘（18:00–次日06:00）",
    "day": "日盘（06:00–18:00，旧格式）",
}
SESSION_SHORT = {"morning": "上午", "afternoon": "下午", "night": "夜间", "day": "全天"}
SESSION_ORDER = {"morning": 0, "afternoon": 1, "night": 2, "day": 0, None: -1}
CN_NUMBERS = "一二三四五六七八"


def _chapter_summary(raw):
    """摘要：取正文里第一段 blockquote（新旧两种格式都是这样开头），
    找不到就退化成列出有哪些 ## 分类。"""
    m = re.search(r"^>\s*(.+)$", raw, re.M)
    if m:
        summary = re.sub(r"[*`]", "", m.group(1).strip())
        if len(summary) > 72:
            cut = summary[:72]
            stop = max(cut.rfind("。"), cut.rfind("；"), cut.rfind("，"))
            summary = (cut[:stop] if stop > 36 else cut) + "…"
        return summary.rstrip("。")
    heads = [re.sub(r"[*`#]", "", h).strip() for h in re.findall(r"^##\s+(.+)$", raw, re.M)]
    heads = [h for h in heads if h and not h.startswith("附")]
    summary = " · ".join(heads[:6])
    if len(heads) > 6:
        summary += " · …"
    return summary


def _find_gaps(dates):
    """dates: 排序后的 'YYYY-MM-DD' 列表。返回缺口的可读描述，比如 '8/28–8/30、9/02–9/08'。"""
    if len(dates) < 2:
        return ""
    parsed = [datetime.date.fromisoformat(d) for d in dates]
    have = set(parsed)
    gaps = []
    cur_start = None
    d = parsed[0]
    while d <= parsed[-1]:
        if d not in have:
            if cur_start is None:
                cur_start = d
        else:
            if cur_start is not None:
                gaps.append((cur_start, d - datetime.timedelta(days=1)))
                cur_start = None
        d += datetime.timedelta(days=1)
    if cur_start is not None:
        gaps.append((cur_start, parsed[-1]))

    def fmt(day):
        return f"{day.month}/{day.day:02d}"

    return "、".join(fmt(a) if a == b else f"{fmt(a)}–{fmt(b)}" for a, b in gaps)


def build_tradingroom():
    target = OUT / "research/tradingroom"
    target.mkdir(parents=True, exist_ok=True)

    full_files = {}   # (date, session|None) -> Path
    brief_files = {}  # (date, session) -> Path
    for f in sorted(REPORTS.glob("20*.md")):
        m = TRADINGROOM_BRIEF_RE.match(f.name)
        if m:
            brief_files[(m.group(1), m.group(2))] = f
            continue
        m = TRADINGROOM_FNAME_RE.match(f.name)
        if not m:
            continue
        full_files[(m.group(1), m.group(2))] = f

    # 每个 (日期, session) 独立成页；session=None 的历史整天格式沿用旧的无后缀 URL。
    pages = []  # (date, session, slug, summary, total_len)
    for (date, session), full_f in full_files.items():
        full_raw = full_f.read_text(encoding="utf-8")
        brief_f = brief_files.get((date, session))
        brief_raw = brief_f.read_text(encoding="utf-8") if brief_f else None

        heading = date
        if session is None:
            # 整天模式，标题就是文件自带的 H1（如 "2026-09-10（美西时间）"）
            lines = full_raw.splitlines()
            heading = lines[0].lstrip("# ").strip() if lines else date

        body_parts = []
        if brief_raw:
            brief_html = md_to_html(brief_raw)
            brief_html = re.sub(r"<h1>.*?</h1>\s*", "", brief_html, count=1, flags=re.S)
            body_parts.append(f'<h2 class="tr-session">精简版</h2>{brief_html}')

        full_html = md_to_html(full_raw)
        full_html = re.sub(r"<h1>.*?</h1>\s*", "", full_html, count=1, flags=re.S)
        if brief_raw:
            body_parts.append(f'<h2 class="tr-session">详细版</h2>{full_html}')
        else:
            body_parts.append(full_html)

        body = "\n".join(body_parts)
        summary = _chapter_summary(brief_raw) if brief_raw else _chapter_summary(full_raw)

        slug = date if session is None else f"{date}-{session}"
        page_title = heading if session is None else f"{date} {SESSION_TITLE.get(session, session)}"
        page = shell(
            f"{page_title} · 面包 Trading Room",
            doc_page(
                page_title,
                "",
                body,
                back=("/research/tradingroom/", "全部日报"),
                eyebrow="Discord 日报",
            ),
        )
        (target / f"{slug}.html").write_text(page, encoding="utf-8")
        pages.append((date, session, slug, summary, len(full_raw) + len(brief_raw or "")))

    # index：按日期分组，同一天下面列出各 session 的独立链接
    by_date = {}
    for date, session, slug, summary, total_len in pages:
        by_date.setdefault(date, []).append((session, slug, summary, total_len))

    rows = []
    for date in sorted(by_date, reverse=True):
        chapters = sorted(by_date[date], key=lambda x: SESSION_ORDER[x[0]])
        if len(chapters) == 1 and chapters[0][0] is None:
            # 历史整天格式：跟以前一样，一行直接链接到当天页面
            _, slug, summary, total_len = chapters[0]
            rows.append(
                f'<a class="row" href="/research/tradingroom/{slug}">'
                f'<span class="d">{date}</span>'
                f'<span class="t">{html.escape(summary)}</span>'
                f'<span class="n">{total_len // 1000}k</span></a>'
            )
        else:
            links = "".join(
                f'<a class="tr-chip" href="/research/tradingroom/{slug}">{SESSION_SHORT.get(s, s)}</a>'
                for s, slug, _, _ in chapters
            )
            top_summary = chapters[0][2]
            total_len = sum(c[3] for c in chapters)
            rows.append(
                f'<div class="row tr-daterow">'
                f'<span class="d">{date}</span>'
                f'<span class="tr-chips">{links}</span>'
                f'<span class="t">{html.escape(top_summary)}</span>'
                f'<span class="n">{total_len // 1000}k</span></div>'
            )

    dates_sorted = sorted(by_date)
    span = f"{dates_sorted[0]} → {dates_sorted[-1]}" if dates_sorted else "—"
    gaps = _find_gaps(dates_sorted)
    gap_note = f"{gaps} 有缺口。" if gaps else "无缺口。"
    body = f"""<div class="rows">{''.join(rows)}</div>
<p style="color:var(--faint);font-size:.85rem">共 {len(dates_sorted)} 天日报，覆盖 {span}。{gap_note}</p>"""

    page = shell(
        "面包 Trading Room 日报",
        doc_page(
            "面包 Trading Room",
            "Discord 群聊逐日观点整理。每条观点标注来源：本人发言 / 他人转述 / 他人评价。",
            body,
            back=("/research/", "研究"),
            eyebrow="Discord 日报",
        ),
    )
    (target / "index.html").write_text(page, encoding="utf-8")
    return pages


def build_talkjun():
    target = OUT / "research/talkjun"
    assets = target / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    entries = []

    for src in sorted(TALKJUN_REPORTS.glob("*.json")):
        exported = json.loads(src.read_text(encoding="utf-8"))
        report = exported["report"]
        video_id = report["video_id"]
        parts = [
            f"> {report['lead']}",
            "",
            f"[打开 YouTube 原视频]({report['source_url']})",
        ]
        for section_index, section in enumerate(report["sections"]):
            parts.extend(["", f"## {CN_NUMBERS[section_index]}、{section['title']}"])
            for item_index, item in enumerate(section["items"], 1):
                parts.extend([
                    "",
                    f"### {item_index}. {item['heading']} [{item['timestamp']}]",
                    "",
                    item["content"],
                ])
        parts.extend([
            "",
            "## 视频最后 15 秒信息页（逐字转录）",
            "",
            "```text",
            report["ending_slide_text"],
            "```",
        ])
        frame = Path(exported.get("ending_frame_path", ""))
        if frame.is_file():
            image_name = f"{video_id}{frame.suffix.lower()}"
            shutil.copy2(frame, assets / image_name)
            parts.extend(["", f"![视频最后15秒原始画面](/research/talkjun/assets/{image_name})"])
        billing = exported.get("gemini_billing_estimate", {})
        if billing:
            parts.extend([
                "",
                "---",
                "",
                f"Gemini 本次估算费用：${billing.get('this_call_estimated_cost_usd', 0):.4f}；"
                f"本工具累计：${billing.get('tool_cumulative_estimated_cost_usd', 0):.4f}；"
                f"按 $10 本地预算估算剩余：${billing.get('tool_estimated_remaining_usd', 0):.4f}。",
                "",
                "该余额为本工具本地估算，不是 AI Studio 实时账户余额，也不包含同账户其他调用。",
            ])
        body = md_to_html("\n".join(parts))
        published = report.get("published_at", "")[:10]
        page = shell(
            f"{report['title']} · Talk君视频总结",
            doc_page(
                report["title"],
                f"发布于 {published} · 时长 {report['duration']}",
                body,
                back=("/research/talkjun/", "全部 Talk君 视频"),
                eyebrow="YouTube 视频内容总结",
            ),
        )
        (target / f"{video_id}.html").write_text(page, encoding="utf-8")
        entries.append((published, video_id, report["title"], report["lead"], report["duration"]))

    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    rows = "".join(
        f'<a class="row" href="/research/talkjun/{video_id}">'
        f'<span class="d">{html.escape(published)}</span>'
        f'<span class="t"><strong>{html.escape(title)}</strong><br>{html.escape(lead)}</span>'
        f'<span class="n">{html.escape(duration)}</span></a>'
        for published, video_id, title, lead, duration in entries
    )
    page = shell(
        "Talk君视频内容总结",
        doc_page(
            "Talk君视频内容总结",
            "按视频讲解顺序整理，结合 YouTube 字幕、Gemini 原生视频理解与末页原图校对。",
            f'<div class="rows">{rows}</div>',
            back=("/research/", "研究"),
            eyebrow="YouTube Digest",
        ),
    )
    (target / "index.html").write_text(page, encoding="utf-8")
    return entries


def build_markdown_page(src, out_rel, title, lede, eyebrow, back):
    body = md_to_html(Path(src).read_text(encoding="utf-8"))
    body = re.sub(r"<h1>.*?</h1>\s*", "", body, count=1, flags=re.S)
    page = shell(title, doc_page(title, lede, body, back=back, eyebrow=eyebrow))
    dest = OUT / out_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding="utf-8")


def build_companies():
    target = OUT / "research/companies"
    target.mkdir(parents=True, exist_ok=True)
    entries = []

    for ticker, (name, abstract) in COMPANIES.items():
        src = WIKI / "entities" / f"{ticker}.md"
        if not src.exists():
            print(f"  WARN: {src} not found, skipping {ticker}")
            continue
        raw = strip_frontmatter(src.read_text(encoding="utf-8"))
        mtime = datetime.datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m-%d")

        body_html = md_to_html(raw)
        # the source's own "# TICKER (Name)" H1 is redundant with our doc-head H1
        body_html = re.sub(r"<h1>.*?</h1>\s*", "", body_html, count=1, flags=re.S)

        abstract_html = f"""<div class="abstract">
  <span class="ico"></span>
  <div class="body"><span class="lbl">Abstract</span><p>{html.escape(abstract)}</p></div>
</div>"""

        page = shell(
            f"{name} · 公司研究",
            doc_page(
                name,
                "",
                abstract_html + f'<p style="color:var(--faint);font-size:.82rem;margin:-1.6em 0 2em">wiki 最后更新 {mtime}</p>' + body_html,
                back=("/research/companies/", "全部公司"),
                eyebrow="公司研究",
            ),
        )
        (target / f"{ticker}.html").write_text(page, encoding="utf-8")
        entries.append((ticker.upper(), name, abstract, mtime))

    rows = "".join(
        f'<a class="tile" href="/research/companies/{t.lower()}">'
        f'<span class="k">{t}</span>'
        f'<h3>{html.escape(n)}</h3>'
        f'<p>{html.escape(a)}</p>'
        f'<span class="go">打开 → <span style="color:var(--faint)">更新于 {m}</span></span></a>'
        for t, n, a, m in entries
    )
    body = f'<div class="deck">{rows}</div>'

    page = shell(
        "公司研究",
        doc_page(
            "公司研究",
            "个股逐一拆解：一句话本质、商业模式物种、多空观点、护城河结构。持续增加中。",
            body,
            back=("/research/", "研究"),
            eyebrow="Company Research",
        ),
    )
    (target / "index.html").write_text(page, encoding="utf-8")
    return entries


def build_research_index(n_reports, n_companies, n_talkjun):
    tiles = f"""<div class="deck">
  <a class="tile" href="/research/companies/">
    <span class="k">公司研究</span>
    <h3>个股拆解</h3>
    <p>一句话本质、商业模式物种、多空观点、护城河结构。已收录 {n_companies} 家，持续增加中。</p>
    <span class="go">打开 →</span>
  </a>
  <a class="tile" href="/research/frank">
    <span class="k">数据审计</span>
    <h3>FrankTrading 复盘审计</h3>
    <p>51 篇周报逐条对账真实行情。周度命中 71%，alpha 只有一周长，防守强于进攻。</p>
    <span class="go">打开 →</span>
  </a>
  <a class="tile" href="/research/tradingroom/">
    <span class="k">Discord 日报</span>
    <h3>面包 Trading Room</h3>
    <p>群内四人观点逐日整理，标注本人发言还是转述。共 {n_reports} 份。</p>
    <span class="go">打开 →</span>
  </a>
  <a class="tile" href="/research/talkjun/">
    <span class="k">YouTube 总结</span>
    <h3>Talk君视频内容总结</h3>
    <p>按照视频讲解顺序整理，保留关键数字、论证路径、操作思路与末页原文。已收录 {n_talkjun} 期。</p>
    <span class="go">打开 →</span>
  </a>
</div>"""
    page = shell(
        "研究",
        f"""<main class="doc">
  <div class="wrap">
    <div class="doc-head">
      <a class="backlink" href="/">← 首页</a>
      <div class="eyebrow">Private</div>
      <h1>研究</h1>
      <p class="lede">仅本人可见。以下内容基于公开发表的文字与私人群聊整理，不对外发布。</p>
    </div>
    {tiles}
  </div>
</main>""",
    )
    (OUT / "research/index.html").write_text(page, encoding="utf-8")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copytree(SITE / "assets", OUT / "assets")
    for f in ("index.html", "privacy.html"):
        shutil.copy(SITE / "public" / f, OUT / f)

    entries = build_tradingroom()
    company_entries = build_companies()
    talkjun_entries = build_talkjun()

    build_markdown_page(
        SITE / "content/frank.md",
        "research/frank.html",
        "FrankTrading 复盘审计",
        "把 51 篇周报里的每一次预判，拿真实行情逐条对账。他确实有 edge，但 edge 的位置和他自己讲的不完全一样。",
        "独立核查 · 不采信自述",
        ("/research/", "研究"),
    )

    build_research_index(len(entries), len(company_entries), len(talkjun_entries))
    print(f"built {len(entries)} tradingroom pages + {len(company_entries)} company pages + {len(talkjun_entries)} TalkJun pages + frank + indexes → {OUT}")


if __name__ == "__main__":
    main()
