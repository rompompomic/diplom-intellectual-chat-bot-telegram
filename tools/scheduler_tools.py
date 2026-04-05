from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

try:
    from apscheduler.executors.pool import ThreadPoolExecutor
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:  # noqa: BLE001
    BackgroundScheduler = None  # type: ignore[assignment]
    ThreadPoolExecutor = None  # type: ignore[assignment]


@dataclass(slots=True)
class SchedulerTools:
    timezone: str = "UTC"
    _scheduler: BackgroundScheduler | None = field(init=False, default=None)
    _last_job_id: str | None = field(default=None, init=False)
    _timers: dict[str, threading.Timer] = field(default_factory=dict, init=False)
    _jobs_meta: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if BackgroundScheduler is not None and ThreadPoolExecutor is not None:
            self._scheduler = BackgroundScheduler(
                timezone=self.timezone,
                executors={"default": ThreadPoolExecutor(max_workers=5)},
            )
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        self._jobs_meta.clear()

    def schedule_shutdown(self, minutes: int) -> dict:
        if minutes <= 0:
            raise ValueError("minutes must be > 0")
        run_at = datetime.now() + timedelta(minutes=minutes)
        job_id = f"shutdown_{int(run_at.timestamp())}"
        if self._scheduler is not None:
            job = self._scheduler.add_job(
                self._shutdown_now,
                trigger="date",
                run_date=run_at,
                id=job_id,
                replace_existing=True,
            )
            self._last_job_id = job.id
            return {"status": "ok", "job_id": job.id, "run_at": run_at.isoformat()}

        timer = threading.Timer(minutes * 60, self._shutdown_now)
        timer.daemon = True
        timer.start()
        self._timers[job_id] = timer
        self._jobs_meta[job_id] = {"next_run_time": run_at.isoformat(), "name": "shutdown"}
        self._last_job_id = job_id
        return {"status": "ok", "job_id": job_id, "run_at": run_at.isoformat()}

    def cancel_shutdown(self) -> dict:
        cancelled = 0
        if self._scheduler is not None:
            for job in self._scheduler.get_jobs():
                if job.id.startswith("shutdown_"):
                    self._scheduler.remove_job(job.id)
                    cancelled += 1
        else:
            for job_id in list(self._timers.keys()):
                if job_id.startswith("shutdown_"):
                    self._timers[job_id].cancel()
                    self._timers.pop(job_id, None)
                    self._jobs_meta.pop(job_id, None)
                    cancelled += 1
        subprocess.run(["shutdown", "/a"], capture_output=True, text=True, check=False)
        return {"status": "ok", "cancelled": cancelled}

    def schedule_open_app(self, app_name: str, app_path: str, minutes: int) -> dict:
        if minutes <= 0:
            raise ValueError("minutes must be > 0")
        run_at = datetime.now() + timedelta(minutes=minutes)
        job_id = f"open_app_{app_name}_{int(run_at.timestamp())}"
        if self._scheduler is not None:
            job = self._scheduler.add_job(
                self._open_app,
                trigger="date",
                run_date=run_at,
                kwargs={"app_path": app_path},
                id=job_id,
                replace_existing=False,
            )
            self._last_job_id = job.id
            return {"status": "ok", "job_id": job.id, "run_at": run_at.isoformat(), "app": app_name}

        timer = threading.Timer(minutes * 60, self._open_app, kwargs={"app_path": app_path})
        timer.daemon = True
        timer.start()
        self._timers[job_id] = timer
        self._jobs_meta[job_id] = {"next_run_time": run_at.isoformat(), "name": f"open_app:{app_name}"}
        self._last_job_id = job_id
        return {"status": "ok", "job_id": job_id, "run_at": run_at.isoformat(), "app": app_name}

    def open_app(self, app_path: str) -> dict:
        self._open_app(app_path)
        return {"status": "ok", "app_path": app_path}

    def schedule_callable(
        self,
        callback: Callable[..., Any],
        minutes: int,
        kwargs: dict[str, Any] | None = None,
        job_prefix: str = "custom",
    ) -> dict:
        if minutes <= 0:
            raise ValueError("minutes must be > 0")
        run_at = datetime.now() + timedelta(minutes=minutes)
        job_id = f"{job_prefix}_{int(run_at.timestamp())}"
        if self._scheduler is not None:
            job = self._scheduler.add_job(
                callback,
                trigger="date",
                run_date=run_at,
                kwargs=kwargs or {},
                id=job_id,
            )
            self._last_job_id = job.id
            return {"status": "ok", "job_id": job.id, "run_at": run_at.isoformat()}

        timer = threading.Timer(minutes * 60, callback, kwargs=kwargs or {})
        timer.daemon = True
        timer.start()
        self._timers[job_id] = timer
        self._jobs_meta[job_id] = {"next_run_time": run_at.isoformat(), "name": job_prefix}
        self._last_job_id = job_id
        return {"status": "ok", "job_id": job_id, "run_at": run_at.isoformat()}

    def list_scheduled_tasks(self) -> dict:
        tasks = []
        if self._scheduler is not None:
            for job in self._scheduler.get_jobs():
                tasks.append(
                    {
                        "job_id": job.id,
                        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                        "name": str(job.func_ref or job.func),
                    }
                )
        else:
            for job_id, meta in self._jobs_meta.items():
                tasks.append(
                    {
                        "job_id": job_id,
                        "next_run_time": meta.get("next_run_time"),
                        "name": meta.get("name"),
                    }
                )
        return {"count": len(tasks), "tasks": tasks}

    def cancel_scheduled_task(self, job_id: str) -> dict:
        if self._scheduler is not None:
            self._scheduler.remove_job(job_id)
        else:
            timer = self._timers.get(job_id)
            if timer is None:
                raise ValueError(f"Task '{job_id}' was not found.")
            timer.cancel()
            self._timers.pop(job_id, None)
            self._jobs_meta.pop(job_id, None)
        return {"status": "ok", "job_id": job_id}

    def cancel_last_task(self) -> dict:
        if not self._last_job_id:
            return {"status": "not_found", "message": "No scheduled tasks yet."}
        job_id = self._last_job_id
        if self._scheduler is not None:
            self._scheduler.remove_job(job_id)
        else:
            timer = self._timers.get(job_id)
            if timer is not None:
                timer.cancel()
                self._timers.pop(job_id, None)
                self._jobs_meta.pop(job_id, None)
        self._last_job_id = None
        return {"status": "ok", "job_id": job_id}

    def _open_app(self, app_path: str) -> None:
        if not os.path.exists(app_path):
            raise FileNotFoundError(app_path)
        os.startfile(app_path)  # type: ignore[attr-defined]

    def _shutdown_now(self) -> None:
        subprocess.run(["shutdown", "/s", "/t", "0"], capture_output=True, text=True, check=False)
