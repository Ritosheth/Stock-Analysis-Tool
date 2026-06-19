import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from ghzw.models import DailyBar, DailyRecord
from ghzw.validation import read_daily_records_csv, validate_next_day


class ValidationTest(unittest.TestCase):
    def test_validate_next_day_calculates_returns_and_verdict(self):
        record = DailyRecord(
            date="2026-06-12",
            code="SZ.301217",
            name="铜冠铜箔",
            record_type="涨停",
            close_price=141.8,
            prev_close_price=127.98,
            change_pct=10.8,
            turnover=6496831675.55,
            turnover_rate=55.4,
            volume_ratio=2.2,
            industries="电子",
            concepts="铜箔",
            market_cycle="上升",
            theme_rank=1,
            theme_tier="主线",
            role="容量核心",
            stage="首板",
            next_action="转强确认加仓",
            net_inflow=100,
            main_net_inflow=50,
            reason_type="不明",
            review="测试",
        )
        next_bar = DailyBar(
            code="SZ.301217",
            date="2026-06-15",
            open=143.0,
            high=150.0,
            low=140.0,
            close=148.0,
        )

        result = validate_next_day([record], {"SZ.301217": next_bar})[0]

        self.assertEqual(result.code, "SZ.301217")
        self.assertEqual(result.action_verdict, "有效")
        self.assertEqual(round(result.max_gain_pct, 2), 5.78)
        self.assertEqual(round(result.close_return_pct, 2), 4.37)

    def test_read_daily_records_csv_converts_new_turnover_yi_header_to_yuan(self):
        csv_text = (
            "日期,代码,名称,类型,涨停板数,收盘价,昨收,涨幅,成交额(亿元),换手率,量比,所属行业,所属概念,"
            "核心题材,市场阶段,市场情绪,题材强度排名,题材层级,个股地位,角色分,角色依据,阶段,次日计划,"
            "资金流-净流入,资金流-主力净流入,上涨逻辑,驱动类型,上涨原因,原因来源,证据时间,一句话复盘\n"
            "2026-06-17,SH.600001,Alpha,涨停,2板,11,10,10,12.35,8,1.2,半导体-存储器,存储器,"
            "存储器,上升,涨停1/跌停0/上涨60%/连板高2/昨板无数据,1,主线,龙头,40,连板2,连板,观察验证,"
            "100,50,逻辑,题材发酵,原因,规则推断,2026-06-17,复盘\n"
        )

        with patch("pathlib.Path.open", mock_open(read_data=csv_text)):
            records = read_daily_records_csv(Path("daily.csv"))

        self.assertEqual(records[0].turnover, 1_235_000_000)
        self.assertEqual(records[0].limit_up_boards, "2板")


if __name__ == "__main__":
    unittest.main()
