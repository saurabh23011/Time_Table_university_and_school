"""Conflict detection and alternative-slot suggestions.

Used after generation, after every manual edit (including dry-run checks while
the user drags a lecture) and before publishing. Overlaps are evaluated on
real clock time, so a teacher shared between two departments that run on
different period grids is still caught.

Severity:
  major – the timetable is invalid and cannot be saved/published
  minor – a warning (e.g. a subject is short of its weekly lecture count)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

from .model import ClassInfo, ExternalBusy, RoomInfo, SessionReq, TeacherInfo, mask, room_suits, room_suits_reason
from .timegrid import DAY_NAMES, fmt_range

MAJOR = "major"
MINOR = "minor"

CONFLICT_TYPES = {
    "teacher_conflict": MAJOR,
    "class_conflict": MAJOR,
    "room_conflict": MAJOR,
    "teacher_availability": MAJOR,
    "class_availability": MAJOR,
    "room_availability": MAJOR,
    "room_type_mismatch": MAJOR,
    "room_capacity": MAJOR,
    "invalid_slot": MAJOR,
    "lecture_count": MINOR,
    "teacher_daily_limit": MINOR,
    "teacher_weekly_limit": MINOR,
}


@dataclass
class EntryView:
    id: int
    class_id: int
    subject_id: int
    subject_name: str
    teacher_id: int
    room_id: int
    day: int
    start: int
    end: int
    length: int = 1
    assignment_id: int | None = None


@dataclass
class AssignmentReq:
    id: int
    class_id: int
    subject_id: int
    subject_name: str
    teacher_id: int
    lectures_per_week: int
    length: int = 1
    room_type: str = "classroom"
    room_tag: str | None = None
    fixed_room_id: int | None = None

    def as_session(self) -> SessionReq:
        return SessionReq(
            key=f"a{self.id}",
            assignment_id=self.id,
            class_id=self.class_id,
            subject_id=self.subject_id,
            subject_name=self.subject_name,
            teacher_id=self.teacher_id,
            length=self.length,
            room_type=self.room_type,
            room_tag=self.room_tag,
            fixed_room_id=self.fixed_room_id,
        )


@dataclass
class Suggestion:
    day: int
    period_index: int
    start: int
    end: int
    room_id: int
    room_name: str
    label: str


@dataclass
class Conflict:
    type: str
    severity: str
    message: str
    entry_ids: list[int]
    day: int | None = None
    start: int | None = None
    end: int | None = None
    suggestions: list[Suggestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["time"] = fmt_range(self.start, self.end) if self.start is not None and self.end is not None else None
        d["day_name"] = DAY_NAMES[self.day] if self.day is not None else None
        return d


@dataclass
class ValidationContext:
    classes: dict[int, ClassInfo]
    teachers: dict[int, TeacherInfo]
    rooms: dict[int, RoomInfo]
    assignments: dict[int, AssignmentReq]
    external: list[ExternalBusy] = field(default_factory=list)

    def cname(self, cid: int) -> str:
        c = self.classes.get(cid)
        return c.name if c else f"class #{cid}"

    def tname(self, tid: int) -> str:
        t = self.teachers.get(tid)
        return t.name if t else f"teacher #{tid}"

    def rname(self, rid: int) -> str:
        r = self.rooms.get(rid)
        return r.name if r else f"room #{rid}"


def _when(day: int, start: int, end: int) -> str:
    return f"{DAY_NAMES[day]} {fmt_range(start, end)}"


def _overlap(a: EntryView, b: EntryView) -> tuple[int, int] | None:
    if a.day != b.day:
        return None
    s, e = max(a.start, b.start), min(a.end, b.end)
    return (s, e) if s < e else None


def _pairwise(entries: list[EntryView], key) -> list[tuple[EntryView, EntryView, int, int]]:
    groups: dict[tuple, list[EntryView]] = defaultdict(list)
    for e in entries:
        groups[(key(e), e.day)].append(e)
    out = []
    for items in groups.values():
        items.sort(key=lambda x: (x.start, x.end, x.id))
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if b.start >= a.end:
                    break
                ov = _overlap(a, b)
                if ov:
                    out.append((a, b, *ov))
    return out


def detect_conflicts(
    ctx: ValidationContext,
    entries: list[EntryView],
    with_suggestions: bool = True,
    suggestion_limit: int = 4,
    focus_entry_id: int | None = None,
) -> list[Conflict]:
    """`focus_entry_id` is the session being edited: suggestions for any clash it is
    part of are free slots for *that* session."""
    conflicts: list[Conflict] = []

    def add(ctype: str, msg: str, ids: list[int], day=None, start=None, end=None):
        conflicts.append(Conflict(ctype, CONFLICT_TYPES[ctype], msg, ids, day, start, end))

    # --- double bookings ----------------------------------------------------
    for a, b, s, e in _pairwise(entries, lambda x: x.teacher_id):
        add(
            "teacher_conflict",
            f"{ctx.tname(a.teacher_id)} is assigned to {ctx.cname(a.class_id)} ({a.subject_name}) and "
            f"{ctx.cname(b.class_id)} ({b.subject_name}) at the same time on {_when(a.day, s, e)}.",
            [a.id, b.id], a.day, s, e,
        )
    for a, b, s, e in _pairwise(entries, lambda x: x.class_id):
        add(
            "class_conflict",
            f"{ctx.cname(a.class_id)} has two subjects at once on {_when(a.day, s, e)}: "
            f"{a.subject_name} and {b.subject_name}.",
            [a.id, b.id], a.day, s, e,
        )
    for a, b, s, e in _pairwise(entries, lambda x: x.room_id):
        add(
            "room_conflict",
            f"{ctx.rname(a.room_id)} is booked by {ctx.cname(a.class_id)} ({a.subject_name}) and "
            f"{ctx.cname(b.class_id)} ({b.subject_name}) on {_when(a.day, s, e)}.",
            [a.id, b.id], a.day, s, e,
        )

    # --- commitments from other timetables --------------------------------
    for ext in ctx.external:
        for en in entries:
            if en.day != ext.day or not (en.start < ext.end and ext.start < en.end):
                continue
            s, e = max(en.start, ext.start), min(en.end, ext.end)
            if ext.kind == "teacher" and en.teacher_id == ext.ref_id:
                add("teacher_conflict",
                    f"{ctx.tname(en.teacher_id)} already teaches {ext.label or 'in another timetable'} "
                    f"on {_when(en.day, s, e)}.", [en.id], en.day, s, e)
            elif ext.kind == "room" and en.room_id == ext.ref_id:
                add("room_conflict",
                    f"{ctx.rname(en.room_id)} is already booked ({ext.label or 'another timetable'}) "
                    f"on {_when(en.day, s, e)}.", [en.id], en.day, s, e)
            elif ext.kind == "class" and en.class_id == ext.ref_id:
                add("class_conflict",
                    f"{ctx.cname(en.class_id)} already has {ext.label or 'a session'} on {_when(en.day, s, e)}.",
                    [en.id], en.day, s, e)

    # --- per-entry checks ---------------------------------------------------
    for en in entries:
        t = ctx.teachers.get(en.teacher_id)
        c = ctx.classes.get(en.class_id)
        r = ctx.rooms.get(en.room_id)
        when = _when(en.day, en.start, en.end)
        if t is not None and not t.is_available(en.day, en.start, en.end):
            why = "outside working hours" if (
                (t.work_start is not None and en.start < t.work_start)
                or (t.work_end is not None and en.end > t.work_end)
            ) else "marked unavailable"
            add("teacher_availability",
                f"{t.name} is {why} on {when} but is scheduled for {ctx.cname(en.class_id)} ({en.subject_name}).",
                [en.id], en.day, en.start, en.end)
        if c is not None:
            if not c.is_available(en.day, en.start, en.end):
                add("class_availability", f"{c.name} is marked unavailable on {when}.", [en.id], en.day, en.start, en.end)
            p = c.grid.find_period_at(en.day, en.start)
            blk = c.grid.block(en.day, p.index, en.length) if p else None
            if blk is None or blk != (en.start, en.end):
                add("invalid_slot",
                    f"{en.subject_name} for {c.name} on {when} does not match {c.name}'s period grid "
                    f"(wrong day, time or it crosses a break).",
                    [en.id], en.day, en.start, en.end)
        if r is not None:
            if not r.is_available(en.day, en.start, en.end):
                add("room_availability", f"{r.name} is unavailable on {when}.", [en.id], en.day, en.start, en.end)
            a = ctx.assignments.get(en.assignment_id) if en.assignment_id else None
            if a is not None and c is not None:
                reason = room_suits_reason(r, a.as_session(), c.strength)
                if reason:
                    ctype = "room_capacity" if "seats" in reason else "room_type_mismatch"
                    add(ctype, f"{r.name} {reason} ({c.name}, {when}).", [en.id], en.day, en.start, en.end)

    # --- weekly lecture counts ----------------------------------------------
    scheduled: dict[int, int] = defaultdict(int)
    ids_by_assignment: dict[int, list[int]] = defaultdict(list)
    for en in entries:
        if en.assignment_id:
            scheduled[en.assignment_id] += en.length
            ids_by_assignment[en.assignment_id].append(en.id)
    for aid, a in ctx.assignments.items():
        have = scheduled.get(aid, 0)
        if have != a.lectures_per_week:
            word = "short of" if have < a.lectures_per_week else "over"
            add("lecture_count",
                f"{a.subject_name} for {ctx.cname(a.class_id)} has {have} of {a.lectures_per_week} required "
                f"lectures per week ({word} the requirement).",
                ids_by_assignment.get(aid, []))

    # --- teacher limits -----------------------------------------------------
    day_load: dict[tuple[int, int], list[int]] = defaultdict(list)
    week_load: dict[int, int] = defaultdict(int)
    for en in entries:
        day_load[(en.teacher_id, en.day)].append(en.id)
        week_load[en.teacher_id] += en.length
    for (tid, day), ids in day_load.items():
        t = ctx.teachers.get(tid)
        load = sum(e.length for e in entries if e.teacher_id == tid and e.day == day)
        if t and t.max_per_day is not None and load > t.max_per_day:
            add("teacher_daily_limit",
                f"{t.name} has {load} periods on {DAY_NAMES[day]} (limit {t.max_per_day}).", ids, day)
    for tid, load in week_load.items():
        t = ctx.teachers.get(tid)
        if t and t.max_per_week is not None and load > t.max_per_week:
            add("teacher_weekly_limit", f"{t.name} has {load} periods this week (limit {t.max_per_week}).",
                [e.id for e in entries if e.teacher_id == tid])

    if with_suggestions:
        by_id = {e.id: e for e in entries}
        cache: dict[int, list[Suggestion]] = {}
        for cf in conflicts:
            if cf.severity != MAJOR or not cf.entry_ids:
                continue
            # suggest moving the edited session, otherwise the last entry of the clash
            tid = focus_entry_id if focus_entry_id in cf.entry_ids else cf.entry_ids[-1]
            target = by_id.get(tid)
            if target is None:
                continue
            if target.id not in cache:
                cache[target.id] = suggest_slots(ctx, entries, target.id, limit=suggestion_limit)
            cf.suggestions = cache[target.id]
    return conflicts


def suggest_slots(
    ctx: ValidationContext,
    entries: list[EntryView],
    entry_id: int,
    limit: int = 5,
    teacher_id: int | None = None,
) -> list[Suggestion]:
    """Free slots where the entry's class, teacher and a suitable room are all available."""
    target = next((e for e in entries if e.id == entry_id), None)
    if target is None:
        return []
    cls = ctx.classes.get(target.class_id)
    tid = teacher_id or target.teacher_id
    teacher = ctx.teachers.get(tid)
    if cls is None or teacher is None:
        return []

    busy_t = defaultdict(int)
    busy_c = defaultdict(int)
    busy_r: dict[tuple[int, int], int] = defaultdict(int)
    tload = defaultdict(int)
    subject_days = set()
    for e in entries:
        if e.id == entry_id:
            continue
        m = mask(e.start, e.end)
        if e.teacher_id == tid:
            busy_t[e.day] |= m
            tload[e.day] += e.length
        if e.class_id == target.class_id:
            busy_c[e.day] |= m
            if e.subject_id == target.subject_id:
                subject_days.add(e.day)
        busy_r[(e.room_id, e.day)] |= m
    for ext in ctx.external:
        m = mask(ext.start, ext.end)
        if ext.kind == "teacher" and ext.ref_id == tid:
            busy_t[ext.day] |= m
        elif ext.kind == "class" and ext.ref_id == target.class_id:
            busy_c[ext.day] |= m
        elif ext.kind == "room":
            busy_r[(ext.ref_id, ext.day)] |= m

    a = ctx.assignments.get(target.assignment_id) if target.assignment_id else None
    session = a.as_session() if a else SessionReq(
        key="tmp", assignment_id=0, class_id=target.class_id, subject_id=target.subject_id,
        subject_name=target.subject_name, teacher_id=tid, length=target.length, room_type="any",
    )
    rooms = [r for r in ctx.rooms.values() if room_suits(r, session, cls.strength)]
    rooms.sort(key=lambda r: (r.id != target.room_id, r.capacity - cls.strength, r.id))

    options: list[tuple[float, Suggestion]] = []
    for day in cls.grid.days:
        for idx in range(len(cls.grid.periods[day])):
            blk = cls.grid.block(day, idx, target.length)
            if blk is None:
                continue
            start, end = blk
            if day == target.day and start == target.start and tid == target.teacher_id:
                continue
            m = mask(start, end)
            if busy_t[day] & m or busy_c[day] & m:
                continue
            if not teacher.is_available(day, start, end) or not cls.is_available(day, start, end):
                continue
            if teacher.max_per_day is not None and tload[day] + target.length > teacher.max_per_day:
                continue
            room = next(
                (r for r in rooms if r.is_available(day, start, end) and not busy_r[(r.id, day)] & m), None
            )
            if room is None:
                continue
            score = 0.0
            score += 10 if day in subject_days else 0
            score += 2 if any(w.overlaps(day, start, end) for w in teacher.avoid) else 0
            score += 0.5 * abs(day - target.day) + 0.2 * abs(start - target.start) / 60
            score += 0.5 * tload[day]
            options.append((score, Suggestion(
                day=day, period_index=idx, start=start, end=end, room_id=room.id, room_name=room.name,
                label=f"{DAY_NAMES[day]} {fmt_range(start, end)} in {room.name}",
            )))
    options.sort(key=lambda x: x[0])
    return [s for _, s in options[:limit]]


def has_major(conflicts: list[Conflict]) -> bool:
    return any(c.severity == MAJOR for c in conflicts)


def summarize(conflicts: list[Conflict]) -> dict:
    by_type: dict[str, int] = defaultdict(int)
    for c in conflicts:
        by_type[c.type] += 1
    return {
        "total": len(conflicts),
        "major": sum(1 for c in conflicts if c.severity == MAJOR),
        "minor": sum(1 for c in conflicts if c.severity == MINOR),
        "by_type": dict(by_type),
    }
