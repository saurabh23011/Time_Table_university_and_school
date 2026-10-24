"""Demo data: a university with two schools on different schedules, and a school.

Run:  python -m app.seed            (adds demo data if the database is empty)
      python -m app.seed --reset    (drops and recreates all tables first)

Demo logins (password for all: Demo@1234)
  superadmin@timetable.dev          Super Admin
  admin@ait.edu.in                  Institution Admin – Aryabhatta Institute of Technology
  cse.admin@ait.edu.in              Department Admin – Computer Science & Engineering
  anita.sharma@ait.edu.in           Teacher
  student.cse3a@ait.edu.in          Student – B.Tech CSE Sem 3 A
  admin@greenvalley.edu.in          Institution Admin – Green Valley Public School
  admin@sut.edu.in                  Institution Admin – Sample University of Technology (CSE only)
  hod.cse@sut.edu.in                Department Admin – CSE
  rajesh.kumar@sut.edu.in           Teacher
  student.cse3a@sut.edu.in          Student – B.Tech CSE Sem 3 A
"""
from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .models import (
    Assignment,
    ClassGroup,
    Department,
    Institution,
    Role,
    Room,
    Schedule,
    Subject,
    Teacher,
    Timetable,
    User,
)
from .security import hash_password
from .services import timetables as svc
from .services.data import InstitutionData

PASSWORD = "Demo@1234"


def _w(day, start, end):
    return {"day": day, "start": start, "end": end}


