"""Timetable generation engine.

Three phases, all respecting hard constraints at every step:

1. **Construction** – constraint-satisfaction backtracking search with
   MRV (most-constrained session first), forward checking on the teacher and
   class of every placement, heuristic value ordering (soft-cost aware) and
   randomised restarts with "squeaky wheel" prioritisation of sessions that
   caused dead ends.
2. **Repair** – if the search budget runs out before every session is placed,
   an ejection-chain repair tries to place the leftovers by relocating a single
   blocking session elsewhere.
3. **Optimisation** – simulated annealing over hard-feasible moves (relocate
   one session, or swap two sessions of the same class) to minimise the soft
   cost: subject repeats per day, teacher gaps and long runs, teacher slot
   preferences, daily balance for classes/teachers and wasted room capacity.

Hard constraints (never violated in the output):
  * a teacher, a class and a room are each used by at most one session at any
    clock minute (checked on real time, so different schedules can mix);
  * teacher, class and room availability windows and teacher working hours;
  * room type / tag / capacity suitability (labs only in matching labs);
  * multi-period sessions use back-to-back periods that do not straddle a break;
  * teacher maximum periods per day and per week;
  * every requested weekly lecture is placed (otherwise reported as unscheduled).
"""
from __future__ import annotations

import math
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .model import (
    ClassInfo,
    Placement,
    Problem,
    RoomInfo,
    SessionReq,
    TeacherInfo,
    mask,
    room_suits,
    room_suits_reason,
)
from .timegrid import DAY_NAMES, fmt_range

NUM_DAYS = 7


@dataclass(frozen=True)
class Candidate:
    day: int
    index: int
    start: int
    end: int
    m: int
    rooms: tuple[int, ...]  # statically suitable + available, best fit first


@dataclass
class Unscheduled:
    session_key: str
    assignment_id: int
    class_id: int
    subject_name: str
    teacher_id: int
    length: int
    reason: str


