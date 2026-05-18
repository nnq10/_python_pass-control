import unittest

from app.pages.scanner import _next_result_token, _schedule_idle


class AliveWidget:
    def __init__(self, exists=True):
        self.exists = exists

    def winfo_exists(self):
        return self.exists


class FakeScannerApp:
    def __init__(self):
        self._scanner_idle_timer = None
        self._scanner_result_token = 0
        self._res = AliveWidget()
        self.callbacks = {}
        self.canceled = []
        self.idle_calls = 0

    def after(self, _delay_ms, callback):
        timer_id = f"timer-{len(self.callbacks) + 1}"
        self.callbacks[timer_id] = callback
        return timer_id

    def after_cancel(self, timer_id):
        self.canceled.append(timer_id)

    def _idle(self):
        self.idle_calls += 1


class ScannerTimerTests(unittest.TestCase):
    def test_new_scan_cancels_previous_idle_timer(self):
        app = FakeScannerApp()

        first_token = _next_result_token(app)
        _schedule_idle(app, first_token, 8000)
        first_timer = app._scanner_idle_timer

        second_token = _next_result_token(app)
        _schedule_idle(app, second_token, 8000)
        second_timer = app._scanner_idle_timer

        self.assertIn(first_timer, app.canceled)
        self.assertNotEqual(first_timer, second_timer)

    def test_stale_idle_callback_cannot_clear_latest_scan(self):
        app = FakeScannerApp()

        first_token = _next_result_token(app)
        _schedule_idle(app, first_token, 8000)
        first_timer = app._scanner_idle_timer

        second_token = _next_result_token(app)
        _schedule_idle(app, second_token, 8000)
        second_timer = app._scanner_idle_timer

        app.callbacks[first_timer]()
        self.assertEqual(app.idle_calls, 0)

        app.callbacks[second_timer]()
        self.assertEqual(app.idle_calls, 1)

    def test_idle_callback_ignores_destroyed_result_area(self):
        app = FakeScannerApp()

        token = _next_result_token(app)
        _schedule_idle(app, token, 8000)
        timer = app._scanner_idle_timer
        app._res.exists = False

        app.callbacks[timer]()
        self.assertEqual(app.idle_calls, 0)


if __name__ == "__main__":
    unittest.main()
