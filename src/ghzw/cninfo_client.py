from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone, timedelta
from typing import Iterable, List, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import ReasonEvidence


CN_TZ = timezone(timedelta(hours=8))


class CninfoEvidenceProvider:
    def __init__(self, timeout: float = 6.0, max_codes: int = 80):
        self.timeout = timeout
        self.max_codes = max_codes

    def get_reasons(self, trade_date: date, codes: Iterable[str]) -> List[ReasonEvidence]:
        evidence: List[ReasonEvidence] = []
        for code in list(codes)[: self.max_codes]:
            evidence.extend(self._safe_fetch(lambda: self.get_announcements(trade_date, code)))
            evidence.extend(self._safe_fetch(lambda: self.get_irm(trade_date, code)))
        return evidence

    def get_announcements(self, trade_date: date, code: str) -> List[ReasonEvidence]:
        code6 = to_cninfo_code(code)
        payload = {
            "pageNum": "1",
            "pageSize": "10",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": code6,
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": "%s~%s" % (trade_date.isoformat(), trade_date.isoformat()),
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        data = self._post_json("http://www.cninfo.com.cn/new/hisAnnouncement/query", payload)
        return parse_announcement_items(data, code, trade_date)

    def get_irm(self, trade_date: date, code: str) -> List[ReasonEvidence]:
        code6 = to_cninfo_code(code)
        org_id = self._fetch_org_id(code6)
        if not org_id:
            return []
        params = {"_t": str(int(time.time()))}
        payload = {
            "stockcode": code6,
            "orgId": org_id,
            "pageSize": "20",
            "pageNum": "1",
            "keyWord": "",
            "startDay": trade_date.isoformat(),
            "endDay": trade_date.isoformat(),
        }
        data = self._post_json("https://irm.cninfo.com.cn/newircs/company/question?%s" % urlencode(params), payload)
        return parse_irm_rows(data, code, trade_date)

    def _fetch_org_id(self, code6: str) -> str:
        data = self._post_json(
            "https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo?%s" % urlencode({"_t": str(int(time.time()))}),
            {"keyWord": code6},
        )
        rows = data.get("data") or []
        if not rows:
            return ""
        return str(rows[0].get("secid") or "")

    def _post_json(self, url: str, payload: Mapping[str, object]):
        body = urlencode(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.cninfo.com.cn/",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _safe_fetch(self, fn):
        try:
            return fn()
        except Exception as exc:
            print("Warning: CNINFO evidence source failed: %s" % exc, file=sys.stderr)
            return []


def parse_announcement_items(payload: Mapping[str, object], code: str, trade_date: date) -> List[ReasonEvidence]:
    result: List[ReasonEvidence] = []
    for item in payload.get("announcements") or []:
        title = _clean_text(item.get("announcementTitle"))
        if not title:
            continue
        published_at = _time_from_ms(item.get("announcementTime"))
        if published_at[:10] != trade_date.isoformat():
            continue
        code6 = str(item.get("secCode") or to_cninfo_code(code))
        announcement_id = str(item.get("announcementId") or "")
        org_id = str(item.get("orgId") or "")
        url = (
            "http://www.cninfo.com.cn/new/disclosure/detail?"
            "stockCode=%s&announcementId=%s&orgId=%s&announcementTime=%s"
            % (code6, announcement_id, org_id, published_at)
        )
        result.append(
            ReasonEvidence(
                date=trade_date.isoformat(),
                code=code,
                reason_type="公告",
                summary=title,
                source="CNINFO",
                confidence="高",
                url=url,
                published_at=published_at,
            )
        )
    return result


def parse_irm_rows(payload: Mapping[str, object], code: str, trade_date: date) -> List[ReasonEvidence]:
    result: List[ReasonEvidence] = []
    for item in payload.get("rows") or []:
        answer = _clean_text(item.get("attachedContent"))
        question = _clean_text(item.get("mainContent"))
        if not answer:
            continue
        published_at = _time_from_ms(item.get("updateDate") or item.get("pubDate"))
        if published_at[:10] != trade_date.isoformat():
            continue
        summary = answer[:80]
        if question:
            summary = "%s；答：%s" % (question[:30], answer[:80])
        result.append(
            ReasonEvidence(
                date=trade_date.isoformat(),
                code=code,
                reason_type="互动易",
                summary=summary,
                source="CNINFO互动易",
                confidence="中",
                published_at=published_at,
            )
        )
    return result


def to_cninfo_code(code: str) -> str:
    return str(code).split(".")[-1]


def _time_from_ms(value: object) -> str:
    try:
        timestamp = int(value) / 1000
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _clean_text(value: object) -> str:
    return str(value or "").replace("<em>", "").replace("</em>", "").strip()
