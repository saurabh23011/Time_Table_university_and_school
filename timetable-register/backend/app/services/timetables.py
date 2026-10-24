"""Timetable generation, validation and editing."""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Timetable, TimetableEntry, utcnow
from ..scheduler import Conflict, EntryView, detect_conflicts, generate, has_major, suggest_slots, summarize
from ..scheduler.conflicts import MAJOR
from ..scheduler.model import room_suits
from ..scheduler.timegrid import DAY_NAMES, fmt_range
from .data import InstitutionData


def scope_label(data: InstitutionData, department_id: int | None) -> str:
    if department_id is None:
        return data.inst.name
    d = data.departments.get(department_id)
    return d.name if d else f"Department #{department_id}"


def timetable_class_ids(data: InstitutionData, tt: Timetable) -> set[int]:
    return data.scope_class_ids(tt.department_id)


def clamp_time_limit(value: float | None) -> float:
    s = get_settings()
    return min(float(value or s.default_time_limit), s.max_time_limit)


def run_generation(
    db: Session,
    data: InstitutionData,
    tt: Timetable,
    keep_locked: bool,
    time_limit: float | None,
    seed: int | None,
    optimise: bool = True,
) -> None:
    class_ids = timetable_class_ids(data, tt)
    if not class_ids:
        raise HTTPException(422, "There are no classes in this scope yet")
    existing = list(db.scalars(select(TimetableEntry).where(TimetableEntry.timetable_id == tt.id))) if tt.id else []
    locked = [e for e in existing if e.locked and e.class_id in class_ids] if keep_locked else []
    problem = data.build_problem(class_ids, locked_entries=locked, exclude_timetable_id=tt.id)
    if not problem.sessions:
        raise HTTPException(422, "No curriculum (subject–teacher assignments) defined for the classes in this scope")
    result = generate(problem, time_limit=clamp_time_limit(time_limit), seed=seed, optimise=optimise)

    for e in existing:
        if e not in locked:
            db.delete(e)
    db.flush()

    sessions = {s.key: s for s in problem.sessions}
    locked_keys = set(problem.locked)
    for p in result.placements:
        if p.session_key in locked_keys:
            continue
        s = sessions[p.session_key]
        db.add(
            TimetableEntry(
                timetable_id=tt.id,
                assignment_id=s.assignment_id,
                class_id=s.class_id,
                subject_id=s.subject_id,
                teacher_id=s.teacher_id,
                room_id=p.room_id,
                day=p.day,
                start_min=p.start,
                end_min=p.end,
                period_index=p.period_index,
                length=s.length,
                locked=False,
            )
        )
    tt.generation = {
        "scope": scope_label(data, tt.department_id),
        "complete": result.complete,
        "soft_score": result.soft_score,
        "soft_breakdown": result.breakdown,
        "warnings": result.warnings,
        "stats": result.stats,
        "locked_kept": len(locked_keys),
        "unscheduled": [
            {
                "assignment_id": u.assignment_id,
                "class_id": u.class_id,
                "class_name": data.classes[u.class_id].name if u.class_id in data.classes else "",
                "subject_name": u.subject_name,
                "teacher_name": data.teachers[u.teacher_id].name if u.teacher_id in data.teachers else "",
                "periods": u.length,
                "reason": u.reason,
            }
            for u in result.unscheduled
        ],
        "generated_at": utcnow().isoformat(),
    }
    db.flush()


def load_entries(db: Session, tt: Timetable) -> list[TimetableEntry]:
    return list(
        db.scalars(
            select(TimetableEntry)
            .where(TimetableEntry.timetable_id == tt.id)
            .order_by(TimetableEntry.day, TimetableEntry.start_min, TimetableEntry.id)
        )
    )


def compute_conflicts(
    data: InstitutionData,
    tt: Timetable,
    views: list[EntryView],
    with_suggestions: bool = True,
    focus_entry_id: int | None = None,
) -> list[Conflict]:
    ctx = data.validation_context(timetable_class_ids(data, tt), exclude_timetable_id=tt.id)
    return detect_conflicts(ctx, views, with_suggestions=with_suggestions, focus_entry_id=focus_entry_id)


def refresh_summary(db: Session, data: InstitutionData, tt: Timetable, with_suggestions: bool = True) -> list[Conflict]:
    entries = load_entries(db, tt)
    conflicts = compute_conflicts(data, tt, [data.entry_view(e) for e in entries], with_suggestions)
    tt.conflict_summary = {**summarize(conflicts), "checked_at": utcnow().isoformat()}
    return conflicts


@dataclass
class EditOutcome:
    ok: bool
    conflicts: list[Conflict]
    blocking: list[Conflict]
    entry: TimetableEntry | None


