"""Engine-level tests: hard constraints are never violated."""
from collections import Counter, defaultdict

import pytest

from app.scheduler import (
    AssignmentReq,
    ClassInfo,
    EntryView,
    ExternalBusy,
    Problem,
    RoomInfo,
    SessionReq,
    TeacherInfo,
    ValidationContext,
    Window,
    build_grid,
    detect_conflicts,
    generate,
    has_major,
)
from app.scheduler.timegrid import DEFAULT_SCHEDULE, ScheduleConfigError, parse_hhmm

UNIV = DEFAULT_SCHEDULE
SCHOOL = {
    "working_days": [0, 1, 2, 3, 4, 5],
    "day_start": "08:00",
    "day_end": "14:00",
    "lecture_minutes": 45,
    "periods_per_day": 7,
    "breaks": [{"name": "Recess", "kind": "lunch", "after_period": 4, "minutes": 30}],
    "day_overrides": {"5": {"periods_per_day": 4}},
}


def assert_hard_ok(problem: Problem, placements):
    sessions = {s.key: s for s in problem.sessions}
    seen = defaultdict(list)
    for p in placements:
        s = sessions[p.session_key]
        for res in (("t", s.teacher_id), ("c", s.class_id), ("r", p.room_id)):
            for (d, a, b) in seen[res]:
                assert not (d == p.day and a < p.end and p.start < b), f"overlap on {res}"
            seen[res].append((p.day, p.start, p.end))
        room = problem.rooms[p.room_id]
        assert room.room_type == s.room_type or s.room_type == "any"
        assert room.capacity >= problem.classes[s.class_id].strength
        assert problem.teachers[s.teacher_id].is_available(p.day, p.start, p.end)
        assert problem.classes[s.class_id].grid.block(p.day, p.period_index, s.length) == (p.start, p.end)
    for ext in problem.external:
        for p in placements:
            s = sessions[p.session_key]
            hit = (ext.kind == "teacher" and s.teacher_id == ext.ref_id) or (
                ext.kind == "room" and p.room_id == ext.ref_id)
            if hit:
                assert not (ext.day == p.day and ext.start < p.end and p.start < ext.end)


def make_problem(n_classes=6, seed_unavail=True):
    grid = build_grid(UNIV)
    classes = {i: ClassInfo(i, f"CSE-{i}", 55, grid) for i in range(1, n_classes + 1)}
    teachers = {i: TeacherInfo(i, f"T{i}", max_per_day=5) for i in range(1, 11)}
    if seed_unavail:
        teachers[1].unavailable = [Window(0, 0, 24 * 60)]  # never on Monday
        teachers[2].work_start = parse_hhmm("10:00")
        teachers[3].avoid = [Window(4, 0, 24 * 60)]
    rooms = {i: RoomInfo(i, f"R{i}", "classroom", 60) for i in range(1, 6)}
    rooms[6] = RoomInfo(6, "Lab-1", "lab", 60, frozenset({"computer"}))
    rooms[7] = RoomInfo(7, "Lab-2", "lab", 60, frozenset({"computer"}))
    sessions = []
    subjects = [("Maths", 4, 1), ("Physics", 3, 1), ("Chem", 3, 1), ("English", 2, 1), ("DSA", 4, 1)]
    for cid in classes:
        for sj, (name, per_week, length) in enumerate(subjects):
            teacher = ((cid + sj) % 10) + 1
            aid = cid * 100 + sj
            for k in range(per_week):
                sessions.append(SessionReq(f"{aid}-{k}", aid, cid, sj, name, teacher, length))
        lab_aid = cid * 100 + 9
        sessions.append(SessionReq(f"{lab_aid}-0", lab_aid, cid, 9, "DSA Lab", ((cid + 7) % 10) + 1, 2, "lab", "computer"))
    return Problem(classes, teachers, rooms, sessions)


