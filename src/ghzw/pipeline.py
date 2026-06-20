from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from .akshare_client import AkshareHistoryProvider, AkshareLimitUpSnapshotProvider
from .analysis import (
    assess_roles,
    assign_roles,
    classify_stage,
    classify_theme_tiers,
    find_limit_up_candidates,
    limit_threshold_for,
    plan_next_action,
    select_turnover_top,
    summarize_themes,
)
from .cache import DailyBarCache
from .cninfo_client import CninfoEvidenceProvider
from .eastmoney_client import EastmoneyEvidenceProvider
from .history import CachedHistoryProvider
from .models import CapitalFlow, DailyRecord, PlateMembership, RoleAssessment, StageTag, StockSnapshot
from .reason_logic import build_reason_logic
from .reasons import infer_suspected_reason, load_local_reasons, resolve_reason_details
from .forum_sources import ForumCollection, collect_forum_discussions
from .reporting import build_report_context, load_recent_daily_records, render_html_report, write_html_report
from .sentiment import classify_market_cycle_from_sentiment, compute_market_sentiment
from .themes import clean_plate_memberships, refine_industry_names, select_core_theme


@dataclass(frozen=True)
class DailyPipelineResult:
    records: List[DailyRecord]
    output_path: Optional[Path] = None
    warning: str = ""
    report_path: Optional[Path] = None
    report_warning: str = ""


