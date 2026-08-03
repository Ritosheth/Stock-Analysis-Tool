import unittest
import tempfile
from datetime import date
from pathlib import Path

from ghzw.event_catalog import build_daily_event_catalog
from ghzw.lifecycle import WatchlistEntry
from ghzw.models import CapitalFlow, DailyBar, PlateMembership, ReasonEvidence, StockSnapshot
from ghzw.pipeline import build_daily_records, run_daily_pipeline, has_enough_historical_snapshot_coverage
from ghzw.theme_hub import FormalThemeClassification


class PipelineTest(unittest.TestCase):
    def test_build_daily_records_uses_local_theme_hub_for_all_four_classification_fields(self):
        snapshots = [
            StockSnapshot(code="SH.600103", name="主题库分类股", last_price=11, prev_close_price=10, turnover=100)
        ]
        memberships = {
            "SH.600103": [
                PlateMembership(code="HY103", name="Futu行业", plate_type="INDUSTRY"),
                PlateMembership(code="GN103", name="Futu概念", plate_type="CONCEPT"),
            ]
        }

        record = build_daily_records(
            trade_date=date(2026, 1, 2),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={},
            capital_flow_by_code={},
            turnover_limit=1,
            formal_classifications_by_code={
                "SH.600103": FormalThemeClassification(
                    industries=["主题库行业"], concepts=["主题库概念", "主题库细分"]
                )
            },
        )[0]

        self.assertEqual(record.industries, "主题库行业")
        self.assertEqual(record.concepts, "主题库概念、主题库细分")
        self.assertEqual(record.raw_theme, "主题库概念")
        self.assertEqual(record.core_theme, "主题库概念")
        self.assertEqual(record.theme_classification_source, "A股主题库")

    def test_build_daily_records_prefers_formal_theme_library_and_marks_fallback(self):
        snapshots = [
            StockSnapshot(code="SH.600101", name="正式分类股", last_price=11, prev_close_price=10, turnover=100),
            StockSnapshot(code="SH.600102", name="待归类股", last_price=11, prev_close_price=10, turnover=90),
        ]
        memberships = {
            "SH.600101": [PlateMembership(code="GN101", name="机器人概念", plate_type="CONCEPT")],
            "SH.600102": [PlateMembership(code="GN102", name="PCB概念", plate_type="CONCEPT")],
        }
        records = build_daily_records(
            trade_date=date(2026, 1, 2),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={},
            capital_flow_by_code={},
            turnover_limit=2,
            formal_themes_by_code={"SH.600101": ["商业航天"]},
        )

        by_code = {record.code: record for record in records}
        self.assertEqual(by_code["SH.600101"].core_theme, "商业航天")
        self.assertEqual(by_code["SH.600101"].theme_classification_source, "A股主题库")
        self.assertEqual(by_code["SH.600102"].theme_classification_source, "Futu分类（A股主题库无相应分类）")
        self.assertEqual(by_code["SH.600102"].as_dict()["题材分类来源"], "Futu分类（A股主题库无相应分类）")

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
        self.assertIn("红旗等级", by_code["SH.600001"].as_dict())
        self.assertIn("红旗信号", by_code["SH.600001"].as_dict())
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
        self.assertIn("红旗与验证缺口", html)
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

    def test_build_daily_records_uses_business_fit_for_theme_and_role_groups(self):
        snapshots = [
            StockSnapshot(
                code="SZ.001270",
                name="铖昌科技",
                last_price=11,
                prev_close_price=10,
                turnover=2_000_000_000,
                turnover_rate=7.3,
                volume_ratio=1.8,
            ),
            StockSnapshot(
                code="SH.600118",
                name="中国卫星",
                last_price=11,
                prev_close_price=10,
                turnover=4_000_000_000,
                turnover_rate=12.9,
                volume_ratio=1.1,
                market_val=80_000_000_000,
            ),
            StockSnapshot(
                code="SH.688409",
                name="富创精密",
                last_price=12,
                prev_close_price=10,
                turnover=3_000_000_000,
                turnover_rate=3.9,
                volume_ratio=1.3,
            ),
        ]
        memberships = {
            "SZ.001270": [
                PlateMembership(code="HY001", name="军工电子Ⅱ", plate_type="INDUSTRY"),
                PlateMembership(code="GN001", name="半导体", plate_type="CONCEPT"),
                PlateMembership(code="GN002", name="商业航天", plate_type="CONCEPT"),
                PlateMembership(code="GN003", name="卫星互联网", plate_type="CONCEPT"),
            ],
            "SH.600118": [
                PlateMembership(code="HY002", name="航天装备Ⅱ", plate_type="INDUSTRY"),
                PlateMembership(code="GN001", name="半导体", plate_type="CONCEPT"),
                PlateMembership(code="GN002", name="商业航天", plate_type="CONCEPT"),
                PlateMembership(code="GN003", name="卫星互联网", plate_type="CONCEPT"),
            ],
            "SH.688409": [
                PlateMembership(code="HY003", name="半导体", plate_type="INDUSTRY"),
                PlateMembership(code="GN001", name="半导体", plate_type="CONCEPT"),
                PlateMembership(code="GN004", name="半导体设备概念", plate_type="CONCEPT"),
            ],
        }

        records = build_daily_records(
            trade_date=date(2026, 6, 28),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={
                "SZ.001270": [DailyBar(code="SZ.001270", date="2026-06-28", close=11, change_pct=10)],
                "SH.600118": [DailyBar(code="SH.600118", date="2026-06-28", close=11, change_pct=10)],
                "SH.688409": [DailyBar(code="SH.688409", date="2026-06-28", close=12, change_pct=20)],
            },
            capital_flow_by_code={snapshot.code: CapitalFlow(code=snapshot.code) for snapshot in snapshots},
            turnover_limit=0,
        )

        by_code = {record.code: record for record in records}
        self.assertEqual(by_code["SZ.001270"].core_theme, "商业航天")
        self.assertEqual(by_code["SH.600118"].core_theme, "商业航天")
        self.assertEqual(by_code["SH.688409"].core_theme, "半导体设备概念")
        self.assertEqual(by_code["SZ.001270"].role, "龙头")
        self.assertEqual(by_code["SH.600118"].role, "容量核心")

    def test_build_daily_records_reclassifies_generic_label_to_daily_event_driver(self):
        snapshots = [
            StockSnapshot(
                code="SZ.002463",
                name="沪电股份",
                last_price=33,
                prev_close_price=30,
                turnover=5_000_000_000,
                turnover_rate=8.5,
                volume_ratio=1.9,
            )
        ]
        memberships = {
            "SZ.002463": [
                PlateMembership(code="HY001", name="元件", plate_type="INDUSTRY"),
                PlateMembership(code="GN001", name="华为概念", plate_type="CONCEPT"),
            ]
        }
        reasons = [
            ReasonEvidence(
                date="2026-07-14",
                code="SZ.002463",
                reason_type="公告",
                summary="中报预告同比增长68%-78%，PCB产品需求持续改善",
                source="公司公告",
                confidence="高",
                published_at="2026-07-13 20:10:00",
            )
        ]

        records = build_daily_records(
            trade_date=date(2026, 7, 14),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={"SZ.002463": [DailyBar(code="SZ.002463", date="2026-07-14", close=33, change_pct=10)]},
            capital_flow_by_code={"SZ.002463": CapitalFlow(code="SZ.002463")},
            turnover_limit=0,
            online_reasons=reasons,
            daily_events=build_daily_event_catalog(date(2026, 7, 14), reasons),
        )

        record = records[0]
        self.assertEqual(record.raw_theme, "华为概念")
        self.assertEqual(record.reclassified_theme, "PCB")
        self.assertIn(record.actual_driver, {"PCB/算力硬件", "中报/业绩预告（PCB/算力硬件）"})
        self.assertIn(record.theme_match_level, {"低", "极低"})
        self.assertIn("泛概念标签", record.theme_mismatch_reason)

    def test_build_daily_records_can_reclassify_robot_label_to_oil_from_business_context(self):
        snapshots = [
            StockSnapshot(
                code="SH.603619",
                name="中曼石油",
                last_price=12.1,
                prev_close_price=11,
                turnover=2_000_000_000,
                turnover_rate=9.8,
                volume_ratio=1.6,
            )
        ]
        memberships = {
            "SH.603619": [
                PlateMembership(code="HY001", name="油服工程", plate_type="INDUSTRY"),
                PlateMembership(code="GN001", name="机器人概念", plate_type="CONCEPT"),
                PlateMembership(code="GN002", name="油气", plate_type="CONCEPT"),
                PlateMembership(code="GN003", name="油气设备服务", plate_type="CONCEPT"),
            ]
        }

        records = build_daily_records(
            trade_date=date(2026, 7, 14),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={"SH.603619": [DailyBar(code="SH.603619", date="2026-07-14", close=12.1, change_pct=10)]},
            capital_flow_by_code={"SH.603619": CapitalFlow(code="SH.603619")},
            turnover_limit=0,
        )

        record = records[0]
        self.assertEqual(record.reclassified_theme, "油气")
        self.assertIn("油气/地缘冲突", record.actual_driver)
        if record.raw_theme == "机器人":
            self.assertEqual(record.theme_match_level, "极低")
            self.assertIn("机器人仅概念标签", record.theme_mismatch_reason)

    def test_build_daily_records_marks_ipo_first_day_as_independent_leader(self):
        snapshots = [
            StockSnapshot(
                code="SZ.001399",
                name="N惠科股份",
                last_price=42,
                prev_close_price=10.12,
                turnover=13_000_000_000,
                turnover_rate=65.9,
                change_rate=315.02,
            )
        ]

        records = build_daily_records(
            trade_date=date(2026, 6, 28),
            snapshots=snapshots,
            memberships_by_code={
                "SZ.001399": [
                    PlateMembership(code="HY001", name="光学光电子", plate_type="INDUSTRY"),
                    PlateMembership(code="GN001", name="消费电子产业", plate_type="CONCEPT"),
                    PlateMembership(code="GN002", name="上市首五日", plate_type="CONCEPT"),
                ]
            },
            history_by_code={"SZ.001399": [DailyBar(code="SZ.001399", date="2026-06-28", close=42, change_pct=315.02)]},
            capital_flow_by_code={"SZ.001399": CapitalFlow(code="SZ.001399")},
            turnover_limit=0,
        )

        self.assertEqual(records[0].role, "IPO首日龙头")
        self.assertIn("新股首日", records[0].role_basis)

    def test_build_daily_records_includes_watchlist_stock_and_lifecycle_fields(self):
        snapshots = [
            StockSnapshot(code="SH.600010", name="Limit", last_price=11, prev_close_price=10, turnover=500, change_rate=10),
            StockSnapshot(code="SH.600011", name="Watch", last_price=18, prev_close_price=18.5, turnover=900, change_rate=-2.7),
            StockSnapshot(code="SH.600012", name="Peer", last_price=11, prev_close_price=10, turnover=800, change_rate=10),
        ]
        memberships = {
            "SH.600010": [PlateMembership(code="GN001", name="AI算力", plate_type="CONCEPT")],
            "SH.600011": [PlateMembership(code="GN001", name="AI算力", plate_type="CONCEPT")],
            "SH.600012": [PlateMembership(code="GN001", name="AI算力", plate_type="CONCEPT")],
        }
        watch_history = [
            DailyBar(code="SH.600011", date="2026-06-%02d" % day, close=10 + day * 0.4, turnover=100_000_000)
            for day in range(1, 21)
        ] + [
            DailyBar(code="SH.600011", date="2026-06-21", close=20, high=20.5, turnover=130_000_000),
            DailyBar(code="SH.600011", date="2026-06-22", close=19.4, high=20.0, turnover=150_000_000),
            DailyBar(code="SH.600011", date="2026-06-23", close=18.8, high=19.1, turnover=160_000_000),
            DailyBar(code="SH.600011", date="2026-06-24", close=18.0, high=18.4, turnover=420_000_000, change_pct=-2.7),
        ]

        records = build_daily_records(
            trade_date=date(2026, 6, 24),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={
                "SH.600010": [DailyBar(code="SH.600010", date="2026-06-24", close=11, change_pct=10)],
                "SH.600011": watch_history,
                "SH.600012": [DailyBar(code="SH.600012", date="2026-06-24", close=11, change_pct=10)],
            },
            capital_flow_by_code={code: CapitalFlow(code=code) for code in ["SH.600010", "SH.600011", "SH.600012"]},
            turnover_limit=1,
            watchlist_entries=[WatchlistEntry(code="SH.600011", note="核心持仓")],
        )

        by_code = {record.code: record for record in records}
        self.assertIn("SH.600011", by_code)
        self.assertEqual(by_code["SH.600011"].record_type, "观察名单")
        self.assertEqual(by_code["SH.600011"].watchlist_note, "核心持仓")
        self.assertIn(by_code["SH.600011"].lifecycle_stage, {"强转弱验证", "趋势破坏"})
        self.assertIn("相对题材偏弱", by_code["SH.600011"].lifecycle_signals)


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
