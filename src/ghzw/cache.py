from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .models import DailyBar


class DailyBarCache:
    def __init__(self, root: Path):
        self._root = root
        self._bars_dir = root / "daily_bars"

    def load(self, code: str) -> List[DailyBar]:
        path = self._path_for(code)
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return sorted([_row_to_bar(row) for row in reader], key=lambda bar: bar.date)

    def load_recent(self, code: str, days: int) -> List[DailyBar]:
        bars = self.load(code)
        return bars[-days:] if days > 0 else bars

    def load_recent_until(self, code: str, days: int, end_date: str) -> List[DailyBar]:
        bars = [bar for bar in self.load(code) if bar.date <= end_date]
        return bars[-days:] if days > 0 else bars

    def save(self, code: str, bars: List[DailyBar]) -> None:
        if not bars:
            return
        self._bars_dir.mkdir(parents=True, exist_ok=True)
        merged: Dict[str, DailyBar] = {bar.date: bar for bar in self.load(code)}
        for bar in bars:
            merged[bar.date] = bar

        with self._path_for(code).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "code",
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover",
                    "turnover_rate",
                    "change_pct",
                ],
            )
            writer.writeheader()
            for bar in sorted(merged.values(), key=lambda item: item.date):
                writer.writerow(
                    {
                        "code": bar.code,
                        "date": bar.date,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "turnover": bar.turnover,
                        "turnover_rate": bar.turnover_rate,
                        "change_pct": bar.change_pct,
                    }
                )

    def _path_for(self, code: str) -> Path:
        safe_code = code.replace(".", "_")
        return self._bars_dir / ("%s.csv" % safe_code)


def _row_to_bar(row: Dict[str, str]) -> DailyBar:
    return DailyBar(
        code=row["code"],
        date=row["date"],
        open=_float(row.get("open")),
        high=_float(row.get("high")),
        low=_float(row.get("low")),
        close=_float(row.get("close")),
        volume=_float(row.get("volume")),
        turnover=_float(row.get("turnover")),
        turnover_rate=_float(row.get("turnover_rate")),
        change_pct=_float(row.get("change_pct")),
    )


def _float(value: object) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
