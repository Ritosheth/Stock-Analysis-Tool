import unittest

from ghzw.models import DailyBar, MarketSentiment, StageTag, StockSnapshot
from ghzw.sentiment import classify_market_cycle_from_sentiment, compute_market_sentiment


class SentimentTest(unittest.TestCase):
    def test_compute_market_sentiment_calculates_core_metrics(self):
        snapshots = [
            StockSnapshot(code="SH.600001", name="A", change_rate=10.0, turnover=300),
            StockSnapshot(code="SH.600002", name="B", change_rate=-10.0, turnover=200),
            StockSnapshot(code="SH.600003", name="C", change_rate=2.0, turnover=100),
            StockSnapshot(code="SH.600004", name="D", change_rate=-1.0, turnover=50),
        ]
        stage_by_code = {
            "SH.600001": StageTag(labels=["连板"], board_streak=3),
            "SH.600003": StageTag(labels=["首板"], board_streak=1),
        }
        history = {
            "SH.600001": [
                DailyBar(code="SH.600001", date="2026-06-13", close=10, change_pct=10.0),
                DailyBar(code="SH.600001", date="2026-06-14", close=11, change_pct=10.0),
            ],
            "SH.600003": [
                DailyBar(code="SH.600003", date="2026-06-13", close=10, change_pct=10.0),
                DailyBar(code="SH.600003", date="2026-06-14", close=10.2, change_pct=2.0),
            ],
        }

        result = compute_market_sentiment(snapshots, stage_by_code, history, turnover_limit=2)

        self.assertEqual(result.limit_up_count, 1)
        self.assertEqual(result.limit_down_count, 1)
        self.assertEqual(result.positive_count, 2)
        self.assertEqual(result.negative_count, 2)
        self.assertEqual(result.max_board_streak, 3)
        self.assertEqual(result.board_streak_count, 2)
        self.assertEqual(result.turnover_top_avg_change_pct, 0.0)
        self.assertEqual(result.yesterday_limit_up_avg_change_pct, 6.0)
        self.assertIn("涨停1/跌停1/上涨50%/连板高3/昨板+6.0%", result.summary)

    def test_classify_market_cycle_from_sentiment(self):
        self.assertEqual(
            classify_market_cycle_from_sentiment(
                MarketSentiment(limit_up_count=85, positive_ratio=0.7, max_board_streak=5, board_streak_count=10)
            ),
            "高潮",
        )
        self.assertEqual(classify_market_cycle_from_sentiment(MarketSentiment(limit_up_count=5, positive_ratio=0.2)), "冰点")
        self.assertEqual(
            classify_market_cycle_from_sentiment(
                MarketSentiment(limit_up_count=15, limit_down_count=22, positive_ratio=0.4, avg_change_pct=-0.8)
            ),
            "退潮",
        )
        self.assertEqual(
            classify_market_cycle_from_sentiment(
                MarketSentiment(limit_up_count=36, positive_ratio=0.6, max_board_streak=3, board_streak_count=6)
            ),
            "修复",
        )
        self.assertEqual(
            classify_market_cycle_from_sentiment(
                MarketSentiment(limit_up_count=52, positive_ratio=0.61, max_board_streak=4, board_streak_count=9, limit_down_count=6)
            ),
            "上升",
        )
        self.assertEqual(classify_market_cycle_from_sentiment(MarketSentiment(limit_up_count=22, positive_ratio=0.5, avg_change_pct=0.1)), "修复")

    def test_classify_market_cycle_avoids高潮_when_board_height_is_thin_and_limit_downs_are_heavy(self):
        result = classify_market_cycle_from_sentiment(
            MarketSentiment(
                limit_up_count=79,
                limit_down_count=22,
                positive_ratio=0.72,
                avg_change_pct=1.1,
                max_board_streak=3,
                board_streak_count=5,
                yesterday_limit_up_avg_change_pct=-3.0,
            )
        )

        self.assertEqual(result, "修复")


if __name__ == "__main__":
    unittest.main()
