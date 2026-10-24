"""End-to-end API tests against the demo data."""
from .conftest import login


def _ids(client, h, iid, resource):
    return {x["name"]: x for x in client.get(f"/api/institutions/{iid}/{resource}", headers=h).json()}


def test_login_and_me(client, admin):
    h, user = admin
    assert user["role"] == "institution_admin"
    me = client.get("/api/auth/me", headers=h).json()
    assert me["institution"]["code"] == "AIT"
    assert client.post("/api/auth/login", json={"email": "admin@ait.edu.in", "password": "nope"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_dashboard(client, admin, ait):
    h, _ = admin
    d = client.get(f"/api/institutions/{ait}/dashboard", headers=h).json()
    t = d["totals"]
    assert t["teachers"] == 14 and t["classes"] == 6 and t["laboratories"] == 4
    assert t["timetables"] >= 1 and t["major_conflicts"] == 0
    assert d["teacher_workload"] and d["room_utilization"]
    assert {x["name"] for x in d["daily_load"]} >= {"Mon", "Fri"}


def test_tenant_isolation(client, ait):
    h, _ = login(client, "admin@greenvalley.edu.in")
    assert client.get(f"/api/institutions/{ait}/teachers", headers=h).status_code == 403
    insts = client.get("/api/institutions", headers=h).json()
    assert len(insts) == 1 and insts[0]["code"] == "GVPS"
    sh, _ = login(client, "superadmin@timetable.dev")
    assert len(client.get("/api/institutions", headers=sh).json()) == 2


def test_role_permissions(client, admin, ait):
    sh, _ = login(client, "student.cse3a@ait.edu.in")
    assert client.post(f"/api/institutions/{ait}/teachers", headers=sh, json={"name": "X"}).status_code == 403
    th, _ = login(client, "anita.sharma@ait.edu.in")
    assert client.post(f"/api/institutions/{ait}/rooms", headers=th, json={"name": "X"}).status_code == 403

    dh, dept_admin = login(client, "cse.admin@ait.edu.in")
    depts = _ids(client, admin[0], ait, "departments")
    cse, ece = depts["Computer Science & Engineering"]["id"], depts["Electronics & Communication"]["id"]
    ok = client.post(f"/api/institutions/{ait}/classes", headers=dh,
                     json={"name": "B.Tech CSE · Sem 7 · A", "department_id": cse, "strength": 50})
    assert ok.status_code == 201, ok.text
    no = client.post(f"/api/institutions/{ait}/classes", headers=dh,
                     json={"name": "ECE intruder", "department_id": ece, "strength": 50})
    assert no.status_code == 403
    # department admins cannot touch institution-level rooms or schedules
    assert client.post(f"/api/institutions/{ait}/rooms", headers=dh, json={"name": "R"}).status_code == 403
    # nor generate an institution-wide timetable
    assert client.post(f"/api/institutions/{ait}/timetables", headers=dh,
                       json={"name": "all", "time_limit": 2}).status_code == 403
    client.delete(f"/api/institutions/{ait}/classes/{ok.json()['id']}", headers=dh)


def test_teacher_updates_own_availability(client):
    th, user = login(client, "anita.sharma@ait.edu.in")
    r = client.put("/api/auth/me/availability", headers=th,
                   json={"unavailable": [{"day": 4, "start": "13:00", "end": "17:00"}]})
    assert r.status_code == 200 and r.json()["id"] == user["teacher_id"]
    bad = client.put("/api/auth/me/availability", headers=th,
                     json={"unavailable": [{"day": 4, "start": "15:00", "end": "13:00"}]})
    assert bad.status_code == 422


def test_schedule_validation_and_preview(client, admin, ait):
    h, _ = admin
    bad = {"name": "Too long", "config": {"working_days": [0], "day_start": "09:00", "day_end": "12:00",
                                          "lecture_minutes": 60, "periods_per_day": 5, "breaks": []}}
    assert client.post(f"/api/institutions/{ait}/schedules", headers=h, json=bad).status_code == 422
    prev = client.post(f"/api/institutions/{ait}/schedules/preview", headers=h, json={
        "working_days": [0, 5], "day_start": "08:00", "day_end": "13:00", "lecture_minutes": 45,
        "periods_per_day": 6, "breaks": [{"name": "Lunch", "kind": "lunch", "after_period": 3, "minutes": 30}],
        "day_overrides": {"5": {"periods_per_day": 3}},
    }).json()
    mon, sat = prev["days"]
    assert [i["type"] for i in mon["items"]].count("period") == 6
    assert [i["type"] for i in sat["items"]].count("period") == 3
    assert any(i["type"] == "lunch" and i["time"] == "10:15–10:45" for i in mon["items"])


def _first_published(client, h, iid):
    return next(t for t in client.get(f"/api/institutions/{iid}/timetables", headers=h).json() if t["status"] == "published")


def test_views(client, admin, ait):
    h, _ = admin
    tt = _first_published(client, h, ait)
    full = client.get(f"/api/institutions/{ait}/timetables/{tt['id']}", headers=h).json()
    opts = full["options"]
    base = f"/api/institutions/{ait}/timetables/{tt['id']}/view"
    cls = client.get(base, headers=h, params={"view": "class", "ref": opts["classes"][0]["id"]}).json()
    assert cls["kind"] == "grid" and cls["entries"] and any(s["kind"] == "lunch" for s in cls["slots"])
    for kind, key in (("teacher", "teachers"), ("room", "rooms"), ("lab", "labs"), ("department", "departments"),
                      ("school", "schools")):
        r = client.get(base, headers=h, params={"view": kind, "ref": opts[key][0]["id"]})
        assert r.status_code == 200, (kind, r.text)
    inst = client.get(base, headers=h, params={"view": "institution"}).json()
    assert inst["kind"] == "master" and len(inst["rows"]) == len(opts["classes"])
    # sciences (6 days) and engineering (5 days) are mixed in the institution view
    assert len(inst["days"]) == 6
    # students can read published timetables but not see drafts
    sh, _ = login(client, "student.cse3a@ait.edu.in")
    assert client.get(base, headers=sh, params={"view": "class", "ref": opts["classes"][0]["id"]}).status_code == 200


def test_generate_edit_conflicts_publish(client, ait):
    dh, _ = login(client, "cse.admin@ait.edu.in")
    ah, _ = login(client, "admin@ait.edu.in")
    depts = _ids(client, ah, ait, "departments")
    cse = depts["Computer Science & Engineering"]["id"]
    r = client.post(f"/api/institutions/{ait}/timetables", headers=dh,
                    json={"name": "CSE draft", "department_id": cse, "time_limit": 4, "seed": 1})
    assert r.status_code == 201, r.text
    tt = r.json()
    assert tt["status"] == "draft" and tt["generation"]["complete"]
    assert tt["conflict_summary"]["major"] == 0
    tid = tt["id"]
    base = f"/api/institutions/{ait}/timetables/{tid}"

    # teachers/students cannot see drafts
    th, _ = login(client, "anita.sharma@ait.edu.in")
    assert client.get(base, headers=th).status_code == 404

    # the shared maths teacher's published science classes are external commitments: no clashes
    conf = client.get(f"{base}/conflicts", headers=dh).json()
    assert conf["summary"]["major"] == 0

    # --- the spec example: move a lecture onto a slot where its teacher is already teaching
    view = client.get(f"{base}/view", headers=dh, params={"view": "institution"}).json()
    entries = view["entries"]
    a = next(e for e in entries if e["length"] == 1)
    clash = next(e for e in entries if e["teacher_id"] == a["teacher_id"] and e["id"] != a["id"]
                 and e["class_id"] != a["class_id"] and e["length"] == 1)
    move = {"day": clash["day"], "period_index": clash["period_index"]}
    dry = client.patch(f"{base}/entries/{a['id']}", headers=dh, json={**move, "dry_run": True}).json()
    assert dry["ok"] is False
    assert any(c["type"] == "teacher_conflict" for c in dry["blocking"])
    rej = client.patch(f"{base}/entries/{a['id']}", headers=dh, json=move)
    assert rej.status_code == 409
    body = rej.json()
    assert "Not saved" in body["detail"]
    sugg = next(c for c in body["blocking"] if c["type"] == "teacher_conflict")["suggestions"]
    assert sugg, "conflict should come with alternative free slots"

    # apply a suggested slot through the suggestions endpoint -> saved and pinned
    options = client.get(f"{base}/entries/{a['id']}/suggestions", headers=dh).json()
    s = options[0]
    ok = client.patch(f"{base}/entries/{a['id']}", headers=dh,
                      json={"day": s["day"], "period_index": s["period_index"], "room_id": s["room_id"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["entry"]["locked"] is True
    assert ok.json()["entry"]["day"] == s["day"]

    # a lab can't be moved into an ordinary classroom
    lab = next(e for e in entries if e["subject_kind"] == "lab")
    classroom = next(x for x in _ids(client, ah, ait, "rooms").values() if x["room_type"] == "classroom")
    bad = client.patch(f"{base}/entries/{lab['id']}", headers=dh, json={"room_id": classroom["id"]})
    assert bad.status_code == 409
    assert any(c["type"] == "room_type_mismatch" for c in bad.json()["blocking"])

    # regenerate keeps the pinned lecture where it was put
    rg = client.post(f"{base}/regenerate", headers=dh, json={"keep_locked": True, "time_limit": 3, "seed": 2})
    assert rg.status_code == 200 and rg.json()["generation"]["locked_kept"] == 1
    after = client.get(f"{base}/view", headers=dh, params={"view": "institution"}).json()["entries"]
    pinned = [e for e in after if e["locked"]]
    assert len(pinned) == 1 and pinned[0]["day"] == s["day"] and pinned[0]["start"] == s["start"]

    # make the timetable invalid behind its back: the teacher becomes unavailable at that time
    teacher_id = pinned[0]["teacher_id"]
    t = client.get(f"/api/institutions/{ait}/teachers/{teacher_id}", headers=ah).json()
    win = {"day": pinned[0]["day"], "start": pinned[0]["time"].split("–")[0], "end": pinned[0]["time"].split("–")[1]}
    client.patch(f"/api/institutions/{ait}/teachers/{teacher_id}", headers=ah,
                 json={"unavailable": t["unavailable"] + [win]})
    pub = client.post(f"{base}/publish", headers=dh)
    assert pub.status_code == 409
    assert any(c["type"] == "teacher_availability" for c in pub.json()["blocking"])
    client.patch(f"/api/institutions/{ait}/teachers/{teacher_id}", headers=ah, json={"unavailable": t["unavailable"]})
    pub = client.post(f"{base}/publish", headers=dh)
    assert pub.status_code == 200 and pub.json()["status"] == "published"

    # publishing CSE archives nothing outside CSE but supersedes the institute one for CSE classes
    statuses = {x["name"]: x["status"] for x in client.get(f"/api/institutions/{ait}/timetables", headers=ah).json()}
    assert statuses["CSE draft"] == "published"
    assert statuses["Institute timetable – Odd Semester"] == "archived"


def test_add_and_delete_entry_updates_counts(client, admin, ait):
    h, _ = admin
    tt = next(t for t in client.get(f"/api/institutions/{ait}/timetables", headers=h).json() if t["status"] == "published")
    base = f"/api/institutions/{ait}/timetables/{tt['id']}"
    entries = client.get(f"{base}/view", headers=h, params={"view": "institution"}).json()["entries"]
    victim = next(e for e in entries if e["length"] == 1)
    assert client.delete(f"{base}/entries/{victim['id']}", headers=h).status_code == 204
    conf = client.get(f"{base}/conflicts", headers=h).json()
    assert any(c["type"] == "lecture_count" for c in conf["conflicts"])
    # put it back where it was
    r = client.post(f"{base}/entries", headers=h, json={
        "assignment_id": victim["assignment_id"], "day": victim["day"], "period_index": victim["period_index"],
        "room_id": victim["room_id"]})
    assert r.status_code == 201, r.text
    conf = client.get(f"{base}/conflicts", headers=h).json()
    assert conf["summary"]["total"] == 0


def test_exports_and_share_link(client, admin, ait):
    h, _ = admin
    tt = _first_published(client, h, ait)
    base = f"/api/institutions/{ait}/timetables/{tt['id']}"
    pdf = client.get(f"{base}/export", headers=h, params={"format": "pdf", "view": "class"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xl = client.get(f"{base}/export", headers=h, params={"format": "xlsx", "view": "teacher"})
    assert xl.status_code == 200 and xl.content[:2] == b"PK"
    inst_pdf = client.get(f"{base}/export", headers=h, params={"format": "pdf", "view": "institution"})
    assert inst_pdf.content.startswith(b"%PDF")
    csv = client.get(f"{base}/export", headers=h, params={"format": "csv"})
    assert csv.text.lstrip("﻿").startswith("day,day_name,start,end")

    share = client.post(f"{base}/share", headers=h).json()
    token = share["share_token"]
    assert share["share_url"].endswith(f"/share/{token}")
    pub = client.get(f"/api/public/share/{token}").json()
    assert pub["name"] == tt["name"] and pub["options"]["classes"]
    v = client.get(f"/api/public/share/{token}/view",
                   params={"view": "class", "ref": pub["options"]["classes"][0]["id"]})
    assert v.status_code == 200 and v.json()["entries"]
    assert client.get(f"/api/public/share/{token}/export", params={"format": "pdf"}).content.startswith(b"%PDF")
    client.delete(f"{base}/share", headers=h)
    assert client.get(f"/api/public/share/{token}").status_code == 404


def test_cannot_delete_used_teacher(client, admin, ait):
    h, _ = admin
    t = next(iter(_ids(client, h, ait, "teachers").values()))
    r = client.delete(f"/api/institutions/{ait}/teachers/{t['id']}", headers=h)
    assert r.status_code == 409 and "inactive" in r.json()["detail"]


def test_super_admin_creates_institution_and_admin(client):
    sh, _ = login(client, "superadmin@timetable.dev")
    r = client.post("/api/institutions", headers=sh,
                    json={"name": "Nalanda College", "code": "NLC", "kind": "college"})
    assert r.status_code == 201
    iid = r.json()["id"]
    assert r.json()["default_schedule_id"]
    u = client.post(f"/api/institutions/{iid}/users", headers=sh, json={
        "email": "admin@nalanda.edu", "full_name": "Nalanda Admin", "password": "Secret@123",
        "role": "institution_admin"})
    assert u.status_code == 201
    nh, _ = login(client, "admin@nalanda.edu", "Secret@123")
    assert client.get(f"/api/institutions/{iid}/dashboard", headers=nh).json()["totals"]["teachers"] == 0


def test_move_by_start_minute_and_free_slots(client, admin, ait):
    h, _ = admin
    tt = _first_published(client, h, ait)
    base = f"/api/institutions/{ait}/timetables/{tt['id']}"
    entries = client.get(f"{base}/view", headers=h, params={"view": "institution"}).json()["entries"]
    e = next(x for x in entries if x["length"] == 1)
    free = client.get(f"{base}/entries/{e['id']}/suggestions", headers=h, params={"limit": 60}).json()
    assert free
    target = free[-1]
    r = client.patch(f"{base}/entries/{e['id']}", headers=h,
                     json={"day": target["day"], "start": target["start"], "room_id": target["room_id"], "dry_run": True})
    assert r.status_code == 200 and r.json()["ok"] is True
    bad = client.patch(f"{base}/entries/{e['id']}", headers=h, json={"day": target["day"], "start": 7})
    assert bad.status_code == 422
    # free slots for placing a curriculum line, and they really are free
    slots = client.get(f"{base}/assignments/{e['assignment_id']}/free-slots", headers=h).json()
    assert slots
    s = slots[0]
    chk = client.post(f"{base}/entries", headers=h, json={
        "assignment_id": e["assignment_id"], "day": s["day"], "period_index": s["period_index"],
        "room_id": s["room_id"], "dry_run": True})
    assert chk.status_code == 201 and chk.json()["ok"] is True
