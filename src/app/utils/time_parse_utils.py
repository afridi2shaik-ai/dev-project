"""
Time parsing utilities for natural language time expressions.

Supports parsing phrases like "in 10 minutes", "tomorrow at 10am", etc.
All times are interpreted as UTC.
"""

import datetime
import re
from typing import Optional

from loguru import logger


class TimeParseError(Exception):
    """Raised when a time expression cannot be parsed."""
    pass


def parse_time_expression(time_text: str) -> datetime.datetime:
    """
    Parse natural language time expressions into UTC datetime objects.

    Supported formats:
    - "in X minutes" / "in X mins"
    - "in X hours" / "in X hrs"
    - "today" (optional "at HH:MM" or "at HH:MM AM/PM")
    - "tomorrow" (optional "at HH:MM" or "at HH:MM AM/PM")

    Args:
        time_text: The natural language time expression

    Returns:
        UTC datetime object

    Raises:
        TimeParseError: If the time expression cannot be parsed
    """
    if not time_text or not time_text.strip():
        raise TimeParseError("Time expression cannot be empty")

    text = time_text.strip().lower()

    # Parse "in X minutes/hours" patterns
    in_pattern = re.match(r'^in\s+(\d+)\s+(minutes?|mins?|hours?|hrs?)$', text)
    if in_pattern:
        amount = int(in_pattern.group(1))
        unit = in_pattern.group(2)

        now = datetime.datetime.now(datetime.timezone.utc)

        if unit in ('minute', 'minutes', 'min', 'mins'):
            return now + datetime.timedelta(minutes=amount)
        elif unit in ('hour', 'hours', 'hr', 'hrs'):
            return now + datetime.timedelta(hours=amount)

    # Parse "today" or "tomorrow" patterns
    day_pattern = re.match(r'^(today|tomorrow)(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?$', text)
    if day_pattern:
        day = day_pattern.group(1)
        hour = day_pattern.group(2)
        minute = day_pattern.group(3) or '0'
        am_pm = day_pattern.group(4)

        now = datetime.datetime.now(datetime.timezone.utc)

        if day == 'tomorrow':
            base_date = now.date() + datetime.timedelta(days=1)
        else:  # today
            base_date = now.date()

        if hour:  # Time specified
            hour = int(hour)
            minute = int(minute)

            # Handle AM/PM
            if am_pm:
                if am_pm == 'pm' and hour != 12:
                    hour += 12
                elif am_pm == 'am' and hour == 12:
                    hour = 0

            # Create the datetime
            try:
                scheduled_time = datetime.datetime.combine(
                    base_date,
                    datetime.time(hour, minute),
                    tzinfo=datetime.timezone.utc
                )

                # If the time has already passed today, schedule for tomorrow
                if day == 'today' and scheduled_time <= now:
                    scheduled_time += datetime.timedelta(days=1)

                return scheduled_time

            except ValueError as e:
                raise TimeParseError(f"Invalid time format: {hour}:{minute}")

        else:  # No time specified, default to 9 AM
            return datetime.datetime.combine(
                base_date,
                datetime.time(9, 0),  # 9:00 AM
                tzinfo=datetime.timezone.utc
            )

    # If we get here, the expression wasn't recognized
    raise TimeParseError(f"Could not parse time expression: '{time_text}'. Supported formats: 'in X minutes/hours', 'today/tomorrow [at HH:MM [AM/PM]]'")


def format_scheduled_time(dt: datetime.datetime) -> str:
    """Format a datetime for display in tool responses."""
    return dt.strftime("%Y-%m-%d %H:%M UTC")


if __name__ == "__main__":
    # Quick test
    test_cases = [
        "in 10 minutes",
        "in 2 hours",
        "today at 10:30 am",
        "tomorrow at 3 pm",
        "today",
        "tomorrow"
    ]

    for case in test_cases:
        try:
            result = parse_time_expression(case)
            print(f"'{case}' -> {format_scheduled_time(result)}")
        except TimeParseError as e:
            print(f"'{case}' -> ERROR: {e}")
