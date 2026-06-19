from __future__ import annotations

import csv
import argparse
import json
import mimetypes
import socket
import traceback
import webbrowser
from dataclasses import dataclass
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Mapping
from urllib.parse import parse_qs, urlparse

from .akshare_client import AkshareHistoryProvider
from .cache import DailyBarCache
from .futu_client import FutuAShareClient
from .history import CachedHistoryProvider
from .pipeline import run_daily_pipeline
from .tushare_client import TushareHistoryProvider
from .validation import pick_next_bars, read_daily_records_csv, validate_next_day, write_validation_csv


REPORT_DAILY_SUFFIX = "-daily-review.csv"
REPORT_VALIDATION_SUFFIX = "-next-day-validation.csv"
REPORT_HTML_SUFFIX = "-daily-report.html"
ASSET_DIR = Path(__file__).with_name("gui_assets")


@dataclass(frozen=True)
class GuiConfig:
    project_root: Path
    output_dir: Path | None = None
    cache_dir: Path | None = None

    @property
    def resolved_output_dir(self) -> Path:
        return self.output_dir or self.project_root / "outputs" / "daily"

    @property
    def resolved_cache_dir(self) -> Path:
        return self.cache_dir or self.project_root / "data" / "cache"


def list_reports(output_dir: Path) -> List[Dict[str, object]]:
    if not output_dir.exists():
        return []

    reports: List[Dict[str, object]] = []
    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        report_type = _report_type(path)
        if report_type is None:
            continue
        reports.append(
            {
                "name": path.name,
                "path": path.name,
                "type": report_type,
                "size": path.stat().st_size,
                "modified": path.stat().st_mtime,
            }
        )
    return sorted(reports, key=lambda item: (float(item["modified"]), str(item["name"])), reverse=True)


def read_report_csv(path: Path) -> Dict[str, object]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return {
        "name": path.name,
        "path": path.name,
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
    }


def safe_report_path(base_dir: Path, requested: str) -> Path:
    base = base_dir.resolve()
    candidate = (base / requested).resolve()
    if base != candidate and base not in candidate.parents:
        raise ValueError("报表路径不在输出目录内")
    if candidate.suffix.lower() not in {".csv", ".html"}:
        raise ValueError("只能读取 CSV 或 HTML 报表")
    return candidate


def json_error(message: str, status: int = 400):
    return status, {"ok": False, "error": message}


def handle_api_request(method: str, raw_path: str, body: bytes, config: GuiConfig):
    parsed = urlparse(raw_path)
    path = parsed.path
    query = parse_qs(parsed.query)

    try:
        if method == "GET" and path == "/api/health":
            return 200, {"ok": True, "message": "GUI 服务运行中"}
        if method == "GET" and path == "/api/reports":
            return 200, {"ok": True, "reports": list_reports(config.resolved_output_dir)}
        if method == "GET" and path == "/api/report":
            requested = (query.get("path") or [""])[0]
            report_path = safe_report_path(config.resolved_output_dir, requested)
            if not report_path.exists():
                return json_error("找不到这个报表文件", 404)
            if report_path.suffix.lower() == ".html":
                return json_error("HTML 报告请通过下载链接打开", 400)
            return 200, {"ok": True, "report": read_report_csv(report_path)}
        if method == "POST" and path == "/api/run-daily":
            return _handle_run_daily(_read_json_body(body), config)
        if method == "POST" and path == "/api/validate":
            return _handle_validate(_read_json_body(body), config)
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:
        traceback.print_exc()
        return json_error(_friendly_error(exc), 500)

    return json_error("未找到这个接口", 404)


