"""Timetable views: class, teacher, room, lab, department/school and institution."""
from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException

from ..models import Timetable, TimetableEntry
from ..scheduler import Conflict
from ..scheduler.timegrid import DAY_NAMES, DAY_SHORT, ScheduleGrid, fmt_range
from .data import InstitutionData

VIEW_TYPES = ("class", "teacher", "room", "lab", "department", "school", "institution")


def enrich(data: InstitutionData, e: TimetableEntry, conflict_types: dict[int, set[str]] | None = None) -> dict:
    subj = data.subjects.get(e.subject_id)
    cls = data.classes.get(e.class_id)
    t = data.teachers.get(e.teacher_id)
    r = data.rooms.get(e.room_id)
    return {
        "id": e.id,
        "assignment_id": e.assignment_id,
        "day": e.day,
        "day_name": DAY_NAMES[e.day],
        "start": e.start_min,
        "end": e.end_min,
        "time": fmt_range(e.start_min, e.end_min),
        "period_index": e.period_index,
        "length": e.length,
        "locked": e.locked,
        "class_id": e.class_id,
        "class_name": cls.name if cls else "",
        "department_id": cls.department_id if cls else None,
        "subject_id": e.subject_id,
        "subject_name": subj.name if subj else "",
        "subject_code": subj.code if subj else "",
        "subject_kind": subj.kind if subj else "theory",
        "color": data.subject_color(e.subject_id),
        "teacher_id": e.teacher_id,
        "teacher_name": t.name if t else "",
        "room_id": e.room_id,
        "room_name": r.name if r else "",
        "room_type": r.room_type if r else "",
        "conflicts": sorted((conflict_types or {}).get(e.id, set())),
    }


def conflict_index(conflicts: list[Conflict]) -> dict[int, set[str]]:
    idx: dict[int, set[str]] = defaultdict(set)
    for c in conflicts:
        if c.severity != "major":
            continue
        for eid in c.entry_ids:
            idx[eid].add(c.type)
    return idx


def union_slots(grids: list[ScheduleGrid], include_breaks: bool = True) -> tuple[list[dict], dict[int, list[str]], list[int]]:
    """Rows for a grid view built from one or more schedules."""
    periods: dict[tuple[int, int], dict] = {}
    breaks: dict[tuple[int, int], dict] = {}
    day_slots: dict[int, set[str]] = defaultdict(set)
    days: set[int] = set()
    for g in grids:
        for day, plist in g.periods.items():
            days.add(day)
            for p in plist:
                key = f"{p.start}-{p.end}"
                periods.setdefault((p.start, p.end), {
                    "key": key, "kind": "period", "start": p.start, "end": p.end,
                    "time": fmt_range(p.start, p.end), "label": p.label,
                })
                day_slots[day].add(key)
        if include_breaks:
            for day, blist in g.breaks.items():
                for b in blist:
                    key = f"{b.start}-{b.end}"
                    breaks.setdefault((b.start, b.end), {
                        "key": key, "kind": b.kind, "start": b.start, "end": b.end,
                        "time": fmt_range(b.start, b.end), "label": b.name,
                    })
                    day_slots[day].add(key)
    rows = list(periods.values())
    for (bs, be), b in breaks.items():
        if not any(ps < be and bs < pe for (ps, pe) in periods):
            rows.append(b)
    rows.sort(key=lambda x: (x["start"], x["end"]))
    # label periods by order when several schedules are mixed
    if len(grids) > 1:
        n = 0
        for r in rows:
            if r["kind"] == "period":
                n += 1
                r["label"] = f"P{n}"
    return rows, {d: sorted(v) for d, v in day_slots.items()}, sorted(days)


def _days_payload(days: list[int]) -> list[dict]:
    return [{"day": d, "name": DAY_NAMES[d], "short": DAY_SHORT[d]} for d in days]


