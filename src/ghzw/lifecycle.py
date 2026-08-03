from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Sequence

from .models import DailyBar, StockSnapshot


@dataclass(frozen=True)
class WatchlistEntry:
    code: str
    name: str = ""
    core_theme: str = ""
    note: str = ""


@dataclass(frozen=True)
class LifecycleRisk:
    code: str
    stage: str = "观察"
    score: float = 0.0
    signals: str = ""
    discipline: str = "记录观察，等待更多信号。"


def load_watchlist(path: Path) -> list[WatchlistEntry]:
    if not path.exists():
        return []
    entries: list[WatchlistEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = _text(row.get("代码") or row.get("code"))
            if not code:
                continue
            entries.append(
                WatchlistEntry(
                    code=code,
                    name=_text(row.get("名称") or row.get("name")),
                    core_theme=_text(row.get("核心题材") or row.get("theme")),
                    note=_text(row.get("备注") or row.get("note")),
                )
            )
    return entries


def assess_lifecycle_risks(
    snapshots: Sequence[StockSnapshot],
    history_by_code: Mapping[str, Sequence[DailyBar]],
    core_theme_by_code: Mapping[str, str],
) -> Dict[str, LifecycleRisk]:
    snapshot_by_code = {snapshot.code: snapshot for snapshot in snapshots}
    theme_avg_change = _theme_avg_change(snapshots, core_theme_by_code)
    result: Dict[str, LifecycleRisk] = {}
    for code, snapshot in snapshot_by_code.items():
        bars = list(history_by_code.get(code, []))
        result[code] = _assess_one(snapshot, bars, theme_avg_change.get(core_theme_by_code.get(code, "")))
    return result


def _assess_one(snapshot: StockSnapshot, bars: Sequence[DailyBar], theme_avg_change: float | None) -> LifecycleRisk:
    score = 0.0
    signals: list[str] = []
    closes = [bar.close for bar in bars if bar.close > 0]
    latest = bars[-1] if bars else None
    latest_turnover = latest.turnover if latest and latest.turnover > 0 else snapshot.turnover

    if len(closes) >= 20:
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        close = closes[-1]
        if close < ma10:
            score += 22
            signals.append("跌破10日线")
        elif close < ma5:
            score += 10
            signals.append("跌破5日线")
        if ma5 < ma10:
            score += 10
            signals.append("短均线转弱")
        if close > ma20 * 1.25:
            score += 6
            signals.append("高位运行")

    if len(bars) >= 8:
        previous_high = max((bar.high or bar.close) for bar in bars[-8:-3])
        recent_high = max((bar.high or bar.close) for bar in bars[-3:])
        recent_close = bars[-1].close
        if previous_high > 0 and recent_high < previous_high * 0.995 and recent_close < previous_high * 0.94:
            score += 18
            signals.append("修复失败")

    if len(bars) >= 6:
        avg_turnover = sum(bar.turnover for bar in bars[-6:-1]) / 5
        if avg_turnover > 0 and latest_turnover >= avg_turnover * 1.8:
            if snapshot.change_pct <= 0:
                score += 22
                signals.append("放量下跌")
            elif snapshot.change_pct < 2:
                score += 16
                signals.append("放量滞涨")

    if len(bars) >= 30 and closes:
        recent_low = min(closes[-60:])
        recent_high = max(closes[-60:])
        if recent_high > recent_low:
            position = (closes[-1] - recent_low) / (recent_high - recent_low)
            if position >= 0.8:
                score += 8
                signals.append("接近区间高位")

    if theme_avg_change is not None:
        relative = snapshot.change_pct - theme_avg_change
        if relative <= -5:
            score += 18
            signals.append("相对题材偏弱")
        elif relative <= -2:
            score += 8
            signals.append("略弱于题材")

    stage = _stage(score, signals)
    return LifecycleRisk(
        code=snapshot.code,
        stage=stage,
        score=round(min(score, 100.0), 1),
        signals="、".join(signals) or "暂无明显强转弱信号",
        discipline=_discipline(stage),
    )


def _theme_avg_change(snapshots: Sequence[StockSnapshot], core_theme_by_code: Mapping[str, str]) -> Dict[str, float]:
    grouped: Dict[str, list[float]] = {}
    for snapshot in snapshots:
        theme = core_theme_by_code.get(snapshot.code, "")
        if not theme or theme == "未匹配":
            continue
        grouped.setdefault(theme, []).append(snapshot.change_pct)
    return {theme: sum(values) / len(values) for theme, values in grouped.items() if values}


def _stage(score: float, signals: Sequence[str]) -> str:
    signal_set = set(signals)
    if score >= 75 or {"跌破10日线", "放量下跌", "相对题材偏弱"}.issubset(signal_set):
        return "趋势破坏"
    if score >= 55 or "修复失败" in signal_set:
        return "强转弱验证"
    if score >= 25 or {"高位运行", "接近区间高位"} & signal_set:
        return "高位换手"
    if "暂无明显强转弱信号" in signal_set:
        return "观察"
    return "一致加速"


def _discipline(stage: str) -> str:
    if stage == "趋势破坏":
        return "退出趋势交易或大幅降仓，等待重新转强证据。"
    if stage == "强转弱验证":
        return "停止加仓，考虑减仓；未来2-3个交易日重点看修复和相对强弱。"
    if stage == "高位换手":
        return "继续持有但提高纪律，观察是否创新高、是否放量滞涨。"
    if stage == "一致加速":
        return "趋势仍强，按计划持有，避免情绪化追高。"
    return "记录观察，等待更多信号。"


def _text(value: object) -> str:
    return str(value or "").strip()
