"""Time configuration -> concrete teaching periods.

An institution, a department or a single class can each carry a *schedule*
(working days, start/end time, lecture length, breaks, lunch, periods per day,
per-day overrides). This module turns that configuration into concrete
periods expressed in minutes from midnight, so that classes running on
different schedules can still be compared on real clock time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ScheduleConfigError(ValueError):
    """Raised when a schedule configuration cannot produce a valid day."""


def parse_hhmm(value: str | int) -> int:
    if isinstance(value, int):
        return value
    try:
        hours, minutes = value.strip().split(":")
        total = int(hours) * 60 + int(minutes)
    except Exception as exc:  # noqa: BLE001
        raise ScheduleConfigError(f"Invalid time '{value}', expected HH:MM") from exc
    if not 0 <= total <= 24 * 60:
        raise ScheduleConfigError(f"Time '{value}' is outside 00:00-24:00")
    return total


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_range(start: int, end: int) -> str:
    return f"{fmt_hhmm(start)}–{fmt_hhmm(end)}"


@dataclass(frozen=True)
class Period:
    day: int
    index: int  # 0-based teaching period number within the day
    start: int  # minutes from midnight
    end: int

    @property
    def label(self) -> str:
        return f"P{self.index + 1}"


@dataclass(frozen=True)
class BreakBlock:
    day: int
    name: str
    kind: str  # "break" | "lunch"
    start: int
    end: int


@dataclass
class ScheduleGrid:
    """All teaching periods and breaks of one schedule, keyed by day."""

    periods: dict[int, list[Period]] = field(default_factory=dict)
    breaks: dict[int, list[BreakBlock]] = field(default_factory=dict)

    @property
    def days(self) -> list[int]:
        return sorted(self.periods)

    def period(self, day: int, index: int) -> Period | None:
        day_periods = self.periods.get(day, [])
        if 0 <= index < len(day_periods):
            return day_periods[index]
        return None

    def block(self, day: int, index: int, length: int) -> tuple[int, int] | None:
        """Return (start, end) for `length` back-to-back periods, or None.

        Periods separated by a break or lunch are *not* consecutive, so a
        two-period lab can never straddle lunch.
        """
        day_periods = self.periods.get(day, [])
        if index < 0 or index + length > len(day_periods):
            return None
        for i in range(index, index + length - 1):
            if day_periods[i].end != day_periods[i + 1].start:
                return None
        return day_periods[index].start, day_periods[index + length - 1].end

    def find_period_at(self, day: int, start: int) -> Period | None:
        for p in self.periods.get(day, []):
            if p.start == start:
                return p
        return None

    def total_periods(self) -> int:
        return sum(len(v) for v in self.periods.values())


DEFAULT_SCHEDULE: dict[str, Any] = {
    "working_days": [0, 1, 2, 3, 4],
    "day_start": "09:00",
    "day_end": "17:00",
    "lecture_minutes": 60,
    "periods_per_day": 7,
    "breaks": [
        {"name": "Short break", "kind": "break", "after_period": 2, "minutes": 15},
        {"name": "Lunch", "kind": "lunch", "after_period": 4, "minutes": 45},
    ],
    "day_overrides": {},
}


def build_grid(config: dict[str, Any]) -> ScheduleGrid:
    """Build the concrete grid for a schedule configuration.

    config keys:
      working_days: list[int]   0=Monday … 6=Sunday
      day_start / day_end: "HH:MM"
      lecture_minutes: int
      periods_per_day: int
      breaks: [{name, kind: break|lunch, after_period: int (1-based), minutes}]
      day_overrides: {"5": {"periods_per_day": 4, "day_start": "08:00", ...}}
    """
    working_days = sorted({int(d) for d in config.get("working_days", [])})
    if not working_days:
        raise ScheduleConfigError("At least one working day is required")
    if any(d < 0 or d > 6 for d in working_days):
        raise ScheduleConfigError("Working days must be between 0 (Mon) and 6 (Sun)")

    overrides = {int(k): v for k, v in (config.get("day_overrides") or {}).items()}
    grid = ScheduleGrid()
    for day in working_days:
        cfg = {**config, **overrides.get(day, {})}
        start = parse_hhmm(cfg.get("day_start", "09:00"))
        end = parse_hhmm(cfg.get("day_end", "17:00"))
        lecture = int(cfg.get("lecture_minutes", 60))
        count = int(cfg.get("periods_per_day", 0))
        if lecture <= 0:
            raise ScheduleConfigError("Lecture duration must be positive")
        if count <= 0:
            raise ScheduleConfigError("Periods per day must be positive")
        if end <= start:
            raise ScheduleConfigError("Day end must be after day start")

        breaks_by_after: dict[int, list[dict]] = {}
        for b in cfg.get("breaks") or []:
            after = int(b.get("after_period", 0))
            minutes = int(b.get("minutes", 0))
            if minutes <= 0 or after <= 0:
                continue
            breaks_by_after.setdefault(after, []).append(b)

        periods: list[Period] = []
        blocks: list[BreakBlock] = []
        cursor = start
        for idx in range(count):
            p = Period(day=day, index=idx, start=cursor, end=cursor + lecture)
            periods.append(p)
            cursor = p.end
            # breaks configured after this (1-based) period, only if more teaching follows
            if idx + 1 < count:
                for b in breaks_by_after.get(idx + 1, []):
                    minutes = int(b["minutes"])
                    blocks.append(
                        BreakBlock(
                            day=day,
                            name=b.get("name") or ("Lunch" if b.get("kind") == "lunch" else "Break"),
                            kind=b.get("kind", "break"),
                            start=cursor,
                            end=cursor + minutes,
                        )
                    )
                    cursor += minutes
        if periods[-1].end > end:
            raise ScheduleConfigError(
                f"{DAY_NAMES[day]}: {count} periods of {lecture} min plus breaks end at "
                f"{fmt_hhmm(periods[-1].end)}, after the configured day end {fmt_hhmm(end)}"
            )
        grid.periods[day] = periods
        grid.breaks[day] = blocks
    return grid


def grid_to_dict(grid: ScheduleGrid) -> dict[str, Any]:
    """JSON-friendly representation used by the API and the frontend."""
    out = []
    for day in grid.days:
        items: list[dict[str, Any]] = [
            {"type": "period", "index": p.index, "label": p.label, "start": p.start, "end": p.end,
             "time": fmt_range(p.start, p.end)}
            for p in grid.periods[day]
        ] + [
            {"type": b.kind, "name": b.name, "start": b.start, "end": b.end, "time": fmt_range(b.start, b.end)}
            for b in grid.breaks.get(day, [])
        ]
        items.sort(key=lambda x: x["start"])
        out.append({"day": day, "name": DAY_NAMES[day], "items": items})
    return {"days": out, "total_periods": grid.total_periods()}