def build_view(
    data: InstitutionData,
    tt: Timetable,
    entries: list[TimetableEntry],
    view_type: str,
    ref_id: int | None,
    conflicts: list[Conflict] | None = None,
) -> dict:
    if view_type not in VIEW_TYPES:
        raise HTTPException(422, f"view must be one of {', '.join(VIEW_TYPES)}")
    cidx = conflict_index(conflicts or [])
    scope_classes = data.scope_class_ids(tt.department_id)

    if view_type in ("department", "school", "institution"):
        if view_type == "institution":
            class_ids = scope_classes
            title = data.inst.name
        else:
            if ref_id is None or ref_id not in data.departments:
                raise HTTPException(422, "Choose a department or school")
            class_ids = data.scope_class_ids(ref_id) & scope_classes
            title = data.departments[ref_id].name
        classes = sorted((data.classes[c] for c in class_ids), key=lambda c: (c.department_id or 0, c.name))
        grids = [data.class_grid(c) for c in classes] or [data.grid(data.inst.default_schedule_id)]
        rows, day_slots, days = union_slots(grids, include_breaks=False)
        sel = [enrich(data, e, cidx) for e in entries if e.class_id in class_ids]
        return {
            "kind": "master", "view": view_type, "ref_id": ref_id, "title": title,
            "subtitle": f"{len(classes)} classes · {len(sel)} sessions",
            "days": _days_payload(days), "slots": rows, "day_slots": day_slots,
            "rows": [
                {"id": c.id, "name": c.name,
                 "department": data.departments[c.department_id].name if c.department_id in data.departments else "",
                 "periods": {str(d): [[p.start, p.end] for p in g.periods[d]] for d in g.days},
                 "breaks": {str(d): [[b.start, b.end, b.name] for b in g.breaks.get(d, [])] for d in g.days}}
                for c, g in ((c, data.class_grid(c)) for c in classes)
            ],
            "entries": sel,
        }

    if ref_id is None:
        raise HTTPException(422, "Choose which class, teacher or room to show")
    if view_type == "class":
        cls = data.classes.get(ref_id)
        if cls is None:
            raise HTTPException(404, "Class not found")
        sel = [e for e in entries if e.class_id == ref_id]
        grids = [data.class_grid(cls)]
        title = cls.name
        dept = data.departments.get(cls.department_id) if cls.department_id else None
        subtitle = " · ".join(x for x in [dept.name if dept else "", f"{cls.strength} students"] if x)
    elif view_type == "teacher":
        t = data.teachers.get(ref_id)
        if t is None:
            raise HTTPException(404, "Teacher not found")
        sel = [e for e in entries if e.teacher_id == ref_id]
        grids = list({id(g): g for g in (data.class_grid(data.classes[e.class_id]) for e in sel)}.values())
        title = t.name
        periods = sum(e.length for e in sel)
        subtitle = f"{t.designation or 'Teacher'} · {periods} periods/week" + (
            f" (limit {t.max_per_week})" if t.max_per_week else "")
    else:  # room / lab
        r = data.rooms.get(ref_id)
        if r is None:
            raise HTTPException(404, "Room not found")
        if view_type == "lab" and r.room_type != "lab":
            raise HTTPException(422, f"{r.name} is not a laboratory")
        sel = [e for e in entries if e.room_id == ref_id]
        grids = list({id(g): g for g in (data.class_grid(data.classes[e.class_id]) for e in sel)}.values())
        title = r.name
        subtitle = f"{r.room_type.replace('_', ' ').title()} · capacity {r.capacity}"
    if not grids:
        grids = [data.grid(data.inst.default_schedule_id)]
    rows, day_slots, days = union_slots(grids)
    return {
        "kind": "grid", "view": view_type, "ref_id": ref_id, "title": title, "subtitle": subtitle,
        "days": _days_payload(days), "slots": rows, "day_slots": day_slots,
        "entries": [enrich(data, e, cidx) for e in sel],
    }


def view_options(data: InstitutionData, tt: Timetable, entries: list[TimetableEntry]) -> dict:
    scope = data.scope_class_ids(tt.department_id)
    teacher_ids = {e.teacher_id for e in entries} | {
        a.teacher_id for a in data.assignments.values() if a.class_id in scope}
    room_ids = {e.room_id for e in entries}
    if tt.department_id is None:
        depts = list(data.departments.values())
    else:
        depts = [data.departments[d] for d in data.subtree(tt.department_id) if d in data.departments]
    return {
        "classes": [{"id": c.id, "name": c.name} for c in sorted((data.classes[i] for i in scope), key=lambda c: c.name)],
        "teachers": [{"id": t.id, "name": t.name} for t in sorted((data.teachers[i] for i in teacher_ids if i in data.teachers), key=lambda t: t.name)],
        "rooms": [{"id": r.id, "name": r.name, "room_type": r.room_type}
                  for r in sorted((data.rooms[i] for i in room_ids if i in data.rooms), key=lambda r: r.name)],
        "labs": [{"id": r.id, "name": r.name} for r in sorted(data.rooms.values(), key=lambda r: r.name)
                 if r.room_type == "lab"],
        "departments": [{"id": d.id, "name": d.name, "kind": d.kind} for d in sorted(depts, key=lambda d: d.name)
                        if d.kind != "school"],
        "schools": [{"id": d.id, "name": d.name, "kind": d.kind} for d in sorted(depts, key=lambda d: d.name)
                    if d.kind in ("school", "faculty", "wing")],
    }


def all_refs(data: InstitutionData, tt: Timetable, entries: list[TimetableEntry], view_type: str) -> list[int]:
    opts = view_options(data, tt, entries)
    key = {"class": "classes", "teacher": "teachers", "room": "rooms", "lab": "labs",
           "department": "departments", "school": "schools"}.get(view_type)
    return [o["id"] for o in opts.get(key, [])] if key else []
