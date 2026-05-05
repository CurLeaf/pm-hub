"""
Merge two dev-time-state JSON documents (stdlib only).

Typical use after exporting from the dashboard on another machine:
  python scripts/merge_dev_time_export.py docs/dev-time-state.json incoming.json -o docs/dev-time-state.json

Merge rule per task key: totalMs and sessions are additive (import adds onto base);
lastEndedAt / note prefer non-empty incoming values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _norm_task(d: object) -> dict[str, object]:
    if not isinstance(d, dict):
        return {"totalMs": 0, "sessions": [], "lastEndedAt": None, "note": ""}
    try:
        tm = max(0, int(d.get("totalMs", 0) or 0))
    except (TypeError, ValueError):
        tm = 0
    sess = d.get("sessions")
    if not isinstance(sess, list):
        sess = []
    le = d.get("lastEndedAt")
    if le is not None and not isinstance(le, str):
        le = None
    note = d.get("note", "")
    if not isinstance(note, str):
        note = ""
    return {"totalMs": tm, "sessions": sess, "lastEndedAt": le, "note": note}


def load_state(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": 1, "tasks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        return {"version": 1, "tasks": {}}
    ver = data.get("version", 1)
    try:
        ver = int(ver)
    except (TypeError, ValueError):
        ver = 1
    raw = data.get("tasks")
    if not isinstance(raw, dict):
        raw = {}
    tasks: dict[str, object] = {}
    for k, v in raw.items():
        if isinstance(k, str) and k.strip():
            tasks[k.strip()] = _norm_task(v)
    return {"version": ver, "tasks": tasks}


def merge(base: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    bt = base.get("tasks")
    if not isinstance(bt, dict):
        bt = {}
    it = incoming.get("tasks")
    if not isinstance(it, dict):
        it = {}
    keys = set(bt) | set(it)
    out_tasks: dict[str, object] = {}
    for k in keys:
        b = _norm_task(bt.get(k)) if k in bt else _norm_task({})
        i = _norm_task(it.get(k)) if k in it else _norm_task({})
        sess_b = b["sessions"] if isinstance(b["sessions"], list) else []
        sess_i = i["sessions"] if isinstance(i["sessions"], list) else []
        merged_sess = list(sess_b) + list(sess_i)
        try:
            btm = int(b.get("totalMs", 0) or 0)
            itm = int(i.get("totalMs", 0) or 0)
        except (TypeError, ValueError):
            btm, itm = 0, 0
        le_out = i.get("lastEndedAt") or b.get("lastEndedAt")
        note_b = str(b.get("note") or "")
        note_i = str(i.get("note") or "")
        note_out = note_i if note_i.strip() else note_b
        out_tasks[k] = {
            "totalMs": max(0, btm + itm),
            "sessions": merged_sess,
            "lastEndedAt": le_out,
            "note": note_out,
        }
    ver = base.get("version", 1)
    try:
        ver = int(ver)
    except (TypeError, ValueError):
        ver = 1
    return {"version": ver, "tasks": out_tasks}


def main() -> int:
    p = argparse.ArgumentParser(description="Merge dev-time-state JSON files.")
    p.add_argument("base", type=Path, help="Existing repo file, e.g. docs/dev-time-state.json")
    p.add_argument("incoming", type=Path, help="Second file to merge in (e.g. exported download)")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write merged JSON here (default: stdout only)",
    )
    args = p.parse_args()
    base = load_state(args.base)
    inc = load_state(args.incoming)
    merged = merge(base, inc)
    text = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
