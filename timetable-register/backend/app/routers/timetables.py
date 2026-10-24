"""Timetable generation, views, editing with conflict checks, publishing, exports and sharing."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import ensure_in, get_access
from ..models import Department, Timetable, TimetableEntry
from ..scheduler import summarize
from ..scheduler.conflicts import Conflict
from ..schemas import EntryCreate, EntryMove, GenerateIn, RegenerateIn, TimetableOut
from ..security import Access
from ..services import exporters
from ..services import timetables as svc
from ..services.data import InstitutionData
from ..services.views import all_refs, build_view, enrich, view_options

router = APIRouter(prefix="/api/institutions/{institution_id}/timetables", tags=["timetables"])


class RenameIn(BaseModel):
    name: str | None = None
    term: str | None = None


def _tt(db: Session, access: Access, tid: int) -> Timetable:
    tt = db.get(Timetable, tid)
    if tt is None or tt.institution_id != access.institution_id:
        raise HTTPException(404, "Timetable not found")
    if tt.status == "draft" and not access.sees_drafts:
        raise HTTPException(404, "Timetable not found")
    return tt


def _require_write(access: Access, tt_department_id: int | None) -> None:
    access.require_admin()
    if access.is_inst_admin:
        return
    if tt_department_id is None:
        raise HTTPException(403, "Only institution admins can manage institution-wide timetables")
    access.require_department(tt_department_id)


def _out(tt: Timetable, entry_count: int | None = None) -> dict:
    d = TimetableOut.model_validate(tt).model_dump()
    d["entry_count"] = entry_count
    if tt.share_token:
        d["share_url"] = f"{get_settings().frontend_url}/share/{tt.share_token}"
    return d


def _conflicts_payload(conflicts: list[Conflict]) -> list[dict]:
    order = {"major": 0, "minor": 1}
    return [c.to_dict() for c in sorted(conflicts, key=lambda c: (order[c.severity], c.type, c.day or 0, c.start or 0))]


@router.get("")
def list_timetables(access: Access = Depends(get_access), db: Session = Depends(get_db)):
    stmt = select(Timetable).where(Timetable.institution_id == access.institution_id)
    if not access.sees_drafts:
        stmt = stmt.where(Timetable.status == "published")
    tts = list(db.scalars(stmt.order_by(Timetable.created_at.desc())))
    counts = dict(
        db.execute(
            select(TimetableEntry.timetable_id, func.count())
            .where(TimetableEntry.timetable_id.in_([t.id for t in tts] or [-1]))
            .group_by(TimetableEntry.timetable_id)
        ).all()
    )
    return [_out(t, counts.get(t.id, 0)) for t in tts]


@router.post("", status_code=201)
def generate_timetable(body: GenerateIn, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    ensure_in(db, Department, body.department_id, access.institution_id, "Department")
    _require_write(access, body.department_id)
    data = InstitutionData(db, access.institution_id)
    tt = Timetable(
        institution_id=access.institution_id, department_id=body.department_id, name=body.name, term=body.term,
        status="draft", created_by_id=access.user.id, generation={}, conflict_summary={},
    )
    db.add(tt)
    db.flush()
    try:
        svc.run_generation(db, data, tt, keep_locked=False, time_limit=body.time_limit, seed=body.seed,
                           optimise=body.optimise)
    except HTTPException:
        db.rollback()
        raise
    svc.refresh_summary(db, data, tt, with_suggestions=False)
    db.commit()
    return _out(tt, len(svc.load_entries(db, tt)))


@router.get("/{timetable_id}")
def get_timetable(timetable_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    data = InstitutionData(db, access.institution_id)
    entries = svc.load_entries(db, tt)
    out = _out(tt, len(entries))
    out["options"] = view_options(data, tt, entries)
    out["can_edit"] = access.is_inst_admin or (
        access.is_admin and tt.department_id is not None and access.can_write_department(tt.department_id))
    out["scope"] = svc.scope_label(data, tt.department_id)
    return out


@router.patch("/{timetable_id}")
def rename_timetable(timetable_id: int, body: RenameIn, access: Access = Depends(get_access),
                     db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(tt, k, v)
    db.commit()
    return _out(tt)


@router.delete("/{timetable_id}", status_code=204)
def delete_timetable(timetable_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    db.delete(tt)
    db.commit()


@router.post("/{timetable_id}/regenerate")
def regenerate(timetable_id: int, body: RegenerateIn, access: Access = Depends(get_access),
               db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    data = InstitutionData(db, access.institution_id)
    svc.run_generation(db, data, tt, keep_locked=body.keep_locked, time_limit=body.time_limit, seed=body.seed)
    if tt.status == "published":
        tt.status = "draft"
        tt.published_at = None
    svc.refresh_summary(db, data, tt, with_suggestions=False)
    db.commit()
    return _out(tt, len(svc.load_entries(db, tt)))


@router.get("/{timetable_id}/view")
def timetable_view(
    timetable_id: int,
    view: str = Query("class"),
    ref: int | None = Query(None),
    access: Access = Depends(get_access),
    db: Session = Depends(get_db),
):
    tt = _tt(db, access, timetable_id)
    data = InstitutionData(db, access.institution_id)
    entries = svc.load_entries(db, tt)
    conflicts = svc.compute_conflicts(data, tt, [data.entry_view(e) for e in entries], with_suggestions=False) \
        if access.is_admin else []
    return build_view(data, tt, entries, view, ref, conflicts)


@router.get("/{timetable_id}/conflicts")
def timetable_conflicts(timetable_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    access.require_admin()
    tt = _tt(db, access, timetable_id)
    data = InstitutionData(db, access.institution_id)
    conflicts = svc.refresh_summary(db, data, tt, with_suggestions=True)
    db.commit()
    return {"summary": tt.conflict_summary, "conflicts": _conflicts_payload(conflicts),
            "unscheduled": tt.generation.get("unscheduled", [])}


def _edit_response(db: Session, data: InstitutionData, outcome: svc.EditOutcome, dry_run: bool):
    payload = {
        "ok": outcome.ok,
        "blocking": _conflicts_payload(outcome.blocking),
        "summary": summarize(outcome.conflicts),
    }
    if not outcome.ok and not dry_run:
        db.rollback()
        first = outcome.blocking[0].message if outcome.blocking else "Major scheduling conflict"
        return JSONResponse(status_code=409, content={"detail": f"Not saved: {first}", **payload})
    if outcome.entry is not None:
        db.commit()
        db.refresh(outcome.entry)
        payload["entry"] = enrich(data, outcome.entry)
    return payload


@router.patch("/{timetable_id}/entries/{entry_id}")
def move_entry(timetable_id: int, entry_id: int, body: EntryMove, access: Access = Depends(get_access),
               db: Session = Depends(get_db)):
    """Move / reassign one session. Every change is conflict-checked; a change that
    creates a major conflict is rejected with 409 and alternative free slots."""
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    entry = db.get(TimetableEntry, entry_id)
    if entry is None or entry.timetable_id != tt.id:
        raise HTTPException(404, "Session not found")
    data = InstitutionData(db, access.institution_id)
    only_lock = body.locked is not None and all(
        getattr(body, f) is None for f in ("day", "period_index", "start", "room_id", "teacher_id"))
    if only_lock and not body.dry_run:
        entry.locked = body.locked
        db.commit()
        return {"ok": True, "blocking": [], "summary": tt.conflict_summary, "entry": enrich(data, entry)}
    outcome = svc.move_entry(db, data, tt, entry, day=body.day, period_index=body.period_index,
                             start=body.start, room_id=body.room_id, teacher_id=body.teacher_id, locked=body.locked,
                             dry_run=body.dry_run)
    return _edit_response(db, data, outcome, body.dry_run)


@router.post("/{timetable_id}/entries", status_code=201)
def add_entry(timetable_id: int, body: EntryCreate, access: Access = Depends(get_access),
              db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    data = InstitutionData(db, access.institution_id)
    outcome = svc.add_entry(db, data, tt, body.assignment_id, body.day, body.period_index, body.room_id,
                            body.locked, body.dry_run)
    return _edit_response(db, data, outcome, body.dry_run)


@router.delete("/{timetable_id}/entries/{entry_id}", status_code=204)
def delete_entry(timetable_id: int, entry_id: int, access: Access = Depends(get_access),
                 db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    entry = db.get(TimetableEntry, entry_id)
    if entry is None or entry.timetable_id != tt.id:
        raise HTTPException(404, "Session not found")
    db.delete(entry)
    db.flush()
    svc.refresh_summary(db, InstitutionData(db, access.institution_id), tt, with_suggestions=False)
    db.commit()


@router.get("/{timetable_id}/entries/{entry_id}/suggestions")
def suggestions(timetable_id: int, entry_id: int, teacher_id: int | None = None, limit: int = Query(8, ge=1, le=60),
                access: Access = Depends(get_access), db: Session = Depends(get_db)):
    access.require_admin()
    tt = _tt(db, access, timetable_id)
    entry = db.get(TimetableEntry, entry_id)
    if entry is None or entry.timetable_id != tt.id:
        raise HTTPException(404, "Session not found")
    data = InstitutionData(db, access.institution_id)
    return [s.__dict__ for s in svc.entry_suggestions(db, data, tt, entry, teacher_id, limit)]


@router.get("/{timetable_id}/assignments/{assignment_id}/free-slots")
def assignment_free_slots(timetable_id: int, assignment_id: int, limit: int = Query(30, ge=1, le=60),
                          access: Access = Depends(get_access), db: Session = Depends(get_db)):
    """Free slots for placing a lecture the generator could not schedule."""
    access.require_admin()
    tt = _tt(db, access, timetable_id)
    data = InstitutionData(db, access.institution_id)
    return [s.__dict__ for s in svc.assignment_free_slots(db, data, tt, assignment_id, limit)]


@router.post("/{timetable_id}/publish")
def publish(timetable_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    data = InstitutionData(db, access.institution_id)
    conflicts = svc.publish(db, data, tt)
    if tt.status != "published":
        db.commit()  # keep the refreshed summary
        majors = [c for c in conflicts if c.severity == "major"]
        return JSONResponse(status_code=409, content={
            "detail": f"Cannot publish: {len(majors)} major conflict(s) must be resolved first",
            "blocking": _conflicts_payload(majors)})
    db.commit()
    return _out(tt)


@router.post("/{timetable_id}/unpublish")
def unpublish(timetable_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    tt.status = "draft"
    tt.published_at = None
    db.commit()
    return _out(tt)


@router.post("/{timetable_id}/share")
def share(timetable_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    if not tt.share_token:
        tt.share_token = svc.new_share_token()
        db.commit()
    return {"share_token": tt.share_token, "share_url": f"{get_settings().frontend_url}/share/{tt.share_token}"}


@router.delete("/{timetable_id}/share", status_code=204)
def unshare(timetable_id: int, access: Access = Depends(get_access), db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    _require_write(access, tt.department_id)
    tt.share_token = None
    db.commit()


def export_timetable(db: Session, data: InstitutionData, tt: Timetable, fmt: str, view: str, ref: int | None) -> Response:
    entries = svc.load_entries(db, tt)
    flat = [enrich(data, e) for e in entries]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tt.name)[:60] or "timetable"
    if fmt == "csv":
        if ref is not None:
            flat = build_view(data, tt, entries, view, ref)["entries"]
        return Response(exporters.to_csv(flat), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'})
    if view in ("institution",):
        views = [build_view(data, tt, entries, view, None)]
    elif ref is not None:
        views = [build_view(data, tt, entries, view, ref)]
    else:
        views = [build_view(data, tt, entries, view, r) for r in all_refs(data, tt, entries, view)]
    if fmt == "pdf":
        return Response(exporters.to_pdf(views, data.inst.name, tt.name), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'})
    if fmt == "xlsx":
        if ref is not None:
            flat = views[0]["entries"]
        return Response(
            exporters.to_xlsx(views, data.inst.name, tt.name, flat),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'},
        )
    raise HTTPException(422, "format must be pdf, xlsx or csv")


@router.get("/{timetable_id}/export")
def export(timetable_id: int, format: str = Query("pdf"), view: str = Query("class"), ref: int | None = None,
           access: Access = Depends(get_access), db: Session = Depends(get_db)):
    tt = _tt(db, access, timetable_id)
    data = InstitutionData(db, access.institution_id)
    return export_timetable(db, data, tt, format, view, ref)
