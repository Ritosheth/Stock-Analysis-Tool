from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Dict, Iterable, List, Mapping, Sequence, Set

from .models import DailyBar, PlateMembership, RoleAssessment, StageTag, StockSnapshot, ThemeSummary


def limit_threshold_for(snapshot: StockSnapshot) -> int:
    if snapshot.is_st or _looks_like_st_name(snapshot.name):
        return 5
    if snapshot.code.startswith("SZ.30") or snapshot.code.startswith("SH.688"):
        return 20
    return 10


def candidate_floor(threshold: int) -> float:
    if threshold == 20:
        return 19.5
    if threshold == 5:
        return 4.8
    return 9.8


def find_limit_up_candidates(snapshots: Iterable[StockSnapshot]) -> List[StockSnapshot]:
    result: List[StockSnapshot] = []
    for snapshot in snapshots:
        if snapshot.is_suspended or snapshot.prev_close_price <= 0:
            continue
        threshold = limit_threshold_for(snapshot)
        if snapshot.change_pct + 1e-9 >= candidate_floor(threshold):
            result.append(replace(snapshot, limit_threshold=threshold))
    return result


def select_turnover_top(snapshots: Iterable[StockSnapshot], limit: int = 30) -> List[StockSnapshot]:
    tradable = [snapshot for snapshot in snapshots if not snapshot.is_suspended]
    return sorted(tradable, key=lambda item: item.turnover, reverse=True)[:limit]


def summarize_themes(
    snapshots: Sequence[StockSnapshot],
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    limit_up_codes: Set[str],
) -> List[ThemeSummary]:
    snapshot_by_code = {snapshot.code: snapshot for snapshot in snapshots}
    grouped: Dict[str, List[StockSnapshot]] = defaultdict(list)
    plate_meta: Dict[str, PlateMembership] = {}

    for code, memberships in memberships_by_code.items():
        snapshot = snapshot_by_code.get(code)
        if snapshot is None:
            continue
        for membership in memberships:
            if membership.plate_type.upper() != "CONCEPT":
                continue
            grouped[membership.code].append(snapshot)
            plate_meta[membership.code] = membership

    summaries: List[ThemeSummary] = []
    for plate_code, members in grouped.items():
        meta = plate_meta[plate_code]
        total_turnover = sum(member.turnover for member in members)
        summaries.append(
            ThemeSummary(
                plate_code=plate_code,
                plate_name=meta.name,
                plate_type=meta.plate_type,
                limit_up_count=sum(1 for member in members if member.code in limit_up_codes),
                avg_change_pct=sum(member.change_pct for member in members) / len(members),
                total_turnover=total_turnover,
                member_codes=[member.code for member in members],
            )
        )

    return sorted(
        summaries,
        key=lambda item: (item.limit_up_count, item.avg_change_pct, item.total_turnover),
        reverse=True,
    )


def classify_market_cycle(snapshots: Sequence[StockSnapshot], limit_up_count: int) -> str:
    tradable = [snapshot for snapshot in snapshots if not snapshot.is_suspended]
    if not tradable:
        return "未知"

    positive_ratio = sum(1 for snapshot in tradable if snapshot.change_pct > 0) / len(tradable)
    avg_change = sum(snapshot.change_pct for snapshot in tradable) / len(tradable)

    if limit_up_count >= 80 or (limit_up_count >= 50 and positive_ratio >= 0.65):
        return "高潮"
    if limit_up_count <= 10 and positive_ratio < 0.35:
        return "冰点"
    if limit_up_count <= 20 and avg_change < -0.5:
        return "退潮"
    if limit_up_count >= 35 and positive_ratio >= 0.55:
        return "上升"
    if limit_up_count >= 20 and avg_change >= 0:
        return "修复"
    return "分歧"


def classify_theme_tiers(theme_summaries: Sequence[ThemeSummary]) -> Dict[str, str]:
    tiers: Dict[str, str] = {}
    for rank, summary in enumerate(theme_summaries, start=1):
        if summary.limit_up_count >= 3 and rank <= 2:
            tiers[summary.plate_code] = "主线"
        elif summary.limit_up_count >= 1 and rank <= 5:
            tiers[summary.plate_code] = "支线"
        elif summary.avg_change_pct > 0:
            tiers[summary.plate_code] = "轮动"
        else:
            tiers[summary.plate_code] = "退潮老题材"
    return tiers


