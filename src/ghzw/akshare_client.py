from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Mapping, Set

from .models import DailyBar, StockSnapshot


class AkshareHistoryProvider:
    def get_history(self, code: str, days: int = 120, end: date | None = None) -> List[DailyBar]:
        import akshare as ak

        end_date = end or date.today()
        start_date = end_date - timedelta(days=days * 2)
        df = ak.stock_zh_a_hist(
            symbol=code.split(".")[-1],
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="qfq",
        )
        rows = df.to_dict("records")
        return normalize_akshare_hist(code, rows)[-days:]


class AkshareLimitUpSnapshotProvider:
    def get_limit_up_snapshots(self, trade_date: date, allowed_codes: Iterable[str]) -> List[StockSnapshot]:
        import akshare as ak

        df = ak.stock_zt_pool_em(date=trade_date.strftime("%Y%m%d"))
        return normalize_limit_up_pool(df.to_dict("records"), set(allowed_codes))


def normalize_akshare_hist(code: str, rows: Iterable[Mapping[str, object]]) -> List[DailyBar]:
    bars: List[DailyBar] = []
    for row in rows:
        bars.append(
            DailyBar(
                code=code,
                date=str(row.get("日期", ""))[:10],
                open=_float(row.get("开盘")),
                high=_float(row.get("最高")),
                low=_float(row.get("最低")),
                close=_float(row.get("收盘")),
                volume=_float(row.get("成交量")),
                turnover=_float(row.get("成交额")),
                turnover_rate=_float(row.get("换手率")),
                change_pct=_float(row.get("涨跌幅")),
            )
        )
    return sorted([bar for bar in bars if bar.date], key=lambda bar: bar.date)


def normalize_limit_up_pool(rows: Iterable[Mapping[str, object]], allowed_codes: Set[str]) -> List[StockSnapshot]:
    snapshots: List[StockSnapshot] = []
    for row in rows:
        code = _to_futu_code(str(row.get("代码") or ""))
        if not code or code not in allowed_codes:
            continue
        last_price = _float(row.get("最新价"))
        change_pct = _float(row.get("涨跌幅"))
        prev_close = _prev_close_from_change(last_price, change_pct)
        snapshots.append(
            StockSnapshot(
                code=code,
                name=str(row.get("名称") or code),
                last_price=last_price,
                prev_close_price=prev_close,
                high_price=last_price,
                turnover=_float(row.get("成交额")),
                turnover_rate=_float(row.get("换手率")),
                change_rate=change_pct,
                is_st="ST" in str(row.get("名称") or "").upper(),
            )
        )
    return snapshots


def _to_futu_code(code6: str) -> str:
    code = code6.strip()
    if len(code) != 6:
        return ""
    if code.startswith("6"):
        return "SH.%s" % code
    if code.startswith(("0", "3")):
        return "SZ.%s" % code
    return ""


def _prev_close_from_change(last_price: float, change_pct: float) -> float:
    denominator = 1 + change_pct / 100
    if denominator <= 0:
        return 0.0
    return last_price / denominator


def _float(value: object) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
