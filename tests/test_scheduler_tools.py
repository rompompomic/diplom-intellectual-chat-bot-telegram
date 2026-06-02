from __future__ import annotations

from tools.scheduler_tools import SchedulerTools


def test_open_app_can_resolve_http_url() -> None:
    scheduler = SchedulerTools()

    target = scheduler._resolve_open_target("https://www.google.com", url="https://example.com/page")

    assert target == "https://example.com/page"
    scheduler.shutdown()


def test_schedule_open_app_stores_url_target() -> None:
    scheduler = SchedulerTools()

    result = scheduler.schedule_open_app(
        app_name="browser",
        app_path="https://www.google.com",
        minutes=60,
        url="https://example.com/page",
    )

    assert result["target"] == "https://example.com/page"
    scheduler.cancel_last_task()
    scheduler.shutdown()