def classify_stage(history: Sequence[DailyBar], limit_threshold: int | None = None) -> StageTag:
    if not history:
        return StageTag(labels=["无K线"])

    bars = list(history)
    latest = bars[-1]
    board_streak = _count_board_streak(bars, limit_threshold=limit_threshold)
    previous_20 = bars[-21:-1] if len(bars) > 1 else []
    previous_60 = bars[-61:-1] if len(bars) >= 61 else []
    is_20d_high = bool(previous_20) and latest.close >= max(bar.close for bar in previous_20)
    is_60d_high = bool(previous_60) and latest.close >= max(bar.close for bar in previous_60)
    is_volume_expanded = _is_volume_expanded(bars)

    labels: List[str] = []
    if board_streak >= 2:
        labels.append("连板")
    elif board_streak == 1:
        labels.append("首板")

    if is_60d_high:
        labels.append("创60日新高")
    elif is_20d_high:
        labels.append("创20日新高")

    if is_volume_expanded:
        labels.append("放量")

    if not labels:
        labels.append(_shape_label(bars))

    return StageTag(
        labels=labels,
        board_streak=board_streak,
        is_20d_high=is_20d_high,
        is_60d_high=is_60d_high,
        is_volume_expanded=is_volume_expanded,
    )


def assign_roles(snapshots: Sequence[StockSnapshot], stage_by_code: Mapping[str, StageTag]) -> Dict[str, str]:
    return {code: assessment.role for code, assessment in assess_roles(snapshots, stage_by_code).items()}


def assess_roles(
    snapshots: Sequence[StockSnapshot],
    stage_by_code: Mapping[str, StageTag],
    theme_tier: str = "未匹配",
) -> Dict[str, RoleAssessment]:
    if not snapshots:
        return {}

    capacity_core = max(snapshots, key=lambda item: item.turnover)
    market_core = max(snapshots, key=lambda item: (item.market_val, item.turnover))
    leader = max(snapshots, key=lambda item: _leadership_score(item, stage_by_code.get(item.code, StageTag(labels=[])), theme_tier))
    result: Dict[str, RoleAssessment] = {}
    for snapshot in snapshots:
        stage = stage_by_code.get(snapshot.code, StageTag(labels=[]))
        score, basis_items = _role_score_with_basis(snapshot, stage, theme_tier)
        role = _base_role(snapshot)
        if _is_ipo_first_day(snapshot):
            role = "IPO首日龙头"
            score += 20
            basis_items.append("新股首日独立周期")
        elif snapshot.code == leader.code and (stage.board_streak > 0 or snapshot.change_pct >= 9.8):
            role = "龙头"
            basis_items.append("题材强度最高")
        elif snapshot.code == capacity_core.code and snapshot.change_pct > 0:
            role = "容量核心"
            basis_items.append("题材内成交额最高")
        elif snapshot.code == market_core.code and snapshot.market_val > 0 and snapshot.change_pct > 0:
            role = "中军"
            basis_items.append("题材内市值最高")
        elif snapshot.change_pct >= 6.0 and snapshot.turnover >= capacity_core.turnover * 0.15:
            role = "补涨"
            basis_items.append("涨幅较强")
        elif snapshot.change_pct <= 0:
            role = "杂毛"
            basis_items.append("涨幅偏弱")
        result[snapshot.code] = RoleAssessment(role=role, score=round(score, 2), basis="、".join(basis_items))
    return result


def plan_next_action(market_cycle: str, role: str, theme_tier: str) -> str:
    if market_cycle in {"退潮", "冰点"}:
        return "退潮空仓" if market_cycle == "退潮" else "冰点轻仓试错"
    if market_cycle == "高潮" and role in {"跟风", "杂毛", "补涨"}:
        return "高潮后排不追"
    if market_cycle in {"分歧", "修复"} and role == "龙头" and theme_tier == "主线":
        return "核心分歧低吸"
    if market_cycle in {"上升", "修复"} and role in {"龙头", "容量核心"} and theme_tier == "主线":
        return "转强确认加仓"
    if theme_tier in {"支线", "轮动"} and role in {"补涨", "跟风"}:
        return "轻仓试错"
    if role in {"杂毛", "跟风"}:
        return "去弱留强"
    return "观察验证"


