import unittest
import tempfile
from datetime import date
from pathlib import Path

from ghzw.models import CapitalFlow, DailyBar, PlateMembership, ReasonEvidence, StockSnapshot
from ghzw.pipeline import build_daily_records, run_daily_pipeline, has_enough_historical_snapshot_coverage


class PipelineTest(unittest.TestCase):
    def test_build_daily_records_merges_limit_up_turnover_theme_stage_and_flow(self):
        snapshots = [
            StockSnapshot(
                code="SH.600001",
                name="Alpha",
                last_price=10.98,
                prev_close_price=10,
                turnover=500,
                turnover_rate=12.3,
                volume_ratio=2.5,
            ),
            StockSnapshot(
                code="SH.600002",
                name="Beta",
                last_price=10.4,
                prev_close_price=10,
                turnover=900,
                turnover_rate=5.0,
                volume_ratio=1.2,
            ),
        ]
        memberships = {
            "SH.600001": [
                PlateMembership(code="HY001", name="半导体", plate_type="INDUSTRY"),
                PlateMembership(code="GN000", name="融资融券", plate_type="CONCEPT"),
                PlateMembership(code="GN001", name="存储器", plate_type="CONCEPT"),
                PlateMembership(code="GN002", name="MCU芯片", plate_type="CONCEPT"),
                PlateMembership(code="GN003", name="人工智能", plate_type="CONCEPT"),
            ],
            "SH.600002": [PlateMembership(code="HY002", name="银行", plate_type="INDUSTRY")],
        }
        history = {
            "SH.600001": [
                DailyBar(code="SH.600001", date="2026-01-0%d" % day, close=9 + day * 0.1, turnover=100)
                for day in range(1, 6)
            ] + [
                DailyBar(code="SH.600001", date="2026-01-06", close=11, turnover=250, change_pct=10),
            ],
            "SH.600002": [DailyBar(code="SH.600002", date="2026-01-02", close=10.4, turnover=900, change_pct=4)],
        }
        flows = {
            "SH.600001": CapitalFlow(code="SH.600001", net_inflow=1000, main_net_inflow=600),
            "SH.600002": CapitalFlow(code="SH.600002", net_inflow=-100, main_net_inflow=-60),
        }

        records = build_daily_records(
            trade_date=date(2026, 1, 2),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code=history,
            capital_flow_by_code=flows,
            turnover_limit=1,
            online_reasons=[
                ReasonEvidence(
                    date="2026-01-02",
                    code="SH.600001",
                    reason_type="公告",
                    summary="签订重大合同",
                    source="CNINFO",
                    confidence="高",
                    published_at="2026-01-02 08:00:00",
                )
            ],
        )

        by_code = {record.code: record for record in records}
        self.assertEqual(by_code["SH.600001"].record_type, "涨停")
        self.assertEqual(by_code["SH.600001"].market_cycle, "分歧")
        self.assertEqual(by_code["SH.600001"].theme_tier, "支线")
        self.assertEqual(by_code["SH.600001"].industries, "半导体-存储器/MCU芯片")
        self.assertEqual(by_code["SH.600001"].concepts, "存储器、MCU芯片、人工智能")
        self.assertEqual(by_code["SH.600001"].core_theme, "存储器")
        self.assertEqual(by_code["SH.600001"].limit_up_boards, "1板")
        self.assertEqual(by_code["SH.600001"].as_dict()["涨停板数"], "1板")
        self.assertEqual(by_code["SH.600001"].as_dict()["成交额(亿元)"], 0.0)
        self.assertIn("涨停", by_code["SH.600001"].market_sentiment)
        self.assertGreater(by_code["SH.600001"].role_score, 0)
        self.assertTrue(by_code["SH.600001"].role_basis)
        self.assertEqual(by_code["SH.600001"].net_inflow, 1000)
        self.assertIn("首板", by_code["SH.600001"].stage)
        self.assertEqual(by_code["SH.600001"].reason_type, "公告：签订重大合同")
        self.assertIn("上涨逻辑", by_code["SH.600001"].as_dict())
        self.assertIn("公告催化", by_code["SH.600001"].as_dict()["上涨逻辑"])
        self.assertEqual(by_code["SH.600001"].reason_source, "CNINFO")
        self.assertEqual(by_code["SH.600001"].evidence_time, "2026-01-02 08:00:00")
        self.assertIn(by_code["SH.600001"].next_action, {"观察验证", "轻仓试错", "核心分歧低吸"})
        self.assertEqual(by_code["SH.600002"].record_type, "成交额Top1")

    def test_run_daily_pipeline_uses_historical_bars_for_past_trade_date(self):
        client = _FakeClient()
        history_provider = _FakeHistoryProvider(
            {
                "SH.600001": [
                    DailyBar(code="SH.600001", date="2026-01-01", close=10, turnover=100, change_pct=0),
                    DailyBar(code="SH.600001", date="2026-01-02", close=10.2, turnover=100, change_pct=2),
                ],
                "SH.600002": [
                    DailyBar(code="SH.600002", date="2026-01-01", close=10, turnover=100, change_pct=0),
                    DailyBar(code="SH.600002", date="2026-01-02", close=11, turnover=900, change_pct=10),
                ],
            }
        )

        result = run_daily_pipeline(
            client=client,
            trade_date=date(2026, 1, 2),
            output_dir=_NoWriteOutputDir(),
            turnover_limit=1,
            history_provider=history_provider,
            evidence_source="none",
        )

        self.assertEqual([record.code for record in result.records], ["SH.600002"])
        self.assertEqual(result.records[0].date, "2026-01-02")
        self.assertEqual(result.records[0].close_price, 11)
        self.assertEqual(result.records[0].prev_close_price, 10)
        self.assertEqual(result.records[0].change_pct, 10)
        self.assertIsNone(client.capital_flow_codes)

    def test_run_daily_pipeline_can_generate_html_report(self):
        client = _FakeClient()
        history_provider = _FakeHistoryProvider(
            {
                "SH.600001": [
                    DailyBar(code="SH.600001", date="2026-01-01", close=10, turnover=100, change_pct=0),
                    DailyBar(code="SH.600001", date="2026-01-02", close=11, turnover=300, change_pct=10),
                ],
                "SH.600002": [
                    DailyBar(code="SH.600002", date="2026-01-01", close=10, turnover=100, change_pct=0),
                    DailyBar(code="SH.600002", date="2026-01-02", close=10.5, turnover=900, change_pct=5),
                ],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = run_daily_pipeline(
                client=client,
                trade_date=date(2026, 1, 2),
                output_dir=Path(tmp),
                turnover_limit=1,
                history_provider=history_provider,
                evidence_source="none",
                generate_html_report=True,
                forum_search_enabled=False,
            )

            self.assertTrue(result.report_path.exists())
            html = result.report_path.read_text(encoding="utf-8")

        self.assertIn("板块结构", html)
        self.assertIn("市场讨论摘要", html)
        self.assertEqual(result.report_warning, "未启用论坛检索")

    def test_low_historical_snapshot_coverage_can_fall_back_to_limit_up_pool(self):
        client = _LargeFakeClient()
        result = run_daily_pipeline(
            client=client,
            trade_date=date(2026, 6, 9),
            output_dir=_NoWriteOutputDir(),
            turnover_limit=30,
            history_provider=_FakeHistoryProvider({}),
            historical_snapshot_provider=_FakeLimitUpSnapshotProvider(),
            evidence_source="none",
        )

        self.assertEqual([record.code for record in result.records], ["SH.600001"])
        self.assertEqual(result.records[0].record_type, "涨停")
        self.assertEqual(result.records[0].name, "历史涨停股")
        self.assertIn("历史轻量模式", result.warning)

    def test_historical_snapshot_coverage_threshold(self):
        self.assertFalse(has_enough_historical_snapshot_coverage(snapshot_count=7, stock_pool_count=5000))
        self.assertTrue(has_enough_historical_snapshot_coverage(snapshot_count=4500, stock_pool_count=5000))

    def test_limit_up_board_label_falls_back_to_news_consecutive_board_text(self):
        snapshots = [
            StockSnapshot(
                code="SH.600003",
                name="Gamma",
                last_price=10.98,
                prev_close_price=10,
                turnover=100_000_000,
            )
        ]
        memberships = {
            "SH.600003": [
                PlateMembership(code="HY003", name="工业金属", plate_type="INDUSTRY"),
                PlateMembership(code="GN003", name="铝概念", plate_type="CONCEPT"),
            ]
        }

        records = build_daily_records(
            trade_date=date(2026, 6, 17),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={"SH.600003": []},
            capital_flow_by_code={"SH.600003": CapitalFlow(code="SH.600003")},
            turnover_limit=0,
            online_reasons=[
                ReasonEvidence(
                    date="2026-06-17",
                    code="SH.600003",
                    reason_type="新闻",
                    summary="3连板Gamma：生产经营正常",
                    source="东方财富新闻",
                    published_at="2026-06-17 17:00:00",
                )
            ],
        )

        self.assertEqual(records[0].limit_up_boards, "3板")
        self.assertEqual(records[0].industries, "工业金属-铝概念")


class _FakeClient:
    def __init__(self):
        self.capital_flow_codes = None

    def get_stock_pool(self):
        return ["SH.600001", "SH.600002"]

    def get_snapshots(self, codes):
        return [
            StockSnapshot(code="SH.600001", name="CurrentLeader", last_price=11, prev_close_price=10, turnover=1000),
            StockSnapshot(code="SH.600002", name="HistoricalLeader", last_price=10.1, prev_close_price=10, turnover=10),
        ]

    def get_owner_plates(self, codes):
        return {code: [PlateMembership(code="GN001", name="人工智能", plate_type="CONCEPT")] for code in codes}

    def get_capital_flows(self, codes):
        self.capital_flow_codes = list(codes)
        return {code: CapitalFlow(code=code, net_inflow=999, main_net_inflow=999) for code in codes}


class _LargeFakeClient(_FakeClient):
    def get_stock_pool(self):
        return ["SH.%06d" % index for index in range(1, 601)]

    def get_snapshots(self, codes):
        return [StockSnapshot(code=code, name=code, last_price=10, prev_close_price=10) for code in codes]


class _FakeLimitUpSnapshotProvider:
    def get_limit_up_snapshots(self, trade_date, allowed_codes):
        return [
            StockSnapshot(
                code="SH.600001",
                name="历史涨停股",
                last_price=11,
                prev_close_price=10,
                turnover=1000,
                turnover_rate=5,
                change_rate=10,
            )
        ]


class _FakeHistoryProvider:
    def __init__(self, bars_by_code):
        self.bars_by_code = bars_by_code

    def get_history(self, code, days=120, end=None):
        bars = [bar for bar in self.bars_by_code.get(code, []) if end is None or bar.date <= end.isoformat()]
        return bars[-days:]


class _NoWriteOutputDir:
    def __truediv__(self, name):
        return _NoWritePath(name)


class _NoWritePath:
    def __init__(self, name):
        self.name = name
        self.parent = self

    def mkdir(self, parents=False, exist_ok=False):
        pass

    def open(self, *args, **kwargs):
        from io import StringIO

        return StringIO()


if __name__ == "__main__":
    unittest.main()
