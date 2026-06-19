import tempfile
import unittest
from pathlib import Path

from ghzw.mainline_reference import load_mainline_matches, match_record_mainline
from ghzw.models import DailyRecord


class MainlineReferenceTest(unittest.TestCase):
    def test_load_mainline_matches_parses_mainline_subsector_and_stock_note(self):
        text = """mainlines:
  - name: AI算力与国产半导体
    subsectors:
      - name: 存储
        stocks:
          - code: SH.603986
            name: 兆易创新
            role: core
            note: NOR Flash与MCU
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mainline_stock_pool.yaml"
            path.write_text(text, encoding="utf-8")

            matches = load_mainline_matches(path)

        self.assertEqual(matches["SH.603986"].mainline, "AI算力与国产半导体")
        self.assertEqual(matches["SH.603986"].subsector, "存储")
        self.assertEqual(matches["SH.603986"].note, "NOR Flash与MCU")

    def test_match_record_mainline_prefers_config_mapping_over_generic_theme(self):
        matches = load_mainline_matches(Path("../A股主线研究学习/config/mainline_stock_pool.yaml"))
        record = _record("SH.603986", "兆易创新", "TMT", "半导体-MCU芯片/存储器")

        result = match_record_mainline(record, matches)

        self.assertEqual(result.display_theme, "AI算力与国产半导体")
        self.assertEqual(result.display_sector, "存储")

    def test_match_record_mainline_uses_reference_style_keyword_fallback(self):
        matches = load_mainline_matches(Path("../A股主线研究学习/config/mainline_stock_pool.yaml"))
        record = _record("SZ.000000", "未收录PCB股", "TMT", "元件-PCB概念/先进封装(Chiplet)")

        result = match_record_mainline(record, matches)

        self.assertEqual(result.display_theme, "AI算力与国产半导体")
        self.assertEqual(result.display_sector, "PCB与覆铜板")


def _record(code, name, core_theme, industries):
    return DailyRecord(
        date="2026-06-17",
        code=code,
        name=name,
        record_type="涨停",
        close_price=11,
        prev_close_price=10,
        change_pct=10,
        turnover=100_000_000,
        turnover_rate=5,
        volume_ratio=1,
        industries=industries,
        concepts=core_theme,
        market_cycle="上升",
        theme_rank=1,
        theme_tier="主线",
        role="龙头",
        stage="首板",
        next_action="观察验证",
        net_inflow=0,
        main_net_inflow=0,
        reason_type="不明",
        review="测试",
        core_theme=core_theme,
        limit_up_boards="1板",
    )


if __name__ == "__main__":
    unittest.main()
