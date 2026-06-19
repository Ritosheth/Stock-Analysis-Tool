import unittest
from datetime import date

from ghzw.cninfo_client import parse_announcement_items, parse_irm_rows, to_cninfo_code


class CninfoClientTest(unittest.TestCase):
    def test_to_cninfo_code_strips_market_prefix(self):
        self.assertEqual(to_cninfo_code("SZ.000001"), "000001")
        self.assertEqual(to_cninfo_code("SH.600001"), "600001")

    def test_parse_announcement_items_returns_reason_evidence(self):
        payload = {
            "announcements": [
                {
                    "secCode": "000001",
                    "announcementTitle": "关于签订重大合同的公告",
                    "announcementTime": 1781395200000,
                    "announcementId": "abc",
                    "orgId": "gssz0000001",
                }
            ]
        }

        result = parse_announcement_items(payload, code="SZ.000001", trade_date=date(2026, 6, 14))

        self.assertEqual(result[0].reason_type, "公告")
        self.assertEqual(result[0].summary, "关于签订重大合同的公告")
        self.assertEqual(result[0].source, "CNINFO")
        self.assertIn("announcementId=abc", result[0].url)

    def test_parse_irm_rows_uses_answer_content(self):
        payload = {
            "rows": [
                {
                    "stockCode": "000001",
                    "mainContent": "公司是否涉及机器人业务？",
                    "attachedContent": "公司已有机器人相关布局。",
                    "updateDate": 1781395200000,
                }
            ]
        }

        result = parse_irm_rows(payload, code="SZ.000001", trade_date=date(2026, 6, 14))

        self.assertEqual(result[0].reason_type, "互动易")
        self.assertIn("机器人相关布局", result[0].summary)
        self.assertEqual(result[0].source, "CNINFO互动易")


if __name__ == "__main__":
    unittest.main()
