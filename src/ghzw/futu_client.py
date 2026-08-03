from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

from .models import CapitalFlow, DailyBar, PlateMembership, ReasonEvidence, StockSnapshot


class RequestPacer:
    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self._min_interval = min_interval
        self._clock = clock
        self._sleeper = sleeper
        self._last_call_at: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last_call_at is not None:
            elapsed = now - self._last_call_at
            remaining = self._min_interval - elapsed
            if remaining > 0:
                self._sleeper(remaining)
                now = self._clock()
        self._last_call_at = now


class FutuAShareClient:
    """Thin adapter around Futu OpenAPI.

    The import is lazy so pure analysis tests can run without OpenD or futu-api.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        history_min_interval: float = 0.55,
        history_rate_limit_sleep: float = 31.0,
    ):
        _ensure_futu_home()
        from futu import OpenQuoteContext

        self._ctx = OpenQuoteContext(host=host, port=port)
        self._history_pacer = RequestPacer(history_min_interval)
        self._history_rate_limit_sleep = history_rate_limit_sleep
        self._history_quota_exhausted = False

    def close(self) -> None:
        self._ctx.close()

    def get_stock_pool(self) -> List[str]:
        from futu import Market, RET_OK, SecurityType

        codes: List[str] = []
        for market in (Market.SH, Market.SZ):
            ret, data = self._ctx.get_stock_basicinfo(market, stock_type=SecurityType.STOCK)
            if ret != RET_OK:
                raise RuntimeError("get_stock_basicinfo failed for %s: %s" % (market, data))
            if data.empty:
                continue
            for _, row in data.iterrows():
                code = str(row.get("code", ""))
                if not code:
                    continue
                stock_name = str(row.get("name", ""))
                stock_child_type = str(row.get("stock_child_type", ""))
                if "DELIST" in stock_child_type.upper() or "退" in stock_name:
                    continue
                codes.append(code)
        return codes

    def get_snapshots(self, codes: Sequence[str], batch_size: int = 400) -> List[StockSnapshot]:
        from futu import RET_OK

        snapshots: List[StockSnapshot] = []
        for batch in _chunks(codes, batch_size):
            ret, data = self._ctx.get_market_snapshot(batch)
            if ret != RET_OK:
                raise RuntimeError("get_market_snapshot failed: %s" % data)
            for _, row in data.iterrows():
                name = str(row.get("stock_name", row.get("name", "")))
                snapshots.append(
                    StockSnapshot(
                        code=str(row.get("code", "")),
                        name=name,
                        last_price=_float(row.get("last_price")),
                        prev_close_price=_float(row.get("prev_close_price")),
                        high_price=_float(row.get("high_price")),
                        turnover=_float(row.get("turnover")),
                        turnover_rate=_float(row.get("turnover_rate")),
                        volume_ratio=_float(row.get("volume_ratio")),
                        market_val=_float(row.get("market_val")),
                        pe_ttm=_float(row.get("pe_ttm")),
                        pb_rate=_float(row.get("pb_rate")),
                        change_rate=_optional_float(row.get("change_rate")),
                        is_st=("ST" in name.upper()),
                        is_suspended=str(row.get("suspension", "")).lower() in {"true", "1", "yes"},
                    )
                )
        return snapshots

    def get_owner_plates(self, codes: Sequence[str], batch_size: int = 200) -> Dict[str, List[PlateMembership]]:
        from futu import RET_OK

        memberships: Dict[str, List[PlateMembership]] = {code: [] for code in codes}
        for batch in _chunks(codes, batch_size):
            ret, data = self._ctx.get_owner_plate(batch)
            if ret != RET_OK:
                raise RuntimeError("get_owner_plate failed: %s" % data)
            for _, row in data.iterrows():
                stock_code = str(row.get("code", row.get("stock_code", "")))
                if not stock_code:
                    continue
                memberships.setdefault(stock_code, []).append(
                    PlateMembership(
                        code=str(row.get("plate_code", "")),
                        name=str(row.get("plate_name", "")),
                        plate_type=str(row.get("plate_type", "")),
                    )
                )
        return memberships

    def get_history(self, code: str, days: int = 120, end: date | None = None) -> List[DailyBar]:
        if self._history_quota_exhausted:
            return []

        ret_ok, kl_day, au_qfq = self._history_constants()
        end_date = end or date.today()
        start_date = end_date - timedelta(days=days * 2)
        for attempt in range(2):
            self._history_pacer.wait()
            ret, data, _ = self._ctx.request_history_kline(
                code,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                ktype=kl_day,
                autype=au_qfq,
                max_count=days,
            )
            if ret == ret_ok:
                break
            if is_history_quota_error(data):
                self._history_quota_exhausted = True
                print(
                    "Warning: Futu history K-line quota is exhausted; continuing without history-based stage tags.",
                    file=sys.stderr,
                )
                return []
            if attempt == 0 and is_history_rate_limit_error(data):
                time.sleep(self._history_rate_limit_sleep)
                continue
            raise RuntimeError("request_history_kline failed for %s: %s" % (code, data))
        bars: List[DailyBar] = []
        for _, row in data.iterrows():
            bars.append(
                DailyBar(
                    code=code,
                    date=str(row.get("time_key", ""))[:10],
                    open=_float(row.get("open")),
                    close=_float(row.get("close")),
                    high=_float(row.get("high")),
                    low=_float(row.get("low")),
                    volume=_float(row.get("volume")),
                    turnover=_float(row.get("turnover")),
                    turnover_rate=_float(row.get("turnover_rate")),
                    change_pct=_float(row.get("change_rate")),
                )
            )
        return bars

    def _history_constants(self):
        if hasattr(self, "_history_ret_ok"):
            return self._history_ret_ok, self._history_kl_day, self._history_au_qfq
        from futu import AuType, KLType, RET_OK

        return RET_OK, KLType.K_DAY, AuType.QFQ

    def get_capital_flows(self, codes: Iterable[str]) -> Dict[str, CapitalFlow]:
        from futu import RET_OK

        result: Dict[str, CapitalFlow] = {}
        for code in codes:
            ret, data = self._ctx.get_capital_flow(code)
            if ret != RET_OK or data.empty:
                result[code] = CapitalFlow(code=code)
                continue
            latest = data.iloc[-1]
            result[code] = CapitalFlow(
                code=code,
                net_inflow=_float(latest.get("capital_inflow")),
                main_net_inflow=_float(latest.get("main_inflow")),
            )
        return result

    def get_reason_evidence(self, trade_date: date, codes: Iterable[str]) -> List[ReasonEvidence]:
        return collect_futu_reason_evidence(self._ctx, trade_date, codes)


def _ensure_futu_home() -> None:
    home = os.environ.get("HOME")
    if not home:
        return

    default_log_dir = Path(home) / ".com.futunn.FutuOpenD" / "Log"
    if _is_writable_directory(default_log_dir):
        return

    fallback_home = _pick_futu_home_fallback()
    (fallback_home / ".com.futunn.FutuOpenD" / "Log").mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(fallback_home)


def _pick_futu_home_fallback() -> Path:
    env_override = os.environ.get("GHZW_FUTU_HOME")
    candidates = []
    if env_override:
        candidates.append(Path(env_override).expanduser())
    candidates.extend(
        [
            Path.cwd() / ".tmp_home",
            Path(tempfile.gettempdir()) / "ghzw-futu-home",
        ]
    )
    for candidate in candidates:
        if _is_writable_directory(candidate):
            return candidate
    raise OSError("No writable fallback HOME for Futu OpenD logs")


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def collect_futu_reason_evidence(ctx, trade_date: date, codes: Iterable[str]) -> List[ReasonEvidence]:
    result: List[ReasonEvidence] = []
    for code in codes:
        result.extend(_safe_collect(lambda: _collect_research_rating(ctx, trade_date, code)))
        result.extend(_safe_collect(lambda: _collect_buybacks(ctx, trade_date, code)))
        result.extend(_safe_collect(lambda: _collect_shareholder_changes(ctx, trade_date, code)))
    return result


def _collect_research_rating(ctx, trade_date: date, code: str) -> List[ReasonEvidence]:
    ret, data = ctx.get_research_rating_summary(code, num=3)
    if ret != 0 or _is_empty_frame(data):
        return []
    evidence: List[ReasonEvidence] = []
    for _, row in data.iterrows():
        update_time = str(row.get("update_time_str") or row.get("update_time") or "")
        if update_time[:10] != trade_date.isoformat():
            continue
        rating = str(row.get("rating") or row.get("rating_type") or "评级更新")
        target = row.get("target_price")
        summary = "分析师评级更新：%s" % rating
        if target not in (None, ""):
            summary += "，目标价%s" % target
        evidence.append(
            ReasonEvidence(
                date=trade_date.isoformat(),
                code=code,
                reason_type="研报",
                summary=summary,
                source="Futu",
                confidence="中",
                published_at=update_time,
            )
        )
    return evidence


def _collect_buybacks(ctx, trade_date: date, code: str) -> List[ReasonEvidence]:
    ret, data = ctx.get_corporate_actions_buybacks(code, num=3)
    if ret != 0 or not isinstance(data, dict):
        return []
    frame = data.get("a_buy_back_list")
    if _is_empty_frame(frame):
        return []
    evidence: List[ReasonEvidence] = []
    for _, row in frame.iterrows():
        published = str(row.get("publ_date_str") or row.get("advance_date_str") or "")
        if published[:10] != trade_date.isoformat():
            continue
        money = row.get("buy_back_money")
        summary = "公司回购事项"
        if money not in (None, ""):
            summary += "，金额%s" % money
        evidence.append(
            ReasonEvidence(
                date=trade_date.isoformat(),
                code=code,
                reason_type="公司行动",
                summary=summary,
                source="Futu",
                confidence="高",
                published_at=published,
            )
        )
    return evidence


def _collect_shareholder_changes(ctx, trade_date: date, code: str) -> List[ReasonEvidence]:
    ret, data = ctx.get_shareholders_holding_changes(code, num=5)
    if ret != 0 or _is_empty_frame(data):
        return []
    evidence: List[ReasonEvidence] = []
    for _, row in data.iterrows():
        holding_date = str(row.get("holding_date_str") or "")
        if holding_date[:10] != trade_date.isoformat():
            continue
        holder = str(row.get("name") or "股东")
        change_num = row.get("share_change_num")
        summary = "%s持股变动" % holder
        if change_num not in (None, ""):
            summary += "，变动%s股" % change_num
        evidence.append(
            ReasonEvidence(
                date=trade_date.isoformat(),
                code=code,
                reason_type="股东变动",
                summary=summary,
                source="Futu",
                confidence="中",
                published_at=holding_date,
            )
        )
    return evidence


def _safe_collect(fn):
    try:
        return fn()
    except Exception as exc:
        print("Warning: Futu evidence source failed: %s" % exc, file=sys.stderr)
        return []


def _is_empty_frame(data) -> bool:
    return data is None or bool(getattr(data, "empty", False))


def _chunks(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(items), size):
        yield list(items[index : index + size])


def _float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_history_rate_limit_error(message: object) -> bool:
    text = str(message)
    return "历史K线" in text and ("频率太高" in text or "每30秒最多60次" in text)


def is_history_quota_error(message: object) -> bool:
    text = str(message)
    return "历史K线" in text and ("额度不足" in text or "正股额度" in text)
