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
