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
from .event_catalog import DailyEvent, build_daily_event_catalog
from .history import CachedHistoryProvider
from .lifecycle import LifecycleRisk, WatchlistEntry, assess_lifecycle_risks, load_watchlist
from .models import CapitalFlow, DailyRecord, PlateMembership, ReasonEvidence, RoleAssessment, StageTag, StockSnapshot
from .reason_logic import build_reason_logic
from .reasons import infer_suspected_reason, load_local_reasons, resolve_reason_details
from .forum_sources import ForumCollection, collect_forum_discussions
from .reporting import build_report_context, load_recent_daily_records, render_html_report, write_html_report
from .sentiment import classify_market_cycle_from_sentiment, compute_market_sentiment
from .themes import clean_plate_memberships, refine_industry_names, select_core_theme
from .theme_hub import (
    FORMAL_THEME_SOURCE,
    FUTU_FALLBACK_THEME_SOURCE,
    FormalThemeClassification,
    load_formal_theme_classifications,
)


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
    watchlist_entries: Sequence[WatchlistEntry] = (),
    daily_events: Sequence[DailyEvent] = (),
    formal_themes_by_code: Mapping[str, Sequence[str]] | None = None,
    formal_classifications_by_code: Mapping[str, FormalThemeClassification] | None = None,
) -> List[DailyRecord]:
    limit_ups = find_limit_up_candidates(snapshots)
    turnover_top = select_turnover_top(snapshots, turnover_limit)
    limit_up_codes = {snapshot.code for snapshot in limit_ups}
    turnover_top_codes = {snapshot.code for snapshot in turnover_top}
    watchlist_by_code = {entry.code: entry for entry in watchlist_entries}
    watchlist_codes = set(watchlist_by_code)
    target_codes = limit_up_codes | turnover_top_codes | watchlist_codes
    snapshot_by_code = {snapshot.code: snapshot for snapshot in snapshots}
    target_snapshots = [snapshot_by_code[code] for code in target_codes if code in snapshot_by_code]
    cleaned_memberships_by_code = {
        code: clean_plate_memberships(memberships)
        for code, memberships in memberships_by_code.items()
    }
    reasons_by_code = {
        code: _matching_reasons(trade_date, code, local_reasons, online_reasons)
        for code in target_codes
    }
    futu_industry_text_by_code = {
        code: refine_industry_names(memberships_by_code.get(code, []))
        for code in target_codes
    }
    futu_concepts_by_code = {
        code: _join_plates(cleaned_memberships_by_code.get(code, []), "CONCEPT")
        for code in target_codes
    }
    daily_events = _merge_daily_events(
        daily_events,
        _infer_daily_events_from_contexts(
            trade_date=trade_date,
            memberships_by_code=cleaned_memberships_by_code,
            industry_text_by_code=futu_industry_text_by_code,
            reasons_by_code=reasons_by_code,
        ),
    )

    theme_summaries = summarize_themes(snapshots, cleaned_memberships_by_code, limit_up_codes)
    theme_rank_by_plate = {summary.plate_code: index + 1 for index, summary in enumerate(theme_summaries)}
    theme_tier_by_plate = classify_theme_tiers(theme_summaries)
    formal_themes_by_code = formal_themes_by_code or {}
    formal_classifications = dict(formal_classifications_by_code or {})
    for code, themes in formal_themes_by_code.items():
        if code not in formal_classifications and themes:
            formal_classifications[code] = FormalThemeClassification(
                industries=[], concepts=list(themes)
            )
    classification_by_code = {
        code: formal_classifications.get(code)
        for code in target_codes
    }
    raw_theme_by_code = {
        code: (
            classification_by_code[code].raw_theme
            if classification_by_code.get(code) is not None
            else select_core_theme(
                cleaned_memberships_by_code.get(code, []),
                theme_rank_by_plate,
                industry_text=futu_industry_text_by_code.get(code, ""),
            )
        )
        for code in target_codes
    }
    reclassification_by_code = {
        code: (
            {
                "theme": classification_by_code[code].core_theme,
                "driver": "A股主题库正式分类",
                "score": 100.0,
                "level": "正式",
                "reason": "采用A股主题库已维护的股票—主题关系。",
            }
            if classification_by_code.get(code)
            else _reclassify_theme(
                code=code,
                raw_theme=raw_theme_by_code.get(code, "未匹配"),
                memberships=cleaned_memberships_by_code.get(code, []),
                industry_text=futu_industry_text_by_code.get(code, ""),
                evidences=reasons_by_code.get(code, []),
                daily_events=daily_events,
            )
        )
        for code in target_codes
    }
    core_theme_by_code = {
        code: (
            classification.core_theme
            if (classification := classification_by_code.get(code)) is not None
            else raw_theme_by_code.get(code, "未匹配")
        )
        for code in target_codes
    }
    theme_source_by_code = {
        code: FORMAL_THEME_SOURCE if classification_by_code.get(code) else FUTU_FALLBACK_THEME_SOURCE
        for code in target_codes
    }
    industry_text_by_code = {
        code: (
            "、".join(classification.industries)
            if (classification := classification_by_code.get(code)) is not None and classification.industries
            else futu_industry_text_by_code.get(code, "")
        )
        for code in target_codes
    }
    concepts_by_code = {
        code: (
            "、".join(classification.concepts)
            if (classification := classification_by_code.get(code)) is not None and classification.concepts
            else futu_concepts_by_code.get(code, "")
        )
        for code in target_codes
    }
    for code, entry in watchlist_by_code.items():
        if entry.core_theme and core_theme_by_code.get(code, "未匹配") == "未匹配":
            core_theme_by_code[code] = entry.core_theme
    selected_theme_plate_by_code = _selected_theme_plate_by_code(cleaned_memberships_by_code, core_theme_by_code, raw_theme_by_code)
    selected_theme_rank_by_code = {
        code: theme_rank_by_plate[plate_code]
        for code, plate_code in selected_theme_plate_by_code.items()
        if plate_code in theme_rank_by_plate
    }
    selected_theme_tier_by_code = {
        code: theme_tier_by_plate[plate_code]
        for code, plate_code in selected_theme_plate_by_code.items()
        if plate_code in theme_tier_by_plate
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
        selected_theme_plate_by_code,
    )
    lifecycle_by_code = assess_lifecycle_risks(target_snapshots, history_by_code, core_theme_by_code)

    records: List[DailyRecord] = []
    for code in sorted(target_codes):
        snapshot = snapshot_by_code.get(code)
        if snapshot is None:
            continue
        memberships = list(memberships_by_code.get(code, []))
        cleaned_memberships = list(cleaned_memberships_by_code.get(code, []))
        flow = capital_flow_by_code.get(code, CapitalFlow(code=code))
        theme_tier = selected_theme_tier_by_code.get(code, "未匹配")
        role_assessment = roles_by_code.get(code, RoleAssessment(role="杂毛", score=0.0, basis="未匹配题材"))
        stage = stage_by_code.get(code, StageTag(labels=[]))
        core_theme = core_theme_by_code.get(code, "未匹配")
        reclassification = reclassification_by_code.get(code, {})
        record_type = _record_type(code, limit_up_codes, turnover_top_codes, watchlist_codes, turnover_limit=turnover_limit)
        next_action = plan_next_action(market_cycle, role_assessment.role, theme_tier)
        lifecycle = lifecycle_by_code.get(code)
        watchlist_entry = watchlist_by_code.get(code)
        suspected_reason = infer_suspected_reason(
            core_theme=core_theme,
            theme_tier=theme_tier,
            record_type=record_type,
            stage=stage,
            main_net_inflow=flow.main_net_inflow,
        )
        candidate_reasons = reasons_by_code.get(code, [])
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
        risk_level, risk_flags = _assess_record_risk(
            snapshot=snapshot,
            core_theme=core_theme,
            reason_logic=reason_logic.logic,
            candidate_reasons=candidate_reasons,
            lifecycle=lifecycle,
            limit_up_boards=_limit_up_board_label(record_type, stage, candidate_reasons),
        )
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
                industries=industry_text_by_code.get(code, refine_industry_names(memberships)),
                concepts=concepts_by_code.get(code, ""),
                market_cycle=market_cycle,
                theme_rank=selected_theme_rank_by_code.get(code),
                theme_tier=theme_tier,
                role=role_assessment.role,
                stage=stage.summary,
                next_action=next_action,
                net_inflow=flow.net_inflow,
                main_net_inflow=flow.main_net_inflow,
                reason_type=reason_summary,
                review=_review(snapshot, memberships, stage, role_assessment.role, market_cycle, theme_tier, next_action, core_theme),
                core_theme=core_theme,
                theme_classification_source=theme_source_by_code.get(code, FUTU_FALLBACK_THEME_SOURCE),
                raw_theme=raw_theme_by_code.get(code, core_theme),
                reclassified_theme=reclassification.get("theme", core_theme),
                actual_driver=reclassification.get("driver", ""),
                driver_event_id=reclassification.get("event_id", ""),
                theme_match_score=float(reclassification.get("score", 0.0)),
                theme_match_level=reclassification.get("level", ""),
                theme_mismatch_reason=reclassification.get("reason", ""),
                reason_logic=reason_logic.logic,
                driver_type=reason_logic.driver_type,
                market_sentiment=sentiment.summary,
                role_score=role_assessment.score,
                role_basis=role_assessment.basis,
                reason_source=reason_logic.source or reason.source,
                evidence_time=reason_logic.evidence_time or reason.evidence_time,
                limit_up_boards=_limit_up_board_label(record_type, stage, candidate_reasons),
                watchlist_note=watchlist_entry.note if watchlist_entry else "",
                lifecycle_stage=lifecycle.stage if lifecycle else "",
                lifecycle_score=lifecycle.score if lifecycle else 0.0,
                lifecycle_signals=lifecycle.signals if lifecycle else "",
                lifecycle_discipline=lifecycle.discipline if lifecycle else "",
                risk_level=risk_level,
                risk_flags=risk_flags,
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
        "原始题材",
        "核心题材",
        "重分类题材",
        "主导催化",
        "主导事件ID",
        "题材匹配分",
        "题材匹配度",
        "偏差原因",
        "市场阶段",
        "市场情绪",
        "题材强度排名",
        "题材层级",
        "个股地位",
        "角色分",
        "角色依据",
        "阶段",
        "次日计划",
        "观察备注",
        "强转弱阶段",
        "强转弱风险分",
        "强转弱信号",
        "观察纪律",
        "红旗等级",
        "红旗信号",
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
    watchlist_entries = load_watchlist(Path("data/watchlist.csv"))
    watchlist_codes = {entry.code for entry in watchlist_entries}
    snapshot_codes = {snapshot.code for snapshot in snapshots}
    target_codes = sorted(({item.code for item in limit_ups} | {item.code for item in turnover_top} | watchlist_codes) & snapshot_codes)
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
    daily_events = build_daily_event_catalog(trade_date, online_reasons)
    formal_classifications_by_code = load_formal_theme_classifications(target_codes)
    records = build_daily_records(
        trade_date=trade_date,
        snapshots=snapshots,
        memberships_by_code=memberships,
        history_by_code=history,
        capital_flow_by_code=capital_flows,
        turnover_limit=turnover_limit,
        local_reasons=local_reasons,
        online_reasons=online_reasons,
        watchlist_entries=watchlist_entries,
        daily_events=daily_events,
        formal_classifications_by_code=formal_classifications_by_code,
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


def _theme_reason_hint(evidences: Sequence[ReasonEvidence]) -> str:
    texts = []
    for evidence in evidences:
        if getattr(evidence, "confidence", "") == "低":
            continue
        texts.append(str(getattr(evidence, "reason_type", "")))
        texts.append(str(getattr(evidence, "summary", "")))
        texts.append(str(getattr(evidence, "source", "")))
    return " / ".join(text for text in texts if text)


_EVENT_CONTEXT_RULES = {
    "PCB/算力硬件": {
        "theme": "PCB",
        "keywords": ("PCB", "覆铜板", "印制电路板", "电子布", "电子树脂", "交换机", "服务器", "共封装光模块", "数据中心"),
        "strong_keywords": ("元件-PCB概念", "PCB概念", "覆铜板", "服务器", "交换机"),
        "driver_detail": "PCB/算力硬件",
    },
    "油气/地缘冲突": {
        "theme": "油气",
        "keywords": ("油气", "石油", "天然气", "油服", "油改概念", "霍尔木兹", "WTI", "深海科技"),
        "strong_keywords": ("油服工程", "油气", "石油", "天然气", "WTI"),
        "driver_detail": "油气/地缘冲突",
    },
    "机器人/康复辅具政策": {
        "theme": "机器人",
        "keywords": ("机器人", "人形机器人", "康复辅具", "康养机器人", "脑机接口", "优必选", "关节模组"),
        "strong_keywords": ("人形机器人", "康复辅具", "优必选", "关节模组"),
        "driver_detail": "机器人/康复辅具政策",
    },
    "医药/健康中国": {
        "theme": "医药",
        "keywords": ("医药", "创新药", "中药", "医疗器械", "健康中国", "基药目录", "生物医药"),
        "strong_keywords": ("健康中国", "创新药", "医疗器械", "生物医药"),
        "driver_detail": "医药/健康中国",
    },
    "MLCC/被动元件": {
        "theme": "MLCC/被动元件",
        "keywords": ("MLCC", "被动元件", "电容", "铝电解电容"),
        "strong_keywords": ("MLCC", "被动元件", "电容"),
        "driver_detail": "MLCC/被动元件",
    },
    "并购重组/跨界收购": {
        "theme": "并购重组",
        "keywords": ("重组", "并购", "收购", "跨界", "问询", "停牌", "资产注入"),
        "strong_keywords": ("重组", "并购", "收购", "跨界", "问询"),
        "driver_detail": "并购重组/跨界收购",
    },
    "中报/业绩预告": {
        "theme": "中报业绩",
        "keywords": ("中报", "业绩预告", "预增", "扭亏", "净利润", "同比增长"),
        "strong_keywords": ("中报", "业绩预告", "预增", "扭亏"),
        "driver_detail": "中报/业绩预告",
    },
}


def _infer_daily_events_from_contexts(
    trade_date: date,
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    industry_text_by_code: Mapping[str, str],
    reasons_by_code: Mapping[str, Sequence[ReasonEvidence]],
) -> List[DailyEvent]:
    events: List[DailyEvent] = []
    for title, rule in _EVENT_CONTEXT_RULES.items():
        matched_codes = []
        strong_hits = 0
        for code, memberships in memberships_by_code.items():
            concepts = "、".join(item.name for item in memberships if item.plate_type.upper() == "CONCEPT")
            reason_hint = _theme_reason_hint(reasons_by_code.get(code, []))
            context = " / ".join(part for part in [industry_text_by_code.get(code, ""), concepts, reason_hint] if part)
            if any(keyword in context for keyword in rule["keywords"]):
                matched_codes.append(code)
            if any(keyword in context for keyword in rule["strong_keywords"]):
                strong_hits += 1
        if not matched_codes:
            continue
        strength = len(matched_codes) + strong_hits * 1.5
        if strength < 3:
            continue
        events.append(
            DailyEvent(
                event_id="%s-context-%s" % (trade_date.isoformat(), title),
                trade_date=trade_date.isoformat(),
                event_type="context",
                event_title=title,
                event_keywords=list(rule["keywords"]),
                strength=round(strength, 1),
                source="板块/业务上下文",
                published_at=trade_date.isoformat(),
            )
        )
    return sorted(events, key=lambda item: (item.strength, item.event_title), reverse=True)


def _merge_daily_events(primary: Sequence[DailyEvent], fallback: Sequence[DailyEvent]) -> List[DailyEvent]:
    by_title: Dict[str, DailyEvent] = {}
    for event in list(primary) + list(fallback):
        current = by_title.get(event.event_title)
        if current is None or event.strength > current.strength:
            by_title[event.event_title] = event
    return sorted(by_title.values(), key=lambda item: (item.strength, item.event_title), reverse=True)


def _reclassify_theme(
    code: str,
    raw_theme: str,
    memberships: Sequence[PlateMembership],
    industry_text: str,
    evidences: Sequence[ReasonEvidence],
    daily_events: Sequence[DailyEvent],
) -> dict:
    concepts_text = "、".join(item.name for item in memberships if item.plate_type.upper() == "CONCEPT")
    evidence_text = _theme_reason_hint(evidences)
    context = " / ".join(part for part in [industry_text, concepts_text, evidence_text] if part)
    best_event = None
    best_score = 0.0
    for event in daily_events:
        score = _event_match_score(event, context, raw_theme)
        if score > best_score:
            best_score = score
            best_event = event

    if best_event is None or best_score < 10:
        inferred = _fallback_reclassification_from_context(raw_theme, context)
        if inferred:
            return inferred
        return {
            "theme": raw_theme,
            "driver": "",
            "event_id": "",
            "score": 100.0 if raw_theme and raw_theme != "未匹配" else 0.0,
            "level": "高" if raw_theme and raw_theme != "未匹配" else "",
            "reason": "" if raw_theme and raw_theme != "未匹配" else "缺少当日事件证据，继续使用标签兜底。",
        }

    reclassified = _theme_from_event(best_event)
    if best_event.event_title == "中报/业绩预告":
        sector_theme = _sector_theme_from_context(context)
        if sector_theme:
            reclassified = sector_theme
    if reclassified == raw_theme:
        return {
            "theme": reclassified,
            "driver": _event_driver_detail(best_event.event_title, context),
            "event_id": best_event.event_id,
            "score": min(100.0, 55.0 + best_score),
            "level": "高",
            "reason": "原始题材与当日主导催化一致。",
        }

    return {
        "theme": reclassified,
        "driver": _event_driver_detail(best_event.event_title, context),
        "event_id": best_event.event_id,
        "score": min(95.0, 35.0 + best_score),
        "level": _match_level(raw_theme, reclassified, best_score, context),
        "reason": _mismatch_reason(raw_theme, reclassified, best_event, context, code),
    }


def _event_match_score(event: DailyEvent, context: str, raw_theme: str) -> float:
    score = event.strength * 0.8
    rule = _EVENT_CONTEXT_RULES.get(event.event_title)
    if rule:
        for keyword in rule["keywords"]:
            if keyword in context:
                score += 4.0
        for keyword in rule["strong_keywords"]:
            if keyword in context:
                score += 8.0
    else:
        for keyword in event.event_keywords:
            if keyword in context:
                score += 4.0
    if raw_theme and raw_theme in event.event_title:
        score += 8.0
    score -= _raw_theme_conflict_penalty(raw_theme, event.event_title, context)
    return score


def _theme_from_event(event: DailyEvent) -> str:
    rule = _EVENT_CONTEXT_RULES.get(event.event_title)
    return str(rule["theme"]) if rule else event.event_title


def _event_driver_detail(event_title: str, context: str) -> str:
    if event_title == "中报/业绩预告":
        sector_theme = _sector_theme_from_context(context)
        if sector_theme == "PCB":
            return "中报/业绩预告（PCB/算力硬件）"
        if sector_theme == "医药":
            return "中报/业绩预告（医药）"
        if sector_theme == "MLCC/被动元件":
            return "中报/业绩预告（被动元件）"
        if sector_theme == "油气":
            return "中报/业绩预告（油气）"
        return "中报/业绩预告"
    if event_title == "PCB/算力硬件":
        if "覆铜板" in context:
            return "PCB/算力硬件（覆铜板）"
        if "服务器" in context or "交换机" in context or "数据中心" in context:
            return "PCB/算力硬件（服务器链）"
    if event_title == "油气/地缘冲突":
        if "油服" in context or "油服工程" in context:
            return "油气/地缘冲突（油服）"
    if event_title == "机器人/康复辅具政策":
        if "优必选" in context:
            return "机器人/康复辅具政策（优必选链）"
        if "康复辅具" in context or "康养机器人" in context:
            return "机器人/康复辅具政策（康养机器人）"
    if event_title == "医药/健康中国":
        if "创新药" in context:
            return "医药/健康中国（创新药）"
        if "医疗器械" in context:
            return "医药/健康中国（医疗器械）"
    return event_title


def _sector_theme_from_context(context: str) -> str:
    if any(text in context for text in ("PCB", "覆铜板", "印制电路板", "电子布", "电子树脂", "交换机", "服务器")):
        return "PCB"
    if any(text in context for text in ("油服", "油气", "石油", "天然气", "WTI")):
        return "油气"
    if any(text in context for text in ("创新药", "医药", "中药", "医疗器械", "生物医药", "健康中国")):
        return "医药"
    if any(text in context for text in ("MLCC", "被动元件", "电容")):
        return "MLCC/被动元件"
    if any(text in context for text in ("机器人", "人形机器人", "康复辅具", "优必选")):
        return "机器人"
    return ""


def _raw_theme_conflict_penalty(raw_theme: str, event_title: str, context: str) -> float:
    if raw_theme == "机器人" and event_title == "油气/地缘冲突" and ("油服" in context or "油气" in context):
        return 12.0
    if raw_theme in {"华为概念", "一带一路", "TMT"} and event_title in {"PCB/算力硬件", "油气/地缘冲突", "医药/健康中国"}:
        return 6.0
    return 0.0


def _fallback_reclassification_from_context(raw_theme: str, context: str) -> dict | None:
    best_title = ""
    best_score = 0.0
    for title, rule in _EVENT_CONTEXT_RULES.items():
        score = 0.0
        for keyword in rule["keywords"]:
            if keyword in context:
                score += 2.5
        for keyword in rule["strong_keywords"]:
            if keyword in context:
                score += 6.0
        if score > best_score:
            best_title = title
            best_score = score
    if best_score < 9:
        return None
    event = DailyEvent(
        event_id="context-fallback-%s" % best_title,
        trade_date="",
        event_type="context",
        event_title=best_title,
        event_keywords=[],
        strength=best_score,
        source="板块/业务上下文",
        published_at="",
    )
    theme = _theme_from_event(event)
    if theme == raw_theme:
        return {
            "theme": theme,
            "driver": _event_driver_detail(best_title, context),
            "event_id": event.event_id,
            "score": min(100.0, 50.0 + best_score),
            "level": "高",
            "reason": "原始题材与上下文主导催化一致。",
        }
    return {
        "theme": theme,
        "driver": _event_driver_detail(best_title, context),
        "event_id": event.event_id,
        "score": min(92.0, 32.0 + best_score),
        "level": _match_level(raw_theme, theme, best_score, context),
        "reason": _mismatch_reason(raw_theme, theme, event, context, ""),
    }


def _match_level(raw_theme: str, reclassified: str, score: float, context: str) -> str:
    if raw_theme == reclassified:
        return "高"
    if raw_theme in {"华为概念", "一带一路", "TMT"}:
        return "极低"
    if raw_theme == "机器人" and not any(text in context for text in ("机器人", "人形", "康复辅具", "优必选")):
        return "极低"
    if raw_theme in {"华为概念", "一带一路"} and reclassified in {"PCB", "油气", "医药"}:
        return "极低"
    if score >= 18:
        return "低"
    return "中"


def _mismatch_reason(raw_theme: str, reclassified: str, event: DailyEvent, context: str, code: str) -> str:
    if raw_theme in {"华为概念", "一带一路", "TMT"}:
        return "%s更像泛概念标签，当日主导催化转向%s。" % (raw_theme, reclassified)
    if raw_theme == "机器人" and not any(text in context for text in ("机器人", "人形", "康复辅具", "优必选")):
        return "机器人仅概念标签，当日主导催化为%s。" % reclassified
    prefix = ("%s " % code) if code else ""
    return "%s原始题材与事件清单不一致，按 %s(%s) 重分类。" % (prefix, event.event_title, reclassified)


def _assess_record_risk(
    snapshot: StockSnapshot,
    core_theme: str,
    reason_logic: str,
    candidate_reasons: Sequence[ReasonEvidence],
    lifecycle: LifecycleRisk | None,
    limit_up_boards: str,
) -> tuple[str, str]:
    score = 0
    flags: list[str] = []
    evidence_text = " ".join(
        [
            reason_logic,
            " ".join(str(getattr(item, "summary", "")) for item in candidate_reasons),
            " ".join(str(getattr(item, "reason_type", "")) for item in candidate_reasons),
        ]
    )

    board_count = 0
    match = re.search(r"(\d+)板", limit_up_boards or "")
    if match:
        board_count = int(match.group(1))
    if board_count >= 4:
        score += 30
        flags.append("高位连板")

    if lifecycle and lifecycle.score >= 70:
        score += 35
        flags.append("强转弱风险高")
    elif lifecycle and lifecycle.score >= 55:
        score += 20
        flags.append("强转弱验证")

    if snapshot.pe_ttm >= 100:
        score += 20
        flags.append("高估值")

    if any(keyword in evidence_text for keyword in ("问询", "异常波动", "停牌", "重组", "跨界收购")):
        score += 35
        flags.append("监管/重组敏感")

    if any(keyword in evidence_text for keyword in ("亏损", "预减")) and snapshot.change_pct >= 9:
        score += 25
        flags.append("业绩承压反而涨停")

    if core_theme in {"机器人", "华为概念", "一带一路", "TMT"} and (
        "暂无明确公告/新闻/龙虎榜证据" in reason_logic or "暂无可验证上涨逻辑" in reason_logic
    ):
        score += 15
        flags.append("泛题材驱动")

    if score >= 70:
        level = "高"
    elif score >= 35:
        level = "中"
    elif score > 0:
        level = "低"
    else:
        level = ""
    return level, "、".join(dict.fromkeys(flags))


def _role_assessments_by_code(
    snapshots: Sequence[StockSnapshot],
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    stage_by_code: Mapping[str, StageTag],
    theme_tier_by_plate: Mapping[str, str],
    selected_theme_plate_by_code: Mapping[str, str] | None = None,
) -> Dict[str, RoleAssessment]:
    assessments_by_code: Dict[str, RoleAssessment] = {}
    groups: Dict[str, List[StockSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        selected_plate = (selected_theme_plate_by_code or {}).get(snapshot.code)
        if selected_plate:
            groups[selected_plate].append(snapshot)
            continue
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


def _selected_theme_plate_by_code(
    memberships_by_code: Mapping[str, Sequence[PlateMembership]],
    core_theme_by_code: Mapping[str, str],
    raw_theme_by_code: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for code, memberships in memberships_by_code.items():
        match = None
        for theme_name in [core_theme_by_code.get(code, ""), (raw_theme_by_code or {}).get(code, "")]:
            if not theme_name or theme_name == "未匹配":
                continue
            match = next(
                (
                    item
                    for item in memberships
                    if item.plate_type.upper() == "CONCEPT" and item.name == theme_name
                ),
                None,
            )
            if match is not None:
                break
        if match is not None:
            result[code] = match.code
    return result


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


def _record_type(code: str, limit_up_codes: set, turnover_top_codes: set, watchlist_codes: set | None = None, turnover_limit: int = 30) -> str:
    if code in limit_up_codes and code in turnover_top_codes:
        return "两者都是"
    if code in limit_up_codes:
        return "涨停"
    if watchlist_codes and code in watchlist_codes:
        return "观察名单"
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
