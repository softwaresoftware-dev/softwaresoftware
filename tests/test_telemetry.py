"""Tests for telemetry — must be disabled and network-silent during the test suite."""

import telemetry


def test_telemetry_disabled_in_tests():
    """conftest disables telemetry before any module import."""
    assert telemetry.ENABLED is False


def test_send_event_noop_when_disabled(monkeypatch):
    """With telemetry disabled, send_event never spawns a network thread."""
    started = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            started.append((args, kwargs))

        def start(self):
            raise AssertionError("telemetry thread started while disabled")

    monkeypatch.setattr(telemetry.threading, "Thread", FakeThread)
    telemetry.send_event("install", plugin_name="x")
    assert started == []


def test_send_event_enabled_uses_background_thread(monkeypatch):
    """Sanity check: when enabled, send_event posts via a daemon thread (mocked)."""
    posted = []
    monkeypatch.setattr(telemetry, "ENABLED", True)
    monkeypatch.setattr(telemetry, "_post", lambda payload: posted.append(payload))

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(telemetry.threading, "Thread", ImmediateThread)
    telemetry.send_event("resolve", plugin_name="x")
    assert len(posted) == 1
    assert posted[0]["event_type"] == "resolve"
