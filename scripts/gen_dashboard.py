"""
Generate docs/dashboard.html and docs/dashboard-qunxing.html from repos.md,
docs/board.md, docs/milestones.md.
Single-file, stdlib only. Do not hand-edit the HTML output; regenerate after SSOT changes.
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timezone

HUB = Path(__file__).resolve().parent.parent
OUT = HUB / "docs" / "dashboard.html"
OUT_QUNXING = HUB / "docs" / "dashboard-qunxing.html"
REPO_PATH = HUB / "repos.md"
BOARD_PATH = HUB / "docs" / "board.md"
MILESTONES_PATH = HUB / "docs" / "milestones.md"

RE_SECTION = re.compile(r"^##\s+(.+?)\s*$")
RE_TASK = re.compile(r"^-\s+\[([xX ])\]\s+(.+)$")
RE_TAG = re.compile(r"\[([a-z0-9-]+)\]")
RE_MENTION = re.compile(r"@\S+")
RE_EFFORT = re.compile(r"effort:(好做|一般|难)")
RE_QX = re.compile(r"QX-(\d+)", re.IGNORECASE)


@dataclass
class Task:
    raw: str
    done: bool
    text: str
    section: str
    tags: list[str] = field(default_factory=list)
    mention: str | None = None


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def parse_repos_index(md: str) -> set[str]:
    """First `repos.md` main table: column `短名` values (one row per data line)."""
    valid: set[str] = set()
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        if "| 短名 |" in lines[i] and lines[i].strip().startswith("|"):
            i += 1
            if i < len(lines) and re.match(r"^\|[-\s|]+\|", lines[i]):
                i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                if re.match(r"^\|[-\s|]+\|", lines[i]):
                    i += 1
                    continue
                parts = [c.strip() for c in lines[i].split("|") if c.strip() != ""]
                if len(parts) >= 1 and parts[0] not in ("短名",):
                    m = re.match(r"^([a-z0-9-]+)$", parts[0])
                    if m:
                        valid.add(m.group(1))
                i += 1
            break
        i += 1
    return valid


def _first_mention(s: str) -> str | None:
    m = RE_MENTION.search(s)
    return m.group(0) if m else None


def parse_board(md: str, valid_tags: set[str] | None) -> tuple[dict[str, list[Task]], list[str]]:
    section_order: list[str] = []
    sections: dict[str, list[Task]] = defaultdict(list)
    current = "未分栏"
    for line in md.splitlines():
        msec = RE_SECTION.match(line)
        if msec:
            current = msec.group(1).strip()
            if current not in section_order:
                section_order.append(current)
            continue
        mt = RE_TASK.match(line)
        if not mt:
            continue
        done = mt.group(1).lower() == "x"
        text = mt.group(2).strip()
        raw = mt.group(0)
        tags: list[str] = []
        for t in RE_TAG.findall(text):
            if valid_tags is None or t in valid_tags:
                if t not in tags:
                    tags.append(t)
        task = Task(
            raw=raw,
            done=done,
            text=text,
            section=current,
            tags=tags,
            mention=_first_mention(text),
        )
        sections[current].append(task)
    return dict(sections), section_order


@dataclass
class Milestone:
    name: str
    target: str
    progress: int


def parse_milestones(md: str) -> list[Milestone]:
    out: list[Milestone] = []
    header_idx = -1
    lines = md.splitlines()
    for i, line in enumerate(lines):
        l = line.lower()
        if (
            "milestone" in l
            and "target" in l
            and "progress" in l
            and line.strip().startswith("|")
        ):
            header_idx = i
            break
    if header_idx < 0:
        return out
    i = header_idx + 1
    if i < len(lines) and re.match(r"^\|[-\s|]+\|", lines[i]):
        i += 1
    while i < len(lines) and lines[i].strip().startswith("|"):
        if re.match(r"^\|[-\s|]+\|", lines[i]):
            i += 1
            continue
        parts = [c.strip() for c in lines[i].split("|") if c.strip() != ""]
        if len(parts) >= 3:
            name, target, pr = parts[0], parts[1], parts[2]
            try:
                p = int(re.sub(r"[^\d]", "", pr) or 0)
            except ValueError:
                p = 0
            p = max(0, min(100, p))
            out.append(Milestone(name=name, target=target, progress=p))
        i += 1
    return out


def task_effort_label(text: str) -> str:
    m = RE_EFFORT.search(text)
    return m.group(1) if m else "未标"


def task_qx_order(text: str) -> int:
    m = RE_QX.search(text)
    return int(m.group(1)) if m else 10_000


def collect_qunxing_tasks(sections: dict[str, list[Task]]) -> list[Task]:
    out: list[Task] = []
    for tasks in sections.values():
        for t in tasks:
            if "qunxing" in t.tags:
                out.append(t)
    return out


def build_qunxing_html(tasks: list[Task], ts: str) -> str:
    """[`qunxing`] tasks only, grouped by effort: 好做 → 一般 → 难 → 未标; QX-* numeric within group."""
    order_eff = ["好做", "一般", "难", "未标"]
    buckets: dict[str, list[Task]] = {e: [] for e in order_eff}
    for t in tasks:
        buckets[task_effort_label(t.text)].append(t)
    for e in order_eff:
        buckets[e].sort(key=lambda x: (task_qx_order(x.text), x.text))

    tier_style = {
        "好做": ("eff-tier-easy", "#2f9e44"),
        "一般": ("eff-tier-mid", "#f08c00"),
        "难": ("eff-tier-hard", "#e03131"),
        "未标": ("eff-tier-unk", "#868e96"),
    }
    kpi_cells = []
    for e in order_eff:
        cls, color = tier_style[e]
        n = len(buckets[e])
        kpi_cells.append(
            f'<div class="kpi {cls}"><div class="kpi-label">{escape(e)}</div>'
            f'<div class="kpi-value" style="color:{color}">{n}</div></div>'
        )
    blocks = []
    for e in order_eff:
        cls, color = tier_style[e]
        items = buckets[e]
        lis = []
        for t in items:
            tag_str = " ".join(
                f'<span class="tag">{escape(x)}</span>' for x in (t.tags or []) if x != "qunxing"
            )
            men = f'<span class="meta">{escape(t.mention)}</span>' if t.mention else ""
            done_cls = "task-done" if t.done else ""
            sec = f'<span class="board-sec">{escape(t.section)}</span>'
            elab = task_effort_label(t.text)
            _, bcolor = tier_style.get(elab, tier_style["未标"])
            eff_badge = f'<span class="eff-badge" style="--c:{bcolor}">{escape(elab)}</span>'
            lis.append(
                f'<li class="task {done_cls}"><div class="task-head">{eff_badge} {sec}</div>'
                f'<div class="task-title">{escape(t.text)}</div>'
                f'<div class="task-meta">{tag_str} {men}</div></li>'
            )
        blocks.append(
            f'<section class="eff-block {cls}"><h2><span class="eff-h2" style="color:{color}">{escape(e)}</span>'
            f' <span class="count">({len(items)})</span></h2><ul class="task-list">'
            + ("".join(lis) or '<li class="empty">（无）</li>')
            + "</ul></section>"
        )
    total = len(tasks)
    open_n = sum(1 for t in tasks if not t.done)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>群兴任务 · pm-hub</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin:0; color:#1a1a1a; background:#f0f3f8; }}
    .wrap {{ max-width: 960px; margin: 0 auto; padding: 1.5rem; }}
    header {{ display:flex; justify-content: space-between; align-items: baseline; flex-wrap:wrap; gap:.75rem; margin-bottom:1rem; }}
    h1 {{ font-size:1.35rem; margin:0; }}
    .nav-top a {{ color:#364fc7; text-decoration:none; font-size:0.9rem; }}
    .nav-top a:hover {{ text-decoration:underline; }}
    .ts {{ color:#666; font-size:0.85rem; }}
    .sub {{ color:#495057; font-size:0.9rem; margin:0 0 1rem; }}
    .kpi-row {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:0.6rem; margin-bottom:1.25rem; }}
    @media (max-width: 600px) {{ .kpi-row {{ grid-template-columns: repeat(2, 1fr); }} }}
    .kpi {{ background:#fff; border:1px solid #dee2e6; border-radius:8px; padding:0.6rem 0.75rem; border-left:4px solid var(--c, #868e96); }}
    .eff-tier-easy {{ --c: #2f9e44; }}
    .eff-tier-mid {{ --c: #f08c00; }}
    .eff-tier-hard {{ --c: #e03131; }}
    .eff-tier-unk {{ --c: #868e96; }}
    .kpi-label {{ font-size:0.75rem; color:#495057; }}
    .kpi-value {{ font-size:1.35rem; font-weight:700; }}
    .eff-block {{ background:#fff; border:1px solid #dee2e6; border-radius:10px; padding:1rem 1.1rem; margin-bottom:1rem; }}
    .eff-block h2 {{ margin:0 0 0.65rem; font-size:1rem; }}
    .count {{ color:#868e96; font-weight:400; font-size:0.9rem; }}
    .task-list {{ list-style:none; margin:0; padding:0; }}
    .task {{ border-bottom:1px solid #eee; padding:0.55rem 0; font-size:0.88rem; }}
    .task:last-child {{ border-bottom:none; }}
    .task-head {{ margin-bottom:0.25rem; display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }}
    .eff-badge {{ font-size:0.72rem; font-weight:600; padding:0.15em 0.45em; border-radius:4px; background:color-mix(in srgb, var(--c) 18%, #fff); color: var(--c); }}
    .board-sec {{ font-size:0.72rem; color:#666; background:#f1f3f5; padding:0.12em 0.4em; border-radius:4px; }}
    .task-title {{ line-height:1.45; }}
    .task-meta {{ margin-top:0.3rem; color:#666; font-size:0.78rem; }}
    .tag {{ display:inline-block; background:#e7f5ff; color:#1864ab; padding:0.1em 0.35em; border-radius:4px; margin-right:0.25rem; font-size:0.72rem; }}
    .task-done .task-title {{ text-decoration: line-through; color:#868e96; }}
    .footer {{ margin-top:1.5rem; font-size:0.78rem; color:#666; }}
    .footer code {{ background:#e9ecef; padding:0.1em 0.35em; border-radius:3px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>群兴任务</h1>
      <div class="nav-top"><a href="dashboard.html">← 总仪表盘</a></div>
      <div class="ts">最后生成：{escape(ts)}</div>
    </header>
    <p class="sub">来源：<code>docs/board.md</code> 中带 <code>[qunxing]</code> 的任务；按 <code>effort:好做|一般|难</code> 分组，组内按 QX 编号排序。</p>
    <p class="sub">合计 <strong>{total}</strong> 条（未完成 <strong>{open_n}</strong>）。</p>
    <div class="kpi-row">{"".join(kpi_cells)}</div>
    {"".join(blocks)}
    <p class="footer">由 <code>python scripts/gen_dashboard.py</code> 生成，请勿手改。</p>
  </div>
</body>
</html>"""