def seed_university(db: Session) -> Institution:
    inst = Institution(name="Aryabhatta Institute of Technology", code="AIT", kind="university",
                       address="Bailey Road, Patna, Bihar", soft_weights={})
    db.add(inst)
    db.flush()
    eng = Schedule(institution_id=inst.id, name="Engineering · 60-min periods", config={
        "working_days": [0, 1, 2, 3, 4], "day_start": "09:00", "day_end": "17:00", "lecture_minutes": 60,
        "periods_per_day": 7,
        "breaks": [{"name": "Tea break", "kind": "break", "after_period": 2, "minutes": 15},
                   {"name": "Lunch", "kind": "lunch", "after_period": 4, "minutes": 45}],
        "day_overrides": {},
    })
    sci = Schedule(institution_id=inst.id, name="Sciences · 50-min periods, Sat half-day", config={
        "working_days": [0, 1, 2, 3, 4, 5], "day_start": "09:30", "day_end": "16:30", "lecture_minutes": 50,
        "periods_per_day": 7,
        "breaks": [{"name": "Short break", "kind": "break", "after_period": 3, "minutes": 10},
                   {"name": "Lunch", "kind": "lunch", "after_period": 5, "minutes": 40}],
        "day_overrides": {"5": {"periods_per_day": 4}},
    })
    db.add_all([eng, sci])
    db.flush()
    inst.default_schedule_id = eng.id

    soe = Department(institution_id=inst.id, name="School of Engineering", code="SOE", kind="school", schedule_id=eng.id)
    sos = Department(institution_id=inst.id, name="School of Sciences", code="SOS", kind="school", schedule_id=sci.id)
    db.add_all([soe, sos])
    db.flush()
    cse = Department(institution_id=inst.id, name="Computer Science & Engineering", code="CSE", parent_id=soe.id)
    ece = Department(institution_id=inst.id, name="Electronics & Communication", code="ECE", parent_id=soe.id)
    phy = Department(institution_id=inst.id, name="Physics", code="PHY", parent_id=sos.id)
    mat = Department(institution_id=inst.id, name="Mathematics", code="MAT", parent_id=sos.id)
    db.add_all([cse, ece, phy, mat])
    db.flush()

    T = {}

    def teacher(key, name, dept, desig, **kw):
        t = Teacher(institution_id=inst.id, department_id=dept.id, name=name, code=key.upper(),
                    email=f"{name.split()[-2].lower() if name.startswith('Dr.') else name.split()[0].lower()}."
                          f"{name.split()[-1].lower()}@ait.edu.in",
                    designation=desig, max_per_day=kw.pop("max_per_day", 5), max_per_week=kw.pop("max_per_week", 18),
                    max_consecutive=kw.pop("max_consecutive", 3), **kw)
        db.add(t)
        T[key] = t
        return t

    teacher("as", "Dr. Anita Sharma", cse, "Professor", unavailable=[_w(4, "13:00", "17:00")],
            preferred=[_w(d, "09:00", "13:00") for d in range(5)])
    teacher("rv", "Rahul Verma", cse, "Assistant Professor")
    teacher("pk", "Priya Kumari", cse, "Assistant Professor", avoid=[_w(0, "09:00", "11:15")])
    teacher("sm", "Suresh Mishra", cse, "Associate Professor", work_start="10:00", work_end="17:00")
    teacher("ns", "Neha Singh", cse, "Assistant Professor")
    teacher("ak", "Amit Kumar", ece, "Associate Professor")
    teacher("kj", "Kavita Jha", ece, "Assistant Professor", unavailable=[_w(2, "09:00", "17:00")])
    teacher("vp", "Vikash Prasad", ece, "Lab Instructor", max_per_week=20)
    teacher("rs", "Dr. Ravi Shankar", mat, "Professor")  # shared: teaches engineering and science classes
    teacher("mt", "Meena Tiwari", mat, "Assistant Professor")
    teacher("sg", "Dr. Sanjay Gupta", phy, "Professor")
    teacher("pd", "Pooja Das", phy, "Assistant Professor")
    teacher("hn", "Harish Nair", phy, "Lab Instructor", max_per_week=20)
    teacher("el", "Elizabeth Lal", cse, "Assistant Professor (English)")
    db.flush()

    R = {}

    def room(key, name, rtype, cap, building, tags=(), dept=None, **kw):
        r = Room(institution_id=inst.id, name=name, code=key.upper(), room_type=rtype, capacity=cap,
                 building=building, tags=list(tags), department_id=dept.id if dept else None, **kw)
        db.add(r)
        R[key] = r

    for i, cap in enumerate([70, 70, 65, 65, 60, 60, 80], start=1):
        room(f"lh{i}", f"LH-{100 + i}", "classroom", cap, "Academic Block A")
    room("sh1", "Seminar Hall", "seminar_hall", 180, "Admin Block", unavailable=[_w(4, "15:00", "17:00")])
    room("cl1", "Computer Lab 1", "lab", 70, "CS Block", ["computer"], cse)
    room("cl2", "Computer Lab 2", "lab", 70, "CS Block", ["computer"], cse)
    room("el1", "Electronics Lab", "lab", 70, "EC Block", ["electronics"], ece)
    room("pl1", "Physics Lab", "lab", 60, "Science Block", ["physics"], phy)
    db.flush()

    S = {}

    def subject(code, name, dept, kind="theory", tag=None, color=None):
        s = Subject(institution_id=inst.id, department_id=dept.id, code=code, name=name, kind=kind,
                    room_type="lab" if kind == "lab" else "classroom", room_tag=tag, color=color)
        db.add(s)
        S[code] = s

    subject("MA201", "Engineering Mathematics III", mat, color="#2563eb")
    subject("CS201", "Data Structures", cse, color="#059669")
    subject("CS202", "Digital Logic Design", cse, color="#d97706")
    subject("CS203", "Object-Oriented Programming", cse, color="#7c3aed")
    subject("HS201", "Technical Communication", cse, color="#db2777")
    subject("CS201L", "Data Structures Lab", cse, "lab", "computer", "#0891b2")
    subject("CS203L", "OOP Lab", cse, "lab", "computer", "#0d9488")
    subject("CS301", "Operating Systems", cse, color="#65a30d")
    subject("CS302", "Database Systems", cse, color="#dc2626")
    subject("CS303", "Computer Networks", cse, color="#4f46e5")
    subject("CS304", "Machine Learning", cse, color="#ca8a04")
    subject("CS302L", "DBMS Lab", cse, "lab", "computer", "#9333ea")
    subject("EC201", "Signals & Systems", ece, color="#0ea5e9")
    subject("EC202", "Analog Electronics", ece, color="#f97316")
    subject("EC203", "Network Theory", ece, color="#14b8a6")
    subject("EC202L", "Analog Electronics Lab", ece, "lab", "electronics", "#a855f7")
    subject("PH101", "Mechanics", phy, color="#e11d48")
    subject("PH102", "Waves & Optics", phy, color="#3b82f6")
    subject("MA101", "Calculus", mat, color="#22c55e")
    subject("PH101L", "Physics Practical I", phy, "lab", "physics", "#eab308")
    subject("PH201", "Thermal Physics", phy, color="#8b5cf6")
    subject("PH202", "Electromagnetism", phy, color="#06b6d4")
    subject("MA201S", "Mathematical Physics", mat, color="#f43f5e")
    subject("PH201L", "Physics Practical II", phy, "lab", "physics", "#84cc16")
    db.flush()

    C = {}

    def klass(key, name, dept, program, term, section, batch, strength):
        c = ClassGroup(institution_id=inst.id, department_id=dept.id, name=name, program=program, term=term,
                       section=section, batch=batch, strength=strength)
        db.add(c)
        C[key] = c

    klass("cse3a", "B.Tech CSE · Sem 3 · A", cse, "B.Tech CSE", "Semester 3", "A", "2024–28", 62)
    klass("cse3b", "B.Tech CSE · Sem 3 · B", cse, "B.Tech CSE", "Semester 3", "B", "2024–28", 60)
    klass("cse5a", "B.Tech CSE · Sem 5 · A", cse, "B.Tech CSE", "Semester 5", "A", "2023–27", 58)
    klass("ece3a", "B.Tech ECE · Sem 3 · A", ece, "B.Tech ECE", "Semester 3", "A", "2024–28", 55)
    klass("bsc1", "B.Sc. Physics · Year 1", phy, "B.Sc. Physics (Hons)", "Year 1", None, "2025–28", 48)
    klass("bsc2", "B.Sc. Physics · Year 2", phy, "B.Sc. Physics (Hons)", "Year 2", None, "2024–27", 45)
    db.flush()

    def cur(cls, code, tch, n, block=1):
        db.add(Assignment(institution_id=inst.id, class_id=C[cls].id, subject_id=S[code].id,
                          teacher_id=T[tch].id, lectures_per_week=n, consecutive_periods=block))

    for sec, (ds, dl, oop, hs) in {"cse3a": ("as", "rv", "pk", "el"), "cse3b": ("rv", "sm", "ns", "el")}.items():
        cur(sec, "MA201", "rs" if sec == "cse3a" else "mt", 4)
        cur(sec, "CS201", ds, 4)
        cur(sec, "CS202", dl, 3)
        cur(sec, "CS203", oop, 3)
        cur(sec, "HS201", hs, 2)
        cur(sec, "CS201L", ds, 2, 2)
        cur(sec, "CS203L", oop, 2, 2)
    cur("cse5a", "CS301", "sm", 4)
    cur("cse5a", "CS302", "pk", 4)
    cur("cse5a", "CS303", "ns", 3)
    cur("cse5a", "CS304", "as", 3)
    cur("cse5a", "CS302L", "pk", 2, 2)
    cur("ece3a", "MA201", "mt", 4)
    cur("ece3a", "EC201", "ak", 4)
    cur("ece3a", "EC202", "kj", 3)
    cur("ece3a", "EC203", "ak", 3)
    cur("ece3a", "HS201", "el", 2)
    cur("ece3a", "EC202L", "vp", 4, 2)
    cur("bsc1", "PH101", "sg", 4)
    cur("bsc1", "PH102", "pd", 4)
    cur("bsc1", "MA101", "rs", 4)
    cur("bsc1", "PH101L", "hn", 4, 2)
    cur("bsc2", "PH201", "pd", 4)
    cur("bsc2", "PH202", "sg", 4)
    cur("bsc2", "MA201S", "rs", 3)
    cur("bsc2", "PH201L", "hn", 4, 2)
    db.flush()

    users = [
        ("admin@ait.edu.in", "AIT Administrator", Role.institution_admin, None, None, None),
        ("cse.admin@ait.edu.in", "CSE Department Admin", Role.department_admin, cse.id, None, None),
        ("anita.sharma@ait.edu.in", "Dr. Anita Sharma", Role.teacher, cse.id, T["as"].id, None),
        ("student.cse3a@ait.edu.in", "Aditya Raj (CSE 3A)", Role.student, cse.id, None, C["cse3a"].id),
    ]
    for email, name, role, dept, tid, cid in users:
        db.add(User(email=email, full_name=name, role=role.value, institution_id=inst.id, department_id=dept,
                    teacher_id=tid, class_id=cid, password_hash=hash_password(PASSWORD)))
    db.flush()
    return inst