def build_daily_records(
    trade_date: date,
    snapshots: Sequence[StockSnapshot],
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    history_by_code: Mapping[str, Sequence],
    capital_flow_by_code: Mapping[str, CapitalFlow],
    turnover_limit: int = 30,
    local_reasons: Sequence = (),
    online_reasons: Sequence = (),
) -> List[DailyRecord]:
    limit_ups = find_limit_up_candidates(snapshots)
    turnover_top = select_turnover_top(snapshots, turnover_limit)
    limit_up_codes = {snapshot.code for snapshot in limit_ups}
    turnover_top_codes = {snapshot.code for snapshot in turnover_top}
    target_codes = limit_up_codes | turnover_top_codes
    snapshot_by_code = {snapshot.code: snapshot for snapshot in snapshots}
    target_snapshots = [snapshot_by_code[code] for code in target_codes if code in snapshot_by_code]
    cleaned_memberships_by_code = {
        code: clean_plate_memberships(memberships)
        for code, memberships in memberships_by_code.items()
    }

    theme_summaries = summarize_themes(snapshots, cleaned_memberships_by_code, limit_up_codes)
    theme_rank_by_plate = {summary.plate_code: index + 1 for index, summary in enumerate(theme_summaries)}
    theme_tier_by_plate = classify_theme_tiers(theme_summaries)
    best_theme_rank_by_code = _best_theme_rank_by_code(cleaned_memberships_by_code, theme_rank_by_plate)
    best_theme_tier_by_code = _best_theme_tier_by_code(cleaned_memberships_by_code, theme_rank_by_plate, theme_tier_by_plate)
    core_theme_by_code = {
        code: select_core_theme(cleaned_memberships_by_code.get(code, []), theme_rank_by_plate)
        for code in target_codes
    }

    stage_by_code: Dict[str, StageTag] = {
        code: classify_stage(
            history_by_code.get(code, []),
            limit_threshold=limit_threshold_for(snapshot_by_code[code]) if code in snapshot_by_code else None,
        )
        for code in target_codes
    }
    sentiment = compute_market_sentiment(snapshots, stage_by_code, history_by_code, turnover_limit=turnover_limit)
    market_cycle = classify_market_cycle_from_sentiment(sentiment)
    roles_by_code = _role_assessments_by_code(
        target_snapshots,
        cleaned_memberships_by_code,
        stage_by_code,
        theme_tier_by_plate,
    )

    records: List[DailyRecord] = []
    for code in sorted(target_codes):
        snapshot = snapshot_by_code.get(code)
        if snapshot is None:
            continue
        memberships = list(memberships_by_code.get(code, []))
        cleaned_memberships = list(cleaned_memberships_by_code.get(code, []))
        flow = capital_flow_by_code.get(code, CapitalFlow(code=code))
        theme_tier = best_theme_tier_by_code.get(code, "未匹配")
        role_assessment = roles_by_code.get(code, RoleAssessment(role="杂毛", score=0.0, basis="未匹配题材"))
        stage = stage_by_code.get(code, StageTag(labels=[]))
        core_theme = core_theme_by_code.get(code, "未匹配")
        record_type = _record_type(code, limit_up_codes, turnover_top_codes, turnover_limit=turnover_limit)
        next_action = plan_next_action(market_cycle, role_assessment.role, theme_tier)
        suspected_reason = infer_suspected_reason(
            core_theme=core_theme,
            theme_tier=theme_tier,
            record_type=record_type,
            stage=stage,
            main_net_inflow=flow.main_net_inflow,
        )
        candidate_reasons = _matching_reasons(trade_date, code, local_reasons, online_reasons)
        reason_logic = build_reason_logic(
            evidences=candidate_reasons,
            suspected_reason=suspected_reason,
            core_theme=core_theme,
            theme_tier=theme_tier,
            record_type=record_type,
            stage=stage,
            main_net_inflow=flow.main_net_inflow,
        )
        reason = resolve_reason_details(trade_date, code, local_reasons, online_reasons, suspected_reason)
        reason_summary = reason_logic.evidence_summary or reason.reason
        records.append(
            DailyRecord(
                date=trade_date.isoformat(),
                code=code,
                name=snapshot.name,
                record_type=record_type,
                close_price=snapshot.last_price,
                prev_close_price=snapshot.prev_close_price,
                change_pct=snapshot.change_pct,
                turnover=snapshot.turnover,
                turnover_rate=snapshot.turnover_rate,
                volume_ratio=snapshot.volume_ratio,
                industries=refine_industry_names(memberships),
                concepts=_join_plates(cleaned_memberships, "CONCEPT"),
                market_cycle=market_cycle,
                theme_rank=best_theme_rank_by_code.get(code),
                theme_tier=theme_tier,
                role=role_assessment.role,
                stage=stage.summary,
                next_action=next_action,
                net_inflow=flow.net_inflow,
                main_net_inflow=flow.main_net_inflow,
                reason_type=reason_summary,
                review=_review(snapshot, memberships, stage, role_assessment.role, market_cycle, theme_tier, next_action, core_theme),
                core_theme=core_theme,
                reason_logic=reason_logic.logic,
                driver_type=reason_logic.driver_type,
                market_sentiment=sentiment.summary,
                role_score=role_assessment.score,
                role_basis=role_assessment.basis,
                reason_source=reason_logic.source or reason.source,
                evidence_time=reason_logic.evidence_time or reason.evidence_time,
                limit_up_boards=_limit_up_board_label(record_type, stage, candidate_reasons),
            )
        )
    return sorted(records, key=lambda item: (item.record_type != "两者都是", -item.change_pct, -item.turnover))


def write_csv(records: Sequence[DailyRecord], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(records[0].as_dict().keys()) if records else [
        "日期",
        "代码",
        "名称",
        "类型",
        "涨停板数",
        "收盘价",
        "昨收",
        "涨幅",
        "成交额(亿元)",
        "换手率",
        "量比",
        "所属行业",
        "所属概念",
        "核心题材",
        "市场阶段",
        "市场情绪",
        "题材强度排名",
        "题材层级",
        "个股地位",
        "角色分",
        "角色依据",
        "阶段",
        "次日计划",
        "资金流-净流入",
        "资金流-主力净流入",
        "上涨逻辑",
        "驱动类型",
        "上涨原因",
        "原因来源",
        "证据时间",
        "一句话复盘",
    ]
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_dict())
    return output_path