def _count_board_streak(bars: Sequence[DailyBar], limit_threshold: int | None = None) -> int:
    streak = 0
    threshold = limit_threshold or _limit_threshold_for_code(bars[-1].code if bars else "")
    floor = candidate_floor(threshold)
    for bar in reversed(bars):
        if bar.change_pct >= floor:
            streak += 1
            continue
        break
    return streak


def _limit_threshold_for_code(code: str) -> int:
    if code.startswith("SZ.30") or code.startswith("SH.688"):
        return 20
    return 10


def _looks_like_st_name(name: str) -> bool:
    upper_name = name.upper().strip()
    return upper_name.startswith("ST") or upper_name.startswith("*ST")


def _is_ipo_first_day(snapshot: StockSnapshot) -> bool:
    return snapshot.name.strip().upper().startswith("N") and snapshot.change_pct >= 44.0


def _base_role(snapshot: StockSnapshot) -> str:
    if snapshot.change_pct <= 0:
        return "杂毛"
    if snapshot.change_pct >= 6.0:
        return "补涨"
    return "跟风"


def _role_score(snapshot: StockSnapshot, stage: StageTag, theme_tier: str) -> float:
    return _role_score_with_basis(snapshot, stage, theme_tier)[0]


def _leadership_score(snapshot: StockSnapshot, stage: StageTag, theme_tier: str) -> float:
    score = 0.0
    score += stage.board_streak * 15
    if snapshot.change_pct >= 9.8:
        score += 20
    elif snapshot.change_pct >= 6:
        score += 8
    if 5 <= snapshot.turnover_rate <= 25:
        score += 5
    if snapshot.volume_ratio >= 1.5:
        score += 5
    if theme_tier == "主线":
        score += 4
    elif theme_tier in {"支线", "轮动"}:
        score += 2
    return score


def _role_score_with_basis(snapshot: StockSnapshot, stage: StageTag, theme_tier: str):
    score = 0.0
    basis: List[str] = []
    if stage.board_streak > 0:
        score += stage.board_streak * 12
        basis.append("连板%d" % stage.board_streak)
    if snapshot.change_pct >= 9.8:
        score += 20
        basis.append("涨停强度")
    elif snapshot.change_pct >= 6:
        score += 10
        basis.append("涨幅%.1f%%" % snapshot.change_pct)
    elif snapshot.change_pct > 0:
        score += 3
        basis.append("红盘")
    else:
        score -= 8

    if snapshot.turnover > 0:
        score += min(snapshot.turnover / 100_000_000, 12)
        basis.append("成交活跃")
    if 3 <= snapshot.turnover_rate <= 20:
        score += 4
        basis.append("换手适中")
    if snapshot.volume_ratio >= 1.5:
        score += 4
        basis.append("量比放大")
    if snapshot.market_val >= 5_000_000_000:
        score += 4
        basis.append("市值中军")
    if theme_tier == "主线":
        score += 5
        basis.append("主线题材")
    elif theme_tier in {"支线", "轮动"}:
        score += 2
        basis.append(theme_tier)
    return score, basis


def _is_volume_expanded(bars: Sequence[DailyBar]) -> bool:
    if len(bars) < 6:
        return False
    latest = bars[-1]
    previous = bars[-6:-1]
    avg_turnover = sum(bar.turnover for bar in previous) / len(previous)
    return avg_turnover > 0 and latest.turnover >= avg_turnover * 2


def _shape_label(bars: Sequence[DailyBar]) -> str:
    if len(bars) < 20:
        return "观察"
    latest = bars[-1]
    recent_low = min(bar.close for bar in bars[-20:])
    recent_high = max(bar.close for bar in bars[-20:])
    if recent_low > 0 and latest.close <= recent_low * 1.15:
        return "低位启动"
    if latest.close >= recent_high * 0.98:
        return "平台突破"
    return "高位震荡"
