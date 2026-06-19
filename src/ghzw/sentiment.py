from __future__ import annotations

from typing import Mapping, Sequence

from .analysis import candidate_floor, limit_threshold_for, select_turnover_top
from .models import DailyBar, MarketSentiment, StageTag, StockSnapshot


def compute_market_sentiment(
    snapshots: Sequence[StockSnapshot],
    stage_by_code: Mapping[str, StageTag],
    history_by_code: Mapping[str, Sequence[DailyBar]],
    turnover_limit: int = 30,
) -> MarketSentiment:
    tradable = [snapshot for snapshot in snapshots if not snapshot.is_suspended]
    if not tradable:
        return MarketSentiment()

    limit_up_count = sum(
        1 for snapshot in tradable
        if snapshot.change_pct >= candidate_floor(limit_threshold_for(snapshot))
    )
    limit_down_count = sum(1 for snapshot in tradable if snapshot.change_pct <= -9.8)
    positive_count = sum(1 for snapshot in tradable if snapshot.change_pct > 0)
    negative_count = sum(1 for snapshot in tradable if snapshot.change_pct < 0)
    positive_ratio = positive_count / len(tradable)
    avg_change_pct = sum(snapshot.change_pct for snapshot in tradable) / len(tradable)
    streaks = [stage.board_streak for stage in stage_by_code.values() if stage.board_streak > 0]
    turnover_top = select_turnover_top(tradable, turnover_limit)
    turnover_top_avg = (
        sum(snapshot.change_pct for snapshot in turnover_top) / len(turnover_top)
        if turnover_top
        else 0.0
    )

    yesterday_changes = _yesterday_limit_up_today_changes(history_by_code)
    yesterday_avg = None
    if yesterday_changes:
        yesterday_avg = sum(yesterday_changes) / len(yesterday_changes)

    return MarketSentiment(
        limit_up_count=limit_up_count,
        limit_down_count=limit_down_count,
        positive_count=positive_count,
        negative_count=negative_count,
        positive_ratio=positive_ratio,
        avg_change_pct=avg_change_pct,
        max_board_streak=max(streaks) if streaks else 0,
        board_streak_count=len(streaks),
        turnover_top_avg_change_pct=turnover_top_avg,
        yesterday_limit_up_avg_change_pct=yesterday_avg,
    )


def classify_market_cycle_from_sentiment(sentiment: MarketSentiment) -> str:
    if sentiment.limit_up_count >= 80 or (sentiment.limit_up_count >= 50 and sentiment.positive_ratio >= 0.65):
        return "高潮"
    if sentiment.limit_up_count <= 10 and sentiment.positive_ratio < 0.35:
        return "冰点"
    if sentiment.limit_up_count <= 20 and sentiment.avg_change_pct < -0.5:
        return "退潮"
    if sentiment.limit_up_count >= 35 and sentiment.positive_ratio >= 0.55:
        return "上升"
    if sentiment.limit_up_count >= 20 and sentiment.avg_change_pct >= 0:
        return "修复"
    return "分歧"


def _yesterday_limit_up_today_changes(history_by_code: Mapping[str, Sequence[DailyBar]]):
    changes = []
    for history in history_by_code.values():
        bars = list(history)
        if len(bars) < 2:
            continue
        yesterday = bars[-2]
        today = bars[-1]
        if yesterday.change_pct >= 9.8:
            changes.append(today.change_pct)
    return changes
