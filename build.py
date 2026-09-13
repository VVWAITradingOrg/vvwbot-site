#!/usr/bin/env python3
"""Build the vvwbot.com static site from markdown sources."""

import datetime
import html
import re
import shutil
from pathlib import Path

import markdown

SITE = Path(__file__).resolve().parent
OUT = SITE / "dist"
REPORTS = Path.home() / "Automation/tradingroom-digest/exports/daily/digests"
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


TRADINGROOM_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\.(day|night))?\.md$")
SESSION_TITLE = {"day": "日盘（06:00–18:00）", "night": "夜盘（18:00–次日06:00）"}
SESSION_ORDER = {"day": 0, "night": 1, None: -1}


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

    by_date = {}
    for f in sorted(REPORTS.glob("20*.md")):
        m = TRADINGROOM_FNAME_RE.match(f.name)
        if not m:
            continue
        date, session = m.group(1), m.group(2)
        by_date.setdefault(date, []).append((session, f))

    entries = []
    for date in sorted(by_date, reverse=True):
        chapters = sorted(by_date[date], key=lambda x: SESSION_ORDER[x[0]])
        body_parts = []
        summaries = []
        total_len = 0
        heading = date

        for session, f in chapters:
            raw = f.read_text(encoding="utf-8")
            total_len += len(raw)
            lines = raw.splitlines()
            if session is None:
                # 整天模式，标题就是文件自带的 H1（如 "2026-09-10（美西时间）"）
                heading = lines[0].lstrip("# ").strip() if lines else date
            summaries.append((session, _chapter_summary(raw)))

            chapter_html = md_to_html(raw)
            chapter_html = re.sub(r"<h1>.*?</h1>\s*", "", chapter_html, count=1, flags=re.S)
            if session:
                chapter_html = f'<h2 class="tr-session">{SESSION_TITLE[session]}</h2>' + chapter_html
            body_parts.append(chapter_html)

        body = "\n".join(body_parts)
        # 摘要：只有一章就直接用；两章都在就各取一小段拼起来
        if len(summaries) == 1:
            summary = summaries[0][1]
        else:
            summary = " ｜ ".join(f"{SESSION_TITLE.get(s, '').split('（')[0]}: {txt}" for s, txt in summaries if txt)

        page = shell(
            f"{date} · 面包 Trading Room",
            doc_page(
                heading if len(chapters) == 1 and chapters[0][0] is None else date,
                "",
                body,
                back=("/research/tradingroom/", "全部日报"),
                eyebrow="Discord 日报",
            ),
        )
        (target / f"{date}.html").write_text(page, encoding="utf-8")
        entries.append((date, summary, total_len))

    entries.sort(key=lambda e: e[0], reverse=True)
    rows = "".join(
        f'<a class="row" href="/research/tradingroom/{d}">'
        f'<span class="d">{d}</span>'
        f'<span class="t">{html.escape(s)}</span>'
        f'<span class="n">{n // 1000}k</span></a>'
        for d, s, n in entries
    )
    dates_sorted = sorted(e[0] for e in entries)
    span = f"{dates_sorted[0]} → {dates_sorted[-1]}" if entries else "—"
    gaps = _find_gaps(dates_sorted)
    gap_note = f"{gaps} 有缺口。" if gaps else "无缺口。"
    body = f"""<div class="rows">{rows}</div>
<p style="color:var(--faint);font-size:.85rem">共 {len(entries)} 份日报，覆盖 {span}。{gap_note}</p>"""

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


def build_research_index(n_reports, n_companies):
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

    build_markdown_page(
        SITE / "content/frank.md",
        "research/frank.html",
        "FrankTrading 复盘审计",
        "把 51 篇周报里的每一次预判，拿真实行情逐条对账。他确实有 edge，但 edge 的位置和他自己讲的不完全一样。",
        "独立核查 · 不采信自述",
        ("/research/", "研究"),
    )

    build_research_index(len(entries), len(company_entries))
    print(f"built {len(entries)} tradingroom pages + {len(company_entries)} company pages + frank + indexes → {OUT}")


if __name__ == "__main__":
    main()
