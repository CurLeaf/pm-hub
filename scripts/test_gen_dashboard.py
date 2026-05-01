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
        for name in ("xlshangpin", "juminshang", "qunxing", "frontend", "backend", "mobile", "infra"):
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

    def test_task_title_html_trailing_doc_link(self):
        raw = "群兴 QX-30 x effort:一般 [qunxing] @嘉松 2026-04-28 (docs/qunxing-qx30-waybill-editor.md)"
        html = _gd.task_title_html(raw)
        self.assertIn("群兴 QX-30", html)
        self.assertIn('href="qunxing-qx30-waybill-editor.md"', html)
        self.assertIn(">说明</a>", html)
        self.assertNotIn("docs/", html)
        self.assertNotIn("[qunxing]", html)

    def test_task_title_html_no_trailing_ref(self):
        raw = "群兴 QX-01 x effort:好做 [qunxing] @tbd 2026-04-26"
        html = _gd.task_title_html(raw)
        self.assertEqual(html, _gd.escape(_gd.strip_bracket_tags(raw)))

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
        # 任务标题已去标签；说明区含 [qunxing] 字面
        self.assertNotIn("effort:好做 [qunxing]", html)
        self.assertNotIn('class="tag"', html)
        self.assertIn("dashboard-xlshangpin.html", html)
        self.assertIn("dashboard-juminshang.html", html)
        if _gd.PERSON_DASHBOARD_MENTION.strip():
            self.assertIn("dashboard-personal.html", html)
            self.assertIn("我的工作", html)
        self.assertNotIn("btn-toggle-hide-done", html)

    def test_collect_tasks_by_mention(self):
        valid = {"qunxing"}
        md = """
## 🟡 正在实现
- [ ] Mine effort:好做 [qunxing] @CurLeaf 2026-01-01
- [ ] Other effort:一般 [qunxing] @凯杰 2026-01-01
"""
        sec, _ = _gd.parse_board(md, valid)
        mine = _gd.collect_tasks_by_mention(sec, "@CurLeaf")
        self.assertEqual(len(mine), 1)
        self.assertIn("Mine", mine[0].text)

    def test_build_personal_dashboard_html(self):
        valid = {"qunxing"}
        sec, _ = _gd.parse_board(
            "## 🟡 正在实现\n"
            "- [ ] 群兴 QX-03 z effort:一般 [qunxing] @CurLeaf\n"
            "- [ ] 群兴 QX-01 a effort:好做 [qunxing] @CurLeaf\n",
            valid,
        )
        tasks = _gd.collect_tasks_by_mention(sec, "@CurLeaf")
        html = _gd.build_personal_dashboard_html(tasks, "2026-01-01 00:00 UTC", "@CurLeaf")
        self.assertIn("我的工作看板", html)
        self.assertIn("@CurLeaf", html)
        self.assertIn("QX-01", html)
        self.assertIn("QX-03", html)
        self.assertIn('class="tag"', html)
        self.assertIn("qunxing", html)
        self.assertIn("btn-toggle-hide-done", html)
        self.assertIn("hide-done-tasks", html)

    def test_collect_tasks_by_tag(self):
        valid = {"qunxing", "xlshangpin"}
        md = """
## S
- [ ] A [qunxing]
- [ ] B [xlshangpin]
"""
        sec, _ = _gd.parse_board(md, valid)
        self.assertEqual(len(_gd.collect_tasks_by_tag(sec, "qunxing")), 1)
        self.assertEqual(len(_gd.collect_tasks_by_tag(sec, "xlshangpin")), 1)

    def test_build_xlshangpin_html(self):
        valid = {"xlshangpin"}
        sec, _ = _gd.parse_board(
            "## S\n- [ ] 兴链 foo effort:好做 [xlshangpin] @a\n",
            valid,
        )
        tasks = _gd.collect_tasks_by_tag(sec, "xlshangpin")
        html = _gd.build_xlshangpin_html(tasks, "2026-01-01 00:00 UTC")
        self.assertIn("兴链尚品任务", html)
        self.assertIn("兴链 foo", html)
        self.assertIn("dashboard-qunxing.html", html)
        self.assertIn("dashboard-juminshang.html", html)

    def test_build_juminshang_html(self):
        valid = {"juminshang"}
        sec, _ = _gd.parse_board(
            "## S\n- [ ] 闽商 foo effort:一般 [juminshang] @a\n",
            valid,
        )
        tasks = _gd.collect_tasks_by_tag(sec, "juminshang")
        html = _gd.build_juminshang_html(tasks, "2026-01-01 00:00 UTC")
        self.assertIn("聚闽商任务", html)
        self.assertIn("闽商 foo", html)
        self.assertIn("dashboard-qunxing.html", html)
        self.assertIn("dashboard-xlshangpin.html", html)

    def test_build_html(self):
        valid = {"backend", "qunxing"}
        sections, order = _gd.parse_board(
            "## S\n- [ ] T [backend] [qunxing] @a\n",
            valid,
        )
        bd = [
            _gd.BurndownPoint("2026-04-01", 5, 1),
            _gd.BurndownPoint("2026-04-02", 5, 2),
        ]
        html = _gd.build_html(sections, order, bd)
        self.assertIn("项目仪表盘", html)
        self.assertIn("qunxing", html)
        self.assertIn("燃尽", html)
        self.assertNotIn("里程碑", html)
        self.assertNotIn("仓库维度", html)
        self.assertNotIn("成员负载", html)
        if _gd.PERSON_DASHBOARD_MENTION.strip():
            self.assertIn("dashboard-personal.html", html)

    def test_board_done_total(self):
        valid = {"qunxing"}
        sec, _ = _gd.parse_board(
            "## A\n- [ ] a [qunxing]\n- [x] b [qunxing]\n",
            valid,
        )
        d, t = _gd.board_done_total(sec)
        self.assertEqual((d, t), (1, 2))

    def test_burndown_upsert(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "burndown-history.json"
            r1 = _gd.upsert_today_burndown(p, 1, 4, today="2026-04-01")
            self.assertEqual(len(r1), 1)
            self.assertEqual(r1[0].done, 1)
            r2 = _gd.upsert_today_burndown(p, 2, 4, today="2026-04-02")
            self.assertEqual(len(r2), 2)
            r3 = _gd.upsert_today_burndown(p, 3, 4, today="2026-04-02")
            self.assertEqual(len(r3), 2)
            self.assertEqual(r3[-1].done, 3)
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(raw["version"], 1)
            self.assertEqual(len(raw["points"]), 2)

    def test_render_burndown_svg(self):
        pts = [
            _gd.BurndownPoint("2026-04-01", 10, 2),
            _gd.BurndownPoint("2026-04-02", 10, 5),
        ]
        svg = _gd.render_burndown_svg(pts)
        self.assertIn("polyline", svg)
        self.assertIn("1971c2", svg)

    def test_task_team_label(self):
        T = _gd.Task
        self.assertEqual(
            _gd.task_team_label(T("", False, "", "", ["qunxing"], None)), "群兴"
        )
        self.assertEqual(
            _gd.task_team_label(T("", False, "", "", ["xlshangpin"], None)), "兴链尚品"
        )
        self.assertEqual(
            _gd.task_team_label(T("", False, "", "", ["juminshang"], None)), "聚闽商"
        )
        self.assertEqual(
            _gd.task_team_label(T("", False, "", "", ["backend"], None)), "其它"
        )
        self.assertEqual(_gd.task_team_label(T("", False, "", "", [], None)), "(无标签)")

    def test_heatmap_in_dashboard_html(self):
        valid = {"qunxing", "xlshangpin", "backend"}
        md = """
## 🟡 正在实现
- [ ] A effort:好做 [qunxing] @a 2026-01-01
## 🟢 待开始
- [ ] B effort:好做 [xlshangpin] @b 2026-01-02
"""
        sec, order = _gd.parse_board(md, valid)
        html = _gd.build_html(sec, order, [])
        self.assertIn("负载热力图", html)
        self.assertIn("团队（产品线）", html)
        self.assertIn("负责人", html)

    def test_heatmap_people_matrix_skips_tbd(self):
        valid = {"qunxing"}
        md = """
## 🟢 待开始
- [ ] X effort:好做 [qunxing] @tbd 2026-01-01
- [ ] Y effort:好做 [qunxing] @me 2026-01-02
"""
        sec, _ = _gd.parse_board(md, valid)
        cnt, wgt = _gd.heatmap_people_matrix(sec)
        self.assertNotIn("@tbd", cnt)
        self.assertIn("@me", cnt)
        self.assertEqual(cnt["@me"].get("🟢 待开始"), 1)
        self.assertEqual(wgt["@me"].get("🟢 待开始"), 1)

    def test_heatmap_team_column_sums_match_section_counts(self):
        """Each board column: sum over team rows == task count in that section."""
        valid = {"qunxing", "xlshangpin", "frontend", "backend"}
        md = """
## 🟡 正在实现
- [ ] A [qunxing] @a
- [ ] B [frontend] [backend] @b
## 🟢 待开始
- [ ] C [xlshangpin] @c
"""
        sec, order = _gd.parse_board(md, valid)
        counts: dict[str, int] = {}
        for sn, tasks in sec.items():
            counts[sn] = len(tasks)
        team_cnt, _team_wgt = _gd.heatmap_team_matrix(sec)
        for sn in sec:
            s = sum(team_cnt.get(row, {}).get(sn, 0) for row in team_cnt)
            self.assertEqual(s, counts[sn], msg=f"section {sn!r}")

    def test_heatmap_team_weights_reflect_effort(self):
        valid = {"qunxing"}
        md = """
## 🟡 正在实现
- [ ] E effort:好做 [qunxing] @a
- [ ] H effort:难 [qunxing] @b
"""
        sec, _ = _gd.parse_board(md, valid)
        _cnt, wgt = _gd.heatmap_team_matrix(sec)
        sec_name = "🟡 正在实现"
        self.assertEqual(wgt["群兴"].get(sec_name), 4)

    def test_task_effort_weight(self):
        self.assertEqual(_gd.task_effort_weight("x effort:好做 [qunxing]"), 1)
        self.assertEqual(_gd.task_effort_weight("x effort:一般 [qunxing]"), 2)
        self.assertEqual(_gd.task_effort_weight("x effort:难 [qunxing]"), 3)
        self.assertEqual(_gd.task_effort_weight("x [qunxing]"), 1)

if __name__ == "__main__":
    unittest.main()
