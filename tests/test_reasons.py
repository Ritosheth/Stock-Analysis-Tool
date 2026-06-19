import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from ghzw.models import ReasonEvidence, StageTag
from ghzw.reasons import infer_suspected_reason, load_local_reasons, resolve_reason, resolve_reason_details


class ReasonAttributionTest(unittest.TestCase):
    def test_load_local_reasons_reads_csv_and_keeps_priority_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reasons.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["日期", "代码", "原因类型", "原因摘要", "来源", "可信度"])
                writer.writeheader()
                writer.writerow({
                    "日期": "2026-06-14",
                    "代码": "SZ.000001",
                    "原因类型": "题材",
                    "原因摘要": "机器人板块集体走强",
                    "来源": "人工维护",
                    "可信度": "中",
                })
                writer.writerow({
                    "日期": "2026-06-14",
                    "代码": "SZ.000001",
                    "原因类型": "公告",
                    "原因摘要": "拟收购资产",
                    "来源": "公司公告",
                    "可信度": "高",
                })

            result = load_local_reasons(path)

        self.assertEqual(result[0].reason_type, "公告")
        self.assertEqual(result[0].summary, "拟收购资产")

    def test_resolve_reason_prefers_local_exact_match(self):
        evidence = [
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="公告",
                summary="拟收购资产",
                source="公司公告",
                confidence="高",
            )
        ]

        result = resolve_reason(
            trade_date=date(2026, 6, 14),
            code="SZ.000001",
            local_reasons=evidence,
            suspected_reason="疑似：人工智能主线发酵，个股涨停",
        )

        self.assertEqual(result, "公告：拟收购资产")

    def test_resolve_reason_details_aggregates_distinct_evidence_by_priority(self):
        evidence = [
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="研报",
                summary="分析师维持买入评级",
                source="Futu",
                confidence="中",
                published_at="2026-06-14 09:00:00",
            ),
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="公告",
                summary="签订重大合同",
                source="CNINFO",
                confidence="高",
                published_at="2026-06-14 08:00:00",
            ),
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="龙虎榜",
                summary="机构净买入3000万元",
                source="东方财富龙虎榜",
                confidence="高",
                published_at="2026-06-14",
            ),
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="新闻",
                summary="银行板块午后拉升",
                source="东方财富新闻",
                confidence="中",
                published_at="2026-06-14 13:30:00",
            ),
        ]

        result = resolve_reason_details(
            trade_date=date(2026, 6, 14),
            code="SZ.000001",
            local_reasons=[],
            online_reasons=evidence,
            suspected_reason="疑似：人工智能主线发酵，个股涨停",
        )

        self.assertEqual(
            result.reason,
            "公告：签订重大合同；龙虎榜：机构净买入3000万元；研报：分析师维持买入评级；新闻：银行板块午后拉升",
        )
        self.assertEqual(result.source, "CNINFO、东方财富龙虎榜、Futu、东方财富新闻")
        self.assertEqual(result.evidence_time, "2026-06-14 08:00:00、2026-06-14、2026-06-14 09:00:00、2026-06-14 13:30:00")

    def test_resolve_reason_details_deduplicates_same_content(self):
        evidence = [
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="新闻",
                summary="银行板块午后拉升",
                source="东方财富新闻",
                confidence="中",
                published_at="2026-06-14 13:30:00",
            ),
            ReasonEvidence(
                date="2026-06-14",
                code="SZ.000001",
                reason_type="快讯",
                summary="银行板块午后拉升",
                source="东方财富快讯",
                confidence="中",
                published_at="2026-06-14 13:31:00",
            ),
        ]

        result = resolve_reason_details(
            trade_date=date(2026, 6, 14),
            code="SZ.000001",
            local_reasons=[],
            online_reasons=evidence,
            suspected_reason="不明",
        )

        self.assertEqual(result.reason, "快讯：银行板块午后拉升")
        self.assertEqual(result.source, "东方财富快讯")

    def test_resolve_reason_details_uses_suspected_when_no_evidence(self):
        result = resolve_reason_details(
            trade_date=date(2026, 6, 14),
            code="SZ.000001",
            local_reasons=[],
            online_reasons=[],
            suspected_reason="疑似：人工智能主线发酵，个股涨停",
        )

        self.assertEqual(result.reason, "疑似：人工智能主线发酵，个股涨停")
        self.assertEqual(result.source, "规则推断")

    def test_infer_suspected_reason_uses_theme_stage_and_flow(self):
        result = infer_suspected_reason(
            core_theme="人工智能",
            theme_tier="主线",
            record_type="涨停",
            stage=StageTag(labels=["首板", "放量"]),
            main_net_inflow=100,
        )

        self.assertEqual(result, "疑似：人工智能主线发酵，个股涨停")

    def test_infer_suspected_reason_returns_unknown_without_signal(self):
        result = infer_suspected_reason(
            core_theme="未匹配",
            theme_tier="未匹配",
            record_type="成交额Top30",
            stage=StageTag(labels=["观察"]),
            main_net_inflow=0,
        )

        self.assertEqual(result, "不明")


if __name__ == "__main__":
    unittest.main()