def run_daily_pipeline(
    client,
    trade_date: date,
    output_dir: Path,
    turnover_limit: int = 30,
    cache_dir: Optional[Path] = None,
    history_provider=None,
    historical_snapshot_provider=None,
    reason_path: Optional[Path] = None,
    evidence_source: str = "auto",
    generate_html_report: bool = False,
    forum_search_enabled: bool = False,
    collect_capital_flow: bool = True,
) -> DailyPipelineResult:
    stock_pool = client.get_stock_pool()
    snapshot_templates = client.get_snapshots(stock_pool)
    if history_provider is None:
        history_provider = client
        if cache_dir is not None:
            history_provider = CachedHistoryProvider(
                cache=DailyBarCache(cache_dir),
                primary_provider=client,
                fallback_provider=AkshareHistoryProvider(),
                disable_fallback_on_error=False,
            )
    uses_historical_snapshot = _should_use_historical_snapshot(trade_date)
    snapshots = snapshot_templates
    warning = ""
    if uses_historical_snapshot:
        snapshot_history = {
            code: history_provider.get_history(code, days=3, end=trade_date)
            for code in stock_pool
        }
        snapshots = _snapshots_from_history(snapshot_templates, snapshot_history, trade_date)
        if not has_enough_historical_snapshot_coverage(len(snapshots), len(stock_pool)):
            provider = historical_snapshot_provider or AkshareLimitUpSnapshotProvider()
            snapshots = provider.get_limit_up_snapshots(trade_date, stock_pool)
            turnover_limit = 0
            warning = "历史轻量模式：全市场历史K线覆盖不足，已改用历史涨停池；本次不含成交额TopN。"
        ensure_historical_snapshot_coverage(trade_date, len(snapshots), len(stock_pool))
    limit_ups = find_limit_up_candidates(snapshots)
    turnover_top = select_turnover_top(snapshots, turnover_limit)
    target_codes = sorted({item.code for item in limit_ups} | {item.code for item in turnover_top})
    memberships = client.get_owner_plates(target_codes)
    history = {code: history_provider.get_history(code, end=trade_date) for code in target_codes}
    if uses_historical_snapshot or not collect_capital_flow:
        capital_flows = {code: CapitalFlow(code=code) for code in target_codes}
    else:
        capital_flows = client.get_capital_flows(target_codes)
    if reason_path is None:
        reason_path = Path("data/reasons/reasons.csv")
    local_reasons = load_local_reasons(reason_path)
    target_names_by_code = {snapshot.code: snapshot.name for snapshot in snapshots if snapshot.code in target_codes}
    online_reasons = _collect_online_reasons(evidence_source, client, trade_date, target_codes, target_names_by_code)
    records = build_daily_records(
        trade_date=trade_date,
        snapshots=snapshots,
        memberships_by_code=memberships,
        history_by_code=history,
        capital_flow_by_code=capital_flows,
        turnover_limit=turnover_limit,
        local_reasons=local_reasons,
        online_reasons=online_reasons,
    )
    output_path = write_csv(records, output_dir / ("%s-daily-review.csv" % trade_date.isoformat()))
    report_path = None
    report_warning = ""
    if generate_html_report:
        try:
            forum_collection = collect_forum_discussions(trade_date, records, enabled=forum_search_enabled)
        except Exception as exc:
            forum_collection = ForumCollection([], "论坛线索未获取：%s" % exc)
        recent_records_by_date, skipped_history_files = load_recent_daily_records(output_dir, trade_date)
        context = build_report_context(
            trade_date=trade_date,
            records=records,
            recent_records_by_date=recent_records_by_date,
            forum_collection=forum_collection,
            skipped_history_files=skipped_history_files,
        )
        report_path = write_html_report(
            render_html_report(context),
            output_dir / ("%s-daily-report.html" % trade_date.isoformat()),
        )
        report_warning = forum_collection.warning
    return DailyPipelineResult(
        records=records,
        output_path=output_path,
        warning=warning,
        report_path=report_path,
        report_warning=report_warning,
    )


def _should_use_historical_snapshot(trade_date: date) -> bool:
    return trade_date < date.today()


