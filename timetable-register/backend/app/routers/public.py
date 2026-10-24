"""Read-only access to a timetable through its share link (no login)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Timetable
from ..services import timetables as svc
from ..services.data import InstitutionData
from ..services.views import build_view, view_options
from .timetables import export_timetable

router = APIRouter(prefix="/api/public/share", tags=["public"])


def _by_token(db: Session, token: str) -> Timetable:
    tt = db.scalar(select(Timetable).where(Timetable.share_token == token))
    if tt is None:
        raise HTTPException(404, "This share link is invalid or has been revoked")
    return tt


@router.get("/{token}")
def shared(token: str, db: Session = Depends(get_db)):
    tt = _by_token(db, token)
    data = InstitutionData(db, tt.institution_id)
    entries = svc.load_entries(db, tt)
    return {
        "id": tt.id, "name": tt.name, "term": tt.term, "status": tt.status,
        "institution": {"id": data.inst.id, "name": data.inst.name, "kind": data.inst.kind},
        "scope": svc.scope_label(data, tt.department_id),
        "options": view_options(data, tt, entries),
        "updated_at": tt.updated_at,
    }


@router.get("/{token}/view")
def shared_view(token: str, view: str = Query("class"), ref: int | None = None, db: Session = Depends(get_db)):
    tt = _by_token(db, token)
    data = InstitutionData(db, tt.institution_id)
    return build_view(data, tt, svc.load_entries(db, tt), view, ref)


@router.get("/{token}/export")
def shared_export(token: str, format: str = Query("pdf"), view: str = Query("class"), ref: int | None = None,
                  db: Session = Depends(get_db)):
    tt = _by_token(db, token)
    return export_timetable(db, InstitutionData(db, tt.institution_id), tt, format, view, ref)
