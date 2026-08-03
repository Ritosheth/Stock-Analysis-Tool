import tempfile
import unittest
from pathlib import Path

from ghzw.lifecycle import assess_lifecycle_risks, load_watchlist
from ghzw.models import DailyBar, StockSnapshot


class LifecycleTest(unittest.TestCase):
    def test_load_watchlist_returns_empty_for_missing_file(self):
        result = load_watchlist(Path("/tmp/does-not-exist-watchlist.csv"))

        self.assertEqual(result, [])

    def test_load_watchlist_reads_code_name_theme_and_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watchlist.csv"
            path.write_text(
                "代码,名称,核心题材,备注\n"
                "SH.600001,Alpha,AI算力,核心持仓\n",
                encoding="utf-8-sig",
            )

            result = load_watchlist(path)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].code, "SH.600001")
        self.assertEqual(result[0].name, "Alpha")
        self.assertEqual(result[0].core_theme, "AI算力")
        self.assertEqual(result[0].note, "核心持仓")

    def test_assess_lifecycle_marks_high_volume_stalling_and_relative_weakness(self):
        snapshots = [
            StockSnapshot(
                code="SH.600001",
                name="Leader",
                last_price=18.0,
                prev_close_price=18.2,
                turnover=420_000_000,
                change_rate=-1.1,
            ),
            StockSnapshot(
                code="SH.600002",
                name="Peer",
                last_price=11.0,
                prev_close_price=10.0,
                turnover=120_000_000,
                change_rate=10.0,
            ),
        ]
        history = {
            "SH.600001": [
                DailyBar(code="SH.600001", date="2026-06-%02d" % day, close=10 + day * 0.4, turnover=100_000_000)
                for day in range(1, 21)
            ]
            + [
                DailyBar(code="SH.600001", date="2026-06-21", close=20.0, high=20.5, turnover=130_000_000, change_pct=6.0),
                DailyBar(code="SH.600001", date="2026-06-22", close=19.4, high=20.2, turnover=150_000_000, change_pct=-3.0),
                DailyBar(code="SH.600001", date="2026-06-23", close=18.8, high=19.2, turnover=170_000_000, change_pct=-3.1),
                DailyBar(code="SH.600001", date="2026-06-24", close=18.0, high=18.5, turnover=420_000_000, change_pct=-1.1),
            ],
            "SH.600002": [
                DailyBar(code="SH.600002", date="2026-06-24", close=11.0, high=11.0, turnover=120_000_000, change_pct=10.0)
            ],
        }

        result = assess_lifecycle_risks(
            snapshots=snapshots,
            history_by_code=history,
            core_theme_by_code={"SH.600001": "AI算力", "SH.600002": "AI算力"},
        )

        risk = result["SH.600001"]
        self.assertEqual(risk.stage, "强转弱验证")
        self.assertGreaterEqual(risk.score, 60)
        self.assertIn("放量下跌", risk.signals)
        self.assertIn("修复失败", risk.signals)
        self.assertIn("相对题材偏弱", risk.signals)
        self.assertIn("减仓", risk.discipline)


if __name__ == "__main__":
    unittest.main()
