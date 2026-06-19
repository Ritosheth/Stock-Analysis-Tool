import tempfile
import unittest
from pathlib import Path

from ghzw.cache import DailyBarCache
from ghzw.models import DailyBar


class DailyBarCacheTest(unittest.TestCase):
    def test_save_and_load_merges_bars_by_code_and_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DailyBarCache(Path(tmpdir))
            cache.save(
                "SZ.301217",
                [
                    DailyBar(code="SZ.301217", date="2026-06-11", open=10, high=11, low=9, close=10.5),
                    DailyBar(code="SZ.301217", date="2026-06-12", open=10.5, high=12, low=10, close=11.5),
                ],
            )
            cache.save(
                "SZ.301217",
                [
                    DailyBar(code="SZ.301217", date="2026-06-12", open=10.6, high=12.2, low=10.1, close=11.8),
                    DailyBar(code="SZ.301217", date="2026-06-15", open=11.8, high=12, low=11, close=11.2),
                ],
            )

            bars = cache.load("SZ.301217")

            self.assertEqual([bar.date for bar in bars], ["2026-06-11", "2026-06-12", "2026-06-15"])
            self.assertEqual(bars[1].close, 11.8)

    def test_load_recent_returns_latest_n_bars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DailyBarCache(Path(tmpdir))
            cache.save(
                "SH.600001",
                [
                    DailyBar(code="SH.600001", date="2026-06-10", close=10),
                    DailyBar(code="SH.600001", date="2026-06-11", close=11),
                    DailyBar(code="SH.600001", date="2026-06-12", close=12),
                ],
            )

            bars = cache.load_recent("SH.600001", days=2)

            self.assertEqual([bar.close for bar in bars], [11, 12])

    def test_load_recent_until_excludes_later_bars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DailyBarCache(Path(tmpdir))
            cache.save(
                "SH.600001",
                [
                    DailyBar(code="SH.600001", date="2026-06-10", close=10),
                    DailyBar(code="SH.600001", date="2026-06-11", close=11),
                    DailyBar(code="SH.600001", date="2026-06-12", close=12),
                ],
            )

            bars = cache.load_recent_until("SH.600001", days=2, end_date="2026-06-11")

            self.assertEqual([bar.date for bar in bars], ["2026-06-10", "2026-06-11"])


if __name__ == "__main__":
    unittest.main()
