import unittest

from ghzw.models import DailyRecord


class DailyRecordModelTest(unittest.TestCase):
    def test_as_dict_outputs_turnover_in_yi_and_limit_up_boards(self):
        record = DailyRecord(
            date="2026-06-17",
            code="SH.600001",
            name="Alpha",
            record_type="涨停",
            close_price=11,
            prev_close_price=10,
            change_pct=10,
            turnover=1_234_567_890,
            turnover_rate=8.88,
            volume_ratio=1.23,
            industries="半导体-存储器/MCU芯片",
            concepts="存储器",
            market_cycle="上升",
            theme_rank=1,
            theme_tier="主线",
            role="龙头",
            stage="连板",
            next_action="观察验证",
            net_inflow=100,
            main_net_inflow=50,
            reason_type="不明",
            review="测试",
            limit_up_boards="2板",
        )

        result = record.as_dict()

        self.assertEqual(result["涨停板数"], "2板")
        self.assertEqual(result["观察备注"], "")
        self.assertEqual(result["强转弱阶段"], "")
        self.assertEqual(result["强转弱风险分"], 0.0)
        self.assertEqual(result["强转弱信号"], "")
        self.assertEqual(result["观察纪律"], "")
        self.assertEqual(result["红旗等级"], "")
        self.assertEqual(result["红旗信号"], "")
        self.assertEqual(result["原始题材"], "未匹配")
        self.assertEqual(result["重分类题材"], "未匹配")
        self.assertEqual(result["主导催化"], "")
        self.assertEqual(result["题材匹配分"], 0.0)
        self.assertEqual(result["题材匹配度"], "")
        self.assertEqual(result["偏差原因"], "")
        self.assertNotIn("成交额", result)
        self.assertEqual(result["成交额(亿元)"], 12.35)
        self.assertEqual(record.turnover, 1_234_567_890)


if __name__ == "__main__":
    unittest.main()
