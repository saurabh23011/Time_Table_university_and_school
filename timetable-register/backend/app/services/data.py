"""Load an institution's data once and convert it into scheduler objects."""
from __future__ import annotations

from collections import defaultdict
from functools import cached_property

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Assignment,
    ClassGroup,
    Department,
    Institution,
    Room,
    Schedule,
    Subject,
    Teacher,
    Timetable,
    TimetableEntry,
)
from ..scheduler import (
    AssignmentReq,
    ClassInfo,
    EntryView,
    ExternalBusy,
    Placement,
    Problem,
    RoomInfo,
    SessionReq,
    SoftWeights,
    TeacherInfo,
    ValidationContext,
    Window,
)
from ..scheduler.timegrid import DEFAULT_SCHEDULE, ScheduleGrid, build_grid, parse_hhmm

PALETTE = [
    "#2563eb", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2",
    "#65a30d", "#dc2626", "#4f46e5", "#0d9488", "#ca8a04", "#9333ea",
]


def to_windows(items: list | None) -> list[Window]:
    out = []
    for w in items or []:
        try:
            out.append(Window(int(w["day"]), parse_hhmm(w["start"]), parse_hhmm(w["end"])))
        except (KeyError, ValueError, TypeError):
            continue
    return out


class InstitutionData:
    def __init__(self, db: Session, institution_id: int):
        self.db = db
        inst = db.get(Institution, institution_id)
        if inst is None:
            raise HTTPException(404, "Institution not found")
        self.inst = inst

        def load(model):
            return {r.id: r for r in db.scalars(select(model).where(model.institution_id == institution_id))}

        self.schedules: dict[int, Schedule] = load(Schedule)
        self.departments: dict[int, Department] = load(Department)
        self.teachers: dict[int, Teacher] = load(Teacher)
        self.rooms: dict[int, Room] = load(Room)
        self.subjects: dict[int, Subject] = load(Subject)
        self.classes: dict[int, ClassGroup] = load(ClassGroup)
        self.assignments: dict[int, Assignment] = load(Assignment)
        self._grids: dict[int | None, ScheduleGrid] = {}

    # ---------------------------------------------------------- hierarchy
    @cached_property
    def children(self) -> dict[int | None, list[int]]:
        ch: dict[int | None, list[int]] = defaultdict(list)
        for d in self.departments.values():
            ch[d.parent_id].append(d.id)
        return ch

    def subtree(self, dept_id: int) -> set[int]:
        out, stack = set(), [dept_id]
        while stack:
            d = stack.pop()
            if d in out:
                continue
            out.add(d)
            stack.extend(self.children.get(d, []))
        return out

    def scope_class_ids(self, department_id: int | None) -> set[int]:
        if department_id is None:
            return set(self.classes)
        depts = self.subtree(department_id)
        return {c.id for c in self.classes.values() if c.department_id in depts}

    # ---------------------------------------------------------- schedules
    def schedule_id_for_class(self, cls: ClassGroup) -> int | None:
        if cls.schedule_id:
            return cls.schedule_id
        seen = set()
        d = self.departments.get(cls.department_id) if cls.department_id else None
        while d is not None and d.id not in seen:
            seen.add(d.id)
            if d.schedule_id:
                return d.schedule_id
            d = self.departments.get(d.parent_id) if d.parent_id else None
        return self.inst.default_schedule_id

    def grid(self, schedule_id: int | None) -> ScheduleGrid:
        if schedule_id not in self._grids:
            sch = self.schedules.get(schedule_id) if schedule_id else None
            self._grids[schedule_id] = build_grid(sch.config if sch else DEFAULT_SCHEDULE)
        return self._grids[schedule_id]

    def class_grid(self, cls: ClassGroup) -> ScheduleGrid:
        return self.grid(self.schedule_id_for_class(cls))

    # ---------------------------------------------------------- converters
    def class_info(self, c: ClassGroup) -> ClassInfo:
        return ClassInfo(c.id, c.name, c.strength, self.class_grid(c), to_windows(c.unavailable))

    def teacher_info(self, t: Teacher) -> TeacherInfo:
        return TeacherInfo(
            id=t.id,
            name=t.name,
            unavailable=to_windows(t.unavailable),
            avoid=to_windows(t.avoid),
            preferred=to_windows(t.preferred),
            work_start=parse_hhmm(t.work_start) if t.work_start else None,
            work_end=parse_hhmm(t.work_end) if t.work_end else None,
            max_per_day=t.max_per_day,
            max_per_week=t.max_per_week,
            max_consecutive=t.max_consecutive,
        )

    def room_info(self, r: Room) -> RoomInfo:
        return RoomInfo(r.id, r.name, r.room_type, r.capacity, frozenset(r.tags or []), to_windows(r.unavailable))

    def assignment_req(self, a: Assignment) -> AssignmentReq | None:
        subj = self.subjects.get(a.subject_id)
        if subj is None:
            return None
        return AssignmentReq(
            id=a.id,
            class_id=a.class_id,
            subject_id=a.subject_id,
            subject_name=subj.name,
            teacher_id=a.teacher_id,
            lectures_per_week=a.lectures_per_week,
            length=a.consecutive_periods,
            room_type=subj.room_type,
            room_tag=subj.room_tag,
            fixed_room_id=a.fixed_room_id,
        )

    def subject_color(self, subject_id: int) -> str:
        s = self.subjects.get(subject_id)
        if s and s.color:
            return s.color
        return PALETTE[subject_id % len(PALETTE)]

    # ---------------------------------------------------------- problems
    def external_busy(self, class_ids: set[int], exclude_timetable_id: int | None) -> list[ExternalBusy]:
        """Teacher/room commitments in other *published* timetables of this institution."""
        q = (
            select(TimetableEntry)
            .join(Timetable, Timetable.id == TimetableEntry.timetable_id)
            .where(Timetable.institution_id == self.inst.id, Timetable.status == "published")
        )
        if exclude_timetable_id is not None:
            q = q.where(Timetable.id != exclude_timetable_id)
        out = []
        for e in self.db.scalars(q):
            if e.class_id in class_ids:
                continue  # superseded by the timetable being built
            cname = self.classes[e.class_id].name if e.class_id in self.classes else "another class"
            subj = self.subjects.get(e.subject_id)
            label = f"{cname} ({subj.name if subj else 'lecture'})"
            out.append(ExternalBusy("teacher", e.teacher_id, e.day, e.start_min, e.end_min, label))
            out.append(ExternalBusy("room", e.room_id, e.day, e.start_min, e.end_min, label))
        return out

    def scope_assignments(self, class_ids: set[int]) -> list[Assignment]:
        return [
            a for a in self.assignments.values()
            if a.class_id in class_ids and a.teacher_id in self.teachers and self.teachers[a.teacher_id].active
            and a.subject_id in self.subjects
        ]

    def build_problem(
        self,
        class_ids: set[int],
        locked_entries: list[TimetableEntry] | None = None,
        exclude_timetable_id: int | None = None,
    ) -> Problem:
        assignments = self.scope_assignments(class_ids)
        sessions: list[SessionReq] = []
        keys_by_assignment: dict[int, list[str]] = defaultdict(list)
        for a in sorted(assignments, key=lambda x: x.id):
            req = self.assignment_req(a)
            if req is None:
                continue
            n = max(1, a.lectures_per_week // max(1, a.consecutive_periods))
            for k in range(n):
                s = req.as_session()
                s.key = f"{a.id}-{k}"
                sessions.append(s)
                keys_by_assignment[a.id].append(s.key)
        locked: dict[str, Placement] = {}
        for e in locked_entries or []:
            keys = keys_by_assignment.get(e.assignment_id or -1, [])
            free = [k for k in keys if k not in locked]
            if not free:
                continue
            locked[free[0]] = Placement(free[0], e.day, e.period_index, e.start_min, e.end_min, e.room_id)
        teacher_ids = {a.teacher_id for a in assignments}
        return Problem(
            classes={cid: self.class_info(self.classes[cid]) for cid in class_ids},
            teachers={tid: self.teacher_info(self.teachers[tid]) for tid in teacher_ids},
            rooms={r.id: self.room_info(r) for r in self.rooms.values() if r.active},
            sessions=sessions,
            locked=locked,
            external=self.external_busy(class_ids, exclude_timetable_id),
            weights=SoftWeights.from_dict(self.inst.soft_weights),
        )

    def validation_context(self, class_ids: set[int], exclude_timetable_id: int | None) -> ValidationContext:
        reqs = {}
        for a in self.scope_assignments(class_ids):
            r = self.assignment_req(a)
            if r:
                reqs[a.id] = r
        return ValidationContext(
            classes={cid: self.class_info(c) for cid, c in self.classes.items()},
            teachers={tid: self.teacher_info(t) for tid, t in self.teachers.items()},
            rooms={rid: self.room_info(r) for rid, r in self.rooms.items()},
            assignments=reqs,
            external=self.external_busy(class_ids, exclude_timetable_id),
        )

    def entry_view(self, e: TimetableEntry) -> EntryView:
        subj = self.subjects.get(e.subject_id)
        return EntryView(
            id=e.id,
            class_id=e.class_id,
            subject_id=e.subject_id,
            subject_name=subj.name if subj else f"Subject #{e.subject_id}",
            teacher_id=e.teacher_id,
            room_id=e.room_id,
            day=e.day,
            start=e.start_min,
            end=e.end_min,
            length=e.length,
            assignment_id=e.assignment_id,
        )
