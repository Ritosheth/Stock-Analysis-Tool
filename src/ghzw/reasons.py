from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Sequence

from .models import ReasonEvidence, StageTag


REASON_PRIORITY = {
    "人工": 0,
    "公告": 1,
    "龙虎榜": 2,
    "公司行动": 3,
    "股东变动": 4,
    "内部人交易": 5,
    "研报": 6,
    "互动易": 7,
    "快讯": 8,
    "新闻": 9,
    "题材": 10,
    "规则": 11,
}


@dataclass(frozen=True)
class ResolvedReason:
    reason: str
    source: str = ""
    evidence_time: str = ""


def load_local_reasons(path: Path) -> List[ReasonEvidence]:
    if not path.exists():
        return []

    result: List[ReasonEvidence] = []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            evidence = ReasonEvidence(
                date=str(row.get("日期", "")).strip(),
                code=str(row.get("代码", "")).strip(),
                reason_type=str(row.get("原因类型", "")).strip(),
                summary=str(row.get("原因摘要", "")).strip(),
                source=str(row.get("来源", "")).strip(),
                confidence=str(row.get("可信度", "")).strip(),
                url=str(row.get("链接", "")).strip(),
                published_at=str(row.get("发布时间", "")).strip(),
            )
            if evidence.date and evidence.code and evidence.summary:
                result.append(evidence)
    return sorted(result, key=_reason_sort_key)


def resolve_reason(
    trade_date: date,
    code: str,
    local_reasons: Sequence[ReasonEvidence],
    suspected_reason: str,
) -> str:
    return resolve_reason_details(trade_date, code, local_reasons, [], suspected_reason).reason


def resolve_reason_details(
    trade_date: date,
    code: str,
    local_reasons: Sequence[ReasonEvidence],
    online_reasons: Sequence[ReasonEvidence],
    suspected_reason: str,
) -> ResolvedReason:
    date_text = trade_date.isoformat()
    candidates = [
        evidence for evidence in list(local_reasons) + list(online_reasons)
        if evidence.date == date_text and evidence.code == code
    ]
    if candidates:
        selected = _dedupe_evidence(sorted(candidates, key=_reason_sort_key))
        return ResolvedReason(
            reason="；".join("%s：%s" % (evidence.reason_type or "原因", evidence.summary) for evidence in selected),
            source="、".join(_unique_texts(evidence.source for evidence in selected)),
            evidence_time="、".join(_unique_texts(evidence.published_at for evidence in selected)),
        )
    if suspected_reason and suspected_reason != "不明":
        return ResolvedReason(reason=suspected_reason, source="规则推断", evidence_time="")
    return ResolvedReason(reason="不明", source="", evidence_time="")


def infer_suspected_reason(
    core_theme: str,
    theme_tier: str,
    record_type: str,
    stage: StageTag,
    main_net_inflow: float,
) -> str:
    labels = set(stage.labels)
    if core_theme and core_theme != "未匹配" and theme_tier == "主线" and record_type in {"涨停", "两者都是"}:
        return "疑似：%s主线发酵，个股涨停" % core_theme
    if core_theme and core_theme != "未匹配" and theme_tier in {"支线", "轮动"} and "放量" in labels:
        return "疑似：%s轮动走强，个股放量" % core_theme
    if "创60日新高" in labels or "创20日新高" in labels:
        return "疑似：趋势突破，创阶段新高"
    if main_net_inflow > 0:
        return "疑似：资金净流入推动"
    return "不明"


class ReasonProvider:
    def get_reasons(self, trade_date: date, codes: Iterable[str]) -> List[ReasonEvidence]:
        return []


def _reason_sort_key(evidence: ReasonEvidence):
    return (
        evidence.date,
        evidence.code,
        REASON_PRIORITY.get(evidence.reason_type, 8),
        _confidence_rank(evidence.confidence),
    )


def _dedupe_evidence(candidates: Sequence[ReasonEvidence]) -> List[ReasonEvidence]:
    selected: List[ReasonEvidence] = []
    seen = set()
    for evidence in candidates:
        key = _normalize_summary(evidence.summary)
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(evidence)
    return selected


def _normalize_summary(value: str) -> str:
    return "".join(str(value or "").split())


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


def _confidence_rank(confidence: str) -> int:
    return {"高": 0, "中": 1, "低": 2}.get(confidence, 3)
