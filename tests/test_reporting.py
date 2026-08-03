import tempfile
import unittest
from datetime import date
from pathlib import Path

from ghzw.forum_sources import ForumCollection, ForumDiscussion
from ghzw.models import DailyRecord
from ghzw.reporting import build_report_context, load_recent_daily_records, render_html_report, write_html_report


class ReportingTest(unittest.TestCase):
    def test_build_context_summarizes_sectors_boards_and_trends(self):
        records = [
            _record("SH.600001", "Alpha", "半导体", "半导体-存储器", 300_000_000, "2板"),
            _record("SH.600002", "Beta", "半导体", "半导体-MCU芯片", 500_000_000, "1板"),
            _record("SH.600003", "Gamma", "机器人", "自动化设备-机器人概念", 100_000_000, "1板"),
        ]
        recent = {
            "2026-06-16": [_record("SH.600004", "Old", "机器人", "自动化设备-机器人概念", 100_000_000, "1板")],
        }

        context = build_report_context(date(2026, 6, 17), records, recent)

        self.assertEqual(context.sectors[0].name, "AI算力与国产半导体")
        self.assertEqual(context.sectors[0].subsector, "存储")
        self.assertEqual(context.sectors[0].limit_up_count, 2)
        self.assertEqual(context.sectors[0].max_board, 2)
        self.assertEqual(context.board_groups[0].label, "2板")
        self.assertIn("最近1个交易样本", context.trend_summary)

    def test_build_context_ranks_theme_research_candidates_by_heat_breadth_and_leaders(self):
        records = [
            _record("SH.600001", "Alpha", "半导体", "半导体-存储器", 3_000_000_000, "1板", volume_ratio=2.0, role="龙头"),
            _record("SH.600002", "Beta", "半导体", "半导体-MCU芯片", 2_000_000_000, "", change_pct=6, volume_ratio=1.8, role="容量核心", record_type="成交额Top30"),
            _record("SH.600003", "Gamma", "半导体", "半导体设备", 1_000_000_000, "", change_pct=3, volume_ratio=1.3, role="中军", record_type="成交额Top30"),
            _record("SH.600004", "Delta", "消费", "食品饮料", 200_000_000, "", change_pct=-1, volume_ratio=3.0, role="杂毛", record_type="成交额Top30"),
        ]

        context = build_report_context(date(2026, 6, 17), records)

        self.assertEqual(context.research_candidates[0].label, "重点研究")
        self.assertEqual(context.research_candidates[0].active_count, 3)
        self.assertEqual(context.research_candidates[0].positive_count, 3)
        self.assertIn("有龙头", context.research_candidates[0].basis)
        self.assertIn("量比放大", context.research_candidates[0].basis)

    def test_render_html_report_contains_sections_and_forum_links(self):
        discussion = ForumDiscussion(
            source="雪球",
            title="半导体涨停原因讨论",
            summary="市场讨论，未经证实",
            url="https://xueqiu.com/123",
            published_at="2026-06-17",
            query="半导体 涨停 原因",
        )
        context = build_report_context(
            date(2026, 6, 17),
            [_record("SH.600001", "Alpha", "半导体", "半导体-存储器", 300_000_000, "2板")],
            forum_collection=ForumCollection([discussion]),
        )

        html = render_html_report(context)

        self.assertIn("板块结构", html)
        self.assertIn("成交额 Top30", html)
        self.assertIn("板块研究候选", html)
        self.assertIn("题材纠偏审计", html)
        self.assertIn("连板梯队", html)
        self.assertIn("市场讨论摘要", html)
        self.assertIn("Alpha", html)
        self.assertIn("3.00亿元", html)
        self.assertIn("https://xueqiu.com/123", html)

    def test_build_context_keeps_top_30_turnover_records_for_report(self):
        records = [
            _record("SH.%06d" % index, "Stock%d" % index, "半导体", "半导体", index * 100_000_000, "1板")
            for index in range(1, 36)
        ]

        context = build_report_context(date(2026, 6, 17), records)

        self.assertEqual(len(context.top_turnover_records), 30)
        self.assertEqual(context.top_turnover_records[0].name, "Stock35")
        self.assertEqual(context.top_turnover_records[-1].name, "Stock6")

    def test_render_html_report_contains_lifecycle_watch_section(self):
        record = _record("SH.600001", "Alpha", "半导体", "半导体-存储器", 300_000_000, "2板")
        record = record.__class__(
            **{
                **record.__dict__,
                "watchlist_note": "核心持仓",
                "lifecycle_stage": "强转弱验证",
                "lifecycle_score": 68.0,
                "lifecycle_signals": "修复失败、相对题材偏弱",
                "lifecycle_discipline": "停止加仓，考虑减仓。",
            }
        )
        context = build_report_context(date(2026, 6, 17), [record])

        html = render_html_report(context)

        self.assertIn("强转弱观察", html)
        self.assertIn("强转弱验证", html)
        self.assertIn("修复失败、相对题材偏弱", html)
        self.assertIn("核心持仓", html)

    def test_render_html_report_contains_red_flag_section(self):
        record = _record("SH.603137", "恒尚节能", "并购重组", "建筑装饰", 600_000_000, "5板")
        record = record.__class__(
            **{
                **record.__dict__,
                "risk_level": "高",
                "risk_flags": "高位连板、监管/重组敏感",
                "reason_logic": "题材发酵主导：跨界收购存储模组资产。",
            }
        )
        context = build_report_context(date(2026, 6, 17), [record])

        html = render_html_report(context)

        self.assertIn("红旗与验证缺口", html)
        self.assertIn("监管/重组敏感", html)
        self.assertIn("恒尚节能", html)

    def test_render_html_report_contains_theme_reclassification_audit(self):
        record = _record("SZ.002463", "沪电股份", "PCB", "元件-PCB概念", 300_000_000, "1板")
        record = record.__class__(
            **{
                **record.__dict__,
                "raw_theme": "华为概念",
                "reclassified_theme": "PCB",
                "actual_driver": "PCB/算力硬件",
                "theme_match_level": "极低",
                "theme_mismatch_reason": "华为概念更像泛概念标签，当日主导催化转向PCB。",
            }
        )
        context = build_report_context(date(2026, 6, 17), [record])

        html = render_html_report(context)

        self.assertIn("题材纠偏审计", html)
        self.assertIn("原始题材", html)
        self.assertIn("重分类题材", html)
        self.assertIn("华为概念", html)
        self.assertIn("PCB/算力硬件", html)

    def test_render_html_report_falls_back_to_public_evidence_when_forum_empty(self):
        record = _record("SH.603986", "兆易创新", "TMT", "半导体-MCU芯片/存储器", 300_000_000, "1板")
        record = record.__class__(
            **{
                **record.__dict__,
                "reason_type": "龙虎榜：普通席位买入",
                "reason_source": "东方财富龙虎榜",
                "evidence_time": "2026-06-17",
            }
        )
        context = build_report_context(
            date(2026, 6, 17),
            [record],
            forum_collection=ForumCollection([], "论坛线索未获取"),
        )

        html = render_html_report(context)

        self.assertIn("雪球/论坛未直接获取", html)
        self.assertIn("东方财富龙虎榜", html)
        self.assertIn("龙虎榜：普通席位买入", html)

    def test_trend_uses_market_sentiment_board_height_when_old_csv_lacks_board_column(self):
        old_record = _record("SH.600001", "Alpha", "半导体", "半导体", 300_000_000, "")
        old_record = old_record.__class__(
            **{**old_record.__dict__, "market_sentiment": "涨停10/跌停0/上涨60%/连板高4/昨板无数据"}
        )

        context = build_report_context(date(2026, 6, 17), [], {"2026-06-16": [old_record]})

        self.assertEqual(context.trend_points[0].max_board, 4)

    def test_write_html_report_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"

            write_html_report("<html>ok</html>", path)

            self.assertEqual(path.read_text(encoding="utf-8"), "<html>ok</html>")

    def test_load_recent_daily_records_skips_current_date_and_reads_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "2026-06-16-daily-review.csv").write_text(
                "日期,代码,名称,类型,涨停板数,收盘价,昨收,涨幅,成交额(亿元),换手率,量比,所属行业,所属概念,"
                "核心题材,市场阶段,市场情绪,题材强度排名,题材层级,个股地位,角色分,角色依据,阶段,次日计划,"
                "资金流-净流入,资金流-主力净流入,上涨原因,原因来源,证据时间,一句话复盘\n"
                "2026-06-16,SH.600001,Alpha,涨停,1板,11,10,10,3,5,1,半导体-存储器,存储器,"
                "半导体,上升,情绪,1,主线,龙头,40,依据,首板,观察,0,0,原因,来源,时间,复盘\n",
                encoding="utf-8-sig",
            )
            (output_dir / "2026-06-17-daily-review.csv").write_text("日期,代码\n", encoding="utf-8-sig")

            records_by_date, skipped = load_recent_daily_records(output_dir, date(2026, 6, 17))

        self.assertEqual(skipped, 0)
        self.assertEqual(list(records_by_date.keys()), ["2026-06-16"])
        self.assertEqual(records_by_date["2026-06-16"][0].turnover, 300_000_000)


def _record(
    code,
    name,
    core_theme,
    industries,
    turnover,
    boards,
    change_pct=10,
    volume_ratio=1,
    role="龙头",
    record_type="涨停",
):
    return DailyRecord(
        date="2026-06-17",
        code=code,
        name=name,
        record_type=record_type,
        close_price=11,
        prev_close_price=10,
        change_pct=change_pct,
        turnover=turnover,
        turnover_rate=5,
        volume_ratio=volume_ratio,
        industries=industries,
        concepts=core_theme,
        market_cycle="上升",
        theme_rank=1,
        theme_tier="主线",
        role=role,
        stage="首板",
        next_action="观察验证",
        net_inflow=0,
        main_net_inflow=0,
        reason_type="不明",
        review="测试",
        core_theme=core_theme,
        market_sentiment="涨停3/跌停0/上涨60%/连板高2/昨板无数据",
        limit_up_boards=boards,
    )


if __name__ == "__main__":
    unittest.main()