def parse_daily_payload(payload: Mapping[str, object], config: GuiConfig) -> Dict[str, object]:
    trade_date = _parse_date(str(payload.get("date") or date.today().isoformat()), "交易日期")
    if trade_date > date.today():
        raise ValueError("交易日期不能晚于今天")
    turnover_limit = _parse_positive_int(payload.get("turnover_limit") or 30, "成交额 TopN")
    host = str(payload.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    port = _parse_positive_int(payload.get("port") or 11111, "Futu OpenD 端口")
    return {
        "date": trade_date,
        "host": host,
        "port": port,
        "turnover_limit": turnover_limit,
        "evidence_source": str(payload.get("evidence_source") or "auto"),
        "output_dir": config.resolved_output_dir,
        "cache_dir": config.resolved_cache_dir,
    }


def parse_validation_payload(payload: Mapping[str, object], config: GuiConfig) -> Dict[str, object]:
    report = str(payload.get("report") or "").strip()
    next_date_text = str(payload.get("next_date") or "").strip()
    if not report:
        raise ValueError("请选择要验证的日报文件")
    if not next_date_text:
        raise ValueError("请填写次日交易日期")
    return {
        "report_path": safe_report_path(config.resolved_output_dir, report),
        "next_date": _parse_date(next_date_text, "次日交易日期"),
        "output_dir": config.resolved_output_dir,
        "cache_dir": config.resolved_cache_dir,
    }


def create_handler(config: GuiConfig):
    class GuiRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/"):
                self._write_json(*handle_api_request("GET", self.path, b"", config))
                return
            if self.path.startswith("/download"):
                self._serve_download()
                return
            self._serve_static()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            self._write_json(*handle_api_request("POST", self.path, body, config))

        def log_message(self, format, *args):
            print("%s - %s" % (self.address_string(), format % args))

        def _write_json(self, status: int, payload: Mapping[str, object]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _serve_static(self) -> None:
            parsed = urlparse(self.path)
            requested = parsed.path.lstrip("/") or "index.html"
            if requested in {"styles.css", "app.js", "index.html"}:
                asset_path = ASSET_DIR / requested
            else:
                asset_path = ASSET_DIR / "index.html"
            if not asset_path.exists():
                self.send_error(404, "Asset not found")
                return
            data = asset_path.read_bytes()
            content_type = mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream"
            if asset_path.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            elif asset_path.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif asset_path.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _serve_download(self) -> None:
            parsed = urlparse(self.path)
            requested = (parse_qs(parsed.query).get("path") or [""])[0]
            try:
                report_path = safe_report_path(config.resolved_output_dir, requested)
            except ValueError as exc:
                self.send_error(400, str(exc))
                return
            if not report_path.exists():
                self.send_error(404, "Report not found")
                return
            data = report_path.read_bytes()
            filename = report_path.name.encode("utf-8").decode("latin-1", errors="ignore")
            content_type = "text/html; charset=utf-8" if report_path.suffix.lower() == ".html" else "text/csv; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return GuiRequestHandler


def pick_server_port(host: str, preferred_port: int) -> int:
    if preferred_port == 0:
        return 0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, preferred_port))
        except OSError:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as fallback_probe:
                fallback_probe.bind((host, 0))
                return int(fallback_probe.getsockname()[1])
    return preferred_port


def run_server(host: str, port: int, config: GuiConfig, open_browser: bool = True) -> None:
    selected_port = pick_server_port(host, port)
    if selected_port != port and port != 0:
        print("端口 %s 已被占用，已自动改用 %s。" % (port, selected_port))
    server = ThreadingHTTPServer((host, selected_port), create_handler(config))
    actual_port = server.server_address[1]
    url = "http://%s:%s" % (host, actual_port)
    print("股海贼王 GUI 已启动：%s" % url)
    print("按 Ctrl+C 可停止服务。")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 GUI 服务...")
    finally:
        server.server_close()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the 股海贼王 local GUI workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    config = GuiConfig(project_root=Path(args.project_root).resolve())
    run_server(args.host, args.port, config, open_browser=not args.no_browser)
    return 0


def _report_type(path: Path) -> str | None:
    name = path.name
    if name.endswith(REPORT_DAILY_SUFFIX):
        return "daily"
    if name.endswith(REPORT_VALIDATION_SUFFIX):
        return "validation"
    if name.endswith(REPORT_HTML_SUFFIX):
        return "html"
    return None


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("%s格式应为 YYYY-MM-DD" % label) from exc


