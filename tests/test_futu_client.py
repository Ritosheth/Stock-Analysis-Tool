import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ghzw.futu_client import (
    FutuAShareClient,
    RequestPacer,
    _pick_futu_home_fallback,
    is_history_quota_error,
    is_history_rate_limit_error,
)


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FutuClientHelpersTest(unittest.TestCase):
    def test_request_pacer_waits_between_calls(self):
        clock = FakeClock()
        pacer = RequestPacer(min_interval=0.55, clock=clock.monotonic, sleeper=clock.sleep)

        pacer.wait()
        clock.now += 0.10
        pacer.wait()

        self.assertEqual(len(clock.sleeps), 1)
        self.assertAlmostEqual(clock.sleeps[0], 0.45, places=6)

    def test_history_rate_limit_error_detection(self):
        self.assertTrue(is_history_rate_limit_error("获取历史K线频率太高，请求失败，每30秒最多60次。"))
        self.assertFalse(is_history_rate_limit_error("行情权限不足"))

    def test_history_quota_error_detection(self):
        self.assertTrue(is_history_quota_error("历史K线额度不足，请求失败（已用正股额度：100/100，期权额度：0/20）。额度会在7天后全部释放。"))
        self.assertFalse(is_history_quota_error("获取历史K线频率太高，请求失败，每30秒最多60次。"))

    def test_get_history_degrades_after_quota_is_exhausted(self):
        client = FutuAShareClient.__new__(FutuAShareClient)
        client._ctx = FakeQuotaContext()
        client._history_pacer = RequestPacer(min_interval=0, clock=lambda: 1.0, sleeper=lambda seconds: None)
        client._history_rate_limit_sleep = 0
        client._history_quota_exhausted = False
        client._history_ret_ok = 0
        client._history_kl_day = "K_DAY"
        client._history_au_qfq = "QFQ"

        first = client.get_history("SH.600001")
        second = client.get_history("SH.600002")

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(client._ctx.calls, 1)

    def test_pick_futu_home_fallback_prefers_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom-home"
            with mock.patch.dict(os.environ, {"GHZW_FUTU_HOME": str(custom)}, clear=False):
                chosen = _pick_futu_home_fallback()
        self.assertEqual(chosen, custom)

    def test_pick_futu_home_fallback_uses_tmp_home_before_system_tmp(self):
        expected = Path.cwd() / ".tmp_home"
        tempdir = Path(tempfile.gettempdir()) / "ghzw-futu-home"
        with mock.patch.dict(os.environ, {}, clear=False):
            with mock.patch("ghzw.futu_client._is_writable_directory", side_effect=lambda path: path in {expected, tempdir}):
                chosen = _pick_futu_home_fallback()
        self.assertEqual(chosen, expected)


class FakeQuotaContext:
    def __init__(self):
        self.calls = 0

    def request_history_kline(self, *args, **kwargs):
        self.calls += 1
        return -1, "历史K线额度不足，请求失败（已用正股额度：100/100，期权额度：0/20）。额度会在7天后全部释放。", None


if __name__ == "__main__":
    unittest.main()
