from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Sequence

from .models import ReasonEvidence


@dataclass(frozen=True)
class DailyEvent:
    event_id: str
    trade_date: str
    event_type: str
    event_title: str
    event_keywords: List[str]
    strength: float
    source: str
    published_at: str


EVENT_SPECS = (
    {
        "slug": "earnings",
        "event_type": "业绩",
        "title": "中报/业绩预告",
        "keywords": ("中报", "业绩预告", "预增", "扭亏", "净利润", "同比增长"),
    },
    {
        "slug": "policy_robotics",
        "event_type": "政策",
        "title": "机器人/康复辅具政策",
        "keywords": ("康复辅具", "康养机器人", "脑机接口", "机器人", "人形机器人", "行动方案"),
    },
    {
        "slug": "pcb_ai_hardware",
        "event_type": "产业链",
        "title": "PCB/算力硬件",
        "keywords": ("PCB", "覆铜板", "印制电路板", "算力硬件", "服务器", "交换机", "电子布", "电子树脂"),
    },
    {
        "slug": "oil_geo",
        "event_type": "地缘/商品",
        "title": "油气/地缘冲突",
        "keywords": ("霍尔木兹", "WTI", "原油", "油价", "石油", "天然气", "地缘"),
    },
    {
        "slug": "healthcare_policy",
        "event_type": "政策/医药",
        "title": "医药/健康中国",
        "keywords": ("健康中国", "基药目录", "创新药", "医药", "中药", "医疗器械"),
    },
    {
        "slug": "mna_restructuring",
        "event_type": "并购重组",
        "title": "并购重组/跨界收购",
        "keywords": ("并购", "重组", "收购", "问询", "停牌", "资产注入", "跨界"),
    },
    {
        "slug": "mlcc_passive",
        "event_type": "产业链",
        "title": "MLCC/被动元件",
        "keywords": ("MLCC", "被动元件", "电容", "铝电解电容"),
    },
)


def build_daily_event_catalog(trade_date: date, evidences: Sequence[ReasonEvidence]) -> List[DailyEvent]:
    rows: List[DailyEvent] = []
    for spec in EVENT_SPECS:
        matched = _matching_evidences(spec["keywords"], evidences)
        if not matched:
            continue
        rows.append(
            DailyEvent(
                event_id="%s-%s" % (trade_date.isoformat(), spec["slug"]),
                trade_date=trade_date.isoformat(),
                event_type=str(spec["event_type"]),
                event_title=str(spec["title"]),
                event_keywords=list(spec["keywords"]),
                strength=_strength(matched),
                source="、".join(_unique_texts(item.source for item in matched)) or "公开线索",
                published_at="、".join(_unique_texts(item.published_at for item in matched if item.published_at)) or trade_date.isoformat(),
            )
        )
    return sorted(rows, key=lambda item: (item.strength, item.event_type, item.event_title), reverse=True)


def _matching_evidences(keywords: Iterable[str], evidences: Sequence[ReasonEvidence]) -> List[ReasonEvidence]:
    result: List[ReasonEvidence] = []
    for evidence in evidences:
        text = "%s %s %s" % (evidence.reason_type, evidence.summary, evidence.source)
        if any(keyword in text for keyword in keywords):
            result.append(evidence)
    return result


def _strength(evidences: Sequence[ReasonEvidence]) -> float:
    base = float(len(evidences))
    confidence_bonus = sum({"高": 1.2, "中": 0.6, "低": 0.2}.get(item.confidence, 0.1) for item in evidences)
    return round(base + confidence_bonus, 1)


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