def build_html(
    valid_repos: set[str],
    sections: dict[str, list[Task]],
    section_order: list[str],
    milestones: list[Milestone],
) -> str:
    now = datetime.now(timezone.utc)
    # Display in a neutral way (UTC). Local TZ: change if needed.
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    by_repo: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_mention: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    counts: dict[str, int] = defaultdict(int)
    for sec, tasks in sections.items():
        for t in tasks:
            counts[sec] += 1
            st = "done" if t.done else "open"
            if t.tags:
                for tag in t.tags:
                    by_repo[tag][st] += 1
            else:
                by_repo["(无标签)"][st] += 1
            m = t.mention
            if m:
                st = "done" if t.done else "open"
                by_mention[m][st] += 1
    kpi = list(section_order) if section_order else list(sections.keys())
    nav_cells = []
    for sec in kpi:
        nav_cells.append(
            f'<div class="kpi"><div class="kpi-label">{escape(sec)}</div><div class="kpi-value">{counts.get(sec, 0)}</div></div>'
        )
    nav = "".join(nav_cells)
    def sort_key(sec: str) -> int:
        order = "🔴🟡🟢✅⏳"
        for o, c in enumerate(order):
            if c in sec:
                return o
        return 99

    ordered_sections = sorted(sections.keys(), key=sort_key)
    col_html = []
    for sec in ordered_sections:
        tasks = sections[sec]
        items = []
        for t in tasks:
            tag_str = " ".join(f'<span class="tag">{escape(x)}</span>' for x in (t.tags or []))
            men = f'<span class="meta">{escape(t.mention)}</span>' if t.mention else ""
            done_cls = "task-done" if t.done else ""
            items.append(
                f'<li class="task {done_cls}"><div class="task-title">{escape(t.text)}</div>'
                f'<div class="task-meta">{tag_str} {men}</div></li>'
            )
        col_html.append(
            f'<div class="column"><h3>{escape(sec)}</h3><ul class="task-list">'
            + ("".join(items) or "<li class=\"empty\">(无)</li>")
            + "</ul></div>"
        )
    # Milestones bars
    ms_rows = []
    for m in milestones:
        w = m.progress
        ms_rows.append(
            f'<div class="milestone"><div class="mname">{escape(m.name)}</div>'
            f'<div class="mbar-outer"><div class="mbar-inner" style="width:{w}%"></div></div>'
            f'<div class="mstat">{w}% <span class="mdate">{escape(m.target)}</span></div></div>'
        )
    # Repo aggregate
    repo_rows = []
    for r in sorted(by_repo.keys()):
        o, d = by_repo[r].get("open", 0), by_repo[r].get("done", 0)
        repo_rows.append(
            f'<div class="agg-line"><span class="rname">{escape(r)}</span><span class="rnum">进行中 {o} · 完成 {d}</span></div>'
        )
    # People aggregate
    people_rows = []
    for p in sorted(by_mention.keys()):
        o, d = by_mention[p].get("open", 0), by_mention[p].get("done", 0)
        people_rows.append(
            f'<div class="agg-line"><span class="pname">{escape(p)}</span><span class="pnum">进行中 {o} · 完成 {d}</span></div>'
        )
    repo_whitelist = " ".join(sorted(valid_repos)) if valid_repos else "—"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>pm-hub 仪表盘</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin:0; color:#1a1a1a; background:#f6f7f9; }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem; }}
    header {{ display:flex; justify-content: space-between; align-items: baseline; margin-bottom: 1rem; flex-wrap:wrap; gap:.5rem; }}
    h1 {{ font-size:1.25rem; margin:0; }}
    .ts {{ color:#666; font-size:0.9rem; }}
    .kpi-row {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(120px,1fr)); gap:0.75rem; margin-bottom:1.5rem; }}
    .kpi {{ background:#fff; border:1px solid #e2e3e5; border-radius:8px; padding:0.75rem 1rem; }}
    .kpi-label {{ font-size:0.8rem; color:#555; }}
    .kpi-value {{ font-size:1.5rem; font-weight:600; }}
    h2 {{ font-size:1rem; margin:1.5rem 0 0.5rem; color:#333; }}
    .columns {{ display:grid; grid-template-columns: 1fr; gap:1rem; }}
    @media (min-width: 800px) {{ .columns {{ grid-template-columns: 1fr 1fr; }} }}
    .column {{ background:#fff; border:1px solid #e2e3e5; border-radius:8px; padding:1rem; }}
    .column h3 {{ margin:0 0 0.5rem; font-size:0.95rem; }}
    .task-list {{ list-style:none; margin:0; padding:0; }}
    .task {{ border-bottom:1px solid #eee; padding:0.5rem 0; font-size:0.9rem; }}
    .task:last-child {{ border-bottom:none; }}
    .task-title {{ line-height:1.4; }}
    .task-meta {{ margin-top:0.25rem; color:#666; font-size:0.8rem; }}
    .tag {{ display:inline-block; background:#eef2ff; color:#364fc7; padding:0.1em 0.4em; border-radius:4px; margin-right:0.3rem; font-size:0.75rem; }}
    .task-done .task-title {{ text-decoration: line-through; color:#888; }}
    .panel {{ background:#fff; border:1px solid #e2e3e5; border-radius:8px; padding:1rem; margin-top:0.5rem; }}
    .milestone {{ display:grid; grid-template-columns: 1fr 3fr 120px; gap:0.5rem; align-items:center; margin:0.4rem 0; font-size:0.9rem; }}
    @media (max-width: 700px) {{ .milestone {{ grid-template-columns: 1fr; }} }}
    .mbar-outer {{ background:#e9ecef; height:8px; border-radius:4px; overflow:hidden; }}
    .mbar-inner {{ background:#2f9e44; height:8px; border-radius:4px; }}
    .mdate {{ color:#666; font-size:0.85em; margin-left:0.35em; }}
    .mstat {{ text-align:right; color:#333; white-space:nowrap; }}
    .agg-line {{ display:flex; justify-content: space-between; padding:0.35rem 0; border-bottom:1px solid #f0f0f0; font-size:0.9rem; }}
    .rname, .pname {{ font-weight:500; }}
    .footer {{ margin-top:2rem; font-size:0.8rem; color:#666; }}
    .footer code {{ background:#eee; padding:0.1em 0.3em; border-radius:3px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>项目仪表盘</h1>
      <div class="ts">最后生成：{escape(ts)}</div>
    </header>
    <p class="footer">已登记仓库短名（标签白名单来源）：<code>{escape(repo_whitelist)}</code></p>
    <div class="kpi-row">{nav}</div>
    <h2>看板</h2>
    <div class="columns">
      {''.join(col_html)}
    </div>
    <h2>里程碑</h2>
    <div class="panel">{''.join(ms_rows) or "<p>（无表格数据，参见 docs/milestones.md）</p>"}</div>
    <h2>仓库维度</h2>
    <div class="panel">{''.join(repo_rows) or "<p>（无带标签任务）</p>"}</div>
    <h2>成员负载</h2>
    <div class="panel">{''.join(people_rows) or "<p>（无 @ 提及）</p>"}</div>
    <p class="footer"><a href="dashboard-qunxing.html">群兴任务专页</a>（按 effort 分组）</p>
    <p class="footer">由 <code>python scripts/gen_dashboard.py</code> 从 Markdown 源生成，请勿手改本文件。</p>
  </div>
</body>
</html>"""


def main() -> int:
    if not REPO_PATH.is_file() or not BOARD_PATH.is_file():
        print("Missing repos.md or docs/board.md", file=sys.stderr)
        return 1
    rtext = read_text(REPO_PATH)
    btext = read_text(BOARD_PATH)
    mtext = read_text(MILESTONES_PATH) if MILESTONES_PATH.is_file() else ""
    valid = parse_repos_index(rtext)
    sections, order = parse_board(btext, valid)
    if not MILESTONES_PATH.is_file():
        milestones: list[Milestone] = []
    else:
        milestones = parse_milestones(mtext)
    html = build_html(valid, sections, order, milestones)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(HUB)}")
    qx_tasks = collect_qunxing_tasks(sections)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    qx_html = build_qunxing_html(qx_tasks, ts)
    OUT_QUNXING.write_text(qx_html, encoding="utf-8")
    print(f"Wrote {OUT_QUNXING.relative_to(HUB)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
