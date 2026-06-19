import unittest
from datetime import date

from ghzw.forum_sources import build_forum_queries, collect_forum_discussions
from ghzw.models import DailyRecord


class ForumSourcesTest(unittest.TestCase):
    def test_build_forum_queries_uses_core_themes_and_turnover_names(self):
        records = [
            _record("SH.600001", "Alpha", "半导体", 300),
            _record("SH.600002", "Beta", "半导体", 500),
            _record("SH.600003", "Gamma", "机器人", 100),
        ]

        result = build_forum_queries(records, max_queries=4)

        self.assertEqual(result[0], "半导体 涨停 原因")
        self.assertIn("Beta 涨停", result)

    def test_collect_forum_discussions_parses_mock_public_results(self):
        def fetch_text(url):
            return '<html><a href="https://xueqiu.com/123">半导体板块涨停原因讨论</a></html>'

        result = collect_forum_discussions(
            date(2026, 6, 17),
            [_record("SH.600001", "Alpha", "半导体", 300)],
            fetch_text=fetch_text,
            max_queries=1,
        )

        self.assertEqual(result.warning, "")
        self.assertEqual(result.discussions[0].source, "雪球")
        self.assertIn("半导体", result.discussions[0].title)

    def test_collect_forum_discussions_returns_warning_on_fetch_failure(self):
        def fetch_text(url):
            raise OSError("network blocked")

        result = collect_forum_discussions(
            date(2026, 6, 17),
            [_record("SH.600001", "Alpha", "半导体", 300)],
            fetch_text=fetch_text,
            max_queries=1,
        )

        self.assertEqual(result.discussions, [])
        self.assertIn("论坛线索未获取", result.warning)


def _record(code, name, core_theme, turnover):
    return DailyRecord(
        date="2026-06-17",
        code=code,
        name=name,
        record_type="涨停",
        close_price=11,
        prev_close_price=10,
        change_pct=10,
        turnover=turnover,
        turnover_rate=5,
        volume_ratio=1,
        industries="半导体-存储器",
        concepts=core_theme,
        market_cycle="上升",
        theme_rank=1,
        theme_tier="主线",
        role="龙头",
        stage="首板",
        next_action="观察验证",
        net_inflow=0,
        main_net_inflow=0,
        reason_type="不明",
        review="测试",
        core_theme=core_theme,
        limit_up_boards="1板",
    )


if __name__ == "__main__":
    unittest.main()
