import unittest
from datetime import date

from ghzw.futu_client import collect_futu_reason_evidence


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows
        self.empty = not bool(rows)

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


class FakeFutuEvidenceContext:
    def get_research_rating_summary(self, code, num=None):
        return 0, FakeFrame([
            {"update_time_str": "2026-06-14 09:00:00", "rating": "买入", "target_price": 15.5}
        ])

    def get_corporate_actions_buybacks(self, code, num=None):
        return 0, {
            "a_buy_back_list": FakeFrame([
                {"publ_date_str": "2026-06-14", "advance_date_str": "2026-06-13", "buy_back_money": 100000000}
            ])
        }

    def get_shareholders_holding_changes(self, code, num=None):
        return 0, FakeFrame([
            {"holding_date_str": "2026-06-14", "name": "重要股东", "share_change_num": 1000000}
        ])


class FutuEvidenceTest(unittest.TestCase):
    def test_collect_futu_reason_evidence_normalizes_structured_events(self):
        result = collect_futu_reason_evidence(
            ctx=FakeFutuEvidenceContext(),
            trade_date=date(2026, 6, 14),
            codes=["SZ.000001"],
        )

        reason_types = [item.reason_type for item in result]
        self.assertIn("研报", reason_types)
        self.assertIn("公司行动", reason_types)
        self.assertIn("股东变动", reason_types)
        self.assertTrue(all(item.source == "Futu" for item in result))
        self.assertTrue(all(item.code == "SZ.000001" for item in result))


if __name__ == "__main__":
    unittest.main()
