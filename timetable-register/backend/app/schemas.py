from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .scheduler.timegrid import ScheduleConfigError, build_grid, parse_hhmm

RoomType = Literal["classroom", "lab", "seminar_hall", "auditorium", "tutorial_room", "other"]
SubjectRoomType = Literal["classroom", "lab", "seminar_hall", "auditorium", "tutorial_room", "other", "any"]
RoleName = Literal["super_admin", "institution_admin", "department_admin", "teacher", "student"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _hhmm(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    parse_hhmm(v)
    h, m = v.split(":")
    return f"{int(h):02d}:{int(m):02d}"


class WindowIn(BaseModel):
    day: int = Field(ge=0, le=6)
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _t(cls, v: str) -> str:
        return _hhmm(v) or "00:00"

    @model_validator(mode="after")
    def _order(self) -> "WindowIn":
        if parse_hhmm(self.end) <= parse_hhmm(self.start):
            raise ValueError("Window end must be after start")
        return self


# ---------------------------------------------------------------- auth / users
class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: str
    institution_id: int | None
    department_id: int | None
    teacher_id: int | None
    class_id: int | None
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str = Field(min_length=8)
    role: RoleName
    institution_id: int | None = None
    department_id: int | None = None
    teacher_id: int | None = None
    class_id: int | None = None
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: RoleName | None = None
    department_id: int | None = None
    teacher_id: int | None = None
    class_id: int | None = None
    is_active: bool | None = None


# ----------------------------------------------------------------- institution
class InstitutionIn(BaseModel):
    name: str
    code: str
    kind: Literal["university", "college", "school"] = "university"
    address: str | None = None
    default_schedule_id: int | None = None
    soft_weights: dict[str, float] = {}


class InstitutionUpdate(BaseModel):
    name: str | None = None
    kind: Literal["university", "college", "school"] | None = None
    address: str | None = None
    default_schedule_id: int | None = None
    soft_weights: dict[str, float] | None = None


class InstitutionOut(ORM):
    id: int
    name: str
    code: str
    kind: str
    address: str | None
    default_schedule_id: int | None
    soft_weights: dict
    created_at: datetime


# -------------------------------------------------------------------- schedules
class BreakIn(BaseModel):
    name: str = "Break"
    kind: Literal["break", "lunch"] = "break"
    after_period: int = Field(ge=1)
    minutes: int = Field(ge=1, le=240)


class ScheduleConfig(BaseModel):
    working_days: list[int] = [0, 1, 2, 3, 4]
    day_start: str = "09:00"
    day_end: str = "17:00"
    lecture_minutes: int = Field(60, ge=10, le=240)
    periods_per_day: int = Field(7, ge=1, le=16)
    breaks: list[BreakIn] = []
    day_overrides: dict[str, dict[str, Any]] = {}

    @field_validator("day_start", "day_end")
    @classmethod
    def _t(cls, v: str) -> str:
        return _hhmm(v) or "00:00"

    @model_validator(mode="after")
    def _valid(self) -> "ScheduleConfig":
        try:
            build_grid(self.model_dump())
        except ScheduleConfigError as exc:
            raise ValueError(str(exc)) from exc
        return self


class ScheduleIn(BaseModel):
    name: str
    config: ScheduleConfig


class ScheduleUpdate(BaseModel):
    name: str | None = None
    config: ScheduleConfig | None = None


class ScheduleOut(ORM):
    id: int
    institution_id: int
    name: str
    config: dict


# ------------------------------------------------------------------ departments
class DepartmentIn(BaseModel):
    name: str
    code: str
    kind: Literal["school", "faculty", "department", "wing"] = "department"
    parent_id: int | None = None
    schedule_id: int | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    kind: Literal["school", "faculty", "department", "wing"] | None = None
    parent_id: int | None = None
    schedule_id: int | None = None


class DepartmentOut(ORM):
    id: int
    institution_id: int
    name: str
    code: str
    kind: str
    parent_id: int | None
    schedule_id: int | None


# --------------------------------------------------------------------- teachers
class TeacherIn(BaseModel):
    name: str
    code: str | None = None
    email: str | None = None
    designation: str | None = None
    department_id: int | None = None
    work_start: str | None = None
    work_end: str | None = None
    max_per_day: int | None = Field(default=None, ge=1, le=16)
    max_per_week: int | None = Field(default=None, ge=1, le=80)
    max_consecutive: int | None = Field(default=None, ge=1, le=16)
    unavailable: list[WindowIn] = []
    avoid: list[WindowIn] = []
    preferred: list[WindowIn] = []
    active: bool = True

    @field_validator("work_start", "work_end")
    @classmethod
    def _t(cls, v):
        return _hhmm(v)


class TeacherUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    email: str | None = None
    designation: str | None = None
    department_id: int | None = None
    work_start: str | None = None
    work_end: str | None = None
    max_per_day: int | None = Field(default=None, ge=1, le=16)
    max_per_week: int | None = Field(default=None, ge=1, le=80)
    max_consecutive: int | None = Field(default=None, ge=1, le=16)
    unavailable: list[WindowIn] | None = None
    avoid: list[WindowIn] | None = None
    preferred: list[WindowIn] | None = None
    active: bool | None = None

    @field_validator("work_start", "work_end")
    @classmethod
    def _t(cls, v):
        return _hhmm(v)


class AvailabilityUpdate(BaseModel):
    unavailable: list[WindowIn] | None = None
    avoid: list[WindowIn] | None = None
    preferred: list[WindowIn] | None = None


class TeacherOut(ORM):
    id: int
    institution_id: int
    department_id: int | None
    name: str
    code: str | None
    email: str | None
    designation: str | None
    work_start: str | None
    work_end: str | None
    max_per_day: int | None
    max_per_week: int | None
    max_consecutive: int | None
    unavailable: list
    avoid: list
    preferred: list
    active: bool


# ------------------------------------------------------------------------ rooms
class RoomIn(BaseModel):
    name: str
    code: str | None = None
    building: str | None = None
    department_id: int | None = None
    room_type: RoomType = "classroom"
    capacity: int = Field(60, ge=1, le=5000)
    tags: list[str] = []
    unavailable: list[WindowIn] = []
    active: bool = True


class RoomUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    building: str | None = None
    department_id: int | None = None
    room_type: RoomType | None = None
    capacity: int | None = Field(default=None, ge=1, le=5000)
    tags: list[str] | None = None
    unavailable: list[WindowIn] | None = None
    active: bool | None = None


class RoomOut(ORM):
    id: int
    institution_id: int
    department_id: int | None
    name: str
    code: str | None
    building: str | None
    room_type: str
    capacity: int
    tags: list
    unavailable: list
    active: bool


# --------------------------------------------------------------------- subjects
class SubjectIn(BaseModel):
    code: str
    name: str
    department_id: int | None = None
    kind: Literal["theory", "lab", "tutorial"] = "theory"
    room_type: SubjectRoomType | None = None
    room_tag: str | None = None
    color: str | None = None

    @model_validator(mode="after")
    def _default_room(self):
        if self.room_type is None:
            self.room_type = "lab" if self.kind == "lab" else "classroom"
        return self


class SubjectUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    department_id: int | None = None
    kind: Literal["theory", "lab", "tutorial"] | None = None
    room_type: SubjectRoomType | None = None
    room_tag: str | None = None
    color: str | None = None


class SubjectOut(ORM):
    id: int
    institution_id: int
    department_id: int | None
    code: str
    name: str
    kind: str
    room_type: str
    room_tag: str | None
    color: str | None


# ---------------------------------------------------------------------- classes
class ClassIn(BaseModel):
    name: str
    department_id: int | None = None
    program: str | None = None
    term: str | None = None
    section: str | None = None
    batch: str | None = None
    strength: int = Field(40, ge=1, le=5000)
    schedule_id: int | None = None
    unavailable: list[WindowIn] = []


class ClassUpdate(BaseModel):
    name: str | None = None
    department_id: int | None = None
    program: str | None = None
    term: str | None = None
    section: str | None = None
    batch: str | None = None
    strength: int | None = Field(default=None, ge=1, le=5000)
    schedule_id: int | None = None
    unavailable: list[WindowIn] | None = None


class ClassOut(ORM):
    id: int
    institution_id: int
    department_id: int | None
    name: str
    program: str | None
    term: str | None
    section: str | None
    batch: str | None
    strength: int
    schedule_id: int | None
    unavailable: list


# ------------------------------------------------------------------ assignments
class AssignmentIn(BaseModel):
    class_id: int
    subject_id: int
    teacher_id: int
    lectures_per_week: int = Field(3, ge=1, le=40)
    consecutive_periods: int = Field(1, ge=1, le=6)
    fixed_room_id: int | None = None

    @model_validator(mode="after")
    def _divisible(self):
        if self.lectures_per_week % self.consecutive_periods:
            raise ValueError("Lectures per week must be a multiple of consecutive periods per session")
        return self


class AssignmentUpdate(BaseModel):
    teacher_id: int | None = None
    lectures_per_week: int | None = Field(default=None, ge=1, le=40)
    consecutive_periods: int | None = Field(default=None, ge=1, le=6)
    fixed_room_id: int | None = None


class AssignmentOut(ORM):
    id: int
    institution_id: int
    class_id: int
    subject_id: int
    teacher_id: int
    lectures_per_week: int
    consecutive_periods: int
    fixed_room_id: int | None


# ------------------------------------------------------------------- timetables
class GenerateIn(BaseModel):
    name: str
    term: str | None = None
    department_id: int | None = None  # None = whole institution
    time_limit: float | None = Field(default=None, ge=1, le=600)
    seed: int | None = None
    optimise: bool = True


class RegenerateIn(BaseModel):
    keep_locked: bool = True
    time_limit: float | None = Field(default=None, ge=1, le=600)
    seed: int | None = None


class TimetableOut(ORM):
    id: int
    institution_id: int
    department_id: int | None
    name: str
    term: str | None
    status: str
    share_token: str | None
    generation: dict
    conflict_summary: dict
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class EntryMove(BaseModel):
    day: int | None = Field(default=None, ge=0, le=6)
    period_index: int | None = Field(default=None, ge=0)
    start: int | None = Field(default=None, ge=0, le=1440, description="start minute; alternative to period_index")
    room_id: int | None = None
    teacher_id: int | None = None
    locked: bool | None = None
    dry_run: bool = False


class EntryCreate(BaseModel):
    assignment_id: int
    day: int = Field(ge=0, le=6)
    period_index: int = Field(ge=0)
    room_id: int | None = None
    locked: bool = False
    dry_run: bool = False
