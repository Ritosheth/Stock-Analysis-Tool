import tempfile
import unittest
from pathlib import Path

from ghzw.cache import DailyBarCache
from ghzw.history import CachedHistoryProvider
from ghzw.models import DailyBar


class FailingProvider:
    def __init__(self):
        self.calls = 0

    def get_history(self, code, days=120, end=None):
        self.calls += 1
        raise RuntimeError("proxy disconnected")


class EmptyProvider:
    def get_history(self, code, days=120, end=None):
        return []


class FailsForOneCodeProvider:
    def __init__(self):
        self.calls = []

    def get_history(self, code, days=120, end=None):
        self.calls.append(code)
        if code == "SZ.000001":
            raise RuntimeError("single stock failed")
        return [DailyBar(code=code, date="2026-06-12", close=10)]


class CachedHistoryProviderTest(unittest.TestCase):
    def test_disables_failing_fallback_after_first_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fallback = FailingProvider()
            provider = CachedHistoryProvider(
                cache=DailyBarCache(Path(tmpdir)),
                primary_provider=EmptyProvider(),
                fallback_provider=fallback,
            )

            self.assertEqual(provider.get_history("SZ.000001"), [])
            self.assertEqual(provider.get_history("SZ.000002"), [])

            self.assertEqual(fallback.calls, 1)

    def test_uses_cache_without_calling_failed_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DailyBarCache(Path(tmpdir))
            cache.save("SZ.000001", [DailyBar(code="SZ.000001", date="2026-06-12", close=10)])
            fallback = FailingProvider()
            provider = CachedHistoryProvider(
                cache=cache,
                primary_provider=EmptyProvider(),
                fallback_provider=fallback,
                min_cached_days=1,
            )

            bars = provider.get_history("SZ.000001", days=1)

            self.assertEqual(len(bars), 1)
            self.assertEqual(fallback.calls, 0)

    def test_primary_single_code_failure_does_not_disable_remaining_codes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            primary = FailsForOneCodeProvider()
            provider = CachedHistoryProvider(
                cache=DailyBarCache(Path(tmpdir)),
                primary_provider=primary,
                fallback_provider=None,
            )

            self.assertEqual(provider.get_history("SZ.000001"), [])
            bars = provider.get_history("SZ.000002")

            self.assertEqual([bar.code for bar in bars], ["SZ.000002"])
            self.assertEqual(primary.calls, ["SZ.000001", "SZ.000002"])

    def test_fallback_can_continue_after_single_code_failure_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fallback = FailsForOneCodeProvider()
            provider = CachedHistoryProvider(
                cache=DailyBarCache(Path(tmpdir)),
                primary_provider=EmptyProvider(),
                fallback_provider=fallback,
                disable_fallback_on_error=False,
            )

            self.assertEqual(provider.get_history("SZ.000001"), [])
            bars = provider.get_history("SZ.000002")

            self.assertEqual([bar.code for bar in bars], ["SZ.000002"])
            self.assertEqual(fallback.calls, ["SZ.000001", "SZ.000002"])


if __name__ == "__main__":
    unittest.main()
