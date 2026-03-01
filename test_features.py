"""
Local feature test runner for the Discord automation bot.

This script:
- Loads config from .env via load_config()
- Simulates message history in the configured timezone
- Tests daily reminder output
- Tests weekly report (scheduled + manual)
- Tests monthly report (scheduled + manual)
- Prints all generated messages so you can review report tables

Run:
    python test_features.py
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

import discord

from main import DiscordAutomationBot, load_config


@dataclass
class FakeAuthor:
    id: int
    bot: bool = False


@dataclass
class FakeMessage:
    author: FakeAuthor
    content: str
    created_at: datetime


class FakeChannel:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = messages
        self.sent_messages: list[str] = []

    async def history(
        self,
        limit: Optional[int] = None,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ):
        yielded = 0
        for msg in sorted(self._messages, key=lambda m: m.created_at, reverse=True):
            if after is not None and not (msg.created_at > after):
                continue
            if before is not None and not (msg.created_at < before):
                continue
            yield msg
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    async def send(self, content: str, **kwargs) -> None:
        self.sent_messages.append(content)


def make_local_dt(tz, y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=tz)


def week_window(now: datetime, manual: bool) -> tuple[date, date]:
    today = now.date()
    days_since_sunday = (today.weekday() + 1) % 7
    start_date = today - timedelta(days=days_since_sunday)
    return start_date, today


def month_window(now: datetime, manual: bool) -> tuple[date, date]:
    today = now.date()
    if manual:
        return today.replace(day=1), today
    first = today.replace(day=1)
    end = first - timedelta(days=1)
    return end.replace(day=1), end


def sample_messages(config, now: datetime) -> list[FakeMessage]:
    users = config.user_ids
    tz = config.timezone
    update_keyword = "daily update"
    non_update_text = "random message"
    messages: list[FakeMessage] = []

    def add(uid: int, dt: datetime, content: str) -> None:
        messages.append(FakeMessage(author=FakeAuthor(uid, bot=False), content=content, created_at=dt))

    # Include manual command messages (must be ignored by counters)
    add(users[0], make_local_dt(tz, now.year, now.month, max(now.day - 1, 1), 9), config.weekly_report_command)
    add(users[1], make_local_dt(tz, now.year, now.month, max(now.day - 1, 1), 10), config.monthly_report_command)
    add(users[2], make_local_dt(tz, now.year, now.month, max(now.day - 1, 1), 11), config.manual_reminder_command)

    # Build messages across last 45 days to cover weekly + monthly windows.
    for offset in range(0, 45):
        day = now.date() - timedelta(days=offset)
        base_dt = datetime.combine(day, time(10, 0), tzinfo=tz)
        # user 0: consistent updater, sometimes duplicate updates same day
        add(users[0], base_dt, update_keyword)
        add(users[0], base_dt + timedelta(hours=1), update_keyword)

        # user 1: updates every 2 days
        if offset % 2 == 0:
            add(users[1], base_dt + timedelta(minutes=30), "updates done")

        # user 2: sparse
        if offset % 5 == 0:
            add(users[2], base_dt + timedelta(hours=2), "Daily Updates posted")

        # user 3: non-update text (should be ignored)
        add(users[3], base_dt + timedelta(hours=3), non_update_text)

    # Add a bot message that matches keyword (should be ignored)
    messages.append(
        FakeMessage(
            author=FakeAuthor(users[0], bot=True),
            content=update_keyword,
            created_at=make_local_dt(tz, now.year, now.month, max(now.day - 2, 1), 13),
        )
    )
    return messages


async def run() -> None:
    # Make emoji/table output safe in Windows terminals using cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    config = load_config()
    intents = discord.Intents.none()
    bot = DiscordAutomationBot(config=config, intents=intents)

    now = datetime.now(config.timezone)
    fake_channel = FakeChannel(sample_messages(config, now))

    async def fake_get_target_channel():
        return fake_channel

    bot.get_target_channel = fake_get_target_channel  # type: ignore[method-assign]

    print("=== CONFIG CHECK ===")
    print(f"Timezone: {config.timezone_name}")
    print(f"Users configured: {len(config.user_ids)}")
    print(f"ONE_UPDATE_PER_DAY={config.one_update_per_day}")
    print(f"RANK_REPORT={config.rank_report}")
    print(f"INCLUDE_MISSED_DAYS={config.include_missed_days}")
    print()

    w_s_start, w_s_end = week_window(now, manual=False)
    w_m_start, w_m_end = week_window(now, manual=True)
    m_s_start, m_s_end = month_window(now, manual=False)
    m_m_start, m_m_end = month_window(now, manual=True)

    print("=== EXPECTED WINDOWS ===")
    print(f"Weekly scheduled: {w_s_start} -> {w_s_end}")
    print(f"Weekly manual:    {w_m_start} -> {w_m_end}")
    print(f"Monthly scheduled:{m_s_start} -> {m_s_end}")
    print(f"Monthly manual:   {m_m_start} -> {m_m_end}")
    print()

    await bot.send_daily_reminder()
    await bot.send_weekly_report(reason="scheduled")
    await bot.send_weekly_report(reason="manual")
    await bot.send_monthly_report(reason="scheduled")
    await bot.send_monthly_report(reason="manual")

    print("=== GENERATED OUTPUTS ===")
    for i, payload in enumerate(fake_channel.sent_messages, start=1):
        print(f"\n--- Message {i} ---")
        print(payload)


if __name__ == "__main__":
    asyncio.run(run())
