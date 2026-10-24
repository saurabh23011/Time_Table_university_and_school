"""Authentication (JWT) and role-based authorisation.

Permission model
----------------
super_admin        everything, every institution
institution_admin  everything inside their own institution (incl. users, rooms, schedules)
department_admin   reads the institution; writes teachers, subjects, classes, curriculum and
                   timetables of their own department subtree; manages teacher/student users there
teacher            reads the institution and published timetables; edits own availability
student            reads published timetables of the institution
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Department, Role, User

ADMIN_ROLES = {Role.super_admin.value, Role.institution_admin.value, Role.department_admin.value}
ROLE_RANK = {
    Role.student.value: 0,
    Role.teacher.value: 1,
    Role.department_admin.value: 2,
    Role.institution_admin.value: 3,
    Role.super_admin.value: 4,
}

_ITER = 240_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_b64, hash_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:  # noqa: BLE001
        return False


def create_token(user: User) -> str:
    s = get_settings()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "inst": user.institution_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=s.token_minutes),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(creds.credentials, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def department_subtree(db: Session, root_id: int | None) -> set[int]:
    """IDs of a department and all its descendants."""
    if root_id is None:
        return set()
    rows = db.execute(select(Department.id, Department.parent_id)).all()
    children: dict[int | None, list[int]] = {}
    for did, pid in rows:
        children.setdefault(pid, []).append(did)
    out, stack = set(), [root_id]
    while stack:
        d = stack.pop()
        if d in out:
            continue
        out.add(d)
        stack.extend(children.get(d, []))
    return out


class Access:
    """Resolved permissions of the current user inside one institution."""

    def __init__(self, user: User, institution_id: int, db: Session):
        self.user = user
        self.institution_id = institution_id
        self.db = db
        self.role = user.role
        if user.role != Role.super_admin.value and user.institution_id != institution_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not belong to this institution")
        self._subtree: set[int] | None = None

    @property
    def is_super(self) -> bool:
        return self.role == Role.super_admin.value

    @property
    def is_inst_admin(self) -> bool:
        return self.role in (Role.super_admin.value, Role.institution_admin.value)

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES

    @property
    def dept_subtree(self) -> set[int]:
        if self._subtree is None:
            self._subtree = department_subtree(self.db, self.user.department_id)
        return self._subtree

    def require_inst_admin(self) -> None:
        if not self.is_inst_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Institution admin rights required")

    def require_admin(self) -> None:
        if not self.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin rights required")

    def can_write_department(self, department_id: int | None) -> bool:
        if self.is_inst_admin:
            return True
        if self.role == Role.department_admin.value:
            return department_id is not None and department_id in self.dept_subtree
        return False

    def require_department(self, department_id: int | None) -> None:
        if not self.can_write_department(department_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "You can only manage records of your own department" if self.is_admin else "Admin rights required",
            )

    @property
    def sees_drafts(self) -> bool:
        return self.is_admin