def test_grid_breaks_and_overrides():
    g = build_grid(SCHOOL)
    assert g.days == [0, 1, 2, 3, 4, 5]
    assert len(g.periods[0]) == 7 and len(g.periods[5]) == 4
    p4, p5 = g.periods[0][3], g.periods[0][4]
    assert p5.start - p4.end == 30  # recess
    assert g.block(0, 3, 2) is None  # a double period cannot straddle the recess
    assert g.block(0, 0, 2) == (480, 570)


def test_grid_rejects_overflowing_day():
    with pytest.raises(ScheduleConfigError):
        build_grid({**UNIV, "periods_per_day": 9})


def test_generates_complete_conflict_free_timetable():
    problem = make_problem()
    res = generate(problem, time_limit=8, seed=1)
    assert res.complete, [u.reason for u in res.unscheduled]
    assert len(res.placements) == len(problem.sessions)
    assert_hard_ok(problem, res.placements)
    # weekly counts preserved
    need = Counter(s.assignment_id for s in problem.sessions)
    got = Counter(int(p.session_key.split("-")[0]) for p in res.placements)
    assert need == got
    # labs only in labs, never across lunch
    sessions = {s.key: s for s in problem.sessions}
    for p in res.placements:
        if sessions[p.session_key].room_type == "lab":
            assert problem.rooms[p.room_id].room_type == "lab"
    # the soft preference to avoid Friday for T3 should usually be honoured
    t3_friday = [p for p in res.placements if sessions[p.session_key].teacher_id == 3 and p.day == 4]
    assert len(t3_friday) <= 1


def test_teacher_daily_limit_is_hard():
    problem = make_problem()
    res = generate(problem, time_limit=6, seed=3)
    sessions = {s.key: s for s in problem.sessions}
    per_day = Counter()
    for p in res.placements:
        s = sessions[p.session_key]
        per_day[(s.teacher_id, p.day)] += s.length
    assert max(per_day.values()) <= 5


def test_cross_schedule_teacher_clash_is_prevented():
    """A teacher shared by a university dept (60-min) and a school wing (45-min)."""
    g1, g2 = build_grid(UNIV), build_grid(SCHOOL)
    classes = {1: ClassInfo(1, "BSc-1", 40, g1), 2: ClassInfo(2, "Grade-9", 40, g2)}
    teachers = {1: TeacherInfo(1, "Shared")}
    rooms = {1: RoomInfo(1, "R1", "classroom", 50), 2: RoomInfo(2, "R2", "classroom", 50)}
    sessions = [SessionReq(f"a{c}-{k}", c, c, c, "Maths", 1) for c in (1, 2) for k in range(12)]
    problem = Problem(classes, teachers, rooms, sessions)
    res = generate(problem, time_limit=5, seed=2)
    assert res.complete
    assert_hard_ok(problem, res.placements)


def test_external_commitments_are_respected():
    problem = make_problem(n_classes=2, seed_unavail=False)
    # T2 and room 1 are busy all Monday in another department's published timetable
    problem.external = [ExternalBusy("teacher", 2, 0, 0, 1440, "ECE-2A"), ExternalBusy("room", 1, 0, 0, 1440, "ECE")]
    res = generate(problem, time_limit=5, seed=4)
    assert res.complete
    assert_hard_ok(problem, res.placements)


def test_impossible_lab_is_reported_with_reason():
    problem = make_problem(n_classes=1)
    problem.rooms = {k: v for k, v in problem.rooms.items() if v.room_type != "lab"}
    res = generate(problem, time_limit=3, seed=1)
    assert not res.complete
    assert len(res.unscheduled) == 1
    assert "No lab" in res.unscheduled[0].reason


def _ctx_for_example():
    grid = build_grid(UNIV)
    classes = {1: ClassInfo(1, "Class A", 40, grid), 2: ClassInfo(2, "Class B", 40, grid)}
    teachers = {1: TeacherInfo(1, "Teacher A"), 2: TeacherInfo(2, "Teacher B")}
    rooms = {1: RoomInfo(1, "R101", "classroom", 50), 2: RoomInfo(2, "R102", "classroom", 50)}
    assignments = {
        11: AssignmentReq(11, 1, 1, "Mathematics", 1, 1),
        12: AssignmentReq(12, 1, 2, "Physics", 1, 1),
        21: AssignmentReq(21, 2, 2, "Physics", 2, 1),
        22: AssignmentReq(22, 2, 1, "Mathematics", 1, 1),
    }
    return ValidationContext(classes, teachers, rooms, assignments)


