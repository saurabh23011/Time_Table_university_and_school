# Timetable Register

A multi-institution timetable management system for universities, colleges and schools. Each institution configures its own working hours, departments, teachers, rooms, subjects, classes and curriculum, then generates a conflict-free weekly timetable automatically, edits it with live conflict checks, publishes it, and exports or shares it.

- **Backend:** Python, FastAPI, SQLAlchemy 2, PostgreSQL, Alembic
- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4
- **Scheduler:** constraint-satisfaction search (backtracking + MRV + forward checking) with repair and simulated-annealing optimisation of soft constraints
- **Auth:** JWT with five roles (super admin, institution admin, department admin, teacher, student)

---

## Quick start (Docker)

```bash
docker compose up --build
```

- App: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs

The backend applies migrations and loads demo data on first start (`SEED_DEMO=true`). Set `SEED_DEMO=false` to start empty.

### Demo accounts (password `Demo@1234`)

| Email | Role |
|---|---|
| superadmin@timetable.dev | Super admin, all institutions |
| admin@ait.edu.in | Institution admin, Aryabhatta Institute of Technology |
| cse.admin@ait.edu.in | Department admin, Computer Science & Engineering |
| anita.sharma@ait.edu.in | Teacher |
| student.cse3a@ait.edu.in | Student, B.Tech CSE Sem 3 A |
| admin@greenvalley.edu.in | Institution admin, Green Valley Public School |

The demo university has two schools on **different schedules** (Engineering: 60‑minute periods Mon–Fri; Sciences: 50‑minute periods with a Saturday half-day) and a mathematics teacher shared between them, so cross-schedule conflict detection is exercised from the start. The demo school runs 45‑minute periods Mon–Sat.

## Running without Docker

