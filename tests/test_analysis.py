import unittest

from ghzw.analysis import (
    assign_roles,
    assess_roles,
    classify_market_cycle,
    classify_stage,
    classify_theme_tiers,
    find_limit_up_candidates,
    plan_next_action,
    select_turnover_top,
    summarize_themes,
)
from ghzw.models import DailyBar, PlateMembership, StageTag, StockSnapshot


class AnalysisTest(unittest.TestCase):
    def test_find_limit_up_candidates_uses_market_specific_thresholds(self):
        snapshots = [
            StockSnapshot(code="SH.600001", name="Main Board", last_price=10.98, prev_close_price=10.0),
            StockSnapshot(code="SZ.300001", name="ChiNext", last_price=11.95, prev_close_price=10.0),
            StockSnapshot(code="SH.688001", name="STAR", last_price=11.94, prev_close_price=10.0),
            StockSnapshot(code="SZ.000001", name="Almost", last_price=10.70, prev_close_price=10.0),
            StockSnapshot(code="SH.600002", name="ST Capped", last_price=10.49, prev_close_price=10.0, is_st=True),
        ]

        result = find_limit_up_candidates(snapshots)

        self.assertEqual([item.code for item in result], ["SH.600001", "SZ.300001", "SH.688001", "SH.600002"])
        self.assertEqual(result[0].limit_threshold, 10)
        self.assertEqual(result[1].limit_threshold, 20)
        self.assertEqual(result[3].limit_threshold, 5)

    def test_select_turnover_top_orders_by_turnover_descending(self):
        snapshots = [
            StockSnapshot(code="SH.600001", name="A", turnover=100),
            StockSnapshot(code="SH.600002", name="B", turnover=300),
            StockSnapshot(code="SH.600003", name="C", turnover=200),
        ]

        result = select_turnover_top(snapshots, limit=2)

        self.assertEqual([item.code for item in result], ["SH.600002", "SH.600003"])

    def test_summarize_themes_counts_limit_ups_and_turnover(self):
        snapshots = [
            StockSnapshot(code="SH.600001", name="A", last_price=10.98, prev_close_price=10.0, turnover=100),
            StockSnapshot(code="SZ.300001", name="B", last_price=11.95, prev_close_price=10.0, turnover=300),
            StockSnapshot(code="SH.600003", name="C", last_price=10.30, prev_close_price=10.0, turnover=50),
        ]
        memberships = {
            "SH.600001": [PlateMembership(code="BK001", name="Robotics", plate_type="CONCEPT")],
            "SZ.300001": [PlateMembership(code="BK001", name="Robotics", plate_type="CONCEPT")],
            "SH.600003": [PlateMembership(code="BK002", name="Consumer", plate_type="INDUSTRY")],
        }
        limit_up_codes = {"SH.600001", "SZ.300001"}

        result = summarize_themes(snapshots, memberships, limit_up_codes)

        self.assertEqual(result[0].plate_name, "Robotics")
        self.assertEqual(result[0].limit_up_count, 2)
        self.assertEqual(result[0].total_turnover, 400)
        self.assertEqual(round(result[0].avg_change_pct, 2), 14.65)

    def test_classify_stage_identifies_consecutive_boards_breakout_and_volume_expansion(self):
        history = [
            DailyBar(code="SH.600001", date="2026-01-%02d" % day, close=10 + day * 0.1, turnover=100)
            for day in range(1, 21)
        ]
        history.extend(
            [
                DailyBar(code="SH.600001", date="2026-01-21", close=13.0, turnover=300, change_pct=10.0),
                DailyBar(code="SH.600001", date="2026-01-22", close=14.3, turnover=350, change_pct=10.0),
            ]
        )

        result = classify_stage(history)

        self.assertEqual(result.board_streak, 2)
        self.assertIn("连板", result.labels)
        self.assertIn("创20日新高", result.labels)
        self.assertIn("放量", result.labels)

    def test_classify_stage_uses_market_specific_board_threshold(self):
        chinext_history = [
            DailyBar(code="SZ.300001", date="2026-01-01", close=10, change_pct=10.0),
            DailyBar(code="SZ.300001", date="2026-01-02", close=11, change_pct=10.0),
        ]
        st_history = [
            DailyBar(code="SH.600001", date="2026-01-01", close=10, change_pct=5.0),
            DailyBar(code="SH.600001", date="2026-01-02", close=10.5, change_pct=5.0),
        ]

        self.assertEqual(classify_stage(chinext_history).board_streak, 0)
        self.assertEqual(classify_stage(st_history, limit_threshold=5).board_streak, 2)

    def test_assign_roles_marks_theme_leader_capacity_core_and_rear(self):
        snapshots = [
            StockSnapshot(code="SH.600001", name="Leader", turnover=300, change_rate=10.0),
            StockSnapshot(code="SH.600002", name="Capacity", turnover=500, change_rate=7.0),
            StockSnapshot(code="SH.600003", name="Rear", turnover=80, change_rate=3.0),
        ]
        stage_by_code = {
            "SH.600001": classify_stage(
                [
                    DailyBar(code="SH.600001", date="2026-01-01", close=10, change_pct=10.0),
                    DailyBar(code="SH.600001", date="2026-01-02", close=11, change_pct=10.0),
                ]
            ),
            "SH.600002": classify_stage([DailyBar(code="SH.600002", date="2026-01-02", close=10, change_pct=7.0)]),
            "SH.600003": classify_stage([DailyBar(code="SH.600003", date="2026-01-02", close=10, change_pct=3.0)]),
        }

        result = assign_roles(snapshots, stage_by_code)

        self.assertEqual(result["SH.600001"], "龙头")
        self.assertEqual(result["SH.600002"], "容量核心")
        self.assertEqual(result["SH.600003"], "跟风")

    def test_assess_roles_scores_leader_capacity_middle_and_weak_names(self):
        snapshots = [
            StockSnapshot(code="SH.600001", name="Leader", turnover=300, market_val=1000, change_rate=10.0, turnover_rate=8, volume_ratio=2.0),
            StockSnapshot(code="SH.600002", name="Capacity", turnover=900, market_val=1200, change_rate=7.0, turnover_rate=5, volume_ratio=1.5),
            StockSnapshot(code="SH.600003", name="Middle", turnover=500, market_val=8000, change_rate=2.0, turnover_rate=2, volume_ratio=1.0),
            StockSnapshot(code="SH.600004", name="Supplement", turnover=180, market_val=900, change_rate=6.5, turnover_rate=6, volume_ratio=1.2),
            StockSnapshot(code="SH.600005", name="Weak", turnover=80, market_val=500, change_rate=-1.0, turnover_rate=1, volume_ratio=0.8),
        ]
        stage_by_code = {
            "SH.600001": StageTag(labels=["连板"], board_streak=2),
            "SH.600002": StageTag(labels=["低位启动"], board_streak=0),
            "SH.600003": StageTag(labels=["观察"], board_streak=0),
            "SH.600004": StageTag(labels=["低位启动"], board_streak=0),
            "SH.600005": StageTag(labels=["观察"], board_streak=0),
        }

        result = assess_roles(snapshots, stage_by_code, theme_tier="主线")

        self.assertEqual(result["SH.600001"].role, "龙头")
        self.assertEqual(result["SH.600002"].role, "容量核心")
        self.assertEqual(result["SH.600003"].role, "中军")
        self.assertEqual(result["SH.600004"].role, "补涨")
        self.assertEqual(result["SH.600005"].role, "杂毛")
        self.assertGreater(result["SH.600001"].score, result["SH.600004"].score)
        self.assertIn("连板2", result["SH.600001"].basis)

    def test_classify_market_cycle_prioritizes_breadth_and_limit_up_count(self):
        hot_market = [
            StockSnapshot(code="SH.%06d" % index, name="S%s" % index, change_rate=3.0)
            for index in range(100)
        ]
        cold_market = [
            StockSnapshot(code="SH.%06d" % index, name="S%s" % index, change_rate=-2.0)
            for index in range(100)
        ]

        self.assertEqual(classify_market_cycle(hot_market, limit_up_count=82), "高潮")
        self.assertEqual(classify_market_cycle(cold_market, limit_up_count=6), "冰点")
        self.assertEqual(classify_market_cycle(hot_market, limit_up_count=35), "上升")

    def test_classify_theme_tiers_marks_mainline_support_rotation_and_fading_old_theme(self):
        summaries = [
            _theme("GN001", "人工智能", limit_up_count=5, avg_change_pct=6.0, total_turnover=1000),
            _theme("GN002", "机器人", limit_up_count=2, avg_change_pct=3.5, total_turnover=600),
            _theme("GN003", "消费", limit_up_count=0, avg_change_pct=1.2, total_turnover=900),
            _theme("GN004", "旧周期", limit_up_count=0, avg_change_pct=-1.5, total_turnover=700),
        ]

        result = classify_theme_tiers(summaries)

        self.assertEqual(result["GN001"], "主线")
        self.assertEqual(result["GN002"], "支线")
        self.assertEqual(result["GN003"], "轮动")
        self.assertEqual(result["GN004"], "退潮老题材")

    def test_plan_next_action_follows_cycle_role_and_theme_tier(self):
        self.assertEqual(plan_next_action("退潮", "龙头", "主线"), "退潮空仓")
        self.assertEqual(plan_next_action("分歧", "龙头", "主线"), "核心分歧低吸")
        self.assertEqual(plan_next_action("上升", "容量核心", "主线"), "转强确认加仓")
        self.assertEqual(plan_next_action("修复", "补涨", "支线"), "轻仓试错")
        self.assertEqual(plan_next_action("高潮", "跟风", "轮动"), "高潮后排不追")


def _theme(code, name, limit_up_count, avg_change_pct, total_turnover):
    from ghzw.models import ThemeSummary

    return ThemeSummary(
        plate_code=code,
        plate_name=name,
        plate_type="CONCEPT",
        limit_up_count=limit_up_count,
        avg_change_pct=avg_change_pct,
        total_turnover=total_turnover,
    )


if __name__ == "__main__":
    unittest.main()
