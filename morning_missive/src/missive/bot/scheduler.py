from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler


def start_daily(*, tz: str, hour: int, minute: int, job_fn) -> None:
    sched = BlockingScheduler(timezone=tz)
    sched.add_job(
        job_fn,
        "cron",
        hour=hour,
        minute=minute,
        misfire_grace_time=1800,  # 30 minutes grace if dyno restarts
        coalesce=True,  # never run more than once per day
    )

    print(f"[OK] Scheduled daily missive at {hour:02d}:{minute:02d} ({tz})")
    sched.start()
