from __future__ import annotations

import json
import re
import sys
from datetime import date
from html import unescape
from typing import Iterable, List, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import ReasonEvidence


EASTMONEY_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_SEARCH_URL = "https://search-api-web.eastmoney.com/search/jsonp"


class EastmoneyEvidenceProvider:
    def __init__(self, timeout: float = 6.0, max_news_codes: int = 40):
        self.timeout = timeout
        self.max_news_codes = max_news_codes

    def get_reasons(
        self,
        trade_date: date,
        codes: Iterable[str],
        names_by_code: Mapping[str, str] | None = None,
    ) -> List[ReasonEvidence]:
        target_codes = list(codes)
        names_by_code = names_by_code or {}
        evidence: List[ReasonEvidence] = []
        evidence.extend(self._safe_fetch(lambda: self.get_billboard(trade_date, target_codes)))
        for code in target_codes[: self.max_news_codes]:
            evidence.extend(
                self._safe_fetch(
                    lambda code=code: self.get_news(trade_date, code, names_by_code.get(code, ""))
                )
            )
        return evidence

    def get_billboard(self, trade_date: date, codes: Sequence[str]) -> List[ReasonEvidence]:
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": (
                "SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,TRADE_DATE,EXPLAIN,"
                "BILLBOARD_NET_AMT,BILLBOARD_BUY_AMT,BILLBOARD_SELL_AMT"
            ),
            "filter": "(TRADE_DATE='%s')" % trade_date.isoformat(),
            "pageNumber": "1",
            "pageSize": "500",
            "sortColumns": "SECURITY_CODE,TRADE_DATE",
            "sortTypes": "1,-1",
            "source": "WEB",
            "client": "WEB",
        }
        return parse_billboard_payload(self._get_json(EASTMONEY_DATACENTER_URL, params), set(codes), trade_date)

    def get_news(self, trade_date: date, code: str, name: str = "") -> List[ReasonEvidence]:
        keyword = to_code6(code)
        search_param = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": 10,
                    "preTag": "",
                    "postTag": "",
                }
            },
        }
        params = {"cb": "ghzw", "param": json.dumps(search_param, ensure_ascii=False)}
        return parse_news_payload(self._get_jsonp(EASTMONEY_SEARCH_URL, params), code, name or keyword, trade_date)

    def _get_json(self, url: str, params: Mapping[str, object]):
        request = Request(
            "%s?%s" % (url, urlencode(params)),
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com/"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_jsonp(self, url: str, params: Mapping[str, object]):
        request = Request(
            "%s?%s" % (url, urlencode(params)),
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.eastmoney.com/"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            return _parse_jsonp(response.read().decode("utf-8"))

    def _safe_fetch(self, fn):
        try:
            return fn()
        except Exception as exc:
            print("Warning: Eastmoney evidence source failed: %s" % exc, file=sys.stderr)
            return []


def parse_billboard_payload(payload: Mapping[str, object], target_codes: set[str], trade_date: date) -> List[ReasonEvidence]:
    target_by_code6 = {to_code6(code): code for code in target_codes}
    result: List[ReasonEvidence] = []
    for item in _payload_rows(payload):
        code6 = _clean_text(item.get("SECURITY_CODE") or item.get("security_code") or item.get("code"))
        code = target_by_code6.get(code6)
        if not code:
            continue
        trade_time = _clean_text(item.get("TRADE_DATE") or item.get("trade_date") or item.get("date"))
        if trade_time[:10] != trade_date.isoformat():
            continue
        explain = _clean_text(item.get("EXPLAIN") or item.get("explain") or "龙虎榜上榜")
        parts = [explain]
        net = _money_wan(item.get("BILLBOARD_NET_AMT") or item.get("billboard_net_amt"))
        buy = _money_wan(item.get("BILLBOARD_BUY_AMT") or item.get("billboard_buy_amt"))
        sell = _money_wan(item.get("BILLBOARD_SELL_AMT") or item.get("billboard_sell_amt"))
        if net:
            parts.append("净买入%s" % net)
        if buy:
            parts.append("买入%s" % buy)
        if sell:
            parts.append("卖出%s" % sell)
        result.append(
            ReasonEvidence(
                date=trade_date.isoformat(),
                code=code,
                reason_type="龙虎榜",
                summary="，".join(parts),
                source="东方财富龙虎榜",
                confidence="高",
                published_at=trade_date.isoformat(),
            )
        )
    return result


def parse_news_payload(payload: Mapping[str, object], code: str, name: str, trade_date: date) -> List[ReasonEvidence]:
    result: List[ReasonEvidence] = []
    code6 = to_code6(code)
    for item in _payload_rows(payload):
        title = _clean_text(item.get("title") or item.get("Title") or item.get("newsTitle"))
        if not title:
            continue
        summary = _clean_text(
            item.get("summary")
            or item.get("content")
            or item.get("digest")
            or item.get("abstract")
            or item.get("description")
        )
        published_at = _clean_text(
            item.get("showTime")
            or item.get("publishTime")
            or item.get("date")
            or item.get("time")
            or item.get("NewsTime")
        )
        if published_at[:10] != trade_date.isoformat():
            continue
        combined = "%s %s" % (title, summary)
        if code6 not in combined and name and name not in combined:
            continue
        reason_type = "快讯" if "快讯" in title or "异动" in title else "新闻"
        source = "东方财富快讯" if reason_type == "快讯" else "东方财富新闻"
        evidence_summary = title if not summary else "%s：%s" % (title, summary)
        result.append(
            ReasonEvidence(
                date=trade_date.isoformat(),
                code=code,
                reason_type=reason_type,
                summary=evidence_summary[:120],
                source=source,
                confidence="中",
                url=_clean_text(item.get("url") or item.get("Url") or item.get("link")),
                published_at=published_at,
            )
        )
    return result[:5]


def to_code6(code: str) -> str:
    return str(code).split(".")[-1]


def _payload_rows(payload: Mapping[str, object]) -> List[Mapping[str, object]]:
    for value in _walk(payload):
        if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
            return list(value)
    return []


def _walk(value):
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _parse_jsonp(text: str):
    stripped = text.strip()
    match = re.match(r"^[^(]*\((.*)\)\s*;?$", stripped, flags=re.S)
    if match:
        stripped = match.group(1)
    return json.loads(stripped)


def _money_wan(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    return "%.2f万元" % (amount / 10000)


def _clean_text(value: object) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())
