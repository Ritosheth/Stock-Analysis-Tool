from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .models import ReasonEvidence, StageTag
from .reasons import REASON_PRIORITY


LOW_QUALITY_PATTERNS = (
    "只个股",
    "只股",
    "突破半年线",
    "站上半年线",
    "突破年线",
    "每笔成交",
    "上午收盘涨停",
    "涨停(附股)",
    "涨停（附股）",
    "龙虎榜营业部",
)


@dataclass(frozen=True)
class ReasonLogicResult:
    logic: str
    driver_type: str
    evidence_summary: str
    source: str = ""
    evidence_time: str = ""


def build_reason_logic(
    evidences: Sequence[ReasonEvidence],
    suspected_reason: str,
    core_theme: str,
    theme_tier: str,
    record_type: str,
    stage: StageTag,
    main_net_inflow: float,
) -> ReasonLogicResult:
    selected = _dedupe_evidence(sorted(
        [evidence for evidence in evidences if not is_low_quality_evidence(evidence)],
        key=_reason_sort_key,
    ))
    main = _pick_main_evidence(selected)
    support = [evidence for evidence in selected if evidence is not main]

    if main is not None:
        driver_type = _driver_type(main)
        logic = _logic_from_main_evidence(main, support, core_theme, theme_tier, record_type, stage)
        ordered_evidence = [main] + support
        return ReasonLogicResult(
            logic=logic,
            driver_type=driver_type,
            evidence_summary="；".join(_format_evidence(evidence) for evidence in ordered_evidence[:4]),
            source="、".join(_unique_texts(evidence.source for evidence in ordered_evidence)),
            evidence_time="、".join(_unique_texts(evidence.published_at for evidence in ordered_evidence)),
        )

    if suspected_reason and suspected_reason != "不明":
        driver_type = _driver_type_from_context(core_theme, theme_tier, main_net_inflow)
        uncertainty = "暂无明确公告/新闻/龙虎榜证据"
        if core_theme and core_theme != "未匹配":
            logic = "%s，%s；结合%s和个股表现，偏%s。" % (
                suspected_reason,
                uncertainty,
                core_theme,
                driver_type,
            )
        else:
            logic = "%s，%s。" % (suspected_reason, uncertainty)
        return ReasonLogicResult(
            logic=logic,
            driver_type=driver_type,
            evidence_summary="题材：%s" % suspected_reason,
            source="规则推断",
            evidence_time="",
        )

    return ReasonLogicResult(
        logic="暂无可验证上涨逻辑，需人工复核。",
        driver_type="不明",
        evidence_summary="不明",
    )


def is_low_quality_evidence(evidence: ReasonEvidence) -> bool:
    text = "%s %s" % (evidence.reason_type, evidence.summary)
    if evidence.reason_type in {"公告", "龙虎榜", "研报", "互动易", "公司行动", "股东变动", "人工"}:
        return False
    return any(pattern in text for pattern in LOW_QUALITY_PATTERNS)


def _logic_from_main_evidence(
    main: ReasonEvidence,
    support: Sequence[ReasonEvidence],
    core_theme: str,
    theme_tier: str,
    record_type: str,
    stage: StageTag,
) -> str:
    driver_type = _driver_type(main)
    parts = ["%s主导：%s" % (driver_type, _shorten(main.summary, 64))]
    if core_theme and core_theme != "未匹配":
        parts.append("题材归属%s/%s" % (core_theme, theme_tier or "未分层"))
    if record_type in {"涨停", "两者都是"}:
        parts.append("股价表现为%s" % record_type)
    if stage.summary != "未分类":
        parts.append("阶段%s" % stage.summary)
    support_text = _support_text(support)
    if support_text:
        parts.append(support_text)
    return "；".join(parts) + "。"


def _support_text(evidences: Sequence[ReasonEvidence]) -> str:
    support_types = []
    for evidence in evidences:
        if evidence.reason_type == "龙虎榜":
            support_types.append("龙虎榜资金作为佐证")
        elif evidence.reason_type in {"新闻", "快讯"}:
            support_types.append("新闻催化作为佐证")
        elif evidence.reason_type == "公告":
            support_types.append("公告作为佐证")
        elif evidence.reason_type == "研报":
            support_types.append("研报观点作为佐证")
    unique = _unique_texts(support_types)
    return "、".join(unique[:2])


def _pick_main_evidence(evidences: Sequence[ReasonEvidence]) -> ReasonEvidence | None:
    if not evidences:
        return None
    preferred_order = ("人工", "公告", "公司行动", "新闻", "快讯", "龙虎榜", "研报", "互动易", "股东变动")
    for reason_type in preferred_order:
        for evidence in evidences:
            if evidence.reason_type == reason_type:
                return evidence
    return evidences[0]


def _driver_type(evidence: ReasonEvidence) -> str:
    if evidence.reason_type in {"公告", "公司行动", "股东变动", "内部人交易"}:
        return "公告催化"
    if evidence.reason_type in {"新闻", "快讯"}:
        return "产业新闻"
    if evidence.reason_type == "龙虎榜":
        return "资金博弈"
    if evidence.reason_type == "研报":
        return "业绩预期"
    if evidence.reason_type == "互动易":
        return "基本面问答"
    return "题材发酵"


def _driver_type_from_context(core_theme: str, theme_tier: str, main_net_inflow: float) -> str:
    if core_theme and core_theme != "未匹配" and theme_tier in {"主线", "支线", "轮动"}:
        return "题材发酵"
    if main_net_inflow > 0:
        return "资金博弈"
    return "不明"


def _format_evidence(evidence: ReasonEvidence) -> str:
    return "%s：%s" % (evidence.reason_type or "原因", _shorten(evidence.summary, 70))


def _reason_sort_key(evidence: ReasonEvidence):
    return (
        REASON_PRIORITY.get(evidence.reason_type, 8),
        _confidence_rank(evidence.confidence),
    )


def _dedupe_evidence(candidates: Sequence[ReasonEvidence]) -> List[ReasonEvidence]:
    selected: List[ReasonEvidence] = []
    seen = set()
    for evidence in candidates:
        key = "".join(str(evidence.summary or "").split())
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(evidence)
    return selected


def _unique_texts(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _shorten(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def _confidence_rank(confidence: str) -> int:
    return {"高": 0, "中": 1, "低": 2}.get(confidence, 3)
