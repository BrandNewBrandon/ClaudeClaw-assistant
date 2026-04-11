from __future__ import annotations

from app.monitors import MonitorRunner, disk_usage_monitor, process_count_monitor


def test_monitor_runner_fires_alert():
    sent: list[tuple[str, str, str]] = []
    runner = MonitorRunner(cooldown_seconds=0)
    runner.register_sender("s", lambda s, c, t: sent.append((s, c, t)))
    runner.register_target("s", "c1")
    runner.register_monitor("test", lambda: "Alert!")
    runner.tick()
    assert len(sent) == 1
    assert "Alert!" in sent[0][2]


def test_monitor_runner_no_alert_when_none():
    sent: list[tuple[str, str, str]] = []
    runner = MonitorRunner(cooldown_seconds=0)
    runner.register_sender("s", lambda s, c, t: sent.append((s, c, t)))
    runner.register_target("s", "c1")
    runner.register_monitor("test", lambda: None)
    runner.tick()
    assert len(sent) == 0


def test_monitor_runner_cooldown_prevents_repeat():
    sent: list[tuple[str, str, str]] = []
    runner = MonitorRunner(cooldown_seconds=3600)
    runner.register_sender("s", lambda s, c, t: sent.append((s, c, t)))
    runner.register_target("s", "c1")
    runner.register_monitor("test", lambda: "Alert!")
    runner.tick()
    runner.tick()
    assert len(sent) == 1


def test_disk_usage_monitor_returns_none_normally():
    result = disk_usage_monitor(threshold_percent=99.9)()
    assert result is None


def test_process_count_monitor_returns_none_normally():
    result = process_count_monitor(threshold=99999)()
    assert result is None


def test_monitor_runner_enabled_toggle():
    runner = MonitorRunner()
    assert runner.enabled is True
    runner.enabled = False
    assert runner.enabled is False
