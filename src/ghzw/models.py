from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StockSnapshot:
    code: str
    name: str
    last_price: float = 0.0
    prev_close_price: float = 0.0
    high_price: float = 0.0
    turnover: float = 0.0
    turnover_rate: float = 0.0
    volume_ratio: float = 0.0
    market_val: float = 0.0
    pe_ttm: float = 0.0
    pb_rate: float = 0.0
    change_rate: Optional[float] = None
    is_st: bool = False
    is_suspended: bool = False
    lot_size: int = 100
    limit_threshold: Optional[int] = None

    @property
    def change_pct(self) -> float:
        if self.change_rate is not None:
            return float(self.change_rate)
        if self.prev_close_price <= 0:
            return 0.0
        return (self.last_price / self.prev_close_price - 1) * 100


@dataclass(frozen=True)
class PlateMembership:
    code: str
    name: str
    plate_type: str


@dataclass(frozen=True)
class ThemeSummary:
    plate_code: str
    plate_name: str
    plate_type: str
    limit_up_count: int
    avg_change_pct: float
    total_turnover: float
    member_codes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DailyBar:
    code: str
    date: str
    close: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    turnover: float = 0.0
    turnover_rate: float = 0.0
    change_pct: float = 0.0


@dataclass(frozen=True)
class StageTag:
    labels: List[str]
    board_streak: int = 0
    is_20d_high: bool = False
    is_60d_high: bool = False
    is_volume_expanded: bool = False

    @property
    def summary(self) -> str:
        return " / ".join(self.labels) if self.labels else "未分类"


@dataclass(frozen=True)
class CapitalFlow:
    code: str
    net_inflow: float = 0.0
    main_net_inflow: float = 0.0


@dataclass(frozen=True)
class ReasonEvidence:
    date: str
    code: str
    reason_type: str
    summary: str
    source: str = ""
    confidence: str = ""
    url: str = ""
    published_at: str = ""


@dataclass(frozen=True)
class MarketSentiment:
    limit_up_count: int = 0
    limit_down_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    positive_ratio: float = 0.0
    avg_change_pct: float = 0.0
    max_board_streak: int = 0
    board_streak_count: int = 0
    turnover_top_avg_change_pct: float = 0.0
    yesterday_limit_up_avg_change_pct: Optional[float] = None

    @property
    def summary(self) -> str:
        yesterday = "昨板无数据"
        if self.yesterday_limit_up_avg_change_pct is not None:
            yesterday = "昨板%+.1f%%" % self.yesterday_limit_up_avg_change_pct
        return "涨停%d/跌停%d/上涨%.0f%%/连板高%d/%s" % (
            self.limit_up_count,
            self.limit_down_count,
            self.positive_ratio * 100,
            self.max_board_streak,
            yesterday,
        )


@dataclass(frozen=True)
class RoleAssessment:
    role: str
    score: float
    basis: str


@dataclass(frozen=True)
class DailyRecord:
    date: str
    code: str
    name: str
    record_type: str
    close_price: float
    prev_close_price: float
    change_pct: float
    turnover: float
    turnover_rate: float
    volume_ratio: float
    industries: str
    concepts: str
    market_cycle: str
    theme_rank: Optional[int]
    theme_tier: str
    role: str
    stage: str
    next_action: str
    net_inflow: float
    main_net_inflow: float
    reason_type: str
    review: str
    core_theme: str = "未匹配"
    reason_logic: str = ""
    driver_type: str = ""
    market_sentiment: str = ""
    role_score: float = 0.0
    role_basis: str = ""
    reason_source: str = ""
    evidence_time: str = ""
    limit_up_boards: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "日期": self.date,
            "代码": self.code,
            "名称": self.name,
            "类型": self.record_type,
            "涨停板数": self.limit_up_boards,
            "收盘价": round(self.close_price, 3),
            "昨收": round(self.prev_close_price, 3),
            "涨幅": round(self.change_pct, 2),
            "成交额(亿元)": round(self.turnover / 100_000_000, 2),
            "换手率": round(self.turnover_rate, 2),
            "量比": round(self.volume_ratio, 2),
            "所属行业": self.industries,
            "所属概念": self.concepts,
            "核心题材": self.core_theme,
            "市场阶段": self.market_cycle,
            "市场情绪": self.market_sentiment,
            "题材强度排名": self.theme_rank if self.theme_rank is not None else "",
            "题材层级": self.theme_tier,
            "个股地位": self.role,
            "角色分": round(self.role_score, 2),
            "角色依据": self.role_basis,
            "阶段": self.stage,
            "次日计划": self.next_action,
            "资金流-净流入": self.net_inflow,
            "资金流-主力净流入": self.main_net_inflow,
            "上涨逻辑": self.reason_logic,
            "驱动类型": self.driver_type,
            "上涨原因": self.reason_type,
            "原因来源": self.reason_source,
            "证据时间": self.evidence_time,
            "一句话复盘": self.review,
        }
