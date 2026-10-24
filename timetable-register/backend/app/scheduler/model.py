"""Pure-Python problem model for the scheduler.

The engine never touches the database. The service layer converts ORM rows
into these dataclasses, which keeps the algorithm easy to unit-test and reuse.
All times are minutes from midnight; intervals are half-open [start, end).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .timegrid import ScheduleGrid


@dataclass(frozen=True)
class Window:
    day: int
    start: int
    end: int

    def overlaps(self, day: int, start: int, end: int) -> bool:
        return self.day == day and self.start < end and start < self.end


def mask(start: int, end: int) -> int:
    """Bitmask with one bit per minute in [start, end).

    Overlap tests across *different* schedules then become a single `&`.
    """
    if end <= start:
        return 0
    return ((1 << (end - start)) - 1) << start


@dataclass
class TeacherInfo:
    id: int
    name: str
    unavailable: list[Window] = field(default_factory=list)  # hard
    avoid: list[Window] = field(default_factory=list)  # soft: prefers not to teach
    preferred: list[Window] = field(default_factory=list)  # soft: prefers to teach
    work_start: int | None = None  # individual working hours (hard)
    work_end: int | None = None
    max_per_day: int | None = None  # periods (hard in generation)
    max_per_week: int | None = None  # periods (hard in generation)
    max_consecutive: int | None = None  # soft

    def is_available(self, day: int, start: int, end: int) -> bool:
        if self.work_start is not None and start < self.work_start:
            return False
        if self.work_end is not None and end > self.work_end:
            return False
        return not any(w.overlaps(day, start, end) for w in self.unavailable)


@dataclass
class RoomInfo:
    id: int
    name: str
    room_type: str  # classroom | lab | seminar_hall | auditorium | other
    capacity: int
    tags: frozenset[str] = frozenset()
    unavailable: list[Window] = field(default_factory=list)

    def is_available(self, day: int, start: int, end: int) -> bool:
        return not any(w.overlaps(day, start, end) for w in self.unavailable)


@dataclass
class ClassInfo:
    id: int
    name: str
    strength: int
    grid: ScheduleGrid
    unavailable: list[Window] = field(default_factory=list)

    def is_available(self, day: int, start: int, end: int) -> bool:
        return not any(w.overlaps(day, start, end) for w in self.unavailable)


@dataclass
class SessionReq:
    """One weekly meeting to place: `length` consecutive periods."""

    key: str
    assignment_id: int
    class_id: int
    subject_id: int
    subject_name: str
    teacher_id: int
    length: int = 1
    room_type: str = "classroom"
    room_tag: str | None = None
    fixed_room_id: int | None = None


@dataclass
class Placement:
    session_key: str
    day: int
    period_index: int
    start: int
    end: int
    room_id: int


@dataclass
class ExternalBusy:
    """A commitment outside the current run (e.g. another department's published timetable)."""

    kind: str  # teacher | room | class
    ref_id: int
    day: int
    start: int
    end: int
    label: str = ""


@dataclass
class SoftWeights:
    subject_repeat_per_day: float = 10.0
    teacher_gap_hour: float = 3.0
    teacher_over_consecutive: float = 8.0
    teacher_avoid_slot: float = 6.0
    teacher_not_preferred: float = 2.0
    class_daily_balance: float = 1.0
    teacher_daily_balance: float = 1.0
    room_wasted_capacity: float = 2.0
    late_slot: float = 0.5

    @classmethod
    def from_dict(cls, data: dict | None) -> "SoftWeights":
        w = cls()
        for k, v in (data or {}).items():
            if hasattr(w, k):
                setattr(w, k, float(v))
        return w


@dataclass
class Problem:
    classes: dict[int, ClassInfo]
    teachers: dict[int, TeacherInfo]
    rooms: dict[int, RoomInfo]
    sessions: list[SessionReq]
    locked: dict[str, Placement] = field(default_factory=dict)
    external: list[ExternalBusy] = field(default_factory=list)
    weights: SoftWeights = field(default_factory=SoftWeights)


def room_suits(room: RoomInfo, session: SessionReq, strength: int) -> bool:
    if session.fixed_room_id is not None:
        return room.id == session.fixed_room_id
    if session.room_type and session.room_type != "any" and room.room_type != session.room_type:
        return False
    if session.room_tag and session.room_tag not in room.tags:
        return False
    return room.capacity >= strength


def room_suits_reason(room: RoomInfo, session: SessionReq, strength: int) -> str | None:
    """Human-readable reason a room does not fit, or None if it fits."""
    if session.fixed_room_id is not None and room.id != session.fixed_room_id:
        return "is not the room fixed for this subject"
    if session.room_type and session.room_type != "any" and room.room_type != session.room_type:
        return f"is a {room.room_type.replace('_', ' ')}, but {session.subject_name} needs a {session.room_type.replace('_', ' ')}"
    if session.room_tag and session.room_tag not in room.tags:
        return f"is not tagged '{session.room_tag}'"
    if room.capacity < strength:
        return f"seats {room.capacity}, but the class has {strength} students"
    return None
