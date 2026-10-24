from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_access
from ..models import Timetable, TimetableEntry
from ..scheduler.timegrid import DAY_SHORT
from ..security import Access
from ..services.data import InstitutionData

router = APIRouter(prefix="/api/institutions/{institution_id}", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(department_id: int | None = None, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    data = InstitutionData(db, access.institution_id)
    dept_ids = data.subtree(department_id) if department_id else None

    def in_scope(dep):
        return dept_ids is None or dep in dept_ids

    teachers = [t for t in data.teachers.values() if t.active and in_scope(t.department_id)]
    classes = [c for c in data.classes.values() if in_scope(c.department_id)]
    subjects = [s for s in data.subjects.values() if in_scope(s.department_id)]
    rooms = [r for r in data.rooms.values() if r.active]
    labs = [r for r in rooms if r.room_type == "lab"]
    class_ids = {c.id for c in classes}

    tts = list(db.scalars(
        select(Timetable).where(Timetable.institution_id == access.institution_id).order_by(Timetable.created_at.desc())
    ))
    if not access.sees_drafts:
        tts = [t for t in tts if t.status == "published"]
    published = [t for t in tts if t.status == "published"]
    current = published or tts[:1]
    current_ids = [t.id for t in current]
    entries = list(db.scalars(select(TimetableEntry).where(TimetableEntry.timetable_id.in_(current_ids or [-1]))))
    entries = [e for e in entries if e.class_id in class_ids]

    # conflicts across timetables that are still in use
    live = [t for t in tts if t.status != "archived"]
    conflict_major = sum(int((t.conflict_summary or {}).get("major", 0)) for t in live)
    conflict_minor = sum(int((t.conflict_summary or {}).get("minor", 0)) for t in live)
    by_type: Counter = Counter()
    for t in live:
        by_type.update((t.conflict_summary or {}).get("by_type", {}))
    unscheduled = sum(len((t.generation or {}).get("unscheduled", [])) for t in live)

    # teacher workload
    scheduled = Counter()
    for e in entries:
        scheduled[e.teacher_id] += e.length
    assigned = Counter()
    for a in data.assignments.values():
        if a.class_id in class_ids:
            assigned[a.teacher_id] += a.lectures_per_week
    workload = []
    for t in teachers:
        cap = t.max_per_week
        workload.append({
            "teacher_id": t.id,
            "name": t.name,
            "department": data.departments[t.department_id].name if t.department_id in data.departments else "",
            "scheduled": scheduled.get(t.id, 0),
            "assigned": assigned.get(t.id, 0),
            "max_per_week": cap,
            "utilization": round(100 * scheduled.get(t.id, 0) / cap, 1) if cap else None,
        })
    workload.sort(key=lambda w: (-w["scheduled"], w["name"]))

    # room utilisation (share of the institution's teaching periods in use)
    base_grid = data.grid(data.inst.default_schedule_id)
    grids = {id(g): g for g in (data.class_grid(c) for c in classes)} or {0: base_grid}
    available = max(g.total_periods() for g in grids.values())
    used = Counter()
    for e in entries:
        used[e.room_id] += e.length
    room_util = [{
        "room_id": r.id, "name": r.name, "room_type": r.room_type, "capacity": r.capacity,
        "used": used.get(r.id, 0), "available": available,
        "utilization": round(100 * used.get(r.id, 0) / available, 1) if available else 0,
    } for r in rooms]
    room_util.sort(key=lambda x: -x["utilization"])

    per_day = defaultdict(int)
    for e in entries:
        per_day[e.day] += e.length
    days = sorted({d for g in grids.values() for d in g.days})

    return {
        "institution": {"id": data.inst.id, "name": data.inst.name, "kind": data.inst.kind},
        "totals": {
            "teachers": len(teachers),
            "classes": len(classes),
            "subjects": len(subjects),
            "classrooms": len([r for r in rooms if r.room_type != "lab"]),
            "laboratories": len(labs),
            "departments": len([d for d in data.departments.values() if in_scope(d.id)]),
            "timetables": len(tts),
            "published": len(published),
            "conflicts": conflict_major + conflict_minor,
            "major_conflicts": conflict_major,
            "minor_conflicts": conflict_minor,
            "unscheduled": unscheduled,
            "weekly_sessions": len(entries),
        },
        "conflicts_by_type": dict(by_type),
        "based_on": [{"id": t.id, "name": t.name, "status": t.status} for t in current],
        "teacher_workload": workload,
        "room_utilization": room_util,
        "avg_room_utilization": round(sum(r["utilization"] for r in room_util) / len(room_util), 1) if room_util else 0,
        "daily_load": [{"day": d, "name": DAY_SHORT[d], "periods": per_day.get(d, 0)} for d in days],
        "recent_timetables": [
            {"id": t.id, "name": t.name, "status": t.status, "created_at": t.created_at,
             "conflicts": (t.conflict_summary or {}).get("major", 0),
             "complete": (t.generation or {}).get("complete")}
            for t in tts[:6]
        ],
    }
