import unittest
from datetime import date

from ghzw.eastmoney_client import parse_billboard_payload, parse_news_payload


class EastmoneyEvidenceTest(unittest.TestCase):
    def test_parse_billboard_payload_returns_lhb_evidence(self):
        payload = {
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": "000001",
                        "TRADE_DATE": "2026-06-14 00:00:00",
                        "EXPLAIN": "日涨幅偏离值达到7%的前5只证券",
                        "BILLBOARD_NET_AMT": 32000000,
                        "BILLBOARD_BUY_AMT": 88000000,
                        "BILLBOARD_SELL_AMT": 56000000,
                    }
                ]
            }
        }

        result = parse_billboard_payload(payload, {"SZ.000001"}, date(2026, 6, 14))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].code, "SZ.000001")
        self.assertEqual(result[0].reason_type, "龙虎榜")
        self.assertIn("日涨幅偏离值达到7%", result[0].summary)
        self.assertIn("净买入3200.00万元", result[0].summary)
        self.assertEqual(result[0].source, "东方财富龙虎榜")
        self.assertEqual(result[0].confidence, "高")

    def test_parse_news_payload_returns_news_and_flash_evidence(self):
        payload = {
            "result": {
                "data": [
                    {
                        "title": "平安银行午后直线拉升",
                        "summary": "银行板块异动",
                        "showTime": "2026-06-14 13:30:00",
                        "url": "https://finance.example/news/1",
                    },
                    {
                        "title": "快讯：平安银行触及涨停",
                        "content": "成交额明显放大",
                        "publishTime": "2026-06-14 14:10:00",
                    },
                    {
                        "title": "平安银行昨日公告",
                        "showTime": "2026-06-13 18:00:00",
                    },
                ]
            }
        }

        result = parse_news_payload(payload, "SZ.000001", "平安银行", date(2026, 6, 14))

        self.assertEqual([item.reason_type for item in result], ["新闻", "快讯"])
        self.assertEqual(result[0].summary, "平安银行午后直线拉升：银行板块异动")
        self.assertEqual(result[0].source, "东方财富新闻")
        self.assertEqual(result[0].url, "https://finance.example/news/1")
        self.assertEqual(result[1].source, "东方财富快讯")


if __name__ == "__main__":
    unittest.main()
