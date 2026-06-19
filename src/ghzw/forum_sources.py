from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Sequence

from .models import DailyRecord


@dataclass(frozen=True)
class ForumDiscussion:
    source: str
    title: str
    summary: str
    url: str
    published_at: str
    query: str


@dataclass(frozen=True)
class ForumCollection:
    discussions: List[ForumDiscussion]
    warning: str = ""


FetchText = Callable[[str], str]


def collect_forum_discussions(
    trade_date: date,
    records: Sequence[DailyRecord],
    enabled: bool = True,
    fetch_text: FetchText | None = None,
    max_queries: int = 4,
    max_results_per_query: int = 2,
) -> ForumCollection:
    if not enabled:
        return ForumCollection([], "未启用论坛检索")

    queries = build_forum_queries(records, max_queries=max_queries)
    if not queries:
        return ForumCollection([], "没有可用于论坛检索的核心题材或重点股")

    fetcher = fetch_text or _fetch_text
    discussions: List[ForumDiscussion] = []
    errors: List[str] = []
    for query in queries:
        for source, url in _search_urls(query):
            try:
                html = fetcher(url)
            except Exception as exc:
                errors.append("%s:%s" % (source, exc))
                continue
            discussions.extend(
                _parse_search_results(
                    source=source,
                    query=query,
                    html=html,
                    published_at=trade_date.isoformat(),
                    limit=max_results_per_query,
                )
            )
            if len([item for item in discussions if item.query == query]) >= max_results_per_query:
                break

    warning = ""
    if not discussions:
        warning = "论坛线索未获取"
        if errors:
            warning = "%s：%s" % (warning, "；".join(errors[:3]))
    return ForumCollection(_dedupe_discussions(discussions), warning)


def build_forum_queries(records: Sequence[DailyRecord], max_queries: int = 6) -> List[str]:
    queries: List[str] = []
    limit_records = [
        record for record in records
        if record.record_type in {"涨停", "两者都是"}
    ]
    theme_counts = {}
    for record in limit_records:
        if record.core_theme and record.core_theme != "未匹配":
            theme_counts[record.core_theme] = theme_counts.get(record.core_theme, 0) + 1
    for theme, _ in sorted(theme_counts.items(), key=lambda item: (-item[1], item[0])):
        _append_unique(queries, "%s 涨停 原因" % theme)

    for record in sorted(limit_records, key=lambda item: item.turnover, reverse=True):
        _append_unique(queries, "%s 涨停" % record.name)

    return queries[:max_queries]


def _search_urls(query: str):
    encoded_xueqiu = urllib.parse.quote(query)
    encoded_site = urllib.parse.quote("site:xueqiu.com %s" % query)
    encoded_guba = urllib.parse.quote("site:guba.eastmoney.com %s" % query)
    return [
        ("雪球", "https://xueqiu.com/k?q=%s" % encoded_xueqiu),
        ("雪球搜索", "https://www.baidu.com/s?wd=%s" % encoded_site),
        ("东方财富股吧", "https://www.baidu.com/s?wd=%s" % encoded_guba),
    ]


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36",
        },
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def _parse_search_results(source: str, query: str, html: str, published_at: str, limit: int) -> List[ForumDiscussion]:
    results: List[ForumDiscussion] = []
    for href, raw_title in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S):
        title = _clean_html(raw_title)
        if not title or len(title) < 4:
            continue
        if "广告" in title or "百度首页" in title:
            continue
        url = urllib.parse.unquote(href)
        results.append(
            ForumDiscussion(
                source=source,
                title=title[:120],
                summary=title[:180],
                url=url,
                published_at=published_at,
                query=query,
            )
        )
        if len(results) >= limit:
            break
    return results


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def _dedupe_discussions(items: Sequence[ForumDiscussion]) -> List[ForumDiscussion]:
    result: List[ForumDiscussion] = []
    seen = set()
    for item in items:
        key = (item.source, item.title, item.url)
        if key in seen:
            continue
        result.append(item)
        seen.add(key)
    return result


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)
