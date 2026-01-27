# daily_playbook/src/playbook/bot/scheduler.py
from __future__ import annotations

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


def start_daily_job(*, tz: str, hhmm: str, job_coro) -> AsyncIOScheduler:
    hh, mm = hhmm.split(":")
    hh_i, mm_i = int(hh), int(mm)

    scheduler = AsyncIOScheduler(timezone=tz)

    async def wrapper():
        await job_coro()

    def fire():
        asyncio.create_task(wrapper())

    scheduler.add_job(
        fire,
        CronTrigger(hour=hh_i, minute=mm_i, timezone=tz),
        id="daily_playbook_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    scheduler.start()
    return scheduler
