import re
import unittest
from pathlib import Path


class GuiAssetsTest(unittest.TestCase):
    def test_daily_reason_column_is_prioritized_before_reason_source(self):
        app_js = Path("src/ghzw/gui_assets/app.js").read_text(encoding="utf-8")
        match = re.search(r"const priorityHeaders = \[(.*?)\];", app_js, flags=re.S)
        self.assertIsNotNone(match)

        block = match.group(1)
        reason_index = block.index('"上涨原因"')
        source_index = block.index('"原因来源"')

        self.assertLess(reason_index, source_index)

    def test_daily_output_headers_include_board_count_and_yi_turnover(self):
        app_js = Path("src/ghzw/gui_assets/app.js").read_text(encoding="utf-8")
        match = re.search(r"const priorityHeaders = \[(.*?)\];", app_js, flags=re.S)
        self.assertIsNotNone(match)

        block = match.group(1)
        type_index = block.index('"类型"')
        boards_index = block.index('"涨停板数"')
        turnover_index = block.index('"成交额(亿元)"')

        self.assertLess(type_index, boards_index)
        self.assertLess(boards_index, turnover_index)
        self.assertNotIn('"成交额"', block)

    def test_lifecycle_headers_are_prioritized_and_filterable(self):
        app_js = Path("src/ghzw/gui_assets/app.js").read_text(encoding="utf-8")
        priority_match = re.search(r"const priorityHeaders = \[(.*?)\];", app_js, flags=re.S)
        filter_match = re.search(r"const filterFields = \[(.*?)\];", app_js, flags=re.S)
        self.assertIsNotNone(priority_match)
        self.assertIsNotNone(filter_match)

        priority_block = priority_match.group(1)
        filter_block = filter_match.group(1)
        next_action_index = priority_block.index('"次日计划"')
        lifecycle_index = priority_block.index('"强转弱阶段"')

        self.assertLess(next_action_index, lifecycle_index)
        self.assertIn('"原始题材"', priority_block)
        self.assertIn('"重分类题材"', priority_block)
        self.assertIn('"主导催化"', priority_block)
        self.assertIn('"题材匹配分"', priority_block)
        self.assertIn('"题材匹配度"', priority_block)
        self.assertIn('"偏差原因"', priority_block)
        self.assertIn('"观察备注"', priority_block)
        self.assertIn('"强转弱风险分"', priority_block)
        self.assertIn('"强转弱信号"', priority_block)
        self.assertIn('"观察纪律"', priority_block)
        self.assertIn('"红旗等级"', priority_block)
        self.assertIn('"红旗信号"', priority_block)
        self.assertIn('"强转弱阶段"', filter_block)
        self.assertIn('"重分类题材"', filter_block)
        self.assertIn('"题材匹配度"', filter_block)
        self.assertIn('"红旗等级"', filter_block)

    def test_html_reports_open_through_download_endpoint(self):
        app_js = Path("src/ghzw/gui_assets/app.js").read_text(encoding="utf-8")

        self.assertIn('type === "html"', app_js)
        self.assertIn("window.open(`/download?path=", app_js)

    def test_fast_mode_is_default_gui_option(self):
        index_html = Path("src/ghzw/gui_assets/index.html").read_text(encoding="utf-8")
        app_js = Path("src/ghzw/gui_assets/app.js").read_text(encoding="utf-8")

        self.assertIn('id="fastMode"', index_html)
        self.assertIn('type="checkbox" checked', index_html)
        self.assertIn("fast_mode: elements.fastMode.checked", app_js)


if __name__ == "__main__":
    unittest.main()
