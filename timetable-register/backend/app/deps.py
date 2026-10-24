from fastapi import Depends, HTTPException, Path
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import Access, get_current_user


def get_access(
    institution_id: int = Path(..., ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Access:
    return Access(user, institution_id, db)


def ensure_in(db: Session, model, obj_id: int | None, institution_id: int, label: str):
    """Make sure a referenced row exists and belongs to the same institution."""
    if obj_id is None:
        return None
    row = db.get(model, obj_id)
    if row is None or getattr(row, "institution_id", None) != institution_id:
        raise HTTPException(422, f"{label} #{obj_id} does not exist in this institution")
    return row
