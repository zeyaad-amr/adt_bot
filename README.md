# Discord Automation Bot

Lightweight Discord bot built with `discord.py` to automate:

- Daily reminder (mentions 6 users in a specific thread)
- Weekly report for week-to-date (Sunday-current day)
- Monthly report for calendar-month window
- Report generation from one thread only
- On-demand weekly/monthly report commands at any time
- Simple free-tier deployment (Railway / Render)

## Features

- Python 3.10+
- No database
- Uses message history scan for fixed calendar windows
- Ignores bot messages in counting
- Always includes all 6 users in weekly report (including `0`)
- Supports monthly report with the same user set
- Handles empty thread safely
- Supports manual weekly report generation from thread command
- Supports manual monthly report generation from thread command
- Logs clear errors for thread lookup and missing permissions
- Resumes schedulers automatically after process restart

## Architecture (Flowchart)

```mermaid
flowchart TD
    A[Bot Process Starts] --> B[Load Env Config]
    B --> C[Discord Login]
    C --> D[on_ready]
    D --> E[Start Daily Scheduler]
    D --> F[Start Weekly Scheduler]

    E --> G[Wait Until Next 16:00 Cairo]
    G --> H[Resolve Thread]
    H --> I[Send Reminder Mentioning 6 Users]
    I --> E

    F --> J[Wait Until Next Sunday 20:00 Cairo]
    J --> K[Resolve Thread]
    K --> L[Read Current Week (Sunday-Today) Messages]
    L --> M[Filter: 6 Users + Non-Bot]
    M --> N[Count Updates]
    N --> O[Post Weekly Report in Thread]
    O --> F

    D --> M1[Start Monthly Scheduler]
    M1 --> M2[Wait Until 1st Day of Next Month]
    M2 --> M3[Read Previous Month Messages]
    M3 --> M4[Post Monthly Report in Thread]
    M4 --> M1

    D --> P[on_message]
    P --> Q{Message equals WEEKLY_REPORT_COMMAND\nand from target thread?}
    Q -- yes --> R[Generate and Post Weekly Report Now]
    Q -- no --> P
```

## Daily Reminder Sequence

```mermaid
sequenceDiagram
    participant S as Daily Scheduler
    participant B as Bot Client
    participant T as Target Thread

    S->>S: Sleep until DAILY_REMINDER_TIME (Cairo)
    S->>B: send_daily_reminder()
    B->>B: get_target_thread()
    B->>T: POST reminder with 6 mentions
    T-->>B: Message created
    B-->>S: Success / log error
```

## Weekly Reporting Pipeline

```mermaid
flowchart LR
    A[Trigger Sunday 20:00 Cairo] --> B[Fetch Thread]
    B --> C[History: last 7 days]
    C --> D{Message author bot?}
    D -- yes --> C
    D -- no --> E{Author in USER_IDS?}
    E -- no --> C
    E -- yes --> F[Count message]
    F --> G[Track active day]
    G --> C
    C --> H[Build report lines for all 6 users]
    H --> I[Post report in same thread]
```

## Example Weekly Distribution (Sample Chart)

```mermaid
pie showData
    title Sample Weekly Update Share
    "User 1" : 9
    "User 2" : 7
    "User 3" : 6
    "User 4" : 4
    "User 5" : 3
    "User 6" : 1
```

## Message Formats

Daily:

```text
<@user1> <@user2> <@user3> <@user4> <@user5> <@user6>
Daily reminder: Please post your update.
```

Weekly:

```text
\U0001F4CA Weekly Report

Period: YYYY-MM-DD to YYYY-MM-DD (Week-to-date)
Total Updates: X

[ASCII table with Rank, User, Updates, Active Days, Missed Days, Contribution %]
```

Monthly:

```text
\U0001F4C8 Monthly Report

Period: YYYY-MM-DD to YYYY-MM-DD (Month-to-date or Previous calendar month)
Total Updates: X

[ASCII table with Rank, User, Updates, Active Days, Missed Days, Contribution %]
```

Manual trigger:

```text
!weekly_report
!monthly_report
```

Post the command in the configured thread to generate the report immediately.

## Configuration

Set environment variables in your host platform (or local shell).
You can start from `.env.example`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | - | Discord bot token |
| `THREAD_ID` | Yes | - | Target Discord thread ID |
| `USER_IDS` | Yes | - | Comma-separated list of exactly 6 user IDs |
| `DAILY_REMINDER_TIME` | No | `16:00` | Daily reminder time (`HH:MM`, Cairo local time) |
| `WEEKLY_REPORT_TIME` | No | `20:00` | Weekly report time (`HH:MM`, Cairo local time) |
| `MONTHLY_REPORT_TIME` | No | `20:00` | Monthly report time (`HH:MM`, Cairo local time) |
| `WEEKLY_REPORT_COMMAND` | No | `!weekly_report` | Command that triggers weekly report on demand in thread |
| `MONTHLY_REPORT_COMMAND` | No | `!monthly_report` | Command that triggers monthly report on demand in thread |
| `TIMEZONE` | No | `Africa/Cairo` | IANA timezone name |
| `ONE_UPDATE_PER_DAY` | No | `false` | Optional dedupe: max 1 update per user per day |
| `RANK_REPORT` | No | `false` | Optional ranking by update count |
| `INCLUDE_MISSED_DAYS` | No | `false` | Optional `Missed Days` in weekly lines |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |

## Permissions Required

Grant the bot these permissions in the server/thread context:

- View Channels
- Send Messages
- Read Message History

If permissions are missing, the bot logs a clear error and continues running.

## Local Run

1. Install dependencies:
```powershell
pip install -r requirements.txt
```

2. Export variables (example in PowerShell):
```powershell
$env:BOT_TOKEN="your-token"
$env:THREAD_ID="123456789012345678"
$env:USER_IDS="111111111111111111,222222222222222222,333333333333333333,444444444444444444,555555555555555555,666666666666666666"
$env:DAILY_REMINDER_TIME="16:00"
$env:WEEKLY_REPORT_TIME="20:00"
$env:MONTHLY_REPORT_TIME="20:00"
$env:WEEKLY_REPORT_COMMAND="!weekly_report"
$env:MONTHLY_REPORT_COMMAND="!monthly_report"
$env:TIMEZONE="Africa/Cairo"
```

3. Start:
```powershell
python main.py
```

## Deployment

### Railway

1. Create new project from repo/folder.
2. Set environment variables listed above.
3. Start command:
```text
python main.py
```
4. Ensure service root is `mindrift_tasks/discord_bot` (or adjust command path).

### Render

1. Create a new `Web Service` or `Background Worker` from repo.
2. Runtime: Python 3.10+.
3. Build command:
```text
pip install -r requirements.txt
```
4. Start command:
```text
python main.py
```
5. Add required environment variables.

## Operational Notes

- Weekly report (scheduled/manual) uses week-to-date: from Sunday of current week to today.
- If today is Sunday, weekly report includes Sunday only.
- Scheduled monthly report runs on day 1 and reports the previous calendar month.
- Manual monthly report reports from day 1 of the current month until now.
- After host restarts, next run is recalculated from current Cairo time.
- No persistent state is required.
- Empty thread produces a valid report with all users at `0`.

## Files

- `main.py`: bot runtime, schedulers, config parsing, report generation
- `requirements.txt`: dependencies (`discord.py`, `tzdata`)
- `.env.example`: ready-to-edit configuration template