def test_spec_example_teacher_conflict_detected_with_suggestions():
    ctx = _ctx_for_example()
    p = ctx.classes[1].grid.periods[0]
    entries = [
        EntryView(1, 1, 1, "Mathematics", 1, 1, 0, p[0].start, p[0].end, 1, 11),  # 9-10 A maths T-A
        EntryView(2, 2, 2, "Physics", 2, 2, 0, p[0].start, p[0].end, 1, 21),  # 9-10 B physics T-B
        EntryView(3, 1, 2, "Physics", 1, 1, 0, p[1].start, p[1].end, 1, 12),  # 10-11 A physics T-A
        EntryView(4, 2, 1, "Mathematics", 1, 2, 0, p[1].start, p[1].end, 1, 22),  # 10-11 B maths T-A  ❌
    ]
    conflicts = detect_conflicts(ctx, entries)
    teacher = [c for c in conflicts if c.type == "teacher_conflict"]
    assert len(teacher) == 1 and set(teacher[0].entry_ids) == {3, 4}
    assert "Teacher A" in teacher[0].message
    assert teacher[0].suggestions, "should propose free alternative slots"
    s = teacher[0].suggestions[0]
    # the suggested slot really is free for class B, Teacher A and the room
    fixed = [e for e in entries if e.id != 4] + [EntryView(4, 2, 1, "Mathematics", 1, s.room_id, s.day, s.start, s.end, 1, 22)]
    assert not has_major(detect_conflicts(ctx, fixed, with_suggestions=False))


def test_room_and_class_conflicts_and_lab_mismatch():
    ctx = _ctx_for_example()
    ctx.rooms[3] = RoomInfo(3, "Chem Lab", "lab", 50)
    ctx.assignments[13] = AssignmentReq(13, 1, 3, "Chem Lab", 2, 2, 2, "lab")
    p = ctx.classes[1].grid.periods[0]
    entries = [
        EntryView(1, 1, 1, "Mathematics", 1, 1, 0, p[0].start, p[0].end, 1, 11),
        EntryView(2, 2, 2, "Physics", 2, 1, 0, p[0].start, p[0].end, 1, 21),  # same room R101
        EntryView(3, 1, 2, "Physics", 2, 2, 0, p[0].start, p[0].end, 1, 12),  # class A twice + T-B twice
        EntryView(5, 1, 3, "Chem Lab", 2, 2, 1, p[0].start, p[1].end, 2, 13),  # lab in a classroom
    ]
    types = Counter(c.type for c in detect_conflicts(ctx, entries, with_suggestions=False))
    assert types["room_conflict"] >= 1
    assert types["class_conflict"] == 1
    assert types["teacher_conflict"] == 1
    assert types["room_type_mismatch"] == 1
    assert types["lecture_count"] >= 1  # e.g. maths for class B is missing


def test_suggestions_target_the_edited_session():
    ctx = _ctx_for_example()
    p = ctx.classes[1].grid.periods[0]
    # entry 9 (low id) is being moved onto entry 20's slot; suggestions must be for entry 9
    entries = [
        EntryView(9, 1, 1, "Mathematics", 1, 1, 0, p[1].start, p[1].end, 1, 11),
        EntryView(20, 2, 1, "Mathematics", 1, 2, 0, p[1].start, p[1].end, 1, 22),
    ]
    clash = next(c for c in detect_conflicts(ctx, entries, focus_entry_id=9) if c.type == "teacher_conflict")
    assert clash.entry_ids[-1] == 20
    s = clash.suggestions[0]
    moved = [EntryView(9, 1, 1, "Mathematics", 1, s.room_id, s.day, s.start, s.end, 1, 11), entries[1]]
    assert not has_major(detect_conflicts(ctx, moved, with_suggestions=False))
