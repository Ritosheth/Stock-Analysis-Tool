import unittest

from ghzw.tushare_client import is_tushare_permission_error, normalize_tushare_daily, to_tushare_code


class TushareClientTest(unittest.TestCase):
    def test_to_tushare_code_converts_futu_a_share_code(self):
        self.assertEqual(to_tushare_code("SZ.301217"), "301217.SZ")
        self.assertEqual(to_tushare_code("SH.688163"), "688163.SH")

    def test_normalize_tushare_daily_maps_daily_fields_to_bars(self):
        rows = [
            {
                "ts_code": "301217.SZ",
                "trade_date": "20260612",
                "open": 134.94,
                "high": 148.0,
                "low": 133.1,
                "close": 141.8,
                "vol": 461061.64,
                "amount": 6496831.67555,
                "pct_chg": 10.8,
            }
        ]

        bars = normalize_tushare_daily("SZ.301217", rows)

        self.assertEqual(bars[0].code, "SZ.301217")
        self.assertEqual(bars[0].date, "2026-06-12")
        self.assertEqual(bars[0].volume, 46106164)
        self.assertEqual(bars[0].turnover, 6496831675.55)
        self.assertEqual(bars[0].change_pct, 10.8)

    def test_detects_daily_permission_error(self):
        self.assertTrue(is_tushare_permission_error("抱歉，您没有接口(daily)访问权限"))
        self.assertFalse(is_tushare_permission_error("网络超时"))


if __name__ == "__main__":
    unittest.main()
