"""Which moment a scheduled run stands for.

GitHub Actions often starts scheduled runs hours late. Deciding "is it due?" from the start time
then skips the job, so the CLI decides from the cron line that fired instead
(`github.event.schedule`), which does not move when the run is delayed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def scheduled_local_time(cron: str, now_utc: datetime, timezone: str) -> datetime:
    """The latest moment at or before `now_utc` that `cron` fired, as naive local time.

    Only plain daily or weekly lines are supported ("M H * * *" or "M H * * D" with numbers),
    which is all the workflows use. The day-of-week field is not checked here: the caller checks
    the local weekday, so a wrong field shows up as "not due" rather than a wrong send.
    """
    fields = cron.split()
    if len(fields) != 5 or not (fields[0].isdigit() and fields[1].isdigit()):
        raise ValueError(f"unsupported cron line: {cron!r}")
    minute, hour = int(fields[0]), int(fields[1])

    fired = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fired > now_utc:  # the run started after UTC midnight: it belongs to the day before
        fired -= timedelta(days=1)
    return fired.astimezone(ZoneInfo(timezone)).replace(tzinfo=None)