def _parse_positive_int(value: object, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s必须是正整数" % label) from exc
    if parsed <= 0:
        raise ValueError("%s必须是正整数" % label)
    return parsed


def _read_json_body(body: bytes) -> Dict[str, object]:
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("请求内容不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("请求内容必须是 JSON 对象")
    return data


def _handle_run_daily(payload: Mapping[str, object], config: GuiConfig):
    parsed = parse_daily_payload(payload, config)
    client = FutuAShareClient(host=str(parsed["host"]), port=int(parsed["port"]))
    try:
        primary_history, fallback_history = _daily_history_sources(client)
        history_provider = CachedHistoryProvider(
            cache=DailyBarCache(parsed["cache_dir"]),
            primary_provider=primary_history,
            fallback_provider=fallback_history,
            disable_fallback_on_error=False,
        )
        result = run_daily_pipeline(
            client=client,
            trade_date=parsed["date"],
            output_dir=parsed["output_dir"],
            turnover_limit=int(parsed["turnover_limit"]),
            cache_dir=parsed["cache_dir"],
            history_provider=history_provider,
            evidence_source=str(parsed["evidence_source"]),
            generate_html_report=True,
            forum_search_enabled=True,
        )
    finally:
        client.close()
    report = read_report_csv(result.output_path) if result.output_path else None
    message = "已生成 %s 行复盘记录" % len(result.records)
    if result.report_path:
        message = "%s，并生成 HTML 报告 %s" % (message, result.report_path.name)
    if result.warning:
        message = "%s。%s" % (message, result.warning)
    if result.report_warning:
        message = "%s。%s" % (message, result.report_warning)
    return 200, {
        "ok": True,
        "message": message,
        "path": result.output_path.name if result.output_path else "",
        "report_html_path": result.report_path.name if result.report_path else "",
        "report_warning": result.report_warning,
        "report": report,
        "reports": list_reports(config.resolved_output_dir),
    }


def _daily_history_sources(futu_client):
    try:
        return TushareHistoryProvider(), AkshareHistoryProvider()
    except ValueError:
        return futu_client, AkshareHistoryProvider()


def _handle_validate(payload: Mapping[str, object], config: GuiConfig):
    parsed = parse_validation_payload(payload, config)
    records = read_daily_records_csv(parsed["report_path"])
    provider = CachedHistoryProvider(
        cache=DailyBarCache(parsed["cache_dir"]),
        primary_provider=AkshareHistoryProvider(),
        fallback_provider=None,
    )
    history = {
        record.code: provider.get_history(record.code, days=10, end=parsed["next_date"])
        for record in records
    }
    next_bars = pick_next_bars(records, history, parsed["next_date"].isoformat())
    rows = validate_next_day(records, next_bars)
    output_path = parsed["output_dir"] / ("%s-next-day-validation.csv" % parsed["next_date"].isoformat())
    write_validation_csv(rows, output_path)
    message = "已生成 %s 行次日验证记录" % len(rows)
    if not rows:
        message = "已生成验证文件，但没有匹配到次日 K 线数据。请检查次日是否为已完成交易日。"
    return 200, {
        "ok": True,
        "message": message,
        "path": output_path.name,
        "report": read_report_csv(output_path),
        "reports": list_reports(config.resolved_output_dir),
    }


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "no module named 'futu'" in lowered or "no module named futu" in lowered:
        return "未安装 futu-api，请先安装富途依赖。"
    if "no module named 'akshare'" in lowered or "no module named akshare" in lowered:
        return "未安装 akshare，次日验证暂不可用。"
    if "connect" in lowered or "connection" in lowered or "10061" in lowered:
        return "无法连接 Futu OpenD，请确认 Futu OpenD 已启动并监听 127.0.0.1:11111。"
    return text or "运行失败，请查看终端日志。"


if __name__ == "__main__":
    raise SystemExit(main())
