"""Institutions (super admin) and user management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ensure_in, get_access
from ..models import ClassGroup, Department, Institution, Role, Schedule, Teacher, User
from ..schemas import InstitutionIn, InstitutionOut, InstitutionUpdate, UserCreate, UserOut, UserUpdate
from ..scheduler.timegrid import DEFAULT_SCHEDULE
from ..security import Access, get_current_user, hash_password

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/institutions", response_model=list[InstitutionOut])
def list_institutions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == Role.super_admin.value:
        return list(db.scalars(select(Institution).order_by(Institution.name)))
    inst = db.get(Institution, user.institution_id) if user.institution_id else None
    return [inst] if inst else []


@router.post("/institutions", response_model=InstitutionOut, status_code=201)
def create_institution(body: InstitutionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != Role.super_admin.value:
        raise HTTPException(403, "Only a super admin can add institutions")
    values = body.model_dump()
    values.pop("default_schedule_id", None)
    inst = Institution(**values)
    db.add(inst)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An institution with this code already exists") from None
    sched = Schedule(institution_id=inst.id, name="Default schedule", config=DEFAULT_SCHEDULE)
    db.add(sched)
    db.flush()
    inst.default_schedule_id = sched.id
    db.commit()
    db.refresh(inst)
    return inst


@router.get("/institutions/{institution_id}", response_model=InstitutionOut)
def get_institution(access: Access = Depends(get_access), db: Session = Depends(get_db)):
    inst = db.get(Institution, access.institution_id)
    if inst is None:
        raise HTTPException(404, "Institution not found")
    return inst


@router.patch("/institutions/{institution_id}", response_model=InstitutionOut)
def update_institution(body: InstitutionUpdate, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    access.require_inst_admin()
    inst = db.get(Institution, access.institution_id)
    values = body.model_dump(exclude_unset=True)
    if "default_schedule_id" in values and values["default_schedule_id"] is not None:
        ensure_in(db, Schedule, values["default_schedule_id"], inst.id, "Schedule")
    for k, v in values.items():
        setattr(inst, k, v)
    db.commit()
    db.refresh(inst)
    return inst


@router.delete("/institutions/{institution_id}", status_code=204)
def delete_institution(access: Access = Depends(get_access), db: Session = Depends(get_db)):
    if not access.is_super:
        raise HTTPException(403, "Only a super admin can delete institutions")
    inst = db.get(Institution, access.institution_id)
    inst.default_schedule_id = None
    db.flush()
    db.delete(inst)
    db.commit()


# ---------------------------------------------------------------------- users
def _check_user_scope(access: Access, db: Session, role: str, department_id: int | None) -> None:
    if role == Role.super_admin.value and not access.is_super:
        raise HTTPException(403, "Only a super admin can create super admins")
    if access.is_inst_admin:
        return
    if access.role == Role.department_admin.value:
        if role not in (Role.teacher.value, Role.student.value, Role.department_admin.value):
            raise HTTPException(403, "Department admins can only manage department staff and students")
        access.require_department(department_id)
        return
    raise HTTPException(403, "Admin rights required")


@router.get("/institutions/{institution_id}/users", response_model=list[UserOut])
def list_users(access: Access = Depends(get_access), db: Session = Depends(get_db)):
    access.require_admin()
    stmt = select(User).where(User.institution_id == access.institution_id).order_by(User.role, User.full_name)
    users = list(db.scalars(stmt))
    if not access.is_inst_admin:
        users = [u for u in users if u.department_id in access.dept_subtree]
    return users


@router.post("/institutions/{institution_id}/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    _check_user_scope(access, db, body.role, body.department_id)
    ensure_in(db, Department, body.department_id, access.institution_id, "Department")
    ensure_in(db, Teacher, body.teacher_id, access.institution_id, "Teacher")
    ensure_in(db, ClassGroup, body.class_id, access.institution_id, "Class")
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    values = body.model_dump()
    password = values.pop("password")
    values["institution_id"] = None if body.role == Role.super_admin.value else access.institution_id
    u = User(**values, password_hash=hash_password(password))
    u.email = u.email.lower()
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.patch("/institutions/{institution_id}/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None or (u.institution_id != access.institution_id and not access.is_super):
        raise HTTPException(404, "User not found")
    values = body.model_dump(exclude_unset=True)
    _check_user_scope(access, db, values.get("role", u.role), values.get("department_id", u.department_id))
    if not access.is_inst_admin:
        access.require_department(u.department_id)
    ensure_in(db, Department, values.get("department_id"), access.institution_id, "Department")
    ensure_in(db, Teacher, values.get("teacher_id"), access.institution_id, "Teacher")
    ensure_in(db, ClassGroup, values.get("class_id"), access.institution_id, "Class")
    if "password" in values:
        pw = values.pop("password")
        if pw:
            u.password_hash = hash_password(pw)
    for k, v in values.items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return u


@router.delete("/institutions/{institution_id}/users/{user_id}", status_code=204)
def delete_user(user_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None or u.institution_id != access.institution_id:
        raise HTTPException(404, "User not found")
    if u.id == access.user.id:
        raise HTTPException(422, "You cannot delete your own account")
    _check_user_scope(access, db, u.role, u.department_id)
    db.delete(u)
    db.commit()
