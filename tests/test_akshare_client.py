import unittest

from ghzw.akshare_client import normalize_akshare_hist, normalize_limit_up_pool


class AkshareClientTest(unittest.TestCase):
    def test_normalize_akshare_hist_maps_chinese_columns_to_daily_bars(self):
        rows = [
            {
                "日期": "2026-06-12",
                "开盘": 134.94,
                "最高": 148.0,
                "最低": 133.1,
                "收盘": 141.8,
                "成交量": 46106164,
                "成交额": 6496831675.55,
                "换手率": 55.4,
                "涨跌幅": 10.8,
            }
        ]

        bars = normalize_akshare_hist("SZ.301217", rows)

        self.assertEqual(bars[0].code, "SZ.301217")
        self.assertEqual(bars[0].date, "2026-06-12")
        self.assertEqual(bars[0].close, 141.8)
        self.assertEqual(bars[0].change_pct, 10.8)

    def test_normalize_limit_up_pool_maps_rows_to_snapshots(self):
        rows = [
            {
                "代码": "600001",
                "名称": "历史涨停股",
                "最新价": 11,
                "涨跌幅": 10,
                "成交额": 1000,
                "换手率": 5,
            },
            {
                "代码": "830001",
                "名称": "北交所样本",
                "最新价": 8,
                "涨跌幅": 30,
                "成交额": 500,
                "换手率": 3,
            },
        ]

        snapshots = normalize_limit_up_pool(rows, allowed_codes={"SH.600001"})

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].code, "SH.600001")
        self.assertEqual(snapshots[0].name, "历史涨停股")
        self.assertEqual(snapshots[0].prev_close_price, 10)
        self.assertEqual(snapshots[0].change_pct, 10)


if __name__ == "__main__":
    unittest.main()