def seed_school(db: Session) -> Institution:
    inst = Institution(name="Green Valley Public School", code="GVPS", kind="school",
                       address="Sasaram, Bihar", soft_weights={"subject_repeat_per_day": 14})
    db.add(inst)
    db.flush()
    sch = Schedule(institution_id=inst.id, name="School day · 45-min periods", config={
        "working_days": [0, 1, 2, 3, 4, 5], "day_start": "08:00", "day_end": "14:00", "lecture_minutes": 45,
        "periods_per_day": 7,
        "breaks": [{"name": "Short break", "kind": "break", "after_period": 2, "minutes": 15},
                   {"name": "Lunch", "kind": "lunch", "after_period": 4, "minutes": 30}],
        "day_overrides": {"5": {"periods_per_day": 4}},
    })
    db.add(sch)
    db.flush()
    inst.default_schedule_id = sch.id
    sec = Department(institution_id=inst.id, name="Secondary Wing", code="SEC", kind="wing")
    db.add(sec)
    db.flush()

    T = {}
    for key, name, desig in [
        ("en", "Ritu Srivastava", "English"), ("hi", "Manoj Pandey", "Hindi"), ("ma", "Deepak Yadav", "Mathematics"),
        ("ma2", "Shalini Roy", "Mathematics"), ("sc", "Arvind Thakur", "Science"), ("sc2", "Nisha Bharti", "Science"),
        ("ss", "Rakesh Choudhary", "Social Science"), ("cs", "Sneha Kumari", "Computer Science"),
        ("pe", "Sunil Paswan", "Physical Education"),
    ]:
        t = Teacher(institution_id=inst.id, department_id=sec.id, name=name, code=key.upper(),
                    designation=f"TGT {desig}", max_per_day=6, max_per_week=30, max_consecutive=3)
        db.add(t)
        T[key] = t
    R = []
    for i in range(1, 5):
        R.append(Room(institution_id=inst.id, name=f"Room {i}0{i}", room_type="classroom", capacity=45, building="Main"))
    R.append(Room(institution_id=inst.id, name="Science Lab", room_type="lab", capacity=45, tags=["science"]))
    R.append(Room(institution_id=inst.id, name="Computer Lab", room_type="lab", capacity=45, tags=["computer"]))
    R.append(Room(institution_id=inst.id, name="Playground", room_type="other", capacity=200))
    db.add_all(R)
    db.flush()
    S = {}
    for code, name, kind, rtype, tag in [
        ("ENG", "English", "theory", "classroom", None), ("HIN", "Hindi", "theory", "classroom", None),
        ("MAT", "Mathematics", "theory", "classroom", None), ("SCI", "Science", "theory", "classroom", None),
        ("SST", "Social Science", "theory", "classroom", None), ("SCIL", "Science Practical", "lab", "lab", "science"),
        ("CSC", "Computer Applications", "lab", "lab", "computer"), ("PE", "Physical Education", "theory", "other", None),
    ]:
        s = Subject(institution_id=inst.id, department_id=sec.id, code=code, name=name, kind=kind,
                    room_type=rtype, room_tag=tag)
        db.add(s)
        S[code] = s
    db.flush()
    plan = {
        "Grade 9 · A": ("ma", "sc"), "Grade 9 · B": ("ma2", "sc2"),
        "Grade 10 · A": ("ma", "sc"), "Grade 10 · B": ("ma2", "sc2"),
    }
    for name, (mt, st) in plan.items():
        c = ClassGroup(institution_id=inst.id, department_id=sec.id, name=name, program="CBSE",
                       term=name.split(" · ")[0], section=name[-1], batch="2026–27", strength=40)
        db.add(c)
        db.flush()
        for code, tch, n, block in [("ENG", "en", 5, 1), ("HIN", "hi", 4, 1), ("MAT", mt, 6, 1), ("SCI", st, 5, 1),
                                    ("SST", "ss", 5, 1), ("SCIL", st, 2, 2), ("CSC", "cs", 2, 2), ("PE", "pe", 2, 1)]:
            db.add(Assignment(institution_id=inst.id, class_id=c.id, subject_id=S[code].id, teacher_id=T[tch].id,
                              lectures_per_week=n, consecutive_periods=block))
    db.add(User(email="admin@greenvalley.edu.in", full_name="Green Valley Principal's Office",
                role=Role.institution_admin.value, institution_id=inst.id, password_hash=hash_password(PASSWORD)))
    db.flush()
    return inst


