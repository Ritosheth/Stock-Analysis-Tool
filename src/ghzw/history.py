from __future__ import annotations

import sys
from datetime import date
from typing import List, Optional

from .cache import DailyBarCache
from .models import DailyBar
from .tushare_client import is_tushare_permission_error


class CachedHistoryProvider:
    def __init__(
        self,
        cache: DailyBarCache,
        primary_provider,
        fallback_provider=None,
        min_cached_days: int = 60,
        disable_fallback_on_error: bool = True,
    ):
        self._cache = cache
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider
        self._min_cached_days = min_cached_days
        self._disable_fallback_on_error = disable_fallback_on_error
        self._disabled_providers = set()

    def get_history(self, code: str, days: int = 120, end: Optional[date] = None) -> List[DailyBar]:
        cached = self._load_cached(code, days, end)
        if self._has_enough_cached(cached, days, end):
            return cached

        fetched = self._fetch(self._primary_provider, code, days, end, disable_on_error=False)
        if not fetched and self._fallback_provider is not None:
            fetched = self._fetch(
                self._fallback_provider,
                code,
                days,
                end,
                disable_on_error=self._disable_fallback_on_error,
            )

        if fetched:
            self._cache.save(code, fetched)
            return self._load_cached(code, days, end)
        return cached

    def _load_cached(self, code: str, days: int, end: Optional[date]) -> List[DailyBar]:
        if end is not None:
            return self._cache.load_recent_until(code, days, end.isoformat())
        return self._cache.load_recent(code, days)

    def _has_enough_cached(self, cached: List[DailyBar], days: int, end: Optional[date]) -> bool:
        if len(cached) < min(days, self._min_cached_days):
            return False
        if end is not None and cached[-1].date < end.isoformat():
            return False
        return True

    def _fetch(self, provider, code: str, days: int, end: Optional[date], disable_on_error: bool) -> List[DailyBar]:
        provider_id = id(provider)
        if provider_id in self._disabled_providers:
            return []
        try:
            return provider.get_history(code, days=days, end=end)
        except Exception as exc:
            if is_tushare_permission_error(exc):
                self._disabled_providers.add(provider_id)
                print(
                    "Warning: TuShare token has no daily interface permission; "
                    "history K-line will use cache/fallback only. "
                    "See https://tushare.pro/document/1?doc_id=108",
                    file=sys.stderr,
                )
                return []
            if disable_on_error:
                self._disabled_providers.add(provider_id)
            print(
                "Warning: history provider %s failed for %s%s: %s"
                % (
                    provider.__class__.__name__,
                    code,
                    " and is disabled for this run" if provider_id in self._disabled_providers else "",
                    exc,
                ),
                file=sys.stderr,
            )
            return []