def _views_with(data: InstitutionData, entries: list[TimetableEntry], changed: EntryView | None,
                remove_id: int | None = None) -> list[EntryView]:
    out = []
    for e in entries:
        if remove_id is not None and e.id == remove_id:
            continue
        if changed is not None and e.id == changed.id:
            out.append(changed)
        else:
            out.append(data.entry_view(e))
    if changed is not None and all(v.id != changed.id for v in out):
        out.append(changed)
    return out


def _blocking(conflicts: list[Conflict], entry_id: int) -> list[Conflict]:
    return [c for c in conflicts if c.severity == MAJOR and entry_id in c.entry_ids]


def _slot(data: InstitutionData, class_id: int, day: int, period_index: int, length: int) -> tuple[int, int]:
    cls = data.classes.get(class_id)
    if cls is None:
        raise HTTPException(404, "Class not found")
    grid = data.class_grid(cls)
    if day not in grid.periods:
        raise HTTPException(422, f"{cls.name} does not meet on {DAY_NAMES[day]}")
    blk = grid.block(day, period_index, length)
    if blk is None:
        raise HTTPException(
            422,
            f"{cls.name} has no {length} back-to-back period(s) starting at P{period_index + 1} on {DAY_NAMES[day]}",
        )
    return blk


def best_room(data: InstitutionData, tt: Timetable, entries: list[EntryView], assignment_id: int | None,
              class_id: int, day: int, start: int, end: int, exclude_entry: int | None = None) -> int | None:
    a = data.assignments.get(assignment_id) if assignment_id else None
    req = data.assignment_req(a) if a else None
    cls = data.classes[class_id]
    rooms = [data.room_info(r) for r in data.rooms.values() if r.active]
    if req:
        rooms = [r for r in rooms if room_suits(r, req.as_session(), cls.strength)]
    rooms.sort(key=lambda r: (r.capacity - cls.strength, r.id))
    busy = {
        v.room_id for v in entries
        if v.id != exclude_entry and v.day == day and v.start < end and start < v.end
    }
    for ext in data.external_busy(timetable_class_ids(data, tt), tt.id):
        if ext.kind == "room" and ext.day == day and ext.start < end and start < ext.end:
            busy.add(ext.ref_id)
    for r in rooms:
        if r.id not in busy and r.is_available(day, start, end):
            return r.id
    return None


def period_at(data: InstitutionData, class_id: int, day: int, start: int) -> int:
    cls = data.classes.get(class_id)
    if cls is None:
        raise HTTPException(404, "Class not found")
    p = data.class_grid(cls).find_period_at(day, start)
    if p is None:
        raise HTTPException(422, f"{cls.name} has no period starting at that time on {DAY_NAMES[day]}")
    return p.index


def move_entry(db: Session, data: InstitutionData, tt: Timetable, entry: TimetableEntry, *, day=None,
               period_index=None, start=None, room_id=None, teacher_id=None, locked=None,
               dry_run=False) -> EditOutcome:
    entries = load_entries(db, tt)
    new_day = entry.day if day is None else day
    if period_index is None and start is not None:
        period_index = period_at(data, entry.class_id, new_day, start)
    new_idx = entry.period_index if period_index is None else period_index
    start, end = _slot(data, entry.class_id, new_day, new_idx, entry.length)
    new_teacher = entry.teacher_id if teacher_id is None else teacher_id
    if new_teacher not in data.teachers:
        raise HTTPException(422, "Unknown teacher")
    if room_id is not None and room_id not in data.rooms:
        raise HTTPException(422, "Unknown room")
    new_room = entry.room_id if room_id is None else room_id
    changed = EntryView(
        id=entry.id, class_id=entry.class_id, subject_id=entry.subject_id,
        subject_name=data.subjects[entry.subject_id].name if entry.subject_id in data.subjects else "",
        teacher_id=new_teacher, room_id=new_room, day=new_day, start=start, end=end,
        length=entry.length, assignment_id=entry.assignment_id,
    )
    views = _views_with(data, entries, changed)
    conflicts = compute_conflicts(data, tt, views, focus_entry_id=entry.id)
    blocking = _blocking(conflicts, entry.id)
    for c in blocking:  # "stay where it is" is not a useful alternative
        c.suggestions = [s for s in c.suggestions if not (s.day == entry.day and s.start == entry.start_min)]
    if dry_run or blocking:
        return EditOutcome(ok=not blocking, conflicts=conflicts, blocking=blocking, entry=None)
    entry.day, entry.period_index, entry.start_min, entry.end_min = new_day, new_idx, start, end
    entry.teacher_id, entry.room_id = new_teacher, new_room
    if locked is not None:
        entry.locked = locked
    elif day is not None or period_index is not None or room_id is not None or teacher_id is not None:
        entry.locked = True  # a manual placement is pinned so regeneration keeps it
    tt.conflict_summary = {**summarize(conflicts), "checked_at": utcnow().isoformat()}
    tt.updated_at = utcnow()
    db.flush()
    return EditOutcome(ok=True, conflicts=conflicts, blocking=[], entry=entry)