NEW_UNI = {"name": "Sample University of Technology", "code": "SUT", "domain": "sut.edu.in",
           "address": "Patna, Bihar"}


def seed_cse_university(db: Session) -> Institution:
    """A second university that runs only a Computer Science & Engineering department,
    on its own timings: 55-minute periods, Monday to Saturday, Saturday half-day."""
    u = NEW_UNI
    inst = Institution(name=u["name"], code=u["code"], kind="university", address=u["address"], soft_weights={})
    db.add(inst)
    db.flush()
    sch = Schedule(institution_id=inst.id, name="CSE · 55-min periods, Sat half-day", config={
        "working_days": [0, 1, 2, 3, 4, 5], "day_start": "09:15", "day_end": "17:00", "lecture_minutes": 55,
        "periods_per_day": 7,
        "breaks": [{"name": "Short break", "kind": "break", "after_period": 2, "minutes": 10},
                   {"name": "Lunch", "kind": "lunch", "after_period": 4, "minutes": 40}],
        "day_overrides": {"5": {"periods_per_day": 4}},
    })
    db.add(sch)
    db.flush()
    inst.default_schedule_id = sch.id
    cse = Department(institution_id=inst.id, name="Computer Science & Engineering", code="CSE", schedule_id=sch.id)
    db.add(cse)
    db.flush()

    T = {}
    for key, name, desig, extra in [
        ("rk", "Dr. Rajesh Kumar", "Professor & Head", {"unavailable": [_w(5, "09:00", "14:00")]}),
        ("sp", "Dr. Sunita Prasad", "Professor", {}),
        ("ar", "Abhishek Ranjan", "Assistant Professor", {}),
        ("mk", "Megha Kumari", "Assistant Professor", {}),
        ("vs", "Vivek Sinha", "Assistant Professor", {}),
        ("ps", "Pallavi Singh", "Assistant Professor", {"preferred": [_w(d, "09:15", "13:00") for d in range(6)]}),
        ("ag", "Ankit Gupta", "Associate Professor", {}),
        ("nr", "Nidhi Rai", "Assistant Professor", {"work_start": "10:00", "work_end": "17:00"}),
        ("dk", "Dr. Dinesh Kumar", "Associate Professor (Mathematics)", {}),
        ("ap", "Dr. Anjali Pandey", "Assistant Professor (Physics)", {}),
        ("ss", "Sanjeev Srivastava", "Assistant Professor (Electrical)", {}),
        ("rt", "Ritika Kashyap", "Assistant Professor (Humanities)", {}),
    ]:
        first, last = name.replace("Dr. ", "").split()[0], name.split()[-1]
        t = Teacher(institution_id=inst.id, department_id=cse.id, name=name, code=key.upper(),
                    email=f"{first.lower()}.{last.lower()}@{u['domain']}", designation=desig,
                    max_per_day=5, max_per_week=18, max_consecutive=3, **extra)
        db.add(t)
        T[key] = t
    db.flush()

    rooms = [Room(institution_id=inst.id, name=f"CR-{200 + i}", code=f"CR{200 + i}", room_type="classroom",
                  capacity=cap, building="CSE Block") for i, cap in enumerate([66, 66, 64, 64, 60, 60], start=1)]
    rooms += [
        Room(institution_id=inst.id, name="Programming Lab 1", room_type="lab", capacity=66, building="CSE Block",
             tags=["computer"]),
        Room(institution_id=inst.id, name="Programming Lab 2", room_type="lab", capacity=66, building="CSE Block",
             tags=["computer"]),
        Room(institution_id=inst.id, name="Project Lab", room_type="lab", capacity=64, building="CSE Block",
             tags=["computer"]),
        Room(institution_id=inst.id, name="AI & ML Lab", room_type="lab", capacity=64, building="Research Block",
             tags=["computer", "gpu"]),
        Room(institution_id=inst.id, name="Seminar Hall", room_type="seminar_hall", capacity=150,
             building="Admin Block", unavailable=[_w(5, "11:00", "14:00")]),
    ]
    db.add_all(rooms)
    db.flush()

    S = {}
    for code, name, kind, tag, color in [
        ("MA101", "Calculus & Linear Algebra", "theory", None, "#2563eb"),
        ("PH103", "Engineering Physics", "theory", None, "#e11d48"),
        ("EE101", "Basic Electrical Engineering", "theory", None, "#f97316"),
        ("HS101", "Professional English", "theory", None, "#db2777"),
        ("CS101", "Programming in C", "theory", None, "#059669"),
        ("CS101L", "C Programming Lab", "lab", "computer", "#0891b2"),
        ("CS102L", "IT Workshop", "lab", "computer", "#14b8a6"),
        ("MA201", "Discrete Mathematics", "theory", None, "#4f46e5"),
        ("CS201", "Data Structures", "theory", None, "#16a34a"),
        ("CS202", "Computer Organisation", "theory", None, "#d97706"),
        ("CS203", "Object-Oriented Programming with Java", "theory", None, "#7c3aed"),
        ("HS201", "Engineering Economics", "theory", None, "#be185d"),
        ("CS201L", "Data Structures Lab", "lab", "computer", "#0e7490"),
        ("CS203L", "Java Lab", "lab", "computer", "#9333ea"),
        ("CS301", "Operating Systems", "theory", None, "#65a30d"),
        ("CS302", "Database Management Systems", "theory", None, "#dc2626"),
        ("CS303", "Theory of Computation", "theory", None, "#0284c7"),
        ("CS304", "Software Engineering", "theory", None, "#ca8a04"),
        ("CS301L", "Operating Systems Lab", "lab", "computer", "#84cc16"),
        ("CS302L", "DBMS Lab", "lab", "computer", "#a855f7"),
        ("CS401", "Machine Learning", "theory", None, "#b45309"),
        ("CS402", "Cloud Computing", "theory", None, "#0ea5e9"),
        ("CS403", "Cryptography & Network Security", "theory", None, "#475569"),
        ("CS404", "Compiler Design", "theory", None, "#8b5cf6"),
        ("CS401L", "Machine Learning Lab", "lab", "gpu", "#ea580c"),
        ("CS490", "Major Project", "lab", "computer", "#15803d"),
    ]:
        s = Subject(institution_id=inst.id, department_id=cse.id, code=code, name=name, kind=kind,
                    room_type="lab" if kind == "lab" else "classroom", room_tag=tag, color=color)
        db.add(s)
        S[code] = s
    db.flush()

    C = {}
    for key, sem, sec, batch, strength in [
        ("cse1a", 1, "A", "2026–30", 64), ("cse3a", 3, "A", "2025–29", 62), ("cse3b", 3, "B", "2025–29", 60),
        ("cse5a", 5, "A", "2024–28", 60), ("cse7a", 7, "A", "2023–27", 58),
    ]:
        c = ClassGroup(institution_id=inst.id, department_id=cse.id, name=f"B.Tech CSE · Sem {sem} · {sec}",
                       program="B.Tech CSE", term=f"Semester {sem}", section=sec, batch=batch, strength=strength)
        db.add(c)
        C[key] = c
    db.flush()

    def cur(cls, code, tch, n, block=1):
        db.add(Assignment(institution_id=inst.id, class_id=C[cls].id, subject_id=S[code].id,
                          teacher_id=T[tch].id, lectures_per_week=n, consecutive_periods=block))

    for code, tch, n, block in [("MA101", "dk", 4, 1), ("PH103", "ap", 3, 1), ("EE101", "ss", 3, 1),
                                ("HS101", "rt", 2, 1), ("CS101", "ps", 4, 1), ("CS101L", "ps", 4, 2),
                                ("CS102L", "mk", 2, 2)]:
        cur("cse1a", code, tch, n, block)
    for sec, ds in (("cse3a", "ar"), ("cse3b", "mk")):
        for code, tch, n, block in [("MA201", "dk", 4, 1), ("CS201", ds, 4, 1), ("CS202", "ag", 3, 1),
                                    ("CS203", "vs", 3, 1), ("HS201", "rt", 2, 1), ("CS201L", ds, 2, 2),
                                    ("CS203L", "vs", 2, 2)]:
            cur(sec, code, tch, n, block)
    for code, tch, n, block in [("CS301", "rk", 4, 1), ("CS302", "sp", 4, 1), ("CS303", "ps", 3, 1),
                                ("CS304", "ag", 3, 1), ("CS301L", "nr", 2, 2), ("CS302L", "sp", 2, 2)]:
        cur("cse5a", code, tch, n, block)
    for code, tch, n, block in [("CS401", "rk", 3, 1), ("CS402", "nr", 3, 1), ("CS403", "nr", 3, 1),
                                ("CS404", "sp", 3, 1), ("CS401L", "rk", 2, 2), ("CS490", "nr", 4, 2)]:
        cur("cse7a", code, tch, n, block)
    db.flush()

    d = u["domain"]
    for email, name, role, dept, tid, cid in [
        (f"admin@{d}", f"{u['code']} Administrator", Role.institution_admin, None, None, None),
        (f"hod.cse@{d}", "Head of Department, CSE", Role.department_admin, cse.id, None, None),
        (f"rajesh.kumar@{d}", "Dr. Rajesh Kumar", Role.teacher, cse.id, T["rk"].id, None),
        (f"student.cse3a@{d}", "Ananya Kumari (CSE 3A)", Role.student, cse.id, None, C["cse3a"].id),
    ]:
        db.add(User(email=email, full_name=name, role=role.value, institution_id=inst.id, department_id=dept,
                    teacher_id=tid, class_id=cid, password_hash=hash_password(PASSWORD)))
    db.flush()
    return inst


