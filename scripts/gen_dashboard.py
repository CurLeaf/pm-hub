"""
Generate docs/dashboard.html, docs/dashboard-qunxing.html, docs/dashboard-xlshangpin.html,
docs/dashboard-juminshang.html, docs/dashboard-personal.html (optional) from repos.md,
docs/board.md, and docs/burndown-history.json (daily snapshot).
Single-file, stdlib only. Do not hand-edit the HTML output; regenerate after SSOT changes.
"""
from __future__ import annotations

import json
import re
import sys
from html import escape
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HUB = Path(__file__).resolve().parent.parent
OUT = HUB / "docs" / "dashboard.html"
OUT_QUNXING = HUB / "docs" / "dashboard-qunxing.html"
OUT_XLSHANGPIN = HUB / "docs" / "dashboard-xlshangpin.html"
OUT_JUMINSHANG = HUB / "docs" / "dashboard-juminshang.html"
OUT_PERSONAL = HUB / "docs" / "dashboard-personal.html"
# 与 board.md 任务行中的 @负责人 完全一致；设为空字符串则不生成本页、总览也不挂链接
PERSON_DASHBOARD_MENTION = "@CurLeaf"
REPO_PATH = HUB / "repos.md"
BOARD_PATH = HUB / "docs" / "board.md"
MILESTONES_PATH = HUB / "docs" / "milestones.md"
BURNDOWN_PATH = HUB / "docs" / "burndown-history.json"
BURNDOWN_MAX_POINTS = 180
SNAPSHOT_TZ = ZoneInfo("Asia/Shanghai")

RE_SECTION = re.compile(r"^##\s+(.+?)\s*$")
RE_TASK = re.compile(r"^-\s+\[([xX ])\]\s+(.+)$")
RE_TAG = re.compile(r"\[([a-z0-9-]+)\]")
RE_MENTION = re.compile(r"@\S+")
RE_EFFORT = re.compile(r"effort:(好做|一般|难)")
RE_QX = re.compile(r"QX-(\d+)", re.IGNORECASE)
# Trailing ref in board line: `… (docs/foo.md)` or `… (https://…)` — shown as a compact link in HTML.
RE_TASK_TRAIL_REF = re.compile(
    r"^(?P<head>.+?)\s+\((?P<ref>docs/[^)]+\.md|https?://[^)]+)\)\s*$"
)

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


@dataclass(frozen=True)
class BurndownPoint:
    """单日看板快照：总任务数与已完成数（剩余 = total - done）。"""

    date: str  # YYYY-MM-DD，按 Asia/Shanghai 日历日
    total: int
    done: int

    @property
    def open(self) -> int:
        return max(0, self.total - self.done)


def snapshot_calendar_date_iso() -> str:
    return datetime.now(SNAPSHOT_TZ).date().isoformat()


def board_done_total(sections: dict[str, list[Task]]) -> tuple[int, int]:
    """返回 (done_count, total_count)。"""
    total = done = 0
    for tasks in sections.values():
        for t in tasks:
            total += 1
            if t.done:
                done += 1
    return done, total


def load_burndown(path: Path) -> list[BurndownPoint]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    pts: list[BurndownPoint] = []
    for row in raw.get("points", []):
        if not isinstance(row, dict) or "date" not in row:
            continue
        try:
            pts.append(
                BurndownPoint(
                    date=str(row["date"]),
                    total=max(0, int(row.get("total", 0))),
                    done=max(0, int(row.get("done", 0))),
                )
            )
        except (TypeError, ValueError):
            continue
    pts.sort(key=lambda p: p.date)
    return pts