**Backend** (Python 3.11+, PostgreSQL 14+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # edit DATABASE_URL / SECRET_KEY, then export the variables
export DATABASE_URL=postgresql+psycopg://timetable:timetable@localhost:5432/timetable
alembic upgrade head
python -m app.seed              # optional demo data (python -m app.seed --reset to start over)
uvicorn app.main:app --reload --port 8000
```

For a quick local trial without PostgreSQL you can use SQLite: `export DATABASE_URL=sqlite:///./timetable.db AUTO_CREATE_TABLES=true`.

**Frontend** (Node 20+):

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev                     # or: npm run build && npm start
```

**Tests:**

```bash
cd backend && pytest            # SQLite by default; set DATABASE_URL to run against PostgreSQL
```

---

## How the requirements are covered

| # | Requirement | Where |
|---|---|---|
| 1 | Multiple institutions, each fully separate | `institution_id` tenant key on every table; `Access` checks in `app/security.py` |
| 2 | Teachers, subject/class assignment, availability | Teachers page; `unavailable` (hard), `preferred` / `avoid` (soft), working hours, daily/weekly limits |
| 3 | Classes, sections, semesters, batches; lectures per week | Classes page; Curriculum page (`lectures_per_week`, `consecutive_periods` for double labs) |
| 4 | Rooms, labs, halls with capacity and type | Rooms & labs page; room type, seats, feature tags (e.g. `computer`), unavailable windows |
| 5 | Automatic generation with all hard rules | `app/scheduler/engine.py` (see below) |
| 6 | Custom time configuration per institution / school / department / class | Working hours page with live preview; breaks, lunch, per-day overrides; inheritance class → department → school → institution |
| 7 | Conflict detection with explanations and alternative slots | `app/scheduler/conflicts.py`; Conflicts panel; every rejected edit lists free alternatives |
| 8 | Views: university, school, department, class, teacher, room, lab | View tabs on the timetable page; institution/school/department views are a time-scaled timeline so mixed period lengths line up |
| 9 | Manual editing with automatic re-checks; no saving major conflicts | Drag-and-drop, change room, substitute teacher, pin, remove, place unscheduled; server returns 409 with alternatives |
| 10 | Roles and permissions | Table below |
| 11 | PDF, Excel/CSV, print, share link | Export menu (per view or every class/teacher/room), print stylesheet, revocable read-only links at `/share/<token>` |
| 12 | Dashboard | Totals, conflicts by type, teacher workload vs. limits, room utilisation, periods per day |

### Roles and permissions

| Action | Super admin | Institution admin | Department admin | Teacher | Student |
|---|---|---|---|---|---|
| Create institutions | ✓ | | | | |
| Working hours, departments, rooms | ✓ | ✓ | read | | |
| Teachers, subjects, classes, curriculum | ✓ | ✓ | own department subtree | read | read |
| Generate / edit / publish timetables | ✓ | ✓ (any scope) | own department subtree | | |
| See drafts and conflicts | ✓ | ✓ | ✓ | | |
| See published timetables, export, print | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edit own availability | | | | ✓ | |
| Manage users | ✓ | ✓ | teachers/students in own department | | |

---

## The scheduling engine

`backend/app/scheduler/` is pure Python with no database dependency, so it can be unit-tested and reused.

**Time model.** Each schedule configuration is turned into concrete periods in minutes from midnight (`timegrid.py`). Every overlap test is done on real clock time using bitmasks (one bit per minute), so a teacher shared between a 60‑minute department and a 50‑minute department can never be double-booked, even though their period numbers don't line up. Multi-period sessions (labs) must use back-to-back periods that don't straddle a break.

**Hard constraints** (never violated in generated output):
- one teacher, one class, one room per moment;
- teacher/class/room unavailability and teacher working hours;
- room type, lab feature and capacity suitability;
- teacher maximum periods per day and per week;
- commitments from other *published* timetables of the institution (so a CSE timetable respects a shared teacher's published Physics classes);
- pinned sessions stay where they are when regenerating.

**Phase 1, construction.** Backtracking search over sessions with *minimum remaining values* ordering (most constrained session first), forward checking on the teacher's and class's other sessions, and value ordering by estimated soft cost. If the node budget runs out it restarts with randomisation and raises the priority of sessions that caused dead ends ("squeaky wheel").

**Phase 2, repair.** Any leftovers are placed by ejection chains: if exactly one placed session blocks a slot, it is moved elsewhere to make room.

**Phase 3, optimisation.** Simulated annealing over feasible moves only (relocate a session, or swap two sessions of the same class) minimising a weighted soft cost:

| Soft constraint | Default weight |
|---|---|
| same subject twice in a day for a class | 10 |
| idle gaps in a teacher's day (per hour) | 3 |
| teacher exceeding preferred back-to-back periods | 8 |
| teacher teaching in an "avoid" slot / outside preferred slots | 6 / 2 |
| uneven daily load for classes / teachers | 1 / 1 |
| wasted room capacity (room utilisation) | 2 |
| late-in-the-day placement | 0.5 |

Weights can be tuned per institution through `soft_weights` (`PATCH /api/institutions/{id}`).

If something truly cannot be placed, the timetable is still produced and each unplaced session comes with a reason (for example *"No lab tagged 'physics' with at least 48 seats exists"* or *"All 30 possible slots are blocked: Dr. Anita Sharma is already teaching in 18; no suitable room is free in 12"*). Admins can place them manually from the free-slot list.

On the demo data the engine places all sessions in about a second; a synthetic 60-class, 66-teacher institution (1,380 sessions) completes in under 5 seconds before optimisation.

## Conflict detection

`detect_conflicts()` runs after generation, after every manual edit (including dry runs while dragging) and before publishing.

| Type | Severity |
|---|---|
| Teacher double-booked, class has two subjects, room double-booked | major |
| Teacher / class / room unavailable | major |
| Lab subject in a non-lab room, room too small | major |
| Session off the class's period grid | major |
| Weekly lectures don't match the curriculum | minor (warning) |
| Teacher over daily / weekly limit | minor (warning) |

Major conflicts block saving an edit (HTTP 409) and block publishing. Each major conflict carries free alternative slots where the class, the teacher and a suitable room are all free.

## API overview

All endpoints are documented at `/docs`. The main ones:

```
POST   /api/auth/login
GET    /api/auth/me
PUT    /api/auth/me/availability                        teacher self-service

GET/POST/PATCH/DELETE /api/institutions[/{id}]
CRUD   /api/institutions/{id}/{departments|schedules|teachers|rooms|subjects|classes|assignments|users}
POST   /api/institutions/{id}/schedules/preview          periods produced by a configuration
GET    /api/institutions/{id}/dashboard[?department_id=]

POST   /api/institutions/{id}/timetables                  generate {name, department_id?, time_limit?, seed?}
GET    /api/institutions/{id}/timetables/{tid}/view?view=class|teacher|room|lab|department|school|institution&ref=
GET    /api/institutions/{id}/timetables/{tid}/conflicts
PATCH  /api/institutions/{id}/timetables/{tid}/entries/{eid}   {day, period_index|start, room_id, teacher_id, locked, dry_run}
POST   /api/institutions/{id}/timetables/{tid}/entries         place a session
GET    /api/institutions/{id}/timetables/{tid}/entries/{eid}/suggestions
GET    /api/institutions/{id}/timetables/{tid}/assignments/{aid}/free-slots
POST   /api/institutions/{id}/timetables/{tid}/regenerate      {keep_locked}
POST   /api/institutions/{id}/timetables/{tid}/publish | unpublish | share
GET    /api/institutions/{id}/timetables/{tid}/export?format=pdf|xlsx|csv&view=&ref=

GET    /api/public/share/{token}[/view|/export]                read-only, no login
```

## Project structure

```
backend/
  app/
    scheduler/        timegrid.py, model.py, engine.py, conflicts.py   (pure algorithm)
    services/         data.py (DB -> scheduler), timetables.py, views.py, exporters.py
    routers/          auth, admin (institutions, users), resources (CRUD), timetables, dashboard, public
    models.py         SQLAlchemy models        schemas.py   Pydantic schemas
    security.py       JWT + role checks        seed.py      demo data
  migrations/         Alembic
  tests/              engine tests + end-to-end API tests
frontend/
  src/app/            login, dashboard, timetables, timetables/[id], setup/*, admin/*, my-availability, share/[token]
  src/components/     TimetableGrid (grid + timeline, drag and drop), ResourcePage (config-driven CRUD), ui
  src/lib/            api client, auth context, types
docker-compose.yml
```

## Production notes

- Set a long random `SECRET_KEY`, restrict `CORS_ORIGINS`, and set `FRONTEND_URL` to the public address (used in share links).
- Run migrations with `alembic upgrade head`; keep `AUTO_CREATE_TABLES=false`.
- Generation runs inside the request (default 15 s, capped by `SCHEDULER_MAX_TIME_LIMIT`). For very large institutions, move `run_generation` to a background worker (Celery/RQ) and poll the timetable's `generation` field.
- Natural extensions: splitting a class into lab batches that run in parallel, elective groups shared across sections, date-based exceptions (holidays, exam weeks), and email notifications on publish.
