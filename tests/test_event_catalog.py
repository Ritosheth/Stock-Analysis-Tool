import unittest
from datetime import date

from ghzw.event_catalog import build_daily_event_catalog
from ghzw.models import ReasonEvidence


class EventCatalogTest(unittest.TestCase):
    def test_build_daily_event_catalog_clusters_public_evidence_into_tradeable_events(self):
        evidences = [
            ReasonEvidence(
                date="2026-07-14",
                code="SH.600183",
                reason_type="公告",
                summary="中报预告同比增长117%-131%，PCB需求旺盛",
                source="公司公告",
                confidence="高",
                published_at="2026-07-13 20:10:00",
            ),
            ReasonEvidence(
                date="2026-07-14",
                code="SZ.001388",
                reason_type="新闻",
                summary="14部门发布康复辅具行动方案，提及康养机器人和脑机接口",
                source="东方财富新闻",
                confidence="中",
                published_at="2026-07-13 21:00:00",
            ),
            ReasonEvidence(
                date="2026-07-14",
                code="SZ.300164",
                reason_type="快讯",
                summary="霍尔木兹海峡风险发酵，WTI原油大涨",
                source="东方财富快讯",
                confidence="中",
                published_at="2026-07-13 22:00:00",
            ),
        ]

        events = build_daily_event_catalog(date(2026, 7, 14), evidences)
        titles = [event.event_title for event in events]

        self.assertIn("中报/业绩预告", titles)
        self.assertIn("机器人/康复辅具政策", titles)
        self.assertIn("油气/地缘冲突", titles)


if __name__ == "__main__":
    unittest.main()
