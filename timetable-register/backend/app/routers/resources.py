"""CRUD endpoints for institution-scoped resources.

/api/institutions/{institution_id}/{departments|schedules|teachers|rooms|subjects|classes|assignments}
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ensure_in, get_access
from ..models import (
    Assignment,
    ClassGroup,
    Department,
    Room,
    Schedule,
    Subject,
    Teacher,
    TimetableEntry,
)
from ..scheduler.timegrid import grid_to_dict
from ..scheduler.timegrid import build_grid
from ..schemas import (
    AssignmentIn,
    AssignmentOut,
    AssignmentUpdate,
    ClassIn,
    ClassOut,
    ClassUpdate,
    DepartmentIn,
    DepartmentOut,
    DepartmentUpdate,
    RoomIn,
    RoomOut,
    RoomUpdate,
    ScheduleConfig,
    ScheduleIn,
    ScheduleOut,
    ScheduleUpdate,
    SubjectIn,
    SubjectOut,
    SubjectUpdate,
    TeacherIn,
    TeacherOut,
    TeacherUpdate,
)
from ..security import Access

router = APIRouter(prefix="/api/institutions/{institution_id}", tags=["resources"])

# Which references each resource has, for same-institution validation
REFS: dict[str, tuple[Any, str]] = {
    "department_id": (Department, "Department"),
    "parent_id": (Department, "Parent department"),
    "schedule_id": (Schedule, "Schedule"),
    "class_id": (ClassGroup, "Class"),
    "subject_id": (Subject, "Subject"),
    "teacher_id": (Teacher, "Teacher"),
    "fixed_room_id": (Room, "Room"),
}


def _dump(payload: BaseModel, exclude_unset: bool) -> dict:
    data = payload.model_dump(exclude_unset=exclude_unset)
    for k, v in list(data.items()):
        if isinstance(v, list) and v and isinstance(v[0], dict) and "day" in v[0]:
            data[k] = v  # windows already dicts
    return data


def _check_refs(db: Session, iid: int, values: dict) -> None:
    for field, (model, label) in REFS.items():
        if field in values and values[field] is not None:
            ensure_in(db, model, values[field], iid, label)


def register(
    name: str,
    model,
    in_schema: type[BaseModel],
    update_schema: type[BaseModel],
    out_schema: type[BaseModel],
    *,
    dept_of: Callable[[Session, dict, Any], int | None] | None,
    order_by,
    usage_check: Callable[[Session, Any], int] | None = None,
    usage_label: str = "",
    filters: tuple[str, ...] = ("department_id",),
    extra_validate: Callable[[Session, Access, dict, Any], None] | None = None,
):
    """dept_of=None means institution-admin-only writes; otherwise the returned
    department must be inside a department admin's subtree."""

    def authorize_write(access: Access, db: Session, values: dict, obj: Any) -> None:
        if dept_of is None:
            access.require_inst_admin()
            return
        access.require_admin()
        if access.is_inst_admin:
            return
        if obj is not None:
            access.require_department(dept_of(db, {}, obj))
        if values or obj is None:
            merged = {}
            if obj is not None:
                merged = {c.key: getattr(obj, c.key) for c in model.__table__.columns}
            merged.update(values)
            access.require_department(dept_of(db, merged, None))

    @router.get(f"/{name}", response_model=list[out_schema], name=f"list_{name}")
    def list_items(
        access: Access = Depends(get_access),
        db: Session = Depends(get_db),
        q: str | None = Query(None, description="search by name"),
        department_id: int | None = None,
        class_id: int | None = None,
        teacher_id: int | None = None,
    ):
        stmt = select(model).where(model.institution_id == access.institution_id)
        if q and hasattr(model, "name"):
            stmt = stmt.where(func.lower(model.name).contains(q.lower()))
        if department_id is not None and "department_id" in filters:
            stmt = stmt.where(model.department_id == department_id)
        if class_id is not None and hasattr(model, "class_id"):
            stmt = stmt.where(model.class_id == class_id)
        if teacher_id is not None and hasattr(model, "teacher_id"):
            stmt = stmt.where(model.teacher_id == teacher_id)
        return list(db.scalars(stmt.order_by(*order_by)))

    @router.get(f"/{name}/{{item_id}}", response_model=out_schema, name=f"get_{name}")
    def get_item(item_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
        return _get(db, access, item_id)

    def _get(db: Session, access: Access, item_id: int):
        obj = db.get(model, item_id)
        if obj is None or obj.institution_id != access.institution_id:
            raise HTTPException(404, f"{name[:-1].title()} not found")
        return obj

    @router.post(f"/{name}", response_model=out_schema, status_code=201, name=f"create_{name}")
    def create_item(payload: in_schema, access: Access = Depends(get_access), db: Session = Depends(get_db)):
        values = _dump(payload, exclude_unset=False)
        _check_refs(db, access.institution_id, values)
        authorize_write(access, db, values, None)
        if extra_validate:
            extra_validate(db, access, values, None)
        obj = model(institution_id=access.institution_id, **values)
        db.add(obj)
        _commit(db)
        db.refresh(obj)
        return obj

    @router.patch(f"/{name}/{{item_id}}", response_model=out_schema, name=f"update_{name}")
    def update_item(item_id: int, payload: update_schema, access: Access = Depends(get_access),
                    db: Session = Depends(get_db)):
        obj = _get(db, access, item_id)
        values = _dump(payload, exclude_unset=True)
        _check_refs(db, access.institution_id, values)
        authorize_write(access, db, values, obj)
        if extra_validate:
            extra_validate(db, access, values, obj)
        for k, v in values.items():
            setattr(obj, k, v)
        _commit(db)
        db.refresh(obj)
        return obj

    @router.delete(f"/{name}/{{item_id}}", status_code=204, name=f"delete_{name}")
    def delete_item(item_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
        obj = _get(db, access, item_id)
        authorize_write(access, db, {}, obj)
        if usage_check:
            n = usage_check(db, obj)
            if n:
                raise HTTPException(
                    409, f"Cannot delete: used by {n} timetable session(s). {usage_label}".strip()
                )
        db.delete(obj)
        _commit(db)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This record conflicts with an existing one (duplicate code or pairing?)") from exc


def _entries_using(column):
    def check(db: Session, obj) -> int:
        return db.scalar(select(func.count()).select_from(TimetableEntry).where(column == obj.id)) or 0
    return check


def _dept_direct(db, values, obj):
    return obj.department_id if obj is not None else values.get("department_id")


def _dept_of_assignment(db: Session, values, obj):
    class_id = obj.class_id if obj is not None else values.get("class_id")
    cls = db.get(ClassGroup, class_id) if class_id else None
    return cls.department_id if cls else None


def _validate_department(db: Session, access: Access, values: dict, obj) -> None:
    parent = values.get("parent_id")
    if obj is not None and parent is not None:
        # prevent cycles
        seen, cur = set(), db.get(Department, parent)
        while cur is not None and cur.id not in seen:
            if cur.id == obj.id:
                raise HTTPException(422, "A department cannot be placed under itself")
            seen.add(cur.id)
            cur = db.get(Department, cur.parent_id) if cur.parent_id else None


def _validate_assignment(db: Session, access: Access, values: dict, obj) -> None:
    lectures = values.get("lectures_per_week", obj.lectures_per_week if obj else None)
    block = values.get("consecutive_periods", obj.consecutive_periods if obj else 1)
    if lectures and block and lectures % block:
        raise HTTPException(422, "Lectures per week must be a multiple of consecutive periods per session")


register("departments", Department, DepartmentIn, DepartmentUpdate, DepartmentOut,
         dept_of=None, order_by=(Department.name,), filters=(), extra_validate=_validate_department)
register("schedules", Schedule, ScheduleIn, ScheduleUpdate, ScheduleOut,
         dept_of=None, order_by=(Schedule.name,), filters=())
register("teachers", Teacher, TeacherIn, TeacherUpdate, TeacherOut,
         dept_of=_dept_direct, order_by=(Teacher.name,),
         usage_check=_entries_using(TimetableEntry.teacher_id), usage_label="Mark the teacher inactive instead.")
register("rooms", Room, RoomIn, RoomUpdate, RoomOut,
         dept_of=None, order_by=(Room.room_type, Room.name),
         usage_check=_entries_using(TimetableEntry.room_id), usage_label="Mark the room inactive instead.")
register("subjects", Subject, SubjectIn, SubjectUpdate, SubjectOut,
         dept_of=_dept_direct, order_by=(Subject.code,),
         usage_check=_entries_using(TimetableEntry.subject_id))
register("classes", ClassGroup, ClassIn, ClassUpdate, ClassOut,
         dept_of=_dept_direct, order_by=(ClassGroup.name,),
         usage_check=_entries_using(TimetableEntry.class_id))
register("assignments", Assignment, AssignmentIn, AssignmentUpdate, AssignmentOut,
         dept_of=_dept_of_assignment, order_by=(Assignment.class_id, Assignment.id), filters=(),
         extra_validate=_validate_assignment)


# -------------------------------------------------------------- schedule grid
@router.post("/schedules/preview", tags=["resources"])
def preview_schedule(config: ScheduleConfig, access: Access = Depends(get_access)):
    """Return the concrete periods/breaks a configuration produces (for live previews)."""
    return grid_to_dict(build_grid(config.model_dump()))


@router.get("/schedules/{schedule_id}/grid", tags=["resources"])
def schedule_grid(schedule_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    s = ensure_in(db, Schedule, schedule_id, access.institution_id, "Schedule")
    return grid_to_dict(build_grid(s.config))


@router.get("/classes/{class_id}/grid", tags=["resources"])
def class_grid(class_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    from ..services.data import InstitutionData

    data = InstitutionData(db, access.institution_id)
    cls = data.classes.get(class_id)
    if cls is None:
        raise HTTPException(404, "Class not found")
    sid = data.schedule_id_for_class(cls)
    return {"schedule_id": sid, **grid_to_dict(data.class_grid(cls))}
