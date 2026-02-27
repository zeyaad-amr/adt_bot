"""
Discord automation bot for daily reminders and weekly reports.

Features:
- Daily reminder in one target channel (default: 4:00 PM Cairo)
- Weekly report every Thursday at 8:00 PM Cairo
- Manual weekly report trigger from the target channel at any time
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

WEEKLY_REPORT_TITLE = "\U0001F4CA Weekly Report"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("discord_automation_bot")


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    channel_id: int
    user_ids: list[int]
    timezone_name: str
    timezone: ZoneInfo
    daily_reminder_time: time
    weekly_report_time: time
    weekly_report_command: str
    manual_reminder_command: str
    update_message_pattern: str
    one_update_per_day: bool
    rank_report: bool
    include_missed_days: bool


def parse_time(value: str, var_name: str) -> time:
    try:
        hour_str, minute_str = value.strip().split(":")
        return time(hour=int(hour_str), minute=int(minute_str))
    except Exception as exc:
        raise ValueError(f"{var_name} must be in HH:MM format. Got: {value!r}") from exc


def parse_int(value: str, var_name: str) -> int:
    try:
        return int(value.strip())
    except Exception as exc:
        raise ValueError(f"{var_name} must be an integer. Got: {value!r}") from exc


def parse_user_ids(value: str) -> list[int]:
    ids = [item.strip() for item in value.split(",") if item.strip()]
    if not ids:
        raise ValueError("USER_IDS is empty.")
    return [parse_int(item, "USER_IDS item") for item in ids]


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> BotConfig:
    token = os.getenv("BOT_TOKEN", "").strip()
    channel_id_raw = os.getenv("CHANNEL_ID", "").strip()
    user_ids_raw = os.getenv("USER_IDS", "").strip()
    timezone_name = os.getenv("TIMEZONE", "Africa/Cairo").strip()
    daily_time_raw = os.getenv("DAILY_REMINDER_TIME", "16:00").strip()
    weekly_time_raw = os.getenv("WEEKLY_REPORT_TIME", "20:00").strip()
    weekly_report_command = os.getenv("WEEKLY_REPORT_COMMAND", "!weekly_report").strip()
    manual_reminder_command = os.getenv("MANUAL_REMINDER_COMMAND", "!daily_reminder").strip()
    update_message_pattern = os.getenv(
        "UPDATE_MESSAGE_PATTERN",
        r"\b(daily\W*updates?|updates?)\b",
    ).strip()
    one_update_per_day = parse_bool(os.getenv("ONE_UPDATE_PER_DAY", "false"))
    rank_report = parse_bool(os.getenv("RANK_REPORT", "false"))
    include_missed_days = parse_bool(os.getenv("INCLUDE_MISSED_DAYS", "false"))

    if not token:
        raise ValueError("BOT_TOKEN is required.")
    if not channel_id_raw:
        raise ValueError("CHANNEL_ID is required.")
    if not user_ids_raw:
        raise ValueError("USER_IDS is required.")
    if not weekly_report_command:
        raise ValueError("WEEKLY_REPORT_COMMAND cannot be empty.")
    if not manual_reminder_command:
        raise ValueError("MANUAL_REMINDER_COMMAND cannot be empty.")
    if not update_message_pattern:
        raise ValueError("UPDATE_MESSAGE_PATTERN cannot be empty.")

    try:
        timezone_obj = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name!r}") from exc

    channel_id = parse_int(channel_id_raw, "CHANNEL_ID")
    user_ids = parse_user_ids(user_ids_raw)

    return BotConfig(
        bot_token=token,
        channel_id=channel_id,
        user_ids=user_ids,
        timezone_name=timezone_name,
        timezone=timezone_obj,
        daily_reminder_time=parse_time(daily_time_raw, "DAILY_REMINDER_TIME"),
        weekly_report_time=parse_time(weekly_time_raw, "WEEKLY_REPORT_TIME"),
        weekly_report_command=weekly_report_command,
        manual_reminder_command=manual_reminder_command,
        update_message_pattern=update_message_pattern,
        one_update_per_day=one_update_per_day,
        rank_report=rank_report,
        include_missed_days=include_missed_days,
    )


def format_daily_reminder() -> str:
    return (
        "@everyone\n"
        "⏰ Daily Update Reminder\n\n"
        "If you didn’t write your update yet, please send it now."
    )


def seconds_until_next_run(target_time: time, timezone_obj: ZoneInfo, weekday: Optional[int] = None) -> float:
    now = datetime.now(timezone_obj)

    if weekday is None:
        candidate = datetime.combine(now.date(), target_time, tzinfo=timezone_obj)
        if candidate <= now:
            candidate += timedelta(days=1)
    else:
        days_ahead = (weekday - now.weekday()) % 7
        candidate_date = now.date() + timedelta(days=days_ahead)
        candidate = datetime.combine(candidate_date, target_time, tzinfo=timezone_obj)
        if candidate <= now:
            candidate += timedelta(days=7)

    return max((candidate - now).total_seconds(), 1.0)


def build_weekly_report(user_ids, counts, missed_days, rank_report, include_missed_days):
    lines = [WEEKLY_REPORT_TITLE, ""]

    ordered_user_ids = user_ids
    if rank_report:
        ordered_user_ids = sorted(user_ids, key=lambda uid: counts[uid], reverse=True)

    for user_id in ordered_user_ids:
        line = f"<@{user_id}> : {counts[user_id]} updates"
        if include_missed_days:
            line += f" | Missed Days: {missed_days[user_id]}"
        lines.append(line)

    return "\n".join(lines)


class DiscordAutomationBot(discord.Client):
    def __init__(self, config: BotConfig, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.tasks_started = False
        self.manual_weekly_command = config.weekly_report_command.strip().lower()
        self.manual_reminder_command = config.manual_reminder_command.strip().lower()
        self.update_message_regex = re.compile(config.update_message_pattern, re.IGNORECASE)

    def is_update_message(self, content: str) -> bool:
        return bool(self.update_message_regex.search(content))

    async def get_target_channel(self) -> Optional[discord.abc.Messageable]:
        channel = self.get_channel(self.config.channel_id)

        if channel is None:
            try:
                channel = await self.fetch_channel(self.config.channel_id)
            except Exception as exc:
                logger.error("Failed to fetch channel: %s", exc)
                return None

        return channel

    async def send_daily_reminder(self):
        channel = await self.get_target_channel()
        if channel is None:
            return

        await channel.send(
            format_daily_reminder(),
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
        logger.info("Daily reminder sent.")

    async def collect_weekly_counts(self, channel):
        now = datetime.now(self.config.timezone)
        start_time = now - timedelta(days=7)

        counts = {uid: 0 for uid in self.config.user_ids}
        active_days = {uid: set() for uid in self.config.user_ids}
        seen_daily = set()

        async for message in channel.history(limit=None, after=start_time):
            if message.author.bot:
                continue

            normalized_content = message.content.strip().lower()
            if normalized_content == self.manual_weekly_command:
                continue
            if normalized_content == self.manual_reminder_command:
                continue
            if not self.is_update_message(message.content):
                continue

            uid = message.author.id
            if uid not in counts:
                continue

            local_day = message.created_at.astimezone(self.config.timezone).date()

            if self.config.one_update_per_day:
                key = (uid, local_day)
                if key in seen_daily:
                    continue
                seen_daily.add(key)

            counts[uid] += 1
            active_days[uid].add(local_day)

        missed_days = {uid: 7 - min(len(days), 7) for uid, days in active_days.items()}
        return counts, missed_days

    async def send_weekly_report(self, reason="scheduled"):
        channel = await self.get_target_channel()
        if channel is None:
            return

        counts, missed_days = await self.collect_weekly_counts(channel)

        report = build_weekly_report(
            self.config.user_ids,
            counts,
            missed_days,
            self.config.rank_report,
            self.config.include_missed_days,
        )

        await channel.send(report)
        logger.info("Weekly report (%s) sent.", reason)

    async def daily_scheduler(self):
        while not self.is_closed():
            wait_seconds = seconds_until_next_run(
                self.config.daily_reminder_time,
                self.config.timezone,
            )
            await asyncio.sleep(wait_seconds)
            await self.send_daily_reminder()

    async def weekly_scheduler(self):
        while not self.is_closed():
            wait_seconds = seconds_until_next_run(
                self.config.weekly_report_time,
                self.config.timezone,
                weekday=3,
            )
            await asyncio.sleep(wait_seconds)
            await self.send_weekly_report()

    async def on_ready(self):
        logger.info("Logged in as %s", self.user)

        if self.tasks_started:
            return

        self.tasks_started = True
        asyncio.create_task(self.daily_scheduler())
        asyncio.create_task(self.weekly_scheduler())
        logger.info("Schedulers started.")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id != self.config.channel_id:
            return

        normalized_content = message.content.strip().lower()
        if normalized_content == self.manual_weekly_command:
            await self.send_weekly_report(reason="manual")
            return
        if normalized_content == self.manual_reminder_command:
            await self.send_daily_reminder()


def main():
    config = load_config()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True

    bot = DiscordAutomationBot(config=config, intents=intents)
    bot.run(config.bot_token)


if __name__ == "__main__":
    main()