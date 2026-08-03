from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from .models import DailyBar, DailyRecord


@dataclass(frozen=True)
class NextDayValidation:
    date: str
    next_date: str
    code: str
    name: str
    next_action: str
    base_close: float
    next_open_return_pct: float
    max_gain_pct: float
    max_drawdown_pct: float
    close_return_pct: float
    action_verdict: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "日期": self.date,
            "次日": self.next_date,
            "代码": self.code,
            "名称": self.name,
            "次日计划": self.next_action,
            "基准收盘价": round(self.base_close, 3),
            "次日开盘收益": round(self.next_open_return_pct, 2),
            "次日最高收益": round(self.max_gain_pct, 2),
            "次日最大回撤": round(self.max_drawdown_pct, 2),
            "次日收盘收益": round(self.close_return_pct, 2),
            "验证结论": self.action_verdict,
        }


def validate_next_day(
    records: Sequence[DailyRecord],
    next_bar_by_code: Mapping[str, DailyBar],
) -> List[NextDayValidation]:
    results: List[NextDayValidation] = []
    for record in records:
        next_bar = next_bar_by_code.get(record.code)
        if next_bar is None or record.close_price <= 0:
            continue
        results.append(
            NextDayValidation(
                date=record.date,
                next_date=next_bar.date,
                code=record.code,
                name=record.name,
                next_action=record.next_action,
                base_close=record.close_price,
                next_open_return_pct=_pct(next_bar.open, record.close_price),
                max_gain_pct=_pct(next_bar.high, record.close_price),
                max_drawdown_pct=_pct(next_bar.low, record.close_price),
                close_return_pct=_pct(next_bar.close, record.close_price),
                action_verdict=_verdict(record.next_action, _pct(next_bar.high, record.close_price), _pct(next_bar.close, record.close_price), _pct(next_bar.low, record.close_price)),
            )
        )
    return results


def write_validation_csv(rows: Sequence[NextDayValidation], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].as_dict().keys()) if rows else [
        "日期",
        "次日",
        "代码",
        "名称",
        "次日计划",
        "基准收盘价",
        "次日开盘收益",
        "次日最高收益",
        "次日最大回撤",
        "次日收盘收益",
        "验证结论",
    ]
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())
    return output_path


def read_daily_records_csv(path: Path) -> List[DailyRecord]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [_row_to_record(row) for row in reader]


def pick_next_bars(records: Sequence[DailyRecord], history_by_code: Mapping[str, Sequence[DailyBar]], next_date: str) -> Dict[str, DailyBar]:
    result: Dict[str, DailyBar] = {}
    for record in records:
        candidates = [bar for bar in history_by_code.get(record.code, []) if bar.date == next_date]
        if candidates:
            result[record.code] = candidates[-1]
    return result


def _pct(value: float, base: float) -> float:
    if base <= 0:
        return 0.0
    return (value / base - 1) * 100


def _verdict(action: str, max_gain_pct: float, close_return_pct: float, max_drawdown_pct: float) -> str:
    if action in {"核心分歧低吸", "转强确认加仓"}:
        return "有效" if max_gain_pct >= 3 and close_return_pct >= 0 else "失效"
    if action in {"高潮后排不追", "退潮空仓"}:
        return "有效" if close_return_pct <= 0 or max_drawdown_pct <= -3 else "失效"
    if action in {"轻仓试错", "观察验证"}:
        return "有效" if max_drawdown_pct > -5 else "失效"
    return "待观察"


def _row_to_record(row: Mapping[str, str]) -> DailyRecord:
    return DailyRecord(
        date=row.get("日期", ""),
        code=row.get("代码", ""),
        name=row.get("名称", ""),
        record_type=row.get("类型", ""),
        limit_up_boards=row.get("涨停板数", ""),
        close_price=_float(row.get("收盘价")),
        prev_close_price=_float(row.get("昨收")),
        change_pct=_float(row.get("涨幅")),
        turnover=_daily_turnover_yuan(row),
        turnover_rate=_float(row.get("换手率")),
        volume_ratio=_float(row.get("量比")),
        industries=row.get("所属行业", ""),
        concepts=row.get("所属概念", ""),
        raw_theme=row.get("原始题材", ""),
        market_cycle=row.get("市场阶段", ""),
        theme_rank=_optional_int(row.get("题材强度排名")),
        theme_tier=row.get("题材层级", ""),
        role=row.get("个股地位", ""),
        stage=row.get("阶段", ""),
        next_action=row.get("次日计划", ""),
        net_inflow=_float(row.get("资金流-净流入")),
        main_net_inflow=_float(row.get("资金流-主力净流入")),
        reason_type=row.get("上涨原因", ""),
        review=row.get("一句话复盘", ""),
        core_theme=row.get("核心题材", "未匹配"),
        theme_classification_source=row.get("题材分类来源", ""),
        reclassified_theme=row.get("重分类题材", row.get("核心题材", "未匹配")),
        actual_driver=row.get("主导催化", ""),
        driver_event_id=row.get("主导事件ID", ""),
        theme_match_score=_float(row.get("题材匹配分")),
        theme_match_level=row.get("题材匹配度", ""),
        theme_mismatch_reason=row.get("偏差原因", ""),
        market_sentiment=row.get("市场情绪", ""),
        role_score=_float(row.get("角色分")),
        role_basis=row.get("角色依据", ""),
        reason_source=row.get("原因来源", ""),
        evidence_time=row.get("证据时间", ""),
        watchlist_note=row.get("观察备注", ""),
        lifecycle_stage=row.get("强转弱阶段", ""),
        lifecycle_score=_float(row.get("强转弱风险分")),
        lifecycle_signals=row.get("强转弱信号", ""),
        lifecycle_discipline=row.get("观察纪律", ""),
        risk_level=row.get("红旗等级", ""),
        risk_flags=row.get("红旗信号", ""),
    )


def _daily_turnover_yuan(row: Mapping[str, str]) -> float:
    if row.get("成交额(亿元)") not in (None, ""):
        return round(_float(row.get("成交额(亿元)")) * 100_000_000, 2)
    return _float(row.get("成交额"))


def _float(value: object) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_int(value: object):
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
