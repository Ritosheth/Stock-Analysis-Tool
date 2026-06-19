from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Iterable, List, Mapping, Optional

from .models import DailyBar


class TushareHistoryProvider:
    def __init__(self, token: Optional[str] = None):
        self._token = token or os.environ.get("TUSHARE_TOKEN")
        if not self._token:
            raise ValueError("TUSHARE_TOKEN is not configured")

    def get_history(self, code: str, days: int = 120, end: date | None = None) -> List[DailyBar]:
        import tushare as ts

        end_date = end or date.today()
        start_date = end_date - timedelta(days=days * 2)
        ts.set_token(self._token)
        pro = ts.pro_api()
        df = pro.daily(
            ts_code=to_tushare_code(code),
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        return normalize_tushare_daily(code, df.to_dict("records"))[-days:]


def to_tushare_code(code: str) -> str:
    market, symbol = code.split(".", 1)
    return "%s.%s" % (symbol, market)


def normalize_tushare_daily(code: str, rows: Iterable[Mapping[str, object]]) -> List[DailyBar]:
    bars: List[DailyBar] = []
    for row in rows:
        trade_date = str(row.get("trade_date", ""))
        if len(trade_date) == 8:
            normalized_date = "%s-%s-%s" % (trade_date[:4], trade_date[4:6], trade_date[6:8])
        else:
            normalized_date = trade_date
        bars.append(
            DailyBar(
                code=code,
                date=normalized_date,
                open=_float(row.get("open")),
                high=_float(row.get("high")),
                low=_float(row.get("low")),
                close=_float(row.get("close")),
                volume=_float(row.get("vol")) * 100,
                turnover=_float(row.get("amount")) * 1000,
                turnover_rate=0.0,
                change_pct=_float(row.get("pct_chg")),
            )
        )
    return sorted([bar for bar in bars if bar.date], key=lambda bar: bar.date)


def is_tushare_permission_error(message: object) -> bool:
    text = str(message)
    return "没有接口" in text and "daily" in text and "访问权限" in text


def _float(value: object) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