def generate_demo_timetable(db: Session, inst: Institution, name: str, publish: bool = True) -> Timetable:
    data = InstitutionData(db, inst.id)
    tt = Timetable(institution_id=inst.id, name=name, term="Odd Semester 2026–27" if inst.kind != "school"
                   else "Session 2026–27", status="draft", generation={}, conflict_summary={})
    db.add(tt)
    db.flush()
    svc.run_generation(db, data, tt, keep_locked=False, time_limit=12, seed=7)
    svc.refresh_summary(db, data, tt, with_suggestions=False)
    if publish:
        svc.publish(db, data, tt)
    return tt


def run(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        todo: list[tuple[Institution, str]] = []
        if db.scalar(select(User).limit(1)) is None or reset:
            db.add(User(email="superadmin@timetable.dev", full_name="Platform Super Admin",
                        role=Role.super_admin.value, password_hash=hash_password(PASSWORD)))
            todo += [(seed_university(db), "Institute timetable – Odd Semester"),
                     (seed_school(db), "School timetable 2026–27")]
        # added later, so it is also created in databases that were seeded before it existed
        if db.scalar(select(Institution).where(Institution.code == NEW_UNI["code"])) is None:
            todo.append((seed_cse_university(db), "CSE timetable – Odd Semester"))
        if not todo:
            print("Database already has the demo data – nothing to add (use --reset to start over).")
            return
        db.commit()
        for inst, name in todo:
            tt = generate_demo_timetable(db, inst, name)
            db.commit()
            g = tt.generation
            print(f"{inst.name}: {g['stats']['placed']}/{g['stats']['sessions']} sessions placed, "
                  f"status={tt.status}, conflicts={tt.conflict_summary}")
    print(f"Seed complete. Log in with any demo account, password: {PASSWORD}")


if __name__ == "__main__":
    run(reset="--reset" in sys.argv)
