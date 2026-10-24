from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Institution, User
from ..schemas import AvailabilityUpdate, InstitutionOut, LoginIn, TeacherOut, TokenOut, UserOut
from ..security import create_token, get_current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(403, "This account is disabled")
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inst = db.get(Institution, user.institution_id) if user.institution_id else None
    return {
        "user": UserOut.model_validate(user),
        "institution": InstitutionOut.model_validate(inst) if inst else None,
    }


@router.put("/me/availability", response_model=TeacherOut)
def update_my_availability(
    body: AvailabilityUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Teachers maintain their own unavailable / preferred / avoid slots."""
    from ..models import Teacher

    if not user.teacher_id:
        raise HTTPException(403, "Your account is not linked to a teacher profile")
    t = db.get(Teacher, user.teacher_id)
    if t is None:
        raise HTTPException(404, "Teacher profile not found")
    for field in ("unavailable", "avoid", "preferred"):
        val = getattr(body, field)
        if val is not None:
            setattr(t, field, [w.model_dump() for w in val])
    db.commit()
    return t
