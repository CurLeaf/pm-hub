"""Unit tests for scripts/gen_dashboard.py (stdlib only)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
# Import gen_dashboard as a top-level module from this directory
_spec = importlib.util.spec_from_file_location("gen_dashboard", SCRIPTS / "gen_dashboard.py")
assert _spec and _spec.loader
_gd = importlib.util.module_from_spec(_spec)
sys.modules["gen_dashboard"] = _gd
_spec.loader.exec_module(_gd)


class TestParsers(unittest.TestCase):
    def test_parse_repos(self):
        md = """
| 短名 | 其它 |
|------|------|
| aa-bb | x |
| invalid_U | n |
        """
        s = _gd.parse_repos_index(md)
        self.assertEqual(s, {"aa-bb"})

    def test_parse_board_tags(self):
        md = """
## 🟡 正在实现
- [ ] 任务 [backend] [frontend] @a 2026-01-01
- [x] 完成 [backend]
        """
        valid = {"backend", "frontend"}
        sec, order = _gd.parse_board(md, valid)
        self.assertIn("🟡 正在实现", order)
        tasks = sec["🟡 正在实现"]
        self.assertEqual(len(tasks), 2)
        self.assertFalse(tasks[0].done)
        self.assertEqual(tasks[0].tags, ["backend", "frontend"])
        self.assertTrue(tasks[1].done)

    def test_parse_milestones(self):
        md = """
| milestone | target   | progress |
|-----|------------|----|
| v0.1 | 2026-01-31 | 10 |
| v0.2 | 2026-02-15 | 0 |
        """
        rows = _gd.parse_milestones(md)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].name, "v0.1")
        self.assertEqual(rows[0].progress, 10)

    def test_regression_repo_fixture(self):
        p = ROOT / "repos.md"
        if not p.is_file():
            self.skipTest("repos.md not present")
        s = _gd.parse_repos_index(p.read_text(encoding="utf-8"))
        for name in ("xlshangpin", "qunxing", "frontend", "backend", "mobile", "infra"):
            self.assertIn(name, s)

    def test_collect_qunxing_tasks(self):
        valid = {"qunxing", "backend"}
        md = """
## 🟢 待开始
- [ ] A effort:好做 [qunxing]
- [ ] B [backend]
"""
        sec, _ = _gd.parse_board(md, valid)
        qx = _gd.collect_qunxing_tasks(sec)
        self.assertEqual(len(qx), 1)
        self.assertIn("A", qx[0].text)

    def test_strip_bracket_tags(self):
        self.assertEqual(
            _gd.strip_bracket_tags(
                "群兴 QX-01 x effort:好做 [qunxing] @tbd 2026-04-26"
            ),
            "群兴 QX-01 x effort:好做 @tbd 2026-04-26",
        )

    def test_build_qunxing_html(self):
        valid = {"qunxing", "backend"}
        sec, _ = _gd.parse_board(
            "## S\n- [ ] 群兴 QX-02 b effort:一般 [qunxing]\n"
            "- [ ] 群兴 QX-01 a effort:好做 [qunxing]\n",
            valid,
        )
        qx = _gd.collect_qunxing_tasks(sec)
        html = _gd.build_qunxing_html(qx, "2026-01-01 00:00 UTC")
        self.assertIn("群兴任务", html)
        self.assertIn("QX-01", html)
        self.assertIn("好做", html)
        self.assertNotIn("[qunxing]", html)
        self.assertNotIn('class="tag"', html)

    def test_build_html(self):
        valid = {"backend"}
        sections, order = _gd.parse_board(
            "## S\n- [ ] T [backend]\n",
            valid,
        )
        ms = [ _gd.Milestone("m", "2026-01-01", 50) ]
        html = _gd.build_html(valid, sections, order, ms)
        self.assertIn("项目仪表盘", html)
        self.assertIn("backend", html)
        self.assertIn("m", html)


if __name__ == "__main__":
    unittest.main()
