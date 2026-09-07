import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "wti_oil_price.py"
SPEC = importlib.util.spec_from_file_location("wti_oil_price", SCRIPT)
WTI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WTI)


class FakeResponse(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


class ResponseTests(unittest.TestCase):
    def test_rejects_body_over_limit_without_content_length(self):
        response = FakeResponse(b"x" * (WTI.MAX_RESPONSE_BYTES + 1))

        with self.assertRaisesRegex(ValueError, "response is too large"):
            WTI.read_json_response(response)

    def test_rejects_oversized_content_length_before_reading(self):
        response = FakeResponse(b"{}", {"Content-Length": str(WTI.MAX_RESPONSE_BYTES + 1)})

        with self.assertRaisesRegex(ValueError, "response is too large"):
            WTI.read_json_response(response)
        self.assertEqual(response.tell(), 0)

    def test_parses_bounded_json_body(self):
        response = FakeResponse(b'{"chart": {"result": []}}')

        self.assertEqual(WTI.read_json_response(response), {"chart": {"result": []}})


class FreshnessTests(unittest.TestCase):
    def test_empty_intraday_series_is_stale(self):
        reason = WTI.stale_reason(2_000_000, [], now=2_000_000)

        self.assertIn("no intraday price samples", reason)

    def test_old_intraday_quote_is_stale(self):
        reason = WTI.stale_reason(2_000_000, [(1_996_400, 91.0)], now=2_000_000)

        self.assertIn("1 hour old", reason)

    def test_fresh_quote_is_not_stale(self):
        reason = WTI.stale_reason(1_999_940, [(1_999_940, 91.0)], now=2_000_000)

        self.assertEqual(reason, "")

    def test_stale_output_keeps_price_and_pauses_alerts(self):
        with (
            mock.patch.object(WTI, "read_market_data", return_value=(91.48, 91.30, 2_000_000, [])),
            mock.patch.object(WTI, "emit") as emit,
            mock.patch.object(WTI, "should_alert") as should_alert,
            mock.patch.object(WTI, "notify") as notify,
        ):
            WTI.main()

        text, tooltip = emit.call_args.args
        self.assertIn("WTI $91.48", text)
        self.assertIn("STALE", text)
        self.assertIn("market closed or Yahoo data delayed", tooltip)
        should_alert.assert_not_called()
        notify.assert_not_called()


class StateFileTests(unittest.TestCase):
    def test_atomic_write_replaces_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            victim = Path(directory) / "victim"
            victim.write_text("leave me alone", encoding="utf-8")
            state_path = Path(directory) / "state.json"
            state_path.symlink_to(victim)

            with mock.patch.object(WTI, "STATE_FILE", str(state_path)):
                WTI.write_alert_state(72.5)

            self.assertEqual(victim.read_text(encoding="utf-8"), "leave me alone")
            self.assertFalse(state_path.is_symlink())
            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["price"], 72.5)
            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)

    def test_read_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            victim = Path(directory) / "victim.json"
            victim.write_text('{"time": 1, "price": 2}', encoding="utf-8")
            state_path = Path(directory) / "state.json"
            state_path.symlink_to(victim)

            with mock.patch.object(WTI, "STATE_FILE", str(state_path)):
                with self.assertRaises(OSError):
                    WTI.read_alert_state()

    def test_tmp_fallback_is_scoped_to_user(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(WTI.state_file_path().endswith(f"-{os.getuid()}.json"))


if __name__ == "__main__":
    unittest.main()
