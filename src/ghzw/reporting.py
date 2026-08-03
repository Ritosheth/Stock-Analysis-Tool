from __future__ import annotations

import html
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from .forum_sources import ForumCollection, ForumDiscussion
from .mainline_reference import DisplayTheme, load_mainline_matches, match_record_mainline
from .models import DailyRecord


@dataclass(frozen=True)
class SectorReport:
    name: str
    subsector: str
    limit_up_count: int
    total_turnover: float
    max_board: int
    tier: str
    industries: str
    representatives: List[str]


@dataclass(frozen=True)
class ThemeResearchCandidate:
    name: str
    subsector: str
    research_score: float
    label: str
    avg_change_pct: float
    total_turnover: float
    active_count: int
    positive_count: int
    limit_up_count: int
    leaders: List[str]
    basis: str


@dataclass(frozen=True)
class BoardGroup:
    label: str
    board_count: int
    records: List[DailyRecord]


@dataclass(frozen=True)
class TrendPoint:
    date: str
    limit_up_count: int
    max_board: int
    top_themes: List[str]


@dataclass(frozen=True)
class ReportContext:
    trade_date: str
    records: List[DailyRecord]
    limit_up_records: List[DailyRecord]
    market_cycle: str
    market_sentiment: str
    top_turnover_records: List[DailyRecord]
    research_candidates: List[ThemeResearchCandidate]
    sectors: List[SectorReport]
    board_groups: List[BoardGroup]
    trend_points: List[TrendPoint]
    trend_summary: str
    discussions: List[ForumDiscussion]
    forum_warning: str
    display_by_code: Mapping[str, DisplayTheme]
    skipped_history_files: int = 0


def build_report_context(
    trade_date: date,
    records: Sequence[DailyRecord],
    recent_records_by_date: Mapping[str, Sequence[DailyRecord]] | None = None,
    forum_collection: ForumCollection | None = None,
    skipped_history_files: int = 0,
) -> ReportContext:
    rows = list(records)
    limit_rows = [record for record in rows if _is_limit_up_record(record)]
    recent = recent_records_by_date or {}
    forum = forum_collection or ForumCollection([])
    trend_points = _trend_points(recent)
    mainline_matches = load_mainline_matches()
    display_by_code = {
        record.code: match_record_mainline(record, mainline_matches)
        for record in rows
    }
    return ReportContext(
        trade_date=trade_date.isoformat(),
        records=rows,
        limit_up_records=limit_rows,
        market_cycle=_first_non_empty([record.market_cycle for record in rows]),
        market_sentiment=_first_non_empty([record.market_sentiment for record in rows]),
        top_turnover_records=sorted(rows, key=lambda item: item.turnover, reverse=True)[:30],
        research_candidates=_theme_research_candidates(rows, display_by_code),
        sectors=_sector_reports(limit_rows, display_by_code),
        board_groups=_board_groups(limit_rows),
        trend_points=trend_points,
        trend_summary=_trend_summary(trend_points),
        discussions=forum.discussions,
        forum_warning=forum.warning,
        display_by_code=display_by_code,
        skipped_history_files=skipped_history_files,
    )