def _snapshots_from_history(
    snapshot_templates: Sequence[StockSnapshot],
    history_by_code: Mapping[str, Sequence],
    trade_date: date,
) -> List[StockSnapshot]:
    template_by_code = {snapshot.code: snapshot for snapshot in snapshot_templates}
    snapshots: List[StockSnapshot] = []
    trade_date_text = trade_date.isoformat()
    for code, bars in history_by_code.items():
        ordered_bars = sorted([bar for bar in bars if bar.date <= trade_date_text], key=lambda bar: bar.date)
        current = next((bar for bar in reversed(ordered_bars) if bar.date == trade_date_text), None)
        if current is None:
            continue
        previous = next((bar for bar in reversed(ordered_bars) if bar.date < trade_date_text), None)
        template = template_by_code.get(code, StockSnapshot(code=code, name=code))
        prev_close = previous.close if previous is not None else _prev_close_from_change(current)
        snapshots.append(
            StockSnapshot(
                code=code,
                name=template.name,
                last_price=current.close,
                prev_close_price=prev_close,
                high_price=current.high,
                turnover=current.turnover,
                turnover_rate=current.turnover_rate,
                volume_ratio=0.0,
                market_val=template.market_val,
                pe_ttm=template.pe_ttm,
                pb_rate=template.pb_rate,
                change_rate=current.change_pct,
                is_st=template.is_st,
                is_suspended=current.volume <= 0 and current.turnover <= 0,
                lot_size=template.lot_size,
            )
        )
    return snapshots


def ensure_historical_snapshot_coverage(trade_date: date, snapshot_count: int, stock_pool_count: int) -> None:
    if snapshot_count > 0:
        return
    raise ValueError(
        "历史K线覆盖不足：%s 未获取到可用股票。"
        "请确认历史数据源可用，重启工作台后重新生成。"
        % trade_date.isoformat()
    )


def has_enough_historical_snapshot_coverage(snapshot_count: int, stock_pool_count: int) -> bool:
    if stock_pool_count < 500:
        return True
    coverage = snapshot_count / stock_pool_count
    return snapshot_count >= 500 and coverage >= 0.5


def _prev_close_from_change(bar) -> float:
    if bar.change_pct <= -99.99:
        return 0.0
    denominator = 1 + bar.change_pct / 100
    if denominator <= 0:
        return 0.0
    return bar.close / denominator