def add_entry(db: Session, data: InstitutionData, tt: Timetable, assignment_id: int, day: int, period_index: int,
              room_id: int | None, locked: bool, dry_run: bool) -> EditOutcome:
    a = data.assignments.get(assignment_id)
    if a is None or a.class_id not in timetable_class_ids(data, tt):
        raise HTTPException(404, "Curriculum line not found in this timetable's scope")
    start, end = _slot(data, a.class_id, day, period_index, a.consecutive_periods)
    entries = load_entries(db, tt)
    views = [data.entry_view(e) for e in entries]
    if room_id is None:
        room_id = best_room(data, tt, views, a.id, a.class_id, day, start, end)
        if room_id is None:
            raise HTTPException(409, {"message": "No suitable room is free in that slot", "conflicts": []})
    temp_id = -1
    new_view = EntryView(
        id=temp_id, class_id=a.class_id, subject_id=a.subject_id,
        subject_name=data.subjects[a.subject_id].name, teacher_id=a.teacher_id, room_id=room_id,
        day=day, start=start, end=end, length=a.consecutive_periods, assignment_id=a.id,
    )
    conflicts = compute_conflicts(data, tt, views + [new_view], focus_entry_id=temp_id)
    blocking = _blocking(conflicts, temp_id)
    if dry_run or blocking:
        return EditOutcome(ok=not blocking, conflicts=conflicts, blocking=blocking, entry=None)
    e = TimetableEntry(
        timetable_id=tt.id, assignment_id=a.id, class_id=a.class_id, subject_id=a.subject_id,
        teacher_id=a.teacher_id, room_id=room_id, day=day, start_min=start, end_min=end,
        period_index=period_index, length=a.consecutive_periods, locked=locked,
    )
    db.add(e)
    db.flush()
    refresh_summary(db, data, tt, with_suggestions=False)
    tt.updated_at = utcnow()
    return EditOutcome(ok=True, conflicts=conflicts, blocking=[], entry=e)


def entry_suggestions(db: Session, data: InstitutionData, tt: Timetable, entry: TimetableEntry,
                      teacher_id: int | None = None, limit: int = 8):
    views = [data.entry_view(e) for e in load_entries(db, tt)]
    ctx = data.validation_context(timetable_class_ids(data, tt), exclude_timetable_id=tt.id)
    return suggest_slots(ctx, views, entry.id, limit=limit, teacher_id=teacher_id)


def assignment_free_slots(db: Session, data: InstitutionData, tt: Timetable, assignment_id: int, limit: int = 30):
    a = data.assignments.get(assignment_id)
    if a is None or a.class_id not in timetable_class_ids(data, tt):
        raise HTTPException(404, "Curriculum line not found in this timetable's scope")
    views = [data.entry_view(e) for e in load_entries(db, tt)]
    probe = EntryView(id=-1, class_id=a.class_id, subject_id=a.subject_id,
                      subject_name=data.subjects[a.subject_id].name, teacher_id=a.teacher_id, room_id=-1,
                      day=-1, start=-1, end=-1, length=a.consecutive_periods, assignment_id=a.id)
    ctx = data.validation_context(timetable_class_ids(data, tt), exclude_timetable_id=tt.id)
    return suggest_slots(ctx, views + [probe], -1, limit=limit)


def publish(db: Session, data: InstitutionData, tt: Timetable) -> list[Conflict]:
    conflicts = refresh_summary(db, data, tt, with_suggestions=False)
    if has_major(conflicts):
        return conflicts
    class_ids = timetable_class_ids(data, tt)
    # archive older published timetables that cover any of the same classes
    others = db.scalars(
        select(Timetable).where(
            Timetable.institution_id == tt.institution_id, Timetable.status == "published", Timetable.id != tt.id
        )
    )
    for other in others:
        if timetable_class_ids(data, other) & class_ids:
            other.status = "archived"
    tt.status = "published"
    tt.published_at = utcnow()
    db.flush()
    return conflicts


def new_share_token() -> str:
    return secrets.token_urlsafe(18)


def describe(day: int, start: int, end: int) -> str:
    return f"{DAY_NAMES[day]} {fmt_range(start, end)}"
