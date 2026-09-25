"""Transport condition set (singapore-consequence-model.md §5).

Six recurring time conditions, all in the normal operating state. Hour windows
line up with DataMall's DAY_TYPE / TIME_PER_HOUR buckets. Closed and degraded
operating states belong to the later scenario work.
"""
from __future__ import annotations

from backend.data_sources.consequence import Condition

CONDITIONS = (
    Condition('weekday_am_peak', 'weekday', 7, 9),
    Condition('weekday_midday', 'weekday', 9, 17),
    Condition('weekday_pm_peak', 'weekday', 17, 20),
    Condition('weekday_night', 'weekday', 20, 7),
    Condition('weekend_day', 'weekend', 7, 20),
    Condition('weekend_night', 'weekend', 20, 7),
)


def hours(condition: Condition) -> tuple:
    """Clock hours (0-23) covered by a condition; windows may wrap midnight."""
    start, end = condition.hour_start, condition.hour_end
    span = (end - start) % 24 or 24
    return tuple((start + i) % 24 for i in range(span))
