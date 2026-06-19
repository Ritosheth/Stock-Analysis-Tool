import unittest

from ghzw.models import ReasonEvidence, StageTag
from ghzw.reason_logic import build_reason_logic, is_low_quality_evidence


class ReasonLogicTest(unittest.TestCase):
    def test_filters_market_statistic_news(self):
        self.assertTrue(is_low_quality_evidence(ReasonEvidence(
            date="2026-06-14",
            code="SZ.000001",
            reason_type="新闻",
            summary="今日44只个股突破半年线",
        )))
        self.assertTrue(is_low_quality_evidence(ReasonEvidence(
            date="2026-06-14",
            code="SZ.000001",
            reason_type="新闻",
            summary="55只股上午收盘涨停(附股)",
        )))
        self.assertFalse(is_low_quality_evidence(ReasonEvidence(
            date="2026-06-14",
            code="SZ.000001",
            reason_type="新闻",
            summary="公司机器人控制器产品进入头部客户供应链",
        )))

    def test_build_reason_logic_prefers_clear_main_driver_and_keeps_concise_evidence(self):
        evidence = [
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="新闻",
                summary="今日44只个股突破半年线",
                source="东方财富新闻",
                published_at="2026-06-14 12:00:00",
            ),
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="龙虎榜",
                summary="机构净买入3000万元",
                source="东方财富龙虎榜",
                published_at="2026-06-14",
            ),
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="新闻",
                summary="公司机器人控制器产品进入头部客户供应链",
                source="东方财富新闻",
                published_at="2026-06-14 13:30:00",
            ),
        ]

        result = build_reason_logic(
            evidences=evidence,
            suspected_reason="疑似：机器人主线发酵，个股涨停",
            core_theme="机器人",
            theme_tier="主线",
            record_type="涨停",
            stage=StageTag(labels=["首板", "放量"], board_streak=1, is_volume_expanded=True),
            main_net_inflow=0,
        )

        self.assertEqual(result.driver_type, "产业新闻")
        self.assertIn("机器人", result.logic)
        self.assertIn("龙虎榜资金作为佐证", result.logic)
        self.assertNotIn("44只个股", result.logic)
        self.assertEqual(
            result.evidence_summary,
            "新闻：公司机器人控制器产品进入头部客户供应链；龙虎榜：机构净买入3000万元",
        )

    def test_build_reason_logic_uses_theme_when_no_quality_evidence(self):
        result = build_reason_logic(
            evidences=[],
            suspected_reason="疑似：机器人主线发酵，个股涨停",
            core_theme="机器人",
            theme_tier="主线",
            record_type="涨停",
            stage=StageTag(labels=["首板"]),
            main_net_inflow=0,
        )

        self.assertEqual(result.driver_type, "题材发酵")
        self.assertIn("暂无明确公告/新闻/龙虎榜证据", result.logic)
        self.assertEqual(result.evidence_summary, "题材：疑似：机器人主线发酵，个股涨停")


if __name__ == "__main__":
    unittest.main()