def _roles_by_code(
    snapshots: Sequence[StockSnapshot],
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    stage_by_code: Mapping[str, StageTag],
) -> Dict[str, str]:
    roles: Dict[str, str] = {}
    groups: Dict[str, List[StockSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        concepts = [item for item in memberships_by_code.get(snapshot.code, []) if item.plate_type.upper() == "CONCEPT"]
        if not concepts:
            groups["__NO_CONCEPT__"].append(snapshot)
            continue
        for concept in concepts:
            groups[concept.code].append(snapshot)
    for group in groups.values():
        roles.update(assign_roles(group, stage_by_code))
    return roles


def _matching_reasons(trade_date: date, code: str, local_reasons: Sequence, online_reasons: Sequence):
    date_text = trade_date.isoformat()
    return [
        evidence for evidence in list(local_reasons) + list(online_reasons)
        if getattr(evidence, "date", "") == date_text and getattr(evidence, "code", "") == code
    ]


def _role_assessments_by_code(
    snapshots: Sequence[StockSnapshot],
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    stage_by_code: Mapping[str, StageTag],
    theme_tier_by_plate: Mapping[str, str],
) -> Dict[str, RoleAssessment]:
    assessments_by_code: Dict[str, RoleAssessment] = {}
    groups: Dict[str, List[StockSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        concepts = [item for item in memberships_by_code.get(snapshot.code, []) if item.plate_type.upper() == "CONCEPT"]
        if not concepts:
            groups["__NO_CONCEPT__"].append(snapshot)
            continue
        for concept in concepts:
            groups[concept.code].append(snapshot)

    for plate_code, group in groups.items():
        theme_tier = theme_tier_by_plate.get(plate_code, "未匹配")
        assessments = assess_roles(group, stage_by_code, theme_tier=theme_tier)
        for code, assessment in assessments.items():
            current = assessments_by_code.get(code)
            if current is None or assessment.score > current.score:
                assessments_by_code[code] = assessment
    return assessments_by_code


def _collect_online_reasons(
    evidence_source: str,
    client,
    trade_date: date,
    target_codes: Sequence[str],
    target_names_by_code: Mapping[str, str] | None = None,
):
    source = evidence_source or "auto"
    if source in {"none", "local"}:
        return []
    reasons = []
    if source in {"auto", "futu"} and hasattr(client, "get_reason_evidence"):
        try:
            reasons.extend(client.get_reason_evidence(trade_date, target_codes))
        except Exception as exc:
            print("Warning: Futu evidence collection failed: %s" % exc)
    if source in {"auto", "cninfo"}:
        try:
            reasons.extend(CninfoEvidenceProvider().get_reasons(trade_date, target_codes))
        except Exception as exc:
            print("Warning: CNINFO evidence collection failed: %s" % exc)
    if source in {"auto", "eastmoney", "news", "billboard"}:
        provider = EastmoneyEvidenceProvider()
        try:
            if source == "news":
                for code in target_codes:
                    reasons.extend(provider.get_news(trade_date, code, (target_names_by_code or {}).get(code, "")))
            elif source == "billboard":
                reasons.extend(provider.get_billboard(trade_date, target_codes))
            else:
                reasons.extend(provider.get_reasons(trade_date, target_codes, target_names_by_code or {}))
        except Exception as exc:
            print("Warning: Eastmoney evidence collection failed: %s" % exc)
    return reasons


def _best_theme_rank_by_code(
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    theme_rank_by_plate: Mapping[str, int],
) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for code, memberships in memberships_by_code.items():
        ranks = [theme_rank_by_plate[item.code] for item in memberships if item.code in theme_rank_by_plate]
        if ranks:
            result[code] = min(ranks)
    return result


def _best_theme_tier_by_code(
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    theme_rank_by_plate: Mapping[str, int],
    theme_tier_by_plate: Mapping[str, str],
) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for code, memberships in memberships_by_code.items():
        ranked = [
            (theme_rank_by_plate[item.code], theme_tier_by_plate[item.code])
            for item in memberships
            if item.code in theme_rank_by_plate and item.code in theme_tier_by_plate
        ]
        if ranked:
            result[code] = sorted(ranked, key=lambda item: item[0])[0][1]
    return result


def _limit_up_board_label(record_type: str, stage: StageTag, evidences: Sequence) -> str:
    if record_type not in {"涨停", "两者都是"}:
        return ""
    if stage.board_streak > 0:
        return "%d板" % stage.board_streak
    evidence_streak = _board_streak_from_evidences(evidences)
    if evidence_streak > 0:
        return "%d板" % evidence_streak
    return "1板"


def _board_streak_from_evidences(evidences: Sequence) -> int:
    streaks: List[int] = []
    for evidence in evidences:
        text = "%s %s" % (getattr(evidence, "summary", ""), getattr(evidence, "reason_type", ""))
        streaks.extend(int(match) for match in re.findall(r"(\d+)连板", text))
    return max(streaks) if streaks else 0


def _record_type(code: str, limit_up_codes: set, turnover_top_codes: set, turnover_limit: int = 30) -> str:
    if code in limit_up_codes and code in turnover_top_codes:
        return "两者都是"
    if code in limit_up_codes:
        return "涨停"
    return "成交额Top%d" % turnover_limit


def _join_plates(memberships: Sequence[PlateMembership], plate_type: str) -> str:
    names = []
    for item in memberships:
        if item.plate_type.upper() == plate_type and item.name not in names:
            names.append(item.name)
    return "、".join(names)


def _review(
    snapshot: StockSnapshot,
    memberships: Sequence[PlateMembership],
    stage: Optional[StageTag],
    role: str,
    market_cycle: str,
    theme_tier: str,
    next_action: str,
    core_theme: str,
) -> str:
    concept = core_theme if core_theme != "未匹配" else "未匹配题材"
    stage_text = stage.summary if stage else "未分类"
    return "%s上涨%.2f%%，市场%s，属于%s/%s，阶段为%s，地位%s，计划%s。" % (
        snapshot.name,
        snapshot.change_pct,
        market_cycle,
        concept,
        theme_tier,
        stage_text,
        role,
        next_action,
    )
