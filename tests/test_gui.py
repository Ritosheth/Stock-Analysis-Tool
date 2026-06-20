import csv
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

from ghzw.gui import (
    GuiConfig,
    handle_api_request,
    list_reports,
    parse_daily_payload,
    parse_validation_payload,
    pick_server_port,
    read_report_csv,
    safe_report_path,
)


class GuiReportTests(unittest.TestCase):
    def test_list_reports_groups_daily_and_validation_csvs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "2026-06-12-daily-review.csv").write_text("日期,代码\n", encoding="utf-8-sig")
            (output_dir / "2026-06-12-daily-report.html").write_text("<html></html>", encoding="utf-8")
            (output_dir / "2026-06-15-next-day-validation.csv").write_text("日期,代码\n", encoding="utf-8-sig")
            (output_dir / "notes.txt").write_text("ignore", encoding="utf-8")

            reports = list_reports(output_dir)

        report_types = {item["name"]: item["type"] for item in reports}
        self.assertEqual(report_types["2026-06-15-next-day-validation.csv"], "validation")
        self.assertEqual(report_types["2026-06-12-daily-review.csv"], "daily")
        self.assertEqual(report_types["2026-06-12-daily-report.html"], "html")

    def test_read_report_csv_returns_headers_rows_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-06-12-daily-review.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["日期", "代码", "名称"])
                writer.writeheader()
                writer.writerow({"日期": "2026-06-12", "代码": "SZ.000001", "名称": "平安银行"})

            result = read_report_csv(path)

        self.assertEqual(result["headers"], ["日期", "代码", "名称"])
        self.assertEqual(result["rows"], [{"日期": "2026-06-12", "代码": "SZ.000001", "名称": "平安银行"}])
        self.assertEqual(result["row_count"], 1)

    def test_safe_report_path_rejects_paths_outside_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"
            output_dir.mkdir()

            with self.assertRaises(ValueError):
                safe_report_path(output_dir, "../secret.csv")

    def test_safe_report_path_allows_html_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"
            output_dir.mkdir()

            path = safe_report_path(output_dir, "2026-06-17-daily-report.html")

        self.assertEqual(path.name, "2026-06-17-daily-report.html")


class GuiPayloadTests(unittest.TestCase):
    def test_parse_daily_payload_uses_defaults(self):
        config = GuiConfig(project_root=Path("/project"))

        parsed = parse_daily_payload({"date": "2026-06-12"}, config)

        self.assertEqual(parsed["date"].isoformat(), "2026-06-12")
        self.assertEqual(parsed["host"], "127.0.0.1")
        self.assertEqual(parsed["port"], 11111)
        self.assertEqual(parsed["turnover_limit"], 30)
        self.assertTrue(parsed["fast_mode"])
        self.assertEqual(parsed["output_dir"], Path("/project/outputs/daily"))
        self.assertEqual(parsed["cache_dir"], Path("/project/data/cache"))

    def test_parse_daily_payload_accepts_deep_mode(self):
        config = GuiConfig(project_root=Path("/project"))

        parsed = parse_daily_payload({"date": "2026-06-12", "fast_mode": False}, config)

        self.assertFalse(parsed["fast_mode"])

    def test_parse_daily_payload_rejects_invalid_date(self):
        config = GuiConfig(project_root=Path("/project"))

        with self.assertRaises(ValueError):
            parse_daily_payload({"date": "2026/06/12"}, config)

    def test_parse_daily_payload_rejects_future_date(self):
        config = GuiConfig(project_root=Path("/project"))

        with self.assertRaises(ValueError):
            parse_daily_payload({"date": "2999-01-01"}, config)

    def test_parse_validation_payload_requires_report_and_next_date(self):
        config = GuiConfig(project_root=Path("/project"))

        with self.assertRaises(ValueError):
            parse_validation_payload({"report": "", "next_date": ""}, config)

    def test_parse_validation_payload_resolves_report_in_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "outputs" / "daily"
            report_dir.mkdir(parents=True)
            report = report_dir / "2026-06-12-daily-review.csv"
            report.write_text("日期,代码\n", encoding="utf-8-sig")
            config = GuiConfig(project_root=root)

            parsed = parse_validation_payload(
                {"report": "2026-06-12-daily-review.csv", "next_date": "2026-06-15"},
                config,
            )

        self.assertEqual(parsed["report_path"].name, "2026-06-12-daily-review.csv")
        self.assertEqual(parsed["next_date"].isoformat(), "2026-06-15")


class GuiApiTests(unittest.TestCase):
    def test_handle_reports_endpoint_lists_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "outputs" / "daily"
            report_dir.mkdir(parents=True)
            (report_dir / "2026-06-12-daily-review.csv").write_text("日期,代码\n", encoding="utf-8-sig")
            config = GuiConfig(project_root=root)

            status, payload = handle_api_request("GET", "/api/reports", b"", config)

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["reports"][0]["name"], "2026-06-12-daily-review.csv")

    def test_handle_report_endpoint_reads_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "outputs" / "daily"
            report_dir.mkdir(parents=True)
            (report_dir / "2026-06-12-daily-review.csv").write_text(
                "日期,代码\n2026-06-12,SZ.000001\n",
                encoding="utf-8-sig",
            )
            config = GuiConfig(project_root=root)

            status, payload = handle_api_request(
                "GET",
                "/api/report?path=2026-06-12-daily-review.csv",
                b"",
                config,
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["report"]["row_count"], 1)

    def test_handle_report_endpoint_rejects_html_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "outputs" / "daily"
            report_dir.mkdir(parents=True)
            (report_dir / "2026-06-17-daily-report.html").write_text("<html></html>", encoding="utf-8")
            config = GuiConfig(project_root=root)

            status, payload = handle_api_request(
                "GET",
                "/api/report?path=2026-06-17-daily-report.html",
                b"",
                config,
            )

        self.assertEqual(status, 400)
        self.assertIn("HTML", payload["error"])

    def test_handle_unknown_endpoint_returns_404(self):
        config = GuiConfig(project_root=Path("/project"))

        status, payload = handle_api_request("GET", "/api/missing", b"", config)

        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])


class GuiServerPortTests(unittest.TestCase):
    def test_pick_server_port_returns_different_port_when_preferred_is_busy(self):
        preferred_probe = _FakeSocket(bind_error=OSError("address in use"))
        fallback_probe = _FakeSocket(bound_port=43210)

        with mock.patch("ghzw.gui.socket.socket", side_effect=[preferred_probe, fallback_probe]):
            selected = pick_server_port("127.0.0.1", 8765)

        self.assertEqual(selected, 43210)


class _FakeSocket:
    def __init__(self, bind_error: Optional[OSError] = None, bound_port: int = 0):
        self.bind_error = bind_error
        self.bound_port = bound_port

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def bind(self, address):
        if self.bind_error:
            raise self.bind_error

    def getsockname(self):
        return ("127.0.0.1", self.bound_port)


if __name__ == "__main__":
    unittest.main()