def save_burndown(path: Path, points: list[BurndownPoint]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "points": [{"date": p.date, "total": p.total, "done": p.done} for p in points],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def upsert_today_burndown(
    path: Path,
    done: int,
    total: int,
    *,
    today: str | None = None,
) -> list[BurndownPoint]:
    """写入或覆盖「当天」快照，裁剪过长历史，返回排序后的序列。"""
    day = today if today else snapshot_calendar_date_iso()
    points = load_burndown(path)
    replaced = False
    merged: list[BurndownPoint] = []
    for p in points:
        if p.date == day:
            merged.append(BurndownPoint(date=day, total=max(0, total), done=max(0, min(done, total))))
            replaced = True
        else:
            merged.append(p)
    if not replaced:
        merged.append(
            BurndownPoint(date=day, total=max(0, total), done=max(0, min(done, total)))
        )
    merged.sort(key=lambda p: p.date)
    if len(merged) > BURNDOWN_MAX_POINTS:
        merged = merged[-BURNDOWN_MAX_POINTS:]
    save_burndown(path, merged)
    return merged


def render_burndown_block(points: list[BurndownPoint], done: int, total: int) -> str:
    """燃尽图区块：剩余任务曲线 + 已完成曲线，附完成度文案。"""
    pct = round(100.0 * done / total, 1) if total else 0.0
    open_n = max(0, total - done)
    meta = (
        f'<p class="burndown-meta">已完成 <strong>{done}</strong> / <strong>{total}</strong> '
        f'（<strong>{pct}%</strong>）· 剩余 <strong>{open_n}</strong> · '
        f'日历日 <code>{escape(snapshot_calendar_date_iso())}</code>（Asia/Shanghai）'
        f'</p>'
    )
    if len(points) >= 2:
        note = (
            '<p class="heat-blurb">蓝线：剩余任务（向下为燃尽）；绿线：已完成（向上）。'
            "每日运行 <code>python scripts/gen_dashboard.py</code> 会写入当日快照。</p>"
        )
    else:
        note = ""
    legend = (
        '<div class="burndown-legend" aria-hidden="true">'
        '<span class="lg"><i class="dot dot-rem"></i>剩余</span>'
        '<span class="lg"><i class="dot dot-done"></i>已完成</span>'
        "</div>"
    )
    svg = render_burndown_svg(points)
    return f"""<h2>燃尽图</h2>
{meta}
{legend}
{note}
<div class="burndown-chart-wrap">{svg}</div>"""


def render_burndown_svg(points: list[BurndownPoint]) -> str:
    if not points:
        return '<p class="heat-empty">（无快照数据）</p>'
    n = len(points)
    W, H = 720, 268
    pl, pr, pt, pb = 50, 18, 32, 50
    cw, ch = W - pl - pr, H - pt - pb
    ymax = max(1, max(p.total for p in points))
    opens = [p.open for p in points]
    dones = [p.done for p in points]

    def x_at(i: int) -> float:
        if n <= 1:
            return pl + cw / 2
        return pl + (i / (n - 1)) * cw

    def y_at(val: float) -> float:
        v = max(0.0, min(float(val), float(ymax)))
        return pt + ch - (v / ymax) * ch

    parts: list[str] = [
        f'<svg class="burndown-svg" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="看板燃尽与完成趋势">'
    ]
    y_ticks = sorted({0, ymax, ymax // 2})
    for gv in y_ticks:
        gy = y_at(gv)
        parts.append(
            f'<line x1="{pl:.1f}" y1="{gy:.1f}" x2="{pl + cw:.1f}" y2="{gy:.1f}" '
            f'stroke="#e9ecef" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pl - 8:.1f}" y="{gy + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#868e96" font-family="system-ui,sans-serif">{gv}</text>'
        )

    pts_rem = " ".join(f"{x_at(i):.1f},{y_at(opens[i]):.1f}" for i in range(n))
    pts_done = " ".join(f"{x_at(i):.1f},{y_at(dones[i]):.1f}" for i in range(n))
    parts.append(
        f'<polyline fill="none" stroke="#1971c2" stroke-width="2.5" stroke-linejoin="round" '
        f'stroke-linecap="round" points="{pts_rem}"/>'
    )
    parts.append(
        f'<polyline fill="none" stroke="#2f9e44" stroke-width="2" stroke-linejoin="round" '
        f'stroke-linecap="round" opacity="0.92" points="{pts_done}"/>'
    )

    label_step = max(1, (n - 1) // 7) if n > 8 else 1
    idx_labels = sorted(set(range(0, n, label_step)) | ({n - 1} if n else set()))
    for i in idx_labels:
        p = points[i]
        lab = p.date[5:] if len(p.date) >= 10 else p.date
        lx = x_at(i)
        parts.append(
            f'<text x="{lx:.1f}" y="{H - 18:.1f}" text-anchor="middle" font-size="10" '
            f'fill="#495057" font-family="system-ui,sans-serif">{escape(lab)}</text>'
        )

    for i in range(n):
        tip = f"{points[i].date} 剩余 {opens[i]} · 完成 {dones[i]} · 共 {points[i].total}"
        cx, cy = x_at(i), y_at(opens[i])
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" fill="#1971c2">'
            f"<title>{escape(tip)}</title></circle>"
        )

    parts.append("</svg>")
    return "\n".join(parts)


def task_effort_label(text: str) -> str:
    m = RE_EFFORT.search(text)
    return m.group(1) if m else "未标"


EFFORT_WEIGHT = {"好做": 1, "一般": 2, "难": 3, "未标": 1}


def task_effort_weight(text: str) -> int:
    """热力图用难度加权：与看板 effort 一致。"""
    return EFFORT_WEIGHT.get(task_effort_label(text), 1)


def task_qx_order(text: str) -> int:
    m = RE_QX.search(text)
    return int(m.group(1)) if m else 10_000


def strip_bracket_tags(text: str) -> str:
    """Remove `[tag]` markers from task text for dashboard display."""
    s = RE_TAG.sub("", text)
    return re.sub(r"  +", " ", s).strip()


def task_title_html(text: str) -> str:
    """Plain text task line → safe HTML: strip `[tags]`, turn trailing `(docs/*.md|url)` into a link."""
    s = strip_bracket_tags(text)
    m = RE_TASK_TRAIL_REF.match(s)
    if not m:
        return escape(s)
    head = m.group("head").strip()
    ref = m.group("ref")
    if ref.startswith("docs/"):
        href = ref[5:]
        label = "说明"
    else:
        href = ref
        label = "链接"
    return (
        f"{escape(head)} "
        f'<a class="task-doc" href="{escape(href)}">{escape(label)}</a>'
    )


def collect_tasks_by_tag(sections: dict[str, list[Task]], tag: str) -> list[Task]:
    out: list[Task] = []
    for tasks in sections.values():
        for t in tasks:
            if tag in t.tags:
                out.append(t)
    return out


def collect_qunxing_tasks(sections: dict[str, list[Task]]) -> list[Task]:
    return collect_tasks_by_tag(sections, "qunxing")


def collect_tasks_by_mention(sections: dict[str, list[Task]], mention: str) -> list[Task]:
    """mention 须与解析到的首处 @xxx 完全一致（含 @）。"""
    if not mention:
        return []
    out: list[Task] = []
    for tasks in sections.values():
        for t in tasks:
            if t.mention == mention:
                out.append(t)
    return out


def default_effort_hub_task_meta_html(t: Task) -> str:
    return f'<span class="meta">{escape(t.mention)}</span>' if t.mention else ""


def visible_repo_tags_html(t: Task) -> str:
    vis = [x for x in (t.tags or []) if x not in TAGS_OMIT_FROM_MAIN_HTML]
    return " ".join(f'<span class="tag">{escape(x)}</span>' for x in vis)


TEAM_HEATMAP_ROW_ORDER = ("群兴", "兴链尚品", "聚闽商", "其它", "(无标签)")


def task_team_label(t: Task) -> str:
    """产品线/团队行：群兴、兴链尚品、聚闽商，其余带标签任务归为其它。"""
    ts = set(t.tags or [])
    if "qunxing" in ts:
        return "群兴"
    if "xlshangpin" in ts:
        return "兴链尚品"
    if "juminshang" in ts:
        return "聚闽商"
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
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """(各格任务条数, 各格 effort 加权和)。加权：好做1、一般2、难3、未标1。"""
    cnt: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    wgt: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for sec_name, tasks in sections.items():
        for t in tasks:
            row = task_team_label(t)
            cnt[row][sec_name] += 1
            wgt[row][sec_name] += task_effort_weight(t.text)
    return {k: dict(v) for k, v in cnt.items()}, {k: dict(v) for k, v in wgt.items()}


def _mention_is_unassigned(mention: str | None) -> bool:
    if not mention:
        return True
    return mention.strip().lower() == "@tbd"


def heatmap_people_matrix(
    sections: dict[str, list[Task]],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """负责人热力图：不含 @tbd；返回 (条数, effort 加权和)。"""
    cnt: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    wgt: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for sec_name, tasks in sections.items():
        for t in tasks:
            if t.mention and not _mention_is_unassigned(t.mention):
                cnt[t.mention][sec_name] += 1
                wgt[t.mention][sec_name] += task_effort_weight(t.text)
    return {k: dict(v) for k, v in cnt.items()}, {k: dict(v) for k, v in wgt.items()}


def _ordered_heatmap_rows_team(
    counts: dict[str, dict[str, int]],
    weights: dict[str, dict[str, int]],
) -> list[str]:
    active = [r for r in counts if sum(counts[r].values()) > 0]
    out: list[str] = []
    for r in TEAM_HEATMAP_ROW_ORDER:
        if r in active:
            out.append(r)
    rest = sorted(
        [r for r in active if r not in out],
        key=lambda r: (-sum(weights.get(r, {}).values()), r),
    )
    return out + rest


def _ordered_heatmap_rows_people(
    counts: dict[str, dict[str, int]],
    weights: dict[str, dict[str, int]],
) -> list[str]:
    active = [r for r in counts if sum(counts[r].values()) > 0]
    return sorted(
        active,
        key=lambda r: (
            -sum(weights.get(r, {}).values()),
            -sum(counts[r].values()),
            r,
        ),
    )


def render_heatmap_table(
    counts: dict[str, dict[str, int]],
    weights: dict[str, dict[str, int]],
    col_keys: list[str],
    row_labels: list[str],
    row_header: str,
) -> str:
    """格内主显任务条数，括号内为 effort 加权和；颜色按加权和。"""
    if not row_labels:
        return '<p class="heat-empty">（无数据）</p>'
    max_v = 1
    for r in row_labels:
        for c in col_keys:
            max_v = max(max_v, weights.get(r, {}).get(c, 0))
    th_cols = "".join(f"<th>{escape(c)}</th>" for c in col_keys)
    body_rows = []
    for r in row_labels:
        cells = []
        for c in col_keys:
            n = counts.get(r, {}).get(c, 0)
            wv = weights.get(r, {}).get(c, 0)
            intensity = (wv / max_v) if max_v else 0.0
            tip = f"{r} · {c}：{n} 条，难度加权 {wv}（好做1·一般2·难3·未标1）"
            inner = f'{n}<span class="heat-w"> ({wv})</span>'
            cells.append(
                f'<td class="hcell" style="--heat:{intensity:.6f}" title="{escape(tip)}">{inner}</td>'
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
    a.task-doc { color: var(--link); font-size: 0.8125rem; font-weight: 500; text-decoration: none; white-space: nowrap; }
    a.task-doc:hover { text-decoration: underline; }
    .task-meta .tag {
      display: inline-block;
      background: #eef2ff;
      color: #364fc7;
      padding: 0.1em 0.4em;
      border-radius: 4px;
      margin-right: 0.3rem;
      font-size: 0.72rem;
    }
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
    task_meta_inner_html: Callable[[Task], str] | None = None,
) -> str:
    """Tasks grouped by effort: 好做 → 一般 → 难 → 未标; sort_within_effort per bucket."""
    meta_fn = task_meta_inner_html or default_effort_hub_task_meta_html
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
            title_disp = task_title_html(t.text)
            meta_inner = meta_fn(t)
            meta_row = f'<div class="task-meta">{meta_inner}</div>' if meta_inner else ""
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
        '<a href="dashboard-xlshangpin.html"><code>xlshangpin</code> 兴链尚品</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-juminshang.html"><code>juminshang</code> 聚闽商</a>'
        + nav_personal_link_html()
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
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-juminshang.html"><code>juminshang</code> 聚闽商</a>'
        + nav_personal_link_html()
    )
    blurb = (
        "来源：<code>docs/board.md</code> 中含 <code>[xlshangpin]</code> 的任务；"
        "按 <code>effort:好做|一般|难</code> 分组，组内按标题排序。"
    )
    return build_effort_hub_html(
        tasks,
        ts,
        page_title="兴链尚品任务 · pm-hub",
        h1="兴链尚品任务",
        blurb=blurb,
        nav_inner_html=nav,
        sort_within_effort=lambda t: (t.text.lower(),),
    )


def build_juminshang_html(tasks: list[Task], ts: str) -> str:
    nav = (
        '<a href="dashboard.html">← 总仪表盘</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-qunxing.html"><code>qunxing</code> 群兴</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-xlshangpin.html"><code>xlshangpin</code> 兴链尚品</a>'
        + nav_personal_link_html()
    )
    blurb = (
        "来源：<code>docs/board.md</code> 中含 <code>[juminshang]</code> 的任务；"
        "按 <code>effort:好做|一般|难</code> 分组，组内按标题排序。"
    )
    return build_effort_hub_html(
        tasks,
        ts,
        page_title="聚闽商任务 · pm-hub",
        h1="聚闽商任务",
        blurb=blurb,
        nav_inner_html=nav,
        sort_within_effort=lambda t: (t.text.lower(),),
    )


def nav_personal_link_html() -> str:
    if not PERSON_DASHBOARD_MENTION.strip():
        return ""
    return '<span class="nav-sep">·</span><a href="dashboard-personal.html">我的工作</a>'


def build_personal_dashboard_html(tasks: list[Task], ts: str, mention: str) -> str:
    nav = (
        '<a href="dashboard.html">← 总仪表盘</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-qunxing.html"><code>qunxing</code> 群兴</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-xlshangpin.html"><code>xlshangpin</code> 兴链尚品</a>'
        '<span class="nav-sep">·</span>'
        '<a href="dashboard-juminshang.html"><code>juminshang</code> 聚闽商</a>'
    )
    blurb = (
        f"来源：<code>docs/board.md</code> 中负责人为 <code>{escape(mention)}</code> 的任务；"
        "条目展示看板分栏与仓库标签；按 <code>effort:好做|一般|难</code> 分组；"
        "组内群兴 QX 按编号，其余按标题排序。"
    )
    label = mention.removeprefix("@").strip() or mention
    return build_effort_hub_html(
        tasks,
        ts,
        page_title=f"{label} · 我的工作 · pm-hub",
        h1=f"我的工作看板（{mention}）",
        blurb=blurb,
        nav_inner_html=nav,
        sort_within_effort=lambda t: (
            (0, task_qx_order(t.text), t.text.lower())
            if RE_QX.search(t.text)
            else (1, 0, t.text.lower())
        ),
        task_meta_inner_html=visible_repo_tags_html,
    )


def build_html(
    sections: dict[str, list[Task]],
    section_order: list[str],
    burndown_points: list[BurndownPoint],
) -> str:
    now = datetime.now(timezone.utc)
    # Display in a neutral way (UTC). Local TZ: change if needed.
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    counts: dict[str, int] = defaultdict(int)
    for sec, tasks in sections.items():
        for t in tasks:
            counts[sec] += 1
    kpi = list(section_order) if section_order else list(sections.keys())
    nav_cells = []
    for sec in kpi:
        nav_cells.append(
            f'<div class="kpi"><div class="kpi-label">{escape(sec)}</div><div class="kpi-value">{counts.get(sec, 0)}</div></div>'
        )
    nav = "".join(nav_cells)
    ordered_sections = sorted(sections.keys(), key=section_sort_key)
    heat_col_keys = list(ordered_sections)
    team_cnt, team_wgt = heatmap_team_matrix(sections)
    people_cnt, people_wgt = heatmap_people_matrix(sections)
    heat_team_html = render_heatmap_table(
        team_cnt,
        team_wgt,
        heat_col_keys,
        _ordered_heatmap_rows_team(team_cnt, team_wgt),
        "团队 ↓ ／ 分栏 →",
    )
    heat_people_html = render_heatmap_table(
        people_cnt,
        people_wgt,
        heat_col_keys,
        _ordered_heatmap_rows_people(people_cnt, people_wgt),
        "负责人 ↓ ／ 分栏 →",
    )
    col_html = []
    for sec in ordered_sections:
        tasks = sections[sec]
        items = []
        for t in tasks:
            title_disp = task_title_html(t.text)
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
    bd_done, bd_total = board_done_total(sections)
    burndown_html = render_burndown_block(burndown_points, bd_done, bd_total)
    personal_hub_block = ""
    personal_footer_extra = ""
    if PERSON_DASHBOARD_MENTION.strip():
        personal_hub_block = (
            '<span class="project-hub-label">个人</span>'
            '<a class="project-chip project-personal" href="dashboard-personal.html">我的工作</a>'
        )
        personal_footer_extra = ' · <a href="dashboard-personal.html">我的工作看板</a>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>pm-hub 仪表盘</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin:0; color:#1a1a1a; background:#f6f7f9; }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 1.5rem; }}
    header {{ display:flex; justify-content: space-between; align-items: baseline; margin-bottom: 1rem; flex-wrap:wrap; gap:.5rem; }}
    h1 {{ font-size:1.25rem; margin:0; }}
    .ts {{ color:#666; font-size:0.9rem; }}
    .kpi-row {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(120px,1fr)); gap:0.75rem; margin-bottom:1.5rem; }}
    .kpi {{ background:#fff; border:1px solid #e2e3e5; border-radius:8px; padding:0.75rem 1rem; }}
    .kpi-label {{ font-size:0.8rem; color:#555; }}
    .kpi-value {{ font-size:1.5rem; font-weight:600; }}
    h2 {{ font-size:1rem; margin:1.5rem 0 0.5rem; color:#333; }}
    .columns {{
      display:grid;
      grid-template-columns: 1fr;
      gap:1rem;
      align-items: stretch;
    }}
    @media screen and (min-width: 900px) {{ .columns {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
    .column {{
      background:#fff;
      border:1px solid #e2e3e5;
      border-radius:8px;
      padding:1rem;
      display:flex;
      flex-direction:column;
      min-height:0;
    }}
    @media screen {{
      .column {{
        height: min(32rem, 58vh);
      }}
      .column .task-list {{
        flex:1;
        min-height:0;
        overflow-y:auto;
        -webkit-overflow-scrolling:touch;
      }}
    }}
    .column h3 {{ margin:0 0 0.5rem; font-size:0.95rem; flex-shrink:0; }}
    .task-list {{ list-style:none; margin:0; padding:0; }}
    .task {{ border-bottom:1px solid #eee; padding:0.5rem 0; font-size:0.9rem; }}
    .task:last-child {{ border-bottom:none; }}
    .task-title {{ line-height:1.4; }}
    .task-meta {{ margin-top:0.25rem; color:#666; font-size:0.8rem; }}
    .tag {{ display:inline-block; background:#eef2ff; color:#364fc7; padding:0.1em 0.4em; border-radius:4px; margin-right:0.3rem; font-size:0.75rem; }}
    .task-done .task-title {{ text-decoration: line-through; color:#888; }}
    a.task-doc {{ color:#364fc7; font-size:0.82rem; font-weight:500; text-decoration:none; margin-left:0.15rem; white-space:nowrap; }}
    a.task-doc:hover {{ text-decoration:underline; }}
    .panel {{ background:#fff; border:1px solid #e2e3e5; border-radius:8px; padding:1rem; margin-top:0.5rem; }}
    .burndown-meta {{ font-size:0.9rem; color:#333; margin:0 0 0.5rem; line-height:1.5; }}
    .burndown-legend {{ display:flex; flex-wrap:wrap; gap:0.75rem 1rem; margin:0 0 0.35rem; font-size:0.82rem; color:#495057; }}
    .burndown-legend .lg {{ display:inline-flex; align-items:center; gap:0.35rem; }}
    .burndown-legend .dot {{ width:0.55rem; height:0.55rem; border-radius:50%; display:inline-block; }}
    .burndown-legend .dot-rem {{ background:#1971c2; }}
    .burndown-legend .dot-done {{ background:#2f9e44; }}
    .burndown-chart-wrap {{ width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; margin-top:0.25rem; }}
    .burndown-svg {{ display:block; width:100%; max-width:720px; height:auto; margin:0 auto; }}
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
      font-weight:700;
      white-space: nowrap;
    }}
    table.heatmap td.hcell .heat-w {{
      font-size: 0.88em;
      font-weight: 600;
      color: #495057;
    }}
    .heat-empty {{ font-size:0.88rem; color:#868e96; margin:0.25rem 0 0.75rem; }}
    h2 .heat-scale {{ font-size:0.78em; font-weight:400; color:#6c757d; margin-left:0.35em; }}
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
    a.project-chip.project-juminshang {{ border-left:3px solid #7950f2; }}
    a.project-chip.project-personal {{ border-left:3px solid #495057; }}
    @media print {{
      body {{ background:#fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .wrap {{ max-width:none; padding:0.75rem; }}
      .heat-scroll,
      .burndown-chart-wrap {{ overflow:visible !important; }}
      table.heatmap {{ min-width:0; width:100%; page-break-inside:auto; }}
      .columns {{ grid-template-columns:1fr !important; gap:0.75rem; }}
      .column {{
        height:auto !important;
        max-height:none !important;
        min-height:0;
        break-inside:auto;
        page-break-inside:auto;
      }}
      .column .task-list {{
        flex:none !important;
        overflow:visible !important;
        max-height:none !important;
      }}
      a.project-chip {{ border:1px solid #ccc; }}
    }}
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
    <nav class="project-hub" aria-label="项目与个人入口">
      <span class="project-hub-label">项目</span>
      <a class="project-chip project-qunxing" href="dashboard-qunxing.html"><code>qunxing</code> 群兴</a>
      <a class="project-chip project-xl" href="dashboard-xlshangpin.html"><code>xlshangpin</code> 兴链尚品</a>
      <a class="project-chip project-juminshang" href="dashboard-juminshang.html"><code>juminshang</code> 聚闽商</a>{personal_hub_block}
    </nav>
    <div class="kpi-row">{nav}</div>
    <h2>负载热力图<span class="heat-scale">（主数字为条数，括号内为难度加权；好做1 · 一般2 · 难3 · 未标1）</span></h2>
    <h3 class="heat-h3">团队（产品线）</h3>
    <div class="heat-scroll">{heat_team_html}</div>
    <h3 class="heat-h3">负责人</h3>
    <div class="heat-scroll">{heat_people_html}</div>
    <h2>看板</h2>
    <div class="columns">
      {''.join(col_html)}
    </div>
    <div class="panel">{burndown_html}</div>
    <p class="footer">项目专页（按 effort 分组）：<a href="dashboard-qunxing.html"><code>qunxing</code> 群兴</a> · <a href="dashboard-xlshangpin.html"><code>xlshangpin</code> 兴链尚品</a> · <a href="dashboard-juminshang.html"><code>juminshang</code> 聚闽商</a>{personal_footer_extra}</p>
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
    valid = parse_repos_index(rtext)
    sections, order = parse_board(btext, valid)
    done, total = board_done_total(sections)
    burndown_pts = upsert_today_burndown(BURNDOWN_PATH, done, total)
    html = build_html(sections, order, burndown_pts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(HUB)}")
    print(f"Wrote {BURNDOWN_PATH.relative_to(HUB)}")
    qx_tasks = collect_qunxing_tasks(sections)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    qx_html = build_qunxing_html(qx_tasks, ts)
    OUT_QUNXING.write_text(qx_html, encoding="utf-8")
    print(f"Wrote {OUT_QUNXING.relative_to(HUB)}")
    xls_tasks = collect_tasks_by_tag(sections, "xlshangpin")
    xls_html = build_xlshangpin_html(xls_tasks, ts)
    OUT_XLSHANGPIN.write_text(xls_html, encoding="utf-8")
    print(f"Wrote {OUT_XLSHANGPIN.relative_to(HUB)}")
    jms_tasks = collect_tasks_by_tag(sections, "juminshang")
    jms_html = build_juminshang_html(jms_tasks, ts)
    OUT_JUMINSHANG.write_text(jms_html, encoding="utf-8")
    print(f"Wrote {OUT_JUMINSHANG.relative_to(HUB)}")
    men = PERSON_DASHBOARD_MENTION.strip()
    if men:
        pers_tasks = collect_tasks_by_mention(sections, men)
        pers_html = build_personal_dashboard_html(pers_tasks, ts, men)
        OUT_PERSONAL.write_text(pers_html, encoding="utf-8")
        print(f"Wrote {OUT_PERSONAL.relative_to(HUB)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
