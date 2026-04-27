"""
Generate docs/dashboard.html, docs/dashboard-qunxing.html, docs/dashboard-xlshangpin.html
from repos.md, docs/board.md, docs/milestones.md.
Single-file, stdlib only. Do not hand-edit the HTML output; regenerate after SSOT changes.
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone

HUB = Path(__file__).resolve().parent.parent
OUT = HUB / "docs" / "dashboard.html"
OUT_QUNXING = HUB / "docs" / "dashboard-qunxing.html"
OUT_XLSHANGPIN = HUB / "docs" / "dashboard-xlshangpin.html"
REPO_PATH = HUB / "repos.md"
BOARD_PATH = HUB / "docs" / "board.md"
MILESTONES_PATH = HUB / "docs" / "milestones.md"

RE_SECTION = re.compile(r"^##\s+(.+?)\s*$")
RE_TASK = re.compile(r"^-\s+\[([xX ])\]\s+(.+)$")
RE_TAG = re.compile(r"\[([a-z0-9-]+)\]")
RE_MENTION = re.compile(r"@\S+")
RE_EFFORT = re.compile(r"effort:(好做|一般|难)")
RE_QX = re.compile(r"QX-(\d+)", re.IGNORECASE)

# Project short names shown as pills; stack tags still omitted from titles/pills (parsed for stats).
TAGS_OMIT_FROM_MAIN_HTML = frozenset({"frontend", "backend"})


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


def strip_bracket_tags(text: str) -> str:
    """Remove `[tag]` markers from task text for dashboard display."""
    s = RE_TAG.sub("", text)
    return re.sub(r"  +", " ", s).strip()


def collect_tasks_by_tag(sections: dict[str, list[Task]], tag: str) -> list[Task]:
    out: list[Task] = []
    for tasks in sections.values():
        for t in tasks:
            if tag in t.tags:
                out.append(t)
    return out


def collect_qunxing_tasks(sections: dict[str, list[Task]]) -> list[Task]:
    return collect_tasks_by_tag(sections, "qunxing")


TEAM_HEATMAP_ROW_ORDER = ("群兴", "星链尚品", "其它", "(无标签)")


def task_team_label(t: Task) -> str:
    """产品线/团队行：群兴、星链尚品、其余带标签任务归为其它。"""
    ts = set(t.tags or [])
    if "qunxing" in ts:
        return "群兴"
    if "xlshangpin" in ts:
        return "星链尚品"
    if not ts:
        return "(无标签)"
    return "其它"


def section_sort_key(sec: str) -> int:
    order = "🔴🟡🟢✅⏳"
    for o, c in enumerate(order):
        if c in sec:
            return o
    return 99


def heatmap_team_matrix(
    sections: dict[str, list[Task]],
) -> dict[str, dict[str, int]]:
    m: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for sec_name, tasks in sections.items():
        for t in tasks:
            m[task_team_label(t)][sec_name] += 1
    return {k: dict(v) for k, v in m.items()}


def _mention_is_unassigned(mention: str | None) -> bool:
    if not mention:
        return True
    return mention.strip().lower() == "@tbd"


def heatmap_people_matrix(
    sections: dict[str, list[Task]],
) -> dict[str, dict[str, int]]:
    m: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for sec_name, tasks in sections.items():
        for t in tasks:
            if t.mention and not _mention_is_unassigned(t.mention):
                m[t.mention][sec_name] += 1
    return {k: dict(v) for k, v in m.items()}


def _ordered_heatmap_rows_team(matrix: dict[str, dict[str, int]]) -> list[str]:
    active = [r for r in matrix if sum(matrix[r].values()) > 0]
    out: list[str] = []
    for r in TEAM_HEATMAP_ROW_ORDER:
        if r in active:
            out.append(r)
    rest = sorted([r for r in active if r not in out])
    return out + rest


def _ordered_heatmap_rows_people(matrix: dict[str, dict[str, int]]) -> list[str]:
    active = [r for r in matrix if sum(matrix[r].values()) > 0]
    return sorted(active, key=lambda r: (-sum(matrix[r].values()), r))


def render_heatmap_table(
    matrix: dict[str, dict[str, int]],
    col_keys: list[str],
    row_labels: list[str],
    row_header: str,
) -> str:
    if not row_labels:
        return '<p class="heat-empty">（无数据）</p>'
    max_v = 1
    for r in row_labels:
        for c in col_keys:
            max_v = max(max_v, matrix[r].get(c, 0))
    th_cols = "".join(f"<th>{escape(c)}</th>" for c in col_keys)
    body_rows = []
    for r in row_labels:
        cells = []
        for c in col_keys:
            v = matrix[r].get(c, 0)
            intensity = (v / max_v) if max_v else 0.0
            tip = f"{r} · {c}：{v} 条"
            cells.append(
                f'<td class="hcell" style="--heat:{intensity:.6f}" title="{escape(tip)}">{v}</td>'
            )
        body_rows.append(
            f'<tr><th scope="row" class="row-head">{escape(r)}</th>{"".join(cells)}</tr>'
        )
    return (
        f'<table class="heatmap"><thead><tr><th class="corner">{escape(row_header)}</th>{th_cols}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table>'
    )


QUNXING_CSS = """
    :root {
      --bg: #fafafa;
      --surface: #fff;
      --text: #212529;
      --muted: #6c757d;
      --border: #e9ecef;
      --link: #1c7ed6;
      --radius: 6px;
    }
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      margin: 0;
      color: var(--text);
      background: var(--bg);
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }
    .wrap { max-width: 880px; margin: 0 auto; padding: 1.25rem 1.25rem 2rem; }
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 0.5rem 1rem;
      margin-bottom: 0.75rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border);
    }
    h1 { font-size: 1.25rem; font-weight: 600; margin: 0; letter-spacing: -0.02em; }
    .nav-top {
      margin-left: auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 0.65rem;
      justify-content: flex-end;
      max-width: 100%;
    }
    .nav-top a { color: var(--link); text-decoration: none; font-size: 0.875rem; }
    .nav-top a:hover { text-decoration: underline; }
    .nav-top code { font-size: 0.8em; background: #f1f3f5; padding: 0.08em 0.3em; border-radius: 3px; }
    .nav-sep { color: var(--muted); font-size: 0.75rem; user-select: none; }
    .ts { width: 100%; color: var(--muted); font-size: 0.8125rem; margin: 0; order: 3; }
    .sub { color: var(--muted); font-size: 0.875rem; margin: 0 0 0.5rem; line-height: 1.55; }
    .sub + .sub { margin-bottom: 1rem; }
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    @media (max-width: 560px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
    .kpi {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.5rem 0.65rem;
      border-left: 3px solid var(--c, #868e96);
    }
    .eff-tier-easy { --c: #2f9e44; }
    .eff-tier-mid { --c: #f08c00; }
    .eff-tier-hard { --c: #e03131; }
    .eff-tier-unk { --c: #868e96; }
    .kpi-label { font-size: 0.6875rem; color: var(--muted); text-transform: none; letter-spacing: 0.02em; }
    .kpi-value { font-size: 1.25rem; font-weight: 600; line-height: 1.2; margin-top: 0.15rem; }
    .eff-block {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.75rem 0;
      margin-bottom: 0.75rem;
      overflow: hidden;
    }
    .eff-block h2 {
      margin: 0;
      padding: 0 0.9rem 0.6rem;
      font-size: 0.9375rem;
      font-weight: 600;
      border-bottom: 1px solid var(--border);
    }
    .count { color: var(--muted); font-weight: 400; font-size: 0.8125rem; }
    .task-list { list-style: none; margin: 0; padding: 0; }
    .task {
      padding: 0.65rem 0.9rem;
      font-size: 0.875rem;
      border-bottom: 1px solid var(--border);
    }
    .task:last-child { border-bottom: none; }
    .task:nth-child(even) { background: #f8f9fa; }
    .task-head {
      margin-bottom: 0.35rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      flex-wrap: wrap;
    }
    .eff-badge {
      font-size: 0.6875rem;
      font-weight: 600;
      padding: 0.1em 0.4em;
      border-radius: 3px;
      background: color-mix(in srgb, var(--c) 14%, transparent);
      color: var(--c);
    }
    .board-sec {
      font-size: 0.6875rem;
      color: var(--muted);
      background: transparent;
      padding: 0;
      border-radius: 0;
    }
    .task-title { line-height: 1.55; color: var(--text); }
    .task-meta { margin-top: 0.35rem; color: var(--muted); font-size: 0.75rem; }
    .task-meta .meta { opacity: 0.9; }
    .task-done .task-title { text-decoration: line-through; color: var(--muted); }
    .empty { padding: 0.65rem 0.9rem; color: var(--muted); font-size: 0.875rem; }
    .footer { margin-top: 1.25rem; font-size: 0.75rem; color: var(--muted); }
    .footer code { background: #f1f3f5; padding: 0.08em 0.35em; border-radius: 3px; font-size: 0.9em; }
    .sub code, .footer code { font-family: ui-monospace, "Cascadia Code", monospace; }
"""


def build_effort_hub_html(
    tasks: list[Task],
    ts: str,
    *,
    page_title: str,
    h1: str,
    blurb: str,
    nav_inner_html: str,
    sort_within_effort: Callable[[Task], object],
) -> str:
    """Tasks grouped by effort: 好做 → 一般 → 难 → 未标; sort_within_effort per bucket."""
    order_eff = ["好做", "一般", "难", "未标"]
    buckets: dict[str, list[Task]] = {e: [] for e in order_eff}
    for t in tasks:
        buckets[task_effort_label(t.text)].append(t)
    for e in order_eff:
        buckets[e].sort(key=sort_within_effort)

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
            title_disp = escape(strip_bracket_tags(t.text))
            men = f'<span class="meta">{escape(t.mention)}</span>' if t.mention else ""
            meta_row = f'<div class="task-meta">{men}</div>' if men else ""
            done_cls = "task-done" if t.done else ""
            sec = f'<span class="board-sec">{escape(t.section)}</span>'
            elab = task_effort_label(t.text)
            _, bcolor = tier_style.get(elab, tier_style["未标"])
            eff_badge = f'<span class="eff-badge" style="--c:{bcolor}">{escape(elab)}</span>'
            lis.append(
                f'<li class="task {done_cls}"><div class="task-head">{eff_badge} {sec}</div>'
                f'<div class="task-title">{title_disp}</div>'
                f"{meta_row}</li>"
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
  <title>{escape(page_title)}</title>
  <style>{QUNXING_CSS}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{escape(h1)}</h1>
      <div class="nav-top">{nav_inner_html}</div>
      <div class="ts">最后生成：{escape(ts)}</div>
    </header>
    <p class="sub">{blurb}</p>
    <p class="sub">合计 <strong>{total}</strong> 条（未完成 <strong>{open_n}</strong>）。</p>
    <div class="kpi-row">{"".join(kpi_cells)}</div>
    {"".join(blocks)}
    <p class="footer">由 <code>python scripts/gen_dashboard.py</code> 生成，请勿手改。</p>
  </div>
</body>
</html>"""


def build_qunxing_html(tasks: list[Task], ts: str) -> str:
    nav = (
        '<a href="dashboard.html">← 总仪表盘</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-xlshangpin.html"><code>xlshangpin</code> 星链尚品</a>'
    )
    blurb = (
        "来源：<code>docs/board.md</code> 中含 <code>[qunxing]</code> 的任务；"
        "按 <code>effort:好做|一般|难</code> 分组，组内按 QX 编号排序。"
    )
    return build_effort_hub_html(
        tasks,
        ts,
        page_title="群兴任务 · pm-hub",
        h1="群兴任务",
        blurb=blurb,
        nav_inner_html=nav,
        sort_within_effort=lambda t: (task_qx_order(t.text), t.text),
    )


def build_xlshangpin_html(tasks: list[Task], ts: str) -> str:
    nav = (
        '<a href="dashboard.html">← 总仪表盘</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-qunxing.html"><code>qunxing</code> 群兴</a>'
    )
    blurb = (
        "来源：<code>docs/board.md</code> 中含 <code>[xlshangpin]</code> 的任务；"
        "按 <code>effort:好做|一般|难</code> 分组，组内按标题排序。"
    )
    return build_effort_hub_html(
        tasks,
        ts,
        page_title="星链尚品任务 · pm-hub",
        h1="星链尚品任务",
        blurb=blurb,
        nav_inner_html=nav,
        sort_within_effort=lambda t: (t.text.lower(),),
    )


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
    ordered_sections = sorted(sections.keys(), key=section_sort_key)
    heat_col_keys = list(ordered_sections)
    team_m = heatmap_team_matrix(sections)
    people_m = heatmap_people_matrix(sections)
    heat_team_html = render_heatmap_table(
        team_m,
        heat_col_keys,
        _ordered_heatmap_rows_team(team_m),
        "团队 ↓ ／ 分栏 →",
    )
    heat_people_html = render_heatmap_table(
        people_m,
        heat_col_keys,
        _ordered_heatmap_rows_people(people_m),
        "负责人 ↓ ／ 分栏 →",
    )
    col_html = []
    for sec in ordered_sections:
        tasks = sections[sec]
        items = []
        for t in tasks:
            title_disp = escape(strip_bracket_tags(t.text))
            vis = [x for x in (t.tags or []) if x not in TAGS_OMIT_FROM_MAIN_HTML]
            tag_str = " ".join(f'<span class="tag">{escape(x)}</span>' for x in vis)
            men = f'<span class="meta">{escape(t.mention)}</span>' if t.mention else ""
            done_cls = "task-done" if t.done else ""
            items.append(
                f'<li class="task {done_cls}"><div class="task-title">{title_disp}</div>'
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
            f'<div class="agg-line"><span class="rname">{escape(r)}</span><span class="rnum">未完成 {o} · 完成 {d}</span></div>'
        )
    # People aggregate
    people_rows = []
    for p in sorted(by_mention.keys()):
        o, d = by_mention[p].get("open", 0), by_mention[p].get("done", 0)
        people_rows.append(
            f'<div class="agg-line"><span class="pname">{escape(p)}</span><span class="pnum">未完成 {o} · 完成 {d}</span></div>'
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
    .heat-blurb {{ font-size:0.88rem; color:#495057; margin:0 0 0.75rem; line-height:1.45; }}
    .heat-h3 {{ font-size:0.92rem; margin:1rem 0 0.35rem; color:#343a40; font-weight:600; }}
    .heat-scroll {{ overflow-x:auto; margin-bottom:0.25rem; -webkit-overflow-scrolling:touch; }}
    table.heatmap {{ width:100%; border-collapse:collapse; font-size:0.82rem; min-width:420px; }}
    table.heatmap th, table.heatmap td {{ border:1px solid #dee2e6; padding:0.42rem 0.5rem; text-align:center; }}
    table.heatmap thead th {{ background:#f1f3f5; font-weight:600; font-size:0.78rem; color:#495057; }}
    table.heatmap th.corner {{ text-align:left; min-width:7rem; }}
    table.heatmap tbody th.row-head {{ text-align:left; background:#f8f9fa; font-weight:600; white-space:nowrap; }}
    table.heatmap td.hcell {{
      --heat: 0;
      background-color: hsl(211, 72%, calc(96% - var(--heat) * 38%));
      color: #212529;
      font-variant-numeric: tabular-nums;
      font-weight:600;
    }}
    .heat-empty {{ font-size:0.88rem; color:#868e96; margin:0.25rem 0 0.75rem; }}
    nav.project-hub {{
      display:flex; flex-wrap:wrap; align-items:center; gap:0.45rem;
      margin:0 0 1rem; padding:0.65rem 0.85rem;
      background:#fff; border:1px solid #e2e3e5; border-radius:8px;
    }}
    .project-hub-label {{ font-size:0.72rem; font-weight:600; color:#495057; margin-right:0.15rem; }}
    a.project-chip {{
      display:inline-flex; align-items:center; gap:0.35rem;
      padding:0.38rem 0.65rem; border-radius:6px; text-decoration:none;
      font-size:0.82rem; border:1px solid #dee2e6; background:#f8f9fa; color:#212529;
    }}
    a.project-chip:hover {{ border-color:#4dabf7; background:#e7f5ff; }}
    a.project-chip code {{
      font-size:0.76rem; background:#e9ecef; padding:0.1em 0.35em; border-radius:4px; color:#495057;
    }}
    a.project-chip.project-qunxing {{ border-left:3px solid #e03131; }}
    a.project-chip.project-xl {{ border-left:3px solid #2f9e44; }}
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
    <nav class="project-hub" aria-label="按项目进入专页">
      <span class="project-hub-label">项目</span>
      <a class="project-chip project-qunxing" href="dashboard-qunxing.html"><code>qunxing</code> 群兴</a>
      <a class="project-chip project-xl" href="dashboard-xlshangpin.html"><code>xlshangpin</code> 星链尚品</a>
    </nav>
    <p class="footer">已登记仓库短名（标签白名单来源）：<code>{escape(repo_whitelist)}</code></p>
    <div class="kpi-row">{nav}</div>
    <h2>负载热力图</h2>
    <p class="heat-blurb">按看板分栏统计任务条数（未完成与已完成均计入）。<strong>团队</strong>行按产品线归类（含 <code>qunxing</code> 为群兴、<code>xlshangpin</code> 为星链尚品，其余有标签为其它）；<strong>负责人</strong>按 <code>@</code> 提及汇总，<strong>不含</strong> <code>@tbd</code>（待分配仍体现在团队表与下方看板）。颜色在同一表内越深表示该格任务越多。任务列表中 <code>qunxing</code> / <code>xlshangpin</code> 以标签展示，与顶部「项目」入口一致。</p>
    <h3 class="heat-h3">团队（产品线）</h3>
    <div class="heat-scroll">{heat_team_html}</div>
    <h3 class="heat-h3">负责人</h3>
    <div class="heat-scroll">{heat_people_html}</div>
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
    <p class="footer">项目专页（按 effort 分组）：<a href="dashboard-qunxing.html"><code>qunxing</code> 群兴</a> · <a href="dashboard-xlshangpin.html"><code>xlshangpin</code> 星链尚品</a></p>
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
    xls_tasks = collect_tasks_by_tag(sections, "xlshangpin")
    xls_html = build_xlshangpin_html(xls_tasks, ts)
    OUT_XLSHANGPIN.write_text(xls_html, encoding="utf-8")
    print(f"Wrote {OUT_XLSHANGPIN.relative_to(HUB)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