def render_html_report(context: ReportContext) -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1f2933; background: #f6f7f9; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin: 28px 0 12px; font-size: 20px; border-bottom: 1px solid #dde3ea; padding-bottom: 8px; }}
    .muted {{ color: #667085; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 18px; }}
    .metric, section {{ background: #fff; border: 1px solid #dde3ea; border-radius: 8px; padding: 14px; }}
    .metric strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dde3ea; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #edf0f3; text-align: left; vertical-align: top; }}
    th {{ background: #f0f3f6; font-weight: 650; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #e7f0ff; color: #1849a9; margin: 0 4px 4px 0; }}
    .warning {{ background: #fff7ed; border-color: #fed7aa; color: #9a3412; }}
    a {{ color: #175cd3; }}
  </style>
</head>
<body>
<main>
  <h1>{date} 股海贼王复盘报告</h1>
  <p class="muted">论坛讨论仅代表公开市场声音，未经证实；公告、新闻、龙虎榜和规则推断需分开看待。</p>
  {overview}
  {turnover}
  {research}
  {theme_audit}
  {sectors}
  {boards}
  {trend}
  {lifecycle}
  {red_flags}
  {discussions}
  {risk}
</main>
</body>
</html>
""".format(
        title=_escape("%s 股海贼王复盘报告" % context.trade_date),
        date=_escape(context.trade_date),
        overview=_render_overview(context),
        turnover=_render_top_turnover(context.top_turnover_records),
        research=_render_research_candidates(context.research_candidates),
        theme_audit=_render_theme_audit(context.records),
        sectors=_render_sectors(context.sectors),
        boards=_render_boards(context.board_groups),
        trend=_render_trend(context),
        lifecycle=_render_lifecycle_watch(context.records),
        red_flags=_render_red_flags(context.records),
        discussions=_render_discussions(context),
        risk=_render_risk(),
    )


def write_html_report(html_text: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def load_recent_daily_records(output_dir: Path, trade_date: date, limit: int = 5):
    from .validation import read_daily_records_csv

    records_by_date: Dict[str, List[DailyRecord]] = {}
    skipped = 0
    for path in sorted(output_dir.glob("*-daily-review.csv"), reverse=True):
        date_text = path.name[:10]
        if date_text >= trade_date.isoformat():
            continue
        try:
            records_by_date[date_text] = read_daily_records_csv(path)
        except Exception:
            skipped += 1
            continue
        if len(records_by_date) >= limit:
            break
    return records_by_date, skipped


def _render_overview(context: ReportContext) -> str:
    top_names = "、".join(
        "%s(%.2f亿元)" % (_escape(record.name), record.turnover / 100_000_000)
        for record in context.top_turnover_records[:5]
    ) or "无"
    return """
  <div class="grid">
    <div class="metric">涨停记录<strong>{limit_count}</strong></div>
    <div class="metric">最高连板<strong>{max_board}板</strong></div>
    <div class="metric">市场阶段<strong>{cycle}</strong></div>
    <div class="metric">情绪摘要<strong>{sentiment}</strong></div>
  </div>
  <section>
    <h2>当日总览</h2>
    <p>成交额核心：{top_names}</p>
  </section>
""".format(
        limit_count=len(context.limit_up_records),
        max_board=max([_board_count(record) for record in context.limit_up_records] or [0]),
        cycle=_escape(context.market_cycle or "未知"),
        sentiment=_escape(context.market_sentiment or "无数据"),
        top_names=top_names,
    )


def _render_top_turnover(records: Sequence[DailyRecord]) -> str:
    rows = []
    for index, record in enumerate(records[:30], start=1):
        rows.append(
            "<tr><td>{rank}</td><td>{name}</td><td>{record_type}</td><td>{turnover:.2f}</td><td>{change:+.2f}%</td><td>{theme}</td><td>{role}</td><td>{reason}</td></tr>".format(
                rank=index,
                name=_escape("%s(%s)" % (record.name, record.code)),
                record_type=_escape(record.record_type),
                turnover=record.turnover / 100_000_000,
                change=record.change_pct,
                theme=_escape(_display_theme(record)),
                role=_escape(record.role),
                reason=_escape(record.reason_type or "不明"),
            )
        )
    body = "\n".join(rows) or '<tr><td colspan="8">暂无成交额榜单数据</td></tr>'
    return """
  <h2>成交额 Top30</h2>
  <table>
    <thead><tr><th>排名</th><th>个股</th><th>入选类型</th><th>成交额(亿元)</th><th>涨幅</th><th>核心题材</th><th>个股地位</th><th>上涨原因</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(body=body)


def _render_research_candidates(candidates: Sequence[ThemeResearchCandidate]) -> str:
    rows = []
    for candidate in candidates[:10]:
        rows.append(
            "<tr><td>{name}</td><td>{subsector}</td><td>{score:.1f}</td><td>{label}</td><td>{change:+.2f}%</td><td>{turnover:.2f}</td><td>{breadth}</td><td>{limit_count}</td><td>{leaders}</td><td>{basis}</td></tr>".format(
                name=_escape(candidate.name),
                subsector=_escape(candidate.subsector),
                score=candidate.research_score,
                label=_escape(candidate.label),
                change=candidate.avg_change_pct,
                turnover=candidate.total_turnover / 100_000_000,
                breadth="%d/%d" % (candidate.positive_count, candidate.active_count),
                limit_count=candidate.limit_up_count,
                leaders=_escape("、".join(candidate.leaders)),
                basis=_escape(candidate.basis),
            )
        )
    body = "\n".join(rows) or '<tr><td colspan="10">暂无板块研究候选</td></tr>'
    return """
  <h2>板块研究候选</h2>
  <table>
    <thead><tr><th>方向</th><th>细分</th><th>研究分</th><th>标签</th><th>均涨幅</th><th>成交额(亿元)</th><th>扩散</th><th>涨停数</th><th>核心个股</th><th>依据</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(body=body)


def _render_theme_audit(records: Sequence[DailyRecord]) -> str:
    mismatches = [
        record
        for record in records
        if record.raw_theme and record.reclassified_theme and record.raw_theme != record.reclassified_theme
    ]
    mismatches = sorted(mismatches, key=lambda item: (item.theme_match_score, item.turnover), reverse=True)[:12]
    rows = []
    for record in mismatches:
        rows.append(
            "<tr><td>{name}</td><td>{raw}</td><td>{new}</td><td>{driver}</td><td>{level}</td><td>{reason}</td></tr>".format(
                name=_escape("%s(%s)" % (record.name, record.code)),
                raw=_escape(record.raw_theme),
                new=_escape(record.reclassified_theme),
                driver=_escape(record.actual_driver),
                level=_escape(record.theme_match_level),
                reason=_escape(record.theme_mismatch_reason),
            )
        )
    body = "\n".join(rows) or '<tr><td colspan="6">当日未发现明显题材重分类偏差</td></tr>'
    return """
  <h2>题材纠偏审计</h2>
  <table>
    <thead><tr><th>个股</th><th>原始题材</th><th>重分类题材</th><th>主导催化</th><th>匹配度</th><th>偏差原因</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(body=body)


def _render_sectors(sectors: Sequence[SectorReport]) -> str:
    rows = []
    for sector in sectors:
        rows.append(
            "<tr><td>{name}</td><td>{subsector}</td><td>{count}</td><td>{turnover:.2f}</td><td>{board}板</td><td>{tier}</td><td>{industries}</td><td>{reps}</td></tr>".format(
                name=_escape(sector.name),
                subsector=_escape(sector.subsector),
                count=sector.limit_up_count,
                turnover=sector.total_turnover / 100_000_000,
                board=sector.max_board,
                tier=_escape(sector.tier),
                industries=_escape(sector.industries),
                reps=_escape("、".join(sector.representatives)),
            )
        )
    body = "\n".join(rows) or '<tr><td colspan="8">无涨停板块数据</td></tr>'
    return """
  <h2>板块结构</h2>
  <table>
    <thead><tr><th>主线</th><th>细分方向</th><th>涨停数</th><th>成交额(亿元)</th><th>最高板</th><th>层级</th><th>行业映射</th><th>代表个股</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(body=body)


def _render_boards(groups: Sequence[BoardGroup]) -> str:
    rows = []
    for group in groups:
        names = "、".join("%s(%s)" % (_escape(record.name), _escape(_display_theme(record))) for record in group.records[:12])
        rows.append("<tr><td>{label}</td><td>{count}</td><td>{names}</td></tr>".format(
            label=_escape(group.label),
            count=len(group.records),
            names=names,
        ))
    body = "\n".join(rows) or '<tr><td colspan="3">无连板梯队数据</td></tr>'
    return """
  <h2>连板梯队</h2>
  <table>
    <thead><tr><th>梯队</th><th>数量</th><th>个股</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(body=body)


def _render_trend(context: ReportContext) -> str:
    rows = []
    for point in context.trend_points:
        rows.append("<tr><td>{date}</td><td>{count}</td><td>{board}板</td><td>{themes}</td></tr>".format(
            date=_escape(point.date),
            count=point.limit_up_count,
            board=point.max_board,
            themes=_escape("、".join(point.top_themes)),
        ))
    body = "\n".join(rows) or '<tr><td colspan="4">暂无可比历史日报</td></tr>'
    skipped = ""
    if context.skipped_history_files:
        skipped = '<p class="muted">有 %d 个历史日报读取失败，已跳过。</p>' % context.skipped_history_files
    return """
  <h2>近期变化趋势</h2>
  <section><p>{summary}</p>{skipped}</section>
  <table>
    <thead><tr><th>日期</th><th>涨停数</th><th>最高板</th><th>前三题材</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(summary=_escape(context.trend_summary), skipped=skipped, body=body)


def _render_discussions(context: ReportContext) -> str:
    if context.discussions:
        items = []
        for item in context.discussions[:12]:
            items.append(
                '<li><span class="pill">{source}</span><a href="{url}">{title}</a><br><span class="muted">{summary} | 查询：{query} | {time}</span></li>'.format(
                    source=_escape(item.source),
                    url=_escape(item.url),
                    title=_escape(item.title),
                    summary=_escape(item.summary),
                    query=_escape(item.query),
                    time=_escape(item.published_at),
                )
            )
        content = "<ul>%s</ul>" % "\n".join(items)
    else:
        clues = _public_evidence_clues(context.records)
        if clues:
            items = []
            for record in clues:
                display = context.display_by_code.get(record.code, DisplayTheme(record.core_theme, record.industries))
                items.append(
                    "<li><span class=\"pill\">{source}</span>{name} / {theme} / {sector}<br><span class=\"muted\">{reason} | {time}</span></li>".format(
                        source=_escape(record.reason_source or "公开线索"),
                        name=_escape(record.name),
                        theme=_escape(display.display_theme),
                        sector=_escape(display.display_sector),
                        reason=_escape(record.reason_type),
                        time=_escape(record.evidence_time),
                    )
                )
            content = '<section class="warning">雪球/论坛未直接获取，以下为公告、新闻、龙虎榜或互动易等公开线索兜底，不能等同论坛观点。</section><ul>%s</ul>' % "\n".join(items)
        else:
            warning = context.forum_warning or "未获取到论坛公开讨论"
            content = '<section class="warning">%s</section>' % _escape(warning)
    return """
  <h2>市场讨论摘要</h2>
  {content}
""".format(content=content)


def _render_lifecycle_watch(records: Sequence[DailyRecord]) -> str:
    candidates = [
        record
        for record in records
        if record.lifecycle_stage or record.watchlist_note or record.lifecycle_score > 0
    ]
    candidates = sorted(candidates, key=lambda item: (item.lifecycle_score, bool(item.watchlist_note), item.turnover), reverse=True)[:10]
    rows = []
    for record in candidates:
        rows.append(
            "<tr><td>{name}</td><td>{theme}</td><td>{stage}</td><td>{score:.1f}</td><td>{signals}</td><td>{note}</td><td>{discipline}</td></tr>".format(
                name=_escape("%s(%s)" % (record.name, record.code)),
                theme=_escape(_display_theme(record)),
                stage=_escape(record.lifecycle_stage or "观察"),
                score=record.lifecycle_score,
                signals=_escape(record.lifecycle_signals),
                note=_escape(record.watchlist_note),
                discipline=_escape(record.lifecycle_discipline),
            )
        )
    body = "\n".join(rows) or '<tr><td colspan="7">暂无明显强转弱观察项</td></tr>'
    return """
  <h2>强转弱观察</h2>
  <table>
    <thead><tr><th>个股</th><th>核心题材</th><th>阶段</th><th>风险分</th><th>信号</th><th>备注</th><th>观察纪律</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(body=body)


def _render_red_flags(records: Sequence[DailyRecord]) -> str:
    risky = [record for record in records if record.risk_level or record.risk_flags]
    risky = sorted(
        risky,
        key=lambda item: (_risk_level_rank(item.risk_level), item.lifecycle_score, item.turnover),
        reverse=True,
    )[:10]
    rows = []
    for record in risky:
        rows.append(
            "<tr><td>{name}</td><td>{theme}</td><td>{level}</td><td>{flags}</td><td>{logic}</td></tr>".format(
                name=_escape("%s(%s)" % (record.name, record.code)),
                theme=_escape(_display_theme(record)),
                level=_escape(record.risk_level or "观察"),
                flags=_escape(record.risk_flags or "暂无"),
                logic=_escape(record.reason_logic or record.reason_type or "暂无"),
            )
        )
    body = "\n".join(rows) or '<tr><td colspan="5">暂无明显红旗信号</td></tr>'
    return """
  <h2>红旗与验证缺口</h2>
  <table>
    <thead><tr><th>个股</th><th>核心题材</th><th>等级</th><th>红旗信号</th><th>当前逻辑</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
""".format(body=body)


def _render_risk() -> str:
    return """
  <h2>风险提示</h2>
  <section>
    <p>本报告用于复盘归因，不构成交易建议。论坛观点属于市场讨论，可能存在情绪化、滞后、误传或幸存者偏差；应与公告、新闻、龙虎榜资金和规则推断分开判断。</p>
  </section>
"""


def _sector_reports(records: Sequence[DailyRecord], display_by_code: Mapping[str, DisplayTheme] | None = None) -> List[SectorReport]:
    groups: Dict[str, List[DailyRecord]] = defaultdict(list)
    for record in records:
        display = (display_by_code or {}).get(record.code)
        has_reference_match = bool(display and (display.role or display.note))
        group_key = "%s||%s" % (
            display.display_theme if display else (record.core_theme or "未匹配"),
            display.display_sector if has_reference_match else "",
        )
        groups[group_key].append(record)
    result: List[SectorReport] = []
    for key, group in groups.items():
        name, subsector = key.split("||", 1)
        industries = []
        for record in group:
            if record.industries and record.industries not in industries:
                industries.append(record.industries)
        if not subsector:
            subsector = "、".join(industries[:2]) or name
        representatives = [
            record.name for record in sorted(group, key=lambda item: item.turnover, reverse=True)[:5]
        ]
        result.append(
            SectorReport(
                name=name,
                subsector=subsector,
                limit_up_count=len(group),
                total_turnover=sum(record.turnover for record in group),
                max_board=max(_board_count(record) for record in group),
                tier=_most_common([record.theme_tier for record in group]),
                industries="、".join(industries[:2]),
                representatives=representatives,
            )
        )
    return sorted(result, key=lambda item: (item.limit_up_count, item.total_turnover), reverse=True)


def _theme_research_candidates(
    records: Sequence[DailyRecord],
    display_by_code: Mapping[str, DisplayTheme] | None = None,
) -> List[ThemeResearchCandidate]:
    groups: Dict[str, List[DailyRecord]] = defaultdict(list)
    subsectors_by_theme: Dict[str, List[str]] = defaultdict(list)
    for record in records:
        name, subsector = _display_theme_parts(record, display_by_code)
        if not name or name == "未匹配":
            continue
        groups[name].append(record)
        if subsector and subsector not in subsectors_by_theme[name]:
            subsectors_by_theme[name].append(subsector)

    result: List[ThemeResearchCandidate] = []
    for name, group in groups.items():
        subsector = "、".join(subsectors_by_theme.get(name, [])[:3]) or name
        score, basis = _research_score_with_basis(group)
        leaders = [
            record.name
            for record in sorted(group, key=lambda item: (_role_rank(item.role), item.turnover), reverse=True)[:3]
        ]
        result.append(
            ThemeResearchCandidate(
                name=name,
                subsector=subsector,
                research_score=round(score, 1),
                label=_research_label(score),
                avg_change_pct=sum(record.change_pct for record in group) / len(group),
                total_turnover=sum(record.turnover for record in group),
                active_count=len(group),
                positive_count=sum(1 for record in group if record.change_pct > 0),
                limit_up_count=sum(1 for record in group if _is_limit_up_record(record)),
                leaders=leaders,
                basis="、".join(basis),
            )
        )
    return sorted(result, key=lambda item: (item.research_score, item.total_turnover), reverse=True)


def _display_theme_parts(
    record: DailyRecord,
    display_by_code: Mapping[str, DisplayTheme] | None = None,
) -> tuple[str, str]:
    display = (display_by_code or {}).get(record.code)
    if display:
        theme = display.display_theme or record.core_theme
        sector = display.display_sector or record.industries or record.core_theme
        return theme, sector
    return record.core_theme or "未匹配", record.industries or record.core_theme or "未匹配"


def _research_score_with_basis(records: Sequence[DailyRecord]) -> tuple[float, List[str]]:
    avg_change = sum(record.change_pct for record in records) / len(records)
    total_turnover = sum(record.turnover for record in records)
    positive_count = sum(1 for record in records if record.change_pct > 0)
    limit_up_count = sum(1 for record in records if _is_limit_up_record(record))
    positive_ratio = positive_count / len(records)
    avg_volume_ratio = sum(record.volume_ratio for record in records) / len(records)
    score = 0.0
    basis: List[str] = []

    if avg_change > 0:
        score += min(avg_change * 2.2, 20)
        basis.append("板块均涨幅%+.1f%%" % avg_change)
    else:
        score += max(avg_change * 1.5, -10)
        basis.append("均涨幅偏弱")

    turnover_yi = total_turnover / 100_000_000
    if turnover_yi >= 30:
        score += 20
        basis.append("成交额高")
    elif turnover_yi >= 10:
        score += 14
        basis.append("成交额活跃")
    elif turnover_yi >= 3:
        score += 8
        basis.append("成交额有关注")

    score += min(len(records) * 4, 16)
    if len(records) >= 3:
        basis.append("样本扩散")

    score += positive_ratio * 15
    if positive_ratio >= 0.75:
        basis.append("上涨扩散")

    if limit_up_count:
        score += min(limit_up_count * 8, 20)
        basis.append("涨停%d只" % limit_up_count)

    leadership_score = 0
    roles = {record.role for record in records}
    if "龙头" in roles:
        leadership_score += 8
        basis.append("有龙头")
    if "容量核心" in roles:
        leadership_score += 6
        basis.append("有容量核心")
    if "中军" in roles:
        leadership_score += 4
        basis.append("有中军")
    score += min(leadership_score, 15)

    if avg_volume_ratio >= 1.5:
        score += 10
        basis.append("量比放大")
    elif avg_volume_ratio >= 1.2:
        score += 5
        basis.append("温和放量")

    if avg_change >= 9 and limit_up_count >= 3:
        score -= 8
        basis.append("短线高潮")
    if avg_volume_ratio >= 2.5 and avg_change < 2:
        score -= 10
        basis.append("放量滞涨")
    if avg_change < 0:
        score -= 6
        basis.append("板块承压")

    return max(score, 0.0), basis


def _research_label(score: float) -> str:
    if score >= 70:
        return "重点研究"
    if score >= 50:
        return "跟踪验证"
    if score >= 35:
        return "观察"
    return "暂缓"


def _role_rank(role: str) -> int:
    return {
        "龙头": 6,
        "容量核心": 5,
        "中军": 4,
        "补涨": 3,
        "跟风": 2,
        "杂毛": 1,
    }.get(role, 0)


def _board_groups(records: Sequence[DailyRecord]) -> List[BoardGroup]:
    grouped: Dict[int, List[DailyRecord]] = defaultdict(list)
    for record in records:
        grouped[_board_count(record)].append(record)
    result = []
    for board_count, group in sorted(grouped.items(), key=lambda item: item[0], reverse=True):
        label = "首板" if board_count <= 1 else "%d板" % board_count
        result.append(BoardGroup(label=label, board_count=board_count, records=sorted(group, key=lambda item: item.turnover, reverse=True)))
    return result


def _trend_points(recent_records_by_date: Mapping[str, Sequence[DailyRecord]]) -> List[TrendPoint]:
    points: List[TrendPoint] = []
    for date_text, records in sorted(recent_records_by_date.items()):
        limit_rows = [record for record in records if _is_limit_up_record(record)]
        points.append(
            TrendPoint(
                date=date_text,
                limit_up_count=len(limit_rows),
                max_board=_max_board_for_records(limit_rows),
                top_themes=[sector.name for sector in _sector_reports(limit_rows)[:3]],
            )
        )
    return points


def _max_board_for_records(records: Sequence[DailyRecord]) -> int:
    explicit = max([_board_count(record) for record in records] or [0])
    sentiment = max([_market_board_count(record.market_sentiment) for record in records] or [0])
    return max(explicit, sentiment)


def _trend_summary(points: Sequence[TrendPoint]) -> str:
    if not points:
        return "暂无可比历史日报，先以当日结构为主。"
    latest = points[-1]
    first = points[0]
    direction = "升温" if latest.limit_up_count > first.limit_up_count else "降温" if latest.limit_up_count < first.limit_up_count else "持平"
    hot_theme = latest.top_themes[0] if latest.top_themes else "未匹配"
    return "最近%d个交易样本中，涨停数从%d到%d，整体%s；最新样本最强题材为%s，最高连板为%d板。" % (
        len(points),
        first.limit_up_count,
        latest.limit_up_count,
        direction,
        hot_theme,
        latest.max_board,
    )


def _board_count(record: DailyRecord) -> int:
    for text in (record.limit_up_boards, record.stage, record.role_basis):
        match = re.search(r"(\d+)板", text or "")
        if match:
            return int(match.group(1))
        match = re.search(r"连板(\d+)", text or "")
        if match:
            return int(match.group(1))
    return 1 if _is_limit_up_record(record) else 0


def _market_board_count(text: str) -> int:
    match = re.search(r"连板高(\d+)", text or "")
    return int(match.group(1)) if match else 0


def _is_limit_up_record(record: DailyRecord) -> bool:
    return record.record_type in {"涨停", "两者都是"}


def _public_evidence_clues(records: Sequence[DailyRecord]) -> List[DailyRecord]:
    result = []
    for record in sorted(records, key=lambda item: item.turnover, reverse=True):
        if not record.reason_type or record.reason_type == "不明":
            continue
        if not record.reason_source and record.reason_type.startswith("题材：疑似"):
            continue
        result.append(record)
        if len(result) >= 12:
            break
    return result


def _first_non_empty(values: Sequence[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _most_common(values: Sequence[str]) -> str:
    counts = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _display_theme(record: DailyRecord) -> str:
    theme = record.core_theme or "未匹配"
    if record.theme_classification_source == "Futu分类（A股主题库无相应分类）":
        return "%s（Futu分类；A股主题库无相应分类）" % theme
    return theme


def _risk_level_rank(level: str) -> int:
    return {"高": 3, "中": 2, "低": 1}.get(level, 0)
