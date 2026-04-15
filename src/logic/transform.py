from typing import Any
from datetime import datetime


def yearweek_to_date(value: str) -> str:
    value = str(value).strip()

    if len(value) == 6 and value.isdigit():
        year = int(value[:4])
        week = int(value[4:6])

        # Monday of ISO week
        dt = datetime.fromisocalendar(year, week, 1)
        return f"{dt.day}/{dt.month}-{dt.year}"

    return value


def apply_transform(value: Any, transform_name: str) -> Any:
    if transform_name == "identity":
        return value

    if transform_name == "combine_period":
        if isinstance(value, (list, tuple)) and len(value) == 2:
            start, end = value
            start_formatted = yearweek_to_date(start)
            end_formatted = yearweek_to_date(end)
            return f"{start_formatted} -> {end_formatted}"

        return yearweek_to_date(value)

    if transform_name == "sek_per_week_label":
        return f"{value} SEK/week"

    if transform_name == "sek_total_label":
        return f"{value} SEK"

    return value