@dataclass
class SolveResult:
    placements: list[Placement]
    unscheduled: list[Unscheduled]
    soft_score: float
    breakdown: dict[str, float]
    warnings: list[str]
    stats: dict[str, float | int | str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.unscheduled


class _State:
    """Mutable occupancy (bitmask per resource per day) plus soft-cost indexes."""

    def __init__(self, problem: Problem):
        self.p = problem
        self.teacher_busy: dict[int, list[int]] = defaultdict(lambda: [0] * NUM_DAYS)
        self.class_busy: dict[int, list[int]] = defaultdict(lambda: [0] * NUM_DAYS)
        self.room_busy: dict[int, list[int]] = defaultdict(lambda: [0] * NUM_DAYS)
        self.teacher_day_load: dict[int, list[int]] = defaultdict(lambda: [0] * NUM_DAYS)
        self.teacher_week_load: Counter[int] = Counter()
        # key -> (Candidate, room_id)
        self.placed: dict[str, tuple[Candidate, int]] = {}
        self.class_day: dict[tuple[int, int], set[str]] = defaultdict(set)
        self.teacher_day: dict[tuple[int, int], set[str]] = defaultdict(set)

    # -- hard feasibility -------------------------------------------------
    def time_ok(self, s: SessionReq, c: Candidate) -> bool:
        if self.teacher_busy[s.teacher_id][c.day] & c.m:
            return False
        if self.class_busy[s.class_id][c.day] & c.m:
            return False
        t = self.p.teachers[s.teacher_id]
        if t.max_per_day is not None and self.teacher_day_load[s.teacher_id][c.day] + s.length > t.max_per_day:
            return False
        if t.max_per_week is not None and self.teacher_week_load[s.teacher_id] + s.length > t.max_per_week:
            return False
        return True

    def free_room(self, c: Candidate) -> int | None:
        for r in c.rooms:
            if not self.room_busy[r][c.day] & c.m:
                return r
        return None

    def apply(self, s: SessionReq, c: Candidate, room: int) -> None:
        self.teacher_busy[s.teacher_id][c.day] |= c.m
        self.class_busy[s.class_id][c.day] |= c.m
        self.room_busy[room][c.day] |= c.m
        self.teacher_day_load[s.teacher_id][c.day] += s.length
        self.teacher_week_load[s.teacher_id] += s.length
        self.placed[s.key] = (c, room)
        self.class_day[(s.class_id, c.day)].add(s.key)
        self.teacher_day[(s.teacher_id, c.day)].add(s.key)

    def remove(self, s: SessionReq) -> tuple[Candidate, int]:
        c, room = self.placed.pop(s.key)
        self.teacher_busy[s.teacher_id][c.day] &= ~c.m
        self.class_busy[s.class_id][c.day] &= ~c.m
        self.room_busy[room][c.day] &= ~c.m
        self.teacher_day_load[s.teacher_id][c.day] -= s.length
        self.teacher_week_load[s.teacher_id] -= s.length
        self.class_day[(s.class_id, c.day)].discard(s.key)
        self.teacher_day[(s.teacher_id, c.day)].discard(s.key)
        return c, room


class Solver:
    def __init__(
        self,
        problem: Problem,
        time_limit: float = 20.0,
        seed: int | None = None,
        optimise: bool = True,
    ):
        self.p = problem
        self.time_limit = max(1.0, float(time_limit))
        self.rng = random.Random(seed)
        self.optimise = optimise
        self.w = problem.weights
        self.sessions: dict[str, SessionReq] = {s.key: s for s in problem.sessions}
        self.warnings: list[str] = []
        self.static_fail: dict[str, str] = {}
        self.cands: dict[str, list[Candidate]] = {}
        self.by_teacher: dict[int, list[str]] = defaultdict(list)
        self.by_class: dict[int, list[str]] = defaultdict(list)
        for s in problem.sessions:
            self.by_teacher[s.teacher_id].append(s.key)
            self.by_class[s.class_id].append(s.key)
        self._tdays_cache: dict[int, list[int]] = {}

    # ------------------------------------------------------------------ setup
    def _suitable_rooms(self, s: SessionReq, cls: ClassInfo) -> list[RoomInfo]:
        rooms = [r for r in self.p.rooms.values() if room_suits(r, s, cls.strength)]
        rooms.sort(key=lambda r: (r.capacity - cls.strength, r.id))
        return rooms

    def _build_candidates(self) -> None:
        for s in self.p.sessions:
            cls = self.p.classes.get(s.class_id)
            teacher = self.p.teachers.get(s.teacher_id)
            if cls is None or teacher is None:
                self.static_fail[s.key] = "Class or teacher record is missing"
                self.cands[s.key] = []
                continue
            rooms = self._suitable_rooms(s, cls)
            if not rooms:
                reasons = sorted({room_suits_reason(r, s, cls.strength) or "" for r in self.p.rooms.values()})
                need = s.room_type.replace("_", " ")
                tag = f" tagged '{s.room_tag}'" if s.room_tag else ""
                self.static_fail[s.key] = (
                    f"No {need}{tag} with at least {cls.strength} seats exists"
                    + (f" (e.g. a room {reasons[0]})" if reasons and reasons[0] else "")
                )
                self.cands[s.key] = []
                continue
            out: list[Candidate] = []
            has_block = teacher_ok = class_ok = False
            for day in cls.grid.days:
                for idx in range(len(cls.grid.periods[day])):
                    blk = cls.grid.block(day, idx, s.length)
                    if blk is None:
                        continue
                    has_block = True
                    start, end = blk
                    if not cls.is_available(day, start, end):
                        continue
                    class_ok = True
                    if not teacher.is_available(day, start, end):
                        continue
                    teacher_ok = True
                    free = tuple(r.id for r in rooms if r.is_available(day, start, end))
                    if not free:
                        continue
                    out.append(Candidate(day, idx, start, end, mask(start, end), free))
            self.cands[s.key] = out
            if not out:
                if not has_block:
                    self.static_fail[s.key] = (
                        f"{cls.name}'s schedule has no {s.length} back-to-back periods without a break"
                    )
                elif not class_ok:
                    self.static_fail[s.key] = f"{cls.name} is marked unavailable in every possible slot"
                elif not teacher_ok:
                    self.static_fail[s.key] = (
                        f"{teacher.name} is unavailable (or outside working hours) in every slot of {cls.name}"
                    )
                else:
                    self.static_fail[s.key] = "Every suitable room is unavailable in every possible slot"

    def _precheck(self) -> None:
        demand_t: Counter[int] = Counter()
        demand_c: Counter[int] = Counter()
        for s in self.p.sessions:
            demand_t[s.teacher_id] += s.length
            demand_c[s.class_id] += s.length
        for tid, need in demand_t.items():
            t = self.p.teachers.get(tid)
            if t and t.max_per_week is not None and need > t.max_per_week:
                self.warnings.append(
                    f"{t.name} is assigned {need} periods/week but the weekly limit is {t.max_per_week}"
                )
        for cid, need in demand_c.items():
            c = self.p.classes.get(cid)
            if c and need > c.grid.total_periods():
                self.warnings.append(
                    f"{c.name} needs {need} periods/week but its schedule only has {c.grid.total_periods()}"
                )
        # room-type supply vs demand (rough upper bound)
        demand_type: Counter[str] = Counter()
        for s in self.p.sessions:
            if s.fixed_room_id is None:
                demand_type[s.room_type] += s.length
        max_periods = max((c.grid.total_periods() for c in self.p.classes.values()), default=0)
        for rtype, need in demand_type.items():
            supply = sum(1 for r in self.p.rooms.values() if r.room_type == rtype or rtype == "any") * max_periods
            if supply and need > supply:
                self.warnings.append(
                    f"{need} periods need a {rtype.replace('_', ' ')}, but rooms of that type offer about {supply}"
                )

    # ------------------------------------------------------------ soft cost
    def _teacher_days(self, tid: int) -> list[int]:
        if tid not in self._tdays_cache:
            days: set[int] = set()
            for key in self.by_teacher.get(tid, []):
                days.update(self.p.classes[self.sessions[key].class_id].grid.days)
            self._tdays_cache[tid] = sorted(days)
        return self._tdays_cache[tid]

    def _class_day_cost(self, st: _State, cid: int, day: int) -> float:
        counts = Counter(self.sessions[k].subject_id for k in st.class_day.get((cid, day), ()))
        return self.w.subject_repeat_per_day * sum(n - 1 for n in counts.values() if n > 1)

    def _teacher_day_cost(self, st: _State, tid: int, day: int) -> float:
        keys = st.teacher_day.get((tid, day))
        if not keys:
            return 0.0
        items = sorted((st.placed[k][0].start, st.placed[k][0].end, self.sessions[k].length) for k in keys)
        cost = 0.0
        t = self.p.teachers[tid]
        run = items[0][2]
        max_c = t.max_consecutive
        for (s0, e0, _), (s1, e1, l1) in zip(items, items[1:]):
            gap = s1 - e0
            if gap > 20:
                cost += self.w.teacher_gap_hour * gap / 60.0
            if gap <= 15:
                run += l1
            else:
                if max_c and run > max_c:
                    cost += self.w.teacher_over_consecutive * (run - max_c)
                run = l1
        if max_c and run > max_c:
            cost += self.w.teacher_over_consecutive * (run - max_c)
        return cost

    def _balance(self, loads: list[float]) -> float:
        if not loads:
            return 0.0
        mean = sum(loads) / len(loads)
        return sum((x - mean) ** 2 for x in loads)

    def _class_balance(self, st: _State, cid: int) -> float:
        days = self.p.classes[cid].grid.days
        loads = [sum(self.sessions[k].length for k in st.class_day.get((cid, d), ())) for d in days]
        return self.w.class_daily_balance * self._balance(loads)

    def _teacher_balance(self, st: _State, tid: int) -> float:
        loads = [st.teacher_day_load[tid][d] for d in self._teacher_days(tid)]
        return self.w.teacher_daily_balance * self._balance(loads)

    def _session_cost(self, st: _State, key: str) -> float:
        s = self.sessions[key]
        c, room = st.placed[key]
        t = self.p.teachers[s.teacher_id]
        cost = 0.0
        if any(w.overlaps(c.day, c.start, c.end) for w in t.avoid):
            cost += self.w.teacher_avoid_slot
        if t.preferred and not any(
            w.day == c.day and w.start <= c.start and c.end <= w.end for w in t.preferred
        ):
            cost += self.w.teacher_not_preferred
        r = self.p.rooms[room]
        strength = self.p.classes[s.class_id].strength
        if r.capacity > 0:
            cost += self.w.room_wasted_capacity * max(0, r.capacity - strength) / r.capacity
        n = len(self.p.classes[s.class_id].grid.periods.get(c.day, [])) or 1
        cost += self.w.late_slot * c.index / n
        return cost

    def _group_cost(self, st: _State, class_days, teacher_days, classes, teachers, keys) -> float:
        total = 0.0
        for cid, d in class_days:
            total += self._class_day_cost(st, cid, d)
        for tid, d in teacher_days:
            total += self._teacher_day_cost(st, tid, d)
        for cid in classes:
            total += self._class_balance(st, cid)
        for tid in teachers:
            total += self._teacher_balance(st, tid)
        for k in keys:
            if k in st.placed:
                total += self._session_cost(st, k)
        return total

    def total_cost(self, st: _State) -> tuple[float, dict[str, float]]:
        b: dict[str, float] = defaultdict(float)
        for (cid, d) in list(st.class_day):
            b["subject_repeat_per_day"] += self._class_day_cost(st, cid, d)
        for (tid, d) in list(st.teacher_day):
            b["teacher_gaps_and_runs"] += self._teacher_day_cost(st, tid, d)
        for cid in self.p.classes:
            if cid in self.by_class:
                b["class_daily_balance"] += self._class_balance(st, cid)
        for tid in self.p.teachers:
            if tid in self.by_teacher:
                b["teacher_daily_balance"] += self._teacher_balance(st, tid)
        for k in st.placed:
            b["slot_preferences_and_room_fit"] += self._session_cost(st, k)
        b = {k: round(v, 2) for k, v in b.items()}
        return round(sum(b.values()), 2), b

    # ------------------------------------------------------- construction
    def _value_score(self, st: _State, s: SessionReq, c: Candidate, room: int) -> float:
        score = 0.0
        same_subject = sum(
            1 for k in st.class_day.get((s.class_id, c.day), ()) if self.sessions[k].subject_id == s.subject_id
        )
        score += self.w.subject_repeat_per_day * same_subject
        t = self.p.teachers[s.teacher_id]
        if any(w.overlaps(c.day, c.start, c.end) for w in t.avoid):
            score += self.w.teacher_avoid_slot
        if t.preferred and not any(w.day == c.day and w.start <= c.start and c.end <= w.end for w in t.preferred):
            score += self.w.teacher_not_preferred
        class_load = sum(self.sessions[k].length for k in st.class_day.get((s.class_id, c.day), ()))
        score += 0.6 * class_load + 0.6 * st.teacher_day_load[s.teacher_id][c.day]
        keys = st.teacher_day.get((s.teacher_id, c.day))
        if keys:
            nearest = min(
                min(abs(st.placed[k][0].start - c.end), abs(c.start - st.placed[k][0].end)) for k in keys
            )
            score += self.w.teacher_gap_hour * max(0, nearest - 20) / 60.0
        r = self.p.rooms[room]
        if r.capacity:
            strength = self.p.classes[s.class_id].strength
            score += self.w.room_wasted_capacity * max(0, r.capacity - strength) / r.capacity
        score += 0.15 * c.index
        return score + self.rng.random() * 1.5

    def _ordered_values(self, st: _State, s: SessionReq) -> list[tuple[Candidate, int]]:
        vals = []
        for c in self.cands[s.key]:
            if not st.time_ok(s, c):
                continue
            room = st.free_room(c)
            if room is None:
                continue
            vals.append((self._value_score(st, s, c, room), c, room))
        vals.sort(key=lambda x: x[0])
        return [(c, r) for _, c, r in vals]

    def _count(self, st: _State, key: str) -> int:
        s = self.sessions[key]
        return sum(1 for c in self.cands[key] if st.time_ok(s, c))

    def _neighbours(self, s: SessionReq) -> set[str]:
        return set(self.by_teacher[s.teacher_id]) | set(self.by_class[s.class_id])

    def _backtrack(
        self, st: _State, todo: list[str], priority: Counter, node_budget: int, deadline: float
    ) -> tuple[bool, dict[str, tuple[Candidate, int]], set[str]]:
        unassigned = set(todo)
        counts = {k: self._count(st, k) for k in unassigned}
        best_snapshot = dict(st.placed)
        best_n = len(st.placed)
        dead_ends: set[str] = set()
        nodes = 0
        stack: list[list] = []  # [key, values, next_index, applied?]

        def select() -> str | None:
            if not unassigned:
                return None
            return min(
                unassigned,
                key=lambda k: (
                    counts[k] / (1.0 + priority[k]),
                    -self.sessions[k].length,
                    -len(self.by_teacher[self.sessions[k].teacher_id]),
                    k,
                ),
            )

        def refresh(s: SessionReq) -> bool:
            ok = True
            for k in self._neighbours(s):
                if k in unassigned:
                    counts[k] = self._count(st, k)
                    if counts[k] == 0:
                        ok = False
            return ok

        first = select()
        if first is None:
            return True, dict(st.placed), dead_ends
        stack.append([first, self._ordered_values(st, self.sessions[first]), 0, False])
        unassigned.discard(first)

        while stack:
            if time.monotonic() > deadline or nodes > node_budget:
                break
            frame = stack[-1]
            key, values, i, applied = frame
            s = self.sessions[key]
            if applied:
                st.remove(s)
                frame[3] = False
                refresh(s)
            progressed = False
            while frame[2] < len(values):
                c, room = values[frame[2]]
                frame[2] += 1
                if not st.time_ok(s, c) or st.room_busy[room][c.day] & c.m:
                    continue
                st.apply(s, c, room)
                nodes += 1
                if refresh(s):
                    frame[3] = True
                    progressed = True
                    break
                st.remove(s)
                refresh(s)
            if not progressed:
                dead_ends.add(key)
                stack.pop()
                unassigned.add(key)
                continue
            if len(st.placed) > best_n:
                best_n = len(st.placed)
                best_snapshot = dict(st.placed)
            nxt = select()
            if nxt is None:
                return True, dict(st.placed), dead_ends
            unassigned.discard(nxt)
            stack.append([nxt, self._ordered_values(st, self.sessions[nxt]), 0, False])

        # unwind so the caller gets a clean state
        while stack:
            key, _, _, applied = stack.pop()
            if applied:
                st.remove(self.sessions[key])
        return False, best_snapshot, dead_ends

    # -------------------------------------------------------------- repair
    def _blockers(self, st: _State, s: SessionReq, c: Candidate) -> list[str]:
        """Placed sessions that stop `s` from using candidate `c` (best room)."""
        out: set[str] = set()
        for k, (pc, _room) in st.placed.items():
            if pc.day != c.day or not pc.m & c.m:
                continue
            o = self.sessions[k]
            if o.teacher_id == s.teacher_id or o.class_id == s.class_id:
                out.add(k)
        if st.free_room(c) is None:
            # pick the occupant of the first suitable room as the blocker
            for r in c.rooms:
                occupants = [
                    k for k, (pc, room) in st.placed.items() if room == r and pc.day == c.day and pc.m & c.m
                ]
                if len(occupants) == 1:
                    out.add(occupants[0])
                    break
            else:
                out.add("__unfixable__")
        return list(out)

    def _repair(self, st: _State, missing: list[str], deadline: float) -> list[str]:
        missing = list(missing)
        improved = True
        while missing and improved and time.monotonic() < deadline:
            improved = False
            self.rng.shuffle(missing)
            for key in list(missing):
                if time.monotonic() > deadline:
                    break
                s = self.sessions[key]
                vals = self._ordered_values(st, s)
                if vals:
                    st.apply(s, *vals[0])
                    missing.remove(key)
                    improved = True
                    continue
                cands = [c for c in self.cands[key]]
                self.rng.shuffle(cands)
                for c in cands:
                    t = self.p.teachers[s.teacher_id]
                    blockers = self._blockers(st, s, c)
                    if len(blockers) != 1 or blockers[0] == "__unfixable__" or blockers[0] in self.p.locked:
                        continue
                    b = self.sessions[blockers[0]]
                    old = st.remove(b)
                    if not st.time_ok(s, c) or st.free_room(c) is None:
                        st.apply(b, *old)
                        continue
                    st.apply(s, c, st.free_room(c))
                    alt = [v for v in self._ordered_values(st, b) if v[0] != old[0]]
                    if alt:
                        st.apply(b, *alt[0])
                        missing.remove(key)
                        improved = True
                        break
                    st.remove(s)
                    st.apply(b, *old)
                    _ = t
        return missing

    # -------------------------------------------------------- optimisation
    def _anneal(self, st: _State, deadline: float, max_iters: int | None = None) -> int:
        movable = [k for k in st.placed if k not in self.p.locked]
        if not movable:
            return 0
        if max_iters is None:
            max_iters = max(30000, 250 * len(movable))
        same_class: dict[tuple[int, int], list[str]] = defaultdict(list)
        for k in movable:
            s = self.sessions[k]
            same_class[(s.class_id, s.length)].append(k)
        temp, t_end = 4.0, 0.05
        iters = 0
        accepted = 0
        alpha = (t_end / temp) ** (1.0 / max_iters)
        while iters < max_iters and time.monotonic() < deadline:
            iters += 1
            temp *= alpha
            key = self.rng.choice(movable)
            s = self.sessions[key]
            if self.rng.random() < 0.7:
                c_new = self.rng.choice(self.cands[key])
                c_old, r_old = st.placed[key]
                if c_new == c_old:
                    continue
                cdays = {(s.class_id, c_old.day), (s.class_id, c_new.day)}
                tdays = {(s.teacher_id, c_old.day), (s.teacher_id, c_new.day)}
                before = self._group_cost(st, cdays, tdays, {s.class_id}, {s.teacher_id}, [key])
                st.remove(s)
                room = st.free_room(c_new) if st.time_ok(s, c_new) else None
                if room is None:
                    st.apply(s, c_old, r_old)
                    continue
                st.apply(s, c_new, room)
                after = self._group_cost(st, cdays, tdays, {s.class_id}, {s.teacher_id}, [key])
                delta = after - before
                if delta <= 0 or self.rng.random() < math.exp(-delta / temp):
                    accepted += 1
                else:
                    st.remove(s)
                    st.apply(s, c_old, r_old)
            else:
                peers = same_class[(s.class_id, s.length)]
                if len(peers) < 2:
                    continue
                key2 = self.rng.choice(peers)
                if key2 == key:
                    continue
                s2 = self.sessions[key2]
                c1, r1 = st.placed[key]
                c2, r2 = st.placed[key2]
                # candidates of s at c2's time and s2 at c1's time
                n1 = next((c for c in self.cands[key] if c.day == c2.day and c.index == c2.index), None)
                n2 = next((c for c in self.cands[key2] if c.day == c1.day and c.index == c1.index), None)
                if n1 is None or n2 is None:
                    continue
                cdays = {(s.class_id, c1.day), (s.class_id, c2.day)}
                tdays = {(s.teacher_id, c1.day), (s.teacher_id, c2.day), (s2.teacher_id, c1.day), (s2.teacher_id, c2.day)}
                teachers = {s.teacher_id, s2.teacher_id}
                before = self._group_cost(st, cdays, tdays, {s.class_id}, teachers, [key, key2])
                st.remove(s)
                st.remove(s2)
                ok = False
                if st.time_ok(s, n1):
                    ra = st.free_room(n1)
                    if ra is not None:
                        st.apply(s, n1, ra)
                        if st.time_ok(s2, n2):
                            rb = st.free_room(n2)
                            if rb is not None:
                                st.apply(s2, n2, rb)
                                ok = True
                        if not ok:
                            st.remove(s)
                if not ok:
                    st.apply(s, c1, r1)
                    st.apply(s2, c2, r2)
                    continue
                after = self._group_cost(st, cdays, tdays, {s.class_id}, teachers, [key, key2])
                delta = after - before
                if delta <= 0 or self.rng.random() < math.exp(-delta / temp):
                    accepted += 1
                else:
                    st.remove(s)
                    st.remove(s2)
                    st.apply(s, c1, r1)
                    st.apply(s2, c2, r2)
        return iters

    # ------------------------------------------------------------ explain
    def _explain(self, st: _State, key: str) -> str:
        if key in self.static_fail:
            return self.static_fail[key]
        s = self.sessions[key]
        teacher_busy = class_busy = room_busy = limit = 0
        t = self.p.teachers[s.teacher_id]
        for c in self.cands[key]:
            if st.teacher_busy[s.teacher_id][c.day] & c.m:
                teacher_busy += 1
            elif st.class_busy[s.class_id][c.day] & c.m:
                class_busy += 1
            elif not st.time_ok(s, c):
                limit += 1
            elif st.free_room(c) is None:
                room_busy += 1
        parts = []
        if teacher_busy:
            parts.append(f"{t.name} is already teaching in {teacher_busy}")
        if class_busy:
            parts.append(f"the class is busy in {class_busy}")
        if limit:
            parts.append(f"{t.name}'s daily/weekly limit blocks {limit}")
        if room_busy:
            parts.append(f"no suitable room is free in {room_busy}")
        total = len(self.cands[key])
        return (
            f"All {total} possible slots are blocked: " + "; ".join(parts)
            if parts
            else "Search budget exhausted before this session could be placed"
        )

    # --------------------------------------------------------------- solve
    def solve(self) -> SolveResult:
        t0 = time.monotonic()
        hard_deadline = t0 + self.time_limit
        build_deadline = t0 + self.time_limit * (0.55 if self.optimise else 0.9)
        self._build_candidates()
        self._precheck()

        base = _State(self.p)
        for ext in self.p.external:
            m = mask(ext.start, ext.end)
            if ext.kind == "teacher":
                base.teacher_busy[ext.ref_id][ext.day] |= m
            elif ext.kind == "room":
                base.room_busy[ext.ref_id][ext.day] |= m
            elif ext.kind == "class":
                base.class_busy[ext.ref_id][ext.day] |= m

        # locked placements are applied as-is (the validator reports any clash)
        for key, pl in self.p.locked.items():
            s = self.sessions.get(key)
            if s is None:
                continue
            c = Candidate(pl.day, pl.period_index, pl.start, pl.end, mask(pl.start, pl.end), (pl.room_id,))
            base.apply(s, c, pl.room_id)

        todo = [s.key for s in self.p.sessions if s.key not in self.p.locked and self.cands.get(s.key)]
        priority: Counter = Counter()
        best: dict[str, tuple[Candidate, int]] = dict(base.placed)
        complete = False
        attempts = 0
        node_budget = max(2000, 30 * len(todo))
        while time.monotonic() < build_deadline:
            attempts += 1
            st = _State(self.p)
            st.teacher_busy = defaultdict(lambda: [0] * NUM_DAYS, {k: list(v) for k, v in base.teacher_busy.items()})
            st.class_busy = defaultdict(lambda: [0] * NUM_DAYS, {k: list(v) for k, v in base.class_busy.items()})
            st.room_busy = defaultdict(lambda: [0] * NUM_DAYS, {k: list(v) for k, v in base.room_busy.items()})
            for key, (c, r) in base.placed.items():
                s = self.sessions[key]
                st.teacher_day_load[s.teacher_id][c.day] += s.length
                st.teacher_week_load[s.teacher_id] += s.length
                st.placed[key] = (c, r)
                st.class_day[(s.class_id, c.day)].add(key)
                st.teacher_day[(s.teacher_id, c.day)].add(key)
            ok, snapshot, dead = self._backtrack(st, todo, priority, node_budget, build_deadline)
            if len(snapshot) > len(best) or ok:
                best = snapshot
            if ok:
                complete = True
                break
            for k in dead:
                priority[k] += 1
            node_budget = int(node_budget * 1.6)

        # rebuild the state from the best assignment found
        st = self._state_from(base, best)
        missing = [k for k in todo if k not in st.placed]
        if missing:
            repair_deadline = min(hard_deadline, time.monotonic() + max(1.0, self.time_limit * 0.25))
            missing = self._repair(st, missing, repair_deadline)

        iters = 0
        if self.optimise and time.monotonic() < hard_deadline:
            iters = self._anneal(st, hard_deadline)

        score, breakdown = self.total_cost(st)
        placements = [
            Placement(k, c.day, c.index, c.start, c.end, room) for k, (c, room) in sorted(st.placed.items())
        ]
        unscheduled = []
        for s in self.p.sessions:
            if s.key in st.placed:
                continue
            unscheduled.append(
                Unscheduled(
                    session_key=s.key,
                    assignment_id=s.assignment_id,
                    class_id=s.class_id,
                    subject_name=s.subject_name,
                    teacher_id=s.teacher_id,
                    length=s.length,
                    reason=self._explain(st, s.key),
                )
            )
        return SolveResult(
            placements=placements,
            unscheduled=unscheduled,
            soft_score=score,
            breakdown=breakdown,
            warnings=self.warnings,
            stats={
                "sessions": len(self.p.sessions),
                "placed": len(placements),
                "attempts": attempts,
                "search_complete": complete,
                "anneal_iterations": iters,
                "seconds": round(time.monotonic() - t0, 2),
            },
        )

    def _state_from(self, base: _State, assignment: dict[str, tuple[Candidate, int]]) -> _State:
        st = _State(self.p)
        st.teacher_busy = defaultdict(lambda: [0] * NUM_DAYS, {k: list(v) for k, v in base.teacher_busy.items()})
        st.class_busy = defaultdict(lambda: [0] * NUM_DAYS, {k: list(v) for k, v in base.class_busy.items()})
        st.room_busy = defaultdict(lambda: [0] * NUM_DAYS, {k: list(v) for k, v in base.room_busy.items()})
        # base already contains locked placements in its busy masks; register them without re-masking
        for key, (c, r) in base.placed.items():
            s = self.sessions[key]
            st.teacher_day_load[s.teacher_id][c.day] += s.length
            st.teacher_week_load[s.teacher_id] += s.length
            st.placed[key] = (c, r)
            st.class_day[(s.class_id, c.day)].add(key)
            st.teacher_day[(s.teacher_id, c.day)].add(key)
        for key, (c, r) in assignment.items():
            if key in base.placed:
                continue
            st.apply(self.sessions[key], c, r)
        return st


def generate(problem: Problem, time_limit: float = 20.0, seed: int | None = None, optimise: bool = True) -> SolveResult:
    return Solver(problem, time_limit=time_limit, seed=seed, optimise=optimise).solve()


def describe_slot(day: int, start: int, end: int) -> str:
    return f"{DAY_NAMES[day]} {fmt_range(start, end)}"
