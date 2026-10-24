"use client";

import { AlertTriangle, Download, Link2, Pin, PinOff, Printer, RefreshCw, Trash2, Wand2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import TimetableGrid, { cellKey } from "@/components/TimetableGrid";
import { Button, Drawer, ErrorNote, Field, Input, Loading, Pill, Select, StatusPill, cx, useLoad, useToast } from "@/components/ui";
import { ApiError, api, download, inst } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CONFLICT_LABEL, type Conflict, type Entry, type Suggestion, type TimetableDetail, type View } from "@/lib/types";

const VIEW_TABS: { key: string; label: string; opt?: keyof TimetableDetail["options"] }[] = [
  { key: "class", label: "Class", opt: "classes" },
  { key: "teacher", label: "Teacher", opt: "teachers" },
  { key: "room", label: "Room", opt: "rooms" },
  { key: "lab", label: "Laboratory", opt: "labs" },
  { key: "department", label: "Department", opt: "departments" },
  { key: "school", label: "School", opt: "schools" },
  { key: "institution", label: "Institution" },
];

export default function TimetablePage() {
  const { id } = useParams<{ id: string }>();
  const { iid, user } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const base = inst(iid!, `/timetables/${id}`);

  const tt = useLoad(() => api<TimetableDetail>(base), [base]);
  const [viewType, setViewType] = useState("class");
  const [ref, setRef] = useState<number | null>(null);
  const [view, setView] = useState<View | null>(null);
  const [viewErr, setViewErr] = useState<string | null>(null);
  const [masterDay, setMasterDay] = useState<number | null>(null);
  const [dragging, setDragging] = useState<Entry | null>(null);
  const [highlight, setHighlight] = useState<Set<string> | null>(null);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [blocked, setBlocked] = useState<{ entry: Entry; conflicts: Conflict[]; detail: string } | null>(null);
  const [conflicts, setConflicts] = useState<{ conflicts: Conflict[]; summary: any; unscheduled: any[] } | null>(null);
  const [panel, setPanel] = useState(false);
  const [focusId, setFocusId] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [share, setShare] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const dragToken = useRef(0);
  const closeExport = useCallback(() => setExportOpen(false), []);

  const d = tt.data;
  const editable = !!d?.can_edit;
  const isAdmin = user && ["super_admin", "institution_admin", "department_admin"].includes(user.role);

  // sensible first view per role
  useEffect(() => {
    if (!d || ref !== null || viewType !== "class") return;
    if (user?.role === "teacher" && user.teacher_id && d.options.teachers.some((t) => t.id === user.teacher_id)) {
      setViewType("teacher");
      setRef(user.teacher_id);
    } else if (user?.role === "student" && user.class_id && d.options.classes.some((c) => c.id === user.class_id)) {
      setRef(user.class_id);
    } else {
      setRef(d.options.classes[0]?.id ?? null);
    }
  }, [d, user, ref, viewType]);

  const loadView = useCallback(async () => {
    if (!d) return;
    const needsRef = viewType !== "institution";
    if (needsRef && ref == null) {
      setView(null);
      return;
    }
    try {
      const v = await api<View>(`${base}/view`, { query: { view: viewType, ref: needsRef ? ref : undefined } });
      setView(v);
      setViewErr(null);
      if (v.kind === "master" && (masterDay == null || !v.days.some((x) => x.day === masterDay))) setMasterDay(v.days[0]?.day ?? 0);
    } catch (e: any) {
      setViewErr(e.message);
    }
  }, [base, d, viewType, ref, masterDay]);

  useEffect(() => {
    loadView();
  }, [loadView]);

  const loadConflicts = useCallback(async () => {
    if (!isAdmin) return;
    try {
      setConflicts(await api(`${base}/conflicts`));
    } catch {
      /* shown elsewhere */
    }
  }, [base, isAdmin]);

  useEffect(() => {
    if (d && isAdmin) loadConflicts();
  }, [d?.id, isAdmin, loadConflicts]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshAll = async () => {
    await Promise.all([loadView(), loadConflicts()]);
    tt.reload();
  };

  function switchView(type: string) {
    setViewType(type);
    const tab = VIEW_TABS.find((t) => t.key === type);
    const first = tab?.opt ? d?.options[tab.opt][0]?.id ?? null : null;
    setRef(first);
  }

  // ------------------------------------------------------------ edits
  async function startDrag(e: Entry) {
    setDragging(e);
    setHighlight(null);
    const token = ++dragToken.current;
    try {
      const s = await api<Suggestion[]>(`${base}/entries/${e.id}/suggestions`, { query: { limit: 60 } });
      if (token === dragToken.current) setHighlight(new Set(s.map((x) => cellKey(x.day, x.start))));
    } catch {
      /* highlighting is a hint only */
    }
  }

  function endDrag() {
    dragToken.current++;
    setDragging(null);
    setHighlight(null);
  }

  async function move(e: Entry, body: Record<string, any>, label = "Moved") {
    setBusy("move");
    try {
      await api(`${base}/entries/${e.id}`, { method: "PATCH", body });
      toast(`${label}: ${e.subject_name}, ${e.class_name}`);
      setBlocked(null);
      setSelected(null);
      await refreshAll();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setBlocked({ entry: e, conflicts: err.body?.blocking ?? [], detail: err.body?.detail ?? err.message });
      } else toast((err as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  async function onDrop(e: Entry, day: number, start: number) {
    endDrag();
    if (e.day === day && e.start === start) return;
    await move(e, { day, start });
  }

  async function act(label: string, fn: () => Promise<any>, done?: string) {
    setBusy(label);
    try {
      await fn();
      if (done) toast(done);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 409 && err.body?.blocking) {
        setConflicts((c) => ({ ...(c ?? { summary: {}, unscheduled: [] }), conflicts: err.body.blocking }));
        setPanel(true);
      }
      toast(err.message, "error");
    } finally {
      setBusy(null);
    }
  }

  if (tt.error) return <ErrorNote error={tt.error} />;
  if (!d) return <Loading />;

  const tab = VIEW_TABS.find((t) => t.key === viewType)!;
  const tabs = VIEW_TABS.filter((t) => !t.opt || d.options[t.opt].length > 0);
  const summary = conflicts?.summary ?? d.conflict_summary ?? {};
  const unscheduled: any[] = d.generation?.unscheduled ?? [];

  return (
    <div className="max-w-[1480px]">
      {/* Header */}
      <div className="no-print mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-[28px] font-semibold leading-tight">{d.name}</h1>
            <StatusPill status={d.status} />
          </div>
          <p className="mt-1 text-ink-soft">
            {d.scope}
            {d.term ? `, ${d.term}` : ""}. {d.entry_count} sessions a week.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isAdmin && (
            <Button onClick={() => setPanel(true)} className={summary.major ? "border-redpen text-redpen" : ""}>
              <AlertTriangle size={15} />
              {summary.major ? `${summary.major} conflicts` : summary.minor ? `${summary.minor} warnings` : "No conflicts"}
            </Button>
          )}
          <div className="relative">
            <Button onClick={() => setExportOpen((o) => !o)} aria-expanded={exportOpen}>
              <Download size={15} /> Export
            </Button>
            {exportOpen && (
              <ExportMenu
                onClose={closeExport}
                onPick={(format, vt, r) =>
                  act("export", () => download(`${base}/export`, { format, view: vt, ref: r }, `timetable.${format}`))
                }
                viewType={viewType}
                refId={viewType === "institution" ? null : ref}
                title={view?.title ?? ""}
              />
            )}
          </div>
          <Button onClick={() => window.print()}>
            <Printer size={15} /> Print
          </Button>
          {editable && (
            <>
              <Button onClick={() => setShare(true)}>
                <Link2 size={15} /> Share
              </Button>
              <Button
                busy={busy === "regen"}
                onClick={() =>
                  window.confirm("Regenerate this timetable? Pinned sessions stay where they are; everything else is rearranged.") &&
                  act("regen", async () => {
                    await api(`${base}/regenerate`, { method: "POST", body: { keep_locked: true } });
                    await refreshAll();
                  }, "Regenerated. Pinned sessions were kept.")
                }
              >
                <RefreshCw size={15} /> Regenerate
              </Button>
              {d.status === "published" ? (
                <Button busy={busy === "pub"} onClick={() => act("pub", async () => { await api(`${base}/unpublish`, { method: "POST" }); tt.reload(); }, "Moved back to draft")}>
                  Unpublish
                </Button>
              ) : (
                <Button
                  variant="primary"
                  busy={busy === "pub"}
                  onClick={() => act("pub", async () => { await api(`${base}/publish`, { method: "POST" }); await refreshAll(); }, "Published. Teachers and students can now see it.")}
                >
                  Publish
                </Button>
              )}
              <Button
                variant="danger"
                aria-label="Delete timetable"
                onClick={() =>
                  window.confirm(`Delete "${d.name}"? This can't be undone.`) &&
                  act("del", async () => {
                    await api(base, { method: "DELETE" });
                    router.push("/timetables");
                  }, "Timetable deleted")
                }
              >
                <Trash2 size={15} />
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Generation report */}
      {isAdmin && (unscheduled.length > 0 || (d.generation?.warnings ?? []).length > 0) && (
        <Unscheduled
          rows={unscheduled}
          warnings={d.generation?.warnings ?? []}
          editable={editable}
          base={base}
          onPlaced={refreshAll}
        />
      )}

      {/* View selector */}
      <div className="no-print mb-4 flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="View" className="flex flex-wrap rounded-[8px] border border-rule bg-sheet p-0.5">
          {tabs.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={viewType === t.key}
              onClick={() => switchView(t.key)}
              className={cx(
                "rounded-[6px] px-3 py-1.5 text-sm",
                viewType === t.key ? "bg-ink font-semibold text-white" : "text-ink-soft hover:text-ink",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab.opt && (
          <Select aria-label={tab.label} className="w-72" value={ref ?? ""} onChange={(e) => setRef(Number(e.target.value))}>
            {d.options[tab.opt].map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        )}
        {view?.kind === "master" && (
          <div className="flex rounded-[8px] border border-rule bg-sheet p-0.5">
            {view.days.map((x) => (
              <button
                key={x.day}
                onClick={() => setMasterDay(x.day)}
                aria-pressed={masterDay === x.day}
                className={cx("rounded-[6px] px-2.5 py-1.5 text-sm", masterDay === x.day ? "bg-register-wash font-semibold text-register-dark" : "text-ink-soft")}
              >
                {x.short}
              </button>
            ))}
          </div>
        )}
        {editable && <p className="text-[13px] text-ink-faint">Drag a session to move it. Green cells are free for its teacher, class and a suitable room.</p>}
      </div>

      <ErrorNote error={viewErr} />
      {view ? (
        <>
          <div className="mb-2 flex flex-wrap items-baseline gap-x-3">
            <h2 className="font-display text-xl font-semibold">{view.title}</h2>
            <p className="text-sm text-ink-soft">{view.subtitle}</p>
            <p className="hidden text-sm text-ink-soft print:block">{d.name}</p>
          </div>
          <TimetableGrid
            view={view}
            editable={editable}
            masterDay={masterDay ?? undefined}
            highlight={highlight}
            dragging={dragging}
            focusId={focusId}
            onSelect={setSelected}
            onDragStart={startDrag}
            onDragEnd={endDrag}
            onDrop={onDrop}
          />
        </>
      ) : (
        !viewErr && <Loading />
      )}

      {/* Session details */}
      <EntryDrawer
        entry={selected}
        onClose={() => setSelected(null)}
        editable={editable}
        base={base}
        iid={iid!}
        conflicts={(conflicts?.conflicts ?? []).filter((c) => selected && c.entry_ids.includes(selected.id))}
        onMove={move}
        onDeleted={async () => {
          setSelected(null);
          toast("Session removed");
          await refreshAll();
        }}
        busy={busy === "move"}
      />

      {/* Rejected edit */}
      <Drawer open={!!blocked} onClose={() => setBlocked(null)} title="Not saved: this creates a conflict" width={480}>
        {blocked && (
          <div className="space-y-4">
            <p className="text-ink-soft">
              {blocked.entry.subject_name} for {blocked.entry.class_name} stays on {blocked.entry.day_name} {blocked.entry.time}.
            </p>
            {blocked.conflicts.map((c, i) => (
              <ConflictItem key={i} c={c} editable={editable} onApply={(s) => move(blocked.entry, { day: s.day, start: s.start, room_id: s.room_id }, "Moved")} />
            ))}
          </div>
        )}
      </Drawer>

      {/* Conflict panel */}
      <Drawer open={panel} onClose={() => setPanel(false)} title="Conflicts and warnings" width={520}>
        {!conflicts ? (
          <Loading />
        ) : conflicts.conflicts.length === 0 ? (
          <div>
            <p className="font-display text-lg font-semibold text-register">No conflicts</p>
            <p className="mt-1 text-ink-soft">
              No teacher, class or room is booked twice, every session is in a suitable room within everyone's availability, and each subject has its weekly lectures.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-ink-soft">
              Major conflicts block publishing. Choose a suggested slot to move the session there; the change is checked again before it's saved.
            </p>
            {conflicts.conflicts.map((c, i) => (
              <ConflictItem
                key={i}
                c={c}
                editable={editable}
                onShow={() => {
                  const eid = c.entry_ids[c.entry_ids.length - 1];
                  setFocusId(eid ?? null);
                  setPanel(false);
                  setViewType("institution");
                  setRef(null);
                  if (c.day != null) setMasterDay(c.day);
                }}
                onApply={async (s) => {
                  const eid = c.entry_ids[c.entry_ids.length - 1];
                  await move({ id: eid, subject_name: "Session", class_name: "" } as Entry, { day: s.day, start: s.start, room_id: s.room_id });
                }}
              />
            ))}
          </div>
        )}
      </Drawer>

      <ShareDrawer open={share} onClose={() => setShare(false)} base={base} token={d.share_token} onChange={() => tt.reload()} />
    </div>
  );
}

/* ------------------------------------------------------------------ pieces */

function ConflictItem({ c, editable, onApply, onShow }: { c: Conflict; editable: boolean; onApply: (s: Suggestion) => void; onShow?: () => void }) {
  return (
    <div className={cx("rounded-[8px] border p-3", c.severity === "major" ? "border-redpen/40" : "border-rule")}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className={cx("text-sm font-semibold", c.severity === "major" ? "text-redpen" : "text-ink")}>{CONFLICT_LABEL[c.type] ?? c.type}</span>
        {c.severity === "minor" ? <Pill>Warning</Pill> : onShow && c.entry_ids.length > 0 && (
          <button onClick={onShow} className="text-[13px] font-semibold text-register">Show on grid</button>
        )}
      </div>
      <p className="text-sm">{c.message}</p>
      {c.suggestions?.length > 0 && editable && (
        <div className="mt-2">
          <p className="mb-1 text-[13px] text-ink-faint">Free alternatives</p>
          <div className="flex flex-wrap gap-1.5">
            {c.suggestions.map((s, i) => (
              <button key={i} onClick={() => onApply(s)} className="rounded-[6px] border border-register/40 bg-register-wash px-2 py-1 text-[13px] text-register-dark hover:border-register">
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ExportMenu({
  onPick,
  onClose,
  viewType,
  refId,
  title,
}: {
  onPick: (format: string, view: string, ref?: number | null) => void;
  onClose: () => void;
  viewType: string;
  refId: number | null;
  title: string;
}) {
  useEffect(() => {
    const h = () => onClose();
    const t = setTimeout(() => window.addEventListener("click", h), 0);
    return () => {
      clearTimeout(t);
      window.removeEventListener("click", h);
    };
  }, [onClose]);
  const items: [string, () => void][] = [
    [`${title || "This view"} as PDF`, () => onPick("pdf", viewType, refId)],
    [`${title || "This view"} as Excel`, () => onPick("xlsx", viewType, refId)],
    ["Every class, one page each (PDF)", () => onPick("pdf", "class")],
    ["Every teacher, one page each (PDF)", () => onPick("pdf", "teacher")],
    ["Every room, one page each (PDF)", () => onPick("pdf", "room")],
    ["Whole timetable as Excel workbook", () => onPick("xlsx", "class")],
    ["All sessions as CSV", () => onPick("csv", "class")],
  ];
  return (
    <div className="absolute right-0 z-30 mt-1 w-[300px] rounded-[8px] border border-rule bg-sheet p-1 shadow-[0_10px_28px_rgba(27,35,64,0.14)]">
      {items.map(([label, fn]) => (
        <button key={label} onClick={fn} className="block w-full truncate rounded-[6px] px-3 py-2 text-left text-sm hover:bg-paper">
          {label}
        </button>
      ))}
    </div>
  );
}

function ShareDrawer({ open, onClose, base, token, onChange }: { open: boolean; onClose: () => void; base: string; token: string | null; onChange: () => void }) {
  const toast = useToast();
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(token ? `${window.location.origin}/share/${token}` : null);
  }, [token]);
  return (
    <Drawer open={open} onClose={onClose} title="Share a read-only link" width={480}>
      <p className="text-ink-soft">Anyone with the link can view and download this timetable without signing in. They can't edit it.</p>
      {url ? (
        <div className="mt-4 space-y-3">
          <Field label="Link">
            <Input readOnly value={url} onFocus={(e) => e.target.select()} />
          </Field>
          <div className="flex gap-2">
            <Button variant="primary" onClick={() => navigator.clipboard.writeText(url).then(() => toast("Link copied"))}>Copy link</Button>
            <Button
              variant="danger"
              onClick={async () => {
                await api(`${base}/share`, { method: "DELETE" });
                toast("Link turned off. The old link no longer works.");
                onChange();
              }}
            >
              Turn off link
            </Button>
          </div>
        </div>
      ) : (
        <Button
          className="mt-4"
          variant="primary"
          onClick={async () => {
            await api(`${base}/share`, { method: "POST" });
            onChange();
          }}
        >
          Create link
        </Button>
      )}
    </Drawer>
  );
}

function EntryDrawer({
  entry,
  onClose,
  editable,
  base,
  iid,
  conflicts,
  onMove,
  onDeleted,
  busy,
}: {
  entry: Entry | null;
  onClose: () => void;
  editable: boolean;
  base: string;
  iid: number;
  conflicts: Conflict[];
  onMove: (e: Entry, body: Record<string, any>, label?: string) => Promise<void>;
  onDeleted: () => void;
  busy: boolean;
}) {
  const rooms = useLoad(() => (editable ? api<any[]>(inst(iid, "/rooms")) : Promise.resolve([])), [iid, editable]);
  const teachers = useLoad(() => (editable ? api<any[]>(inst(iid, "/teachers")) : Promise.resolve([])), [iid, editable]);
  const [slots, setSlots] = useState<Suggestion[] | null>(null);
  const [room, setRoom] = useState<string>("");
  const [teacher, setTeacher] = useState<string>("");
  useEffect(() => {
    setSlots(null);
    setRoom(entry ? String(entry.room_id) : "");
    setTeacher(entry ? String(entry.teacher_id) : "");
  }, [entry]);

  const suitableRooms = useMemo(
    () => (rooms.data ?? []).filter((r) => r.active && (!entry || (entry.subject_kind === "lab" ? r.room_type === "lab" : r.room_type !== "lab"))),
    [rooms.data, entry],
  );

  if (!entry) return null;
  return (
    <Drawer open onClose={onClose} title={entry.subject_name} width={480}>
      <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-sm">
        <dt className="text-ink-faint">Class</dt>
        <dd className="font-semibold">{entry.class_name}</dd>
        <dt className="text-ink-faint">When</dt>
        <dd>
          {entry.day_name} {entry.time}
          {entry.length > 1 && <span className="text-ink-faint"> ({entry.length} periods)</span>}
        </dd>
        <dt className="text-ink-faint">Teacher</dt>
        <dd>{entry.teacher_name}</dd>
        <dt className="text-ink-faint">Room</dt>
        <dd>{entry.room_name}</dd>
        <dt className="text-ink-faint">Subject code</dt>
        <dd>{entry.subject_code}</dd>
        <dt className="text-ink-faint">Pinned</dt>
        <dd>{entry.locked ? "Yes, kept in place when regenerating" : "No"}</dd>
      </dl>

      {conflicts.length > 0 && (
        <div className="mt-4 space-y-2">
          {conflicts.map((c, i) => (
            <p key={i} className="rounded-[6px] bg-redpen-wash px-3 py-2 text-sm text-redpen">{c.message}</p>
          ))}
        </div>
      )}

      {editable && (
        <div className="mt-6 space-y-5">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => onMove(entry, { locked: !entry.locked }, entry.locked ? "Unpinned" : "Pinned")}>
              {entry.locked ? <PinOff size={14} /> : <Pin size={14} />} {entry.locked ? "Unpin" : "Pin in place"}
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={async () => {
                if (!window.confirm("Remove this session from the timetable? The subject will be short of its weekly lectures.")) return;
                await api(`${base}/entries/${entry.id}`, { method: "DELETE" });
                onDeleted();
              }}
            >
              <Trash2 size={14} /> Remove session
            </Button>
          </div>

          <div>
            <p className="mb-1 font-semibold">Move to a free period</p>
            {slots === null ? (
              <Button
                size="sm"
                onClick={async () => setSlots(await api<Suggestion[]>(`${base}/entries/${entry.id}/suggestions`, { query: { limit: 10 } }))}
              >
                <Wand2 size={14} /> Find free periods
              </Button>
            ) : slots.length === 0 ? (
              <p className="text-sm text-ink-soft">No period is free for this class, teacher and a suitable room at the same time.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {slots.map((s, i) => (
                  <button key={i} disabled={busy} onClick={() => onMove(entry, { day: s.day, start: s.start, room_id: s.room_id })}
                    className="rounded-[6px] border border-register/40 bg-register-wash px-2 py-1 text-[13px] text-register-dark hover:border-register">
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-[1fr_auto] items-end gap-2">
            <Field label="Room">
              <Select value={room} onChange={(e) => setRoom(e.target.value)}>
                {suitableRooms.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} ({r.capacity} seats)
                  </option>
                ))}
              </Select>
            </Field>
            <Button disabled={room === String(entry.room_id)} busy={busy} onClick={() => onMove(entry, { room_id: Number(room) }, "Room changed")}>
              Change room
            </Button>
          </div>
          <div className="grid grid-cols-[1fr_auto] items-end gap-2">
            <Field label="Teacher" hint="for a substitution">
              <Select value={teacher} onChange={(e) => setTeacher(e.target.value)}>
                {(teachers.data ?? []).filter((t) => t.active).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </Select>
            </Field>
            <Button disabled={teacher === String(entry.teacher_id)} busy={busy} onClick={() => onMove(entry, { teacher_id: Number(teacher) }, "Teacher changed")}>
              Assign
            </Button>
          </div>
          <p className="text-[13px] text-ink-faint">Every change is checked for teacher, class and room clashes before it's saved. Moved sessions are pinned automatically.</p>
        </div>
      )}
    </Drawer>
  );
}

function Unscheduled({ rows, warnings, editable, base, onPlaced }: { rows: any[]; warnings: string[]; editable: boolean; base: string; onPlaced: () => Promise<void> }) {
  const toast = useToast();
  const [open, setOpen] = useState<number | null>(null);
  const [slots, setSlots] = useState<Suggestion[] | null>(null);
  return (
    <div className="no-print mb-5 rounded-[8px] border border-redpen/30 bg-sheet p-4">
      {rows.length > 0 && (
        <>
          <p className="font-semibold text-redpen">{rows.length} session(s) could not be placed</p>
          <ul className="mt-2 divide-y divide-rule-soft">
            {rows.map((u, i) => (
              <li key={i} className="py-2 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <span className="font-semibold">{u.subject_name}</span> for {u.class_name} with {u.teacher_name}
                    <p className="text-ink-soft">{u.reason}</p>
                  </div>
                  {editable && (
                    <Button size="sm" onClick={async () => {
                      setOpen(i);
                      setSlots(await api<Suggestion[]>(`${base}/assignments/${u.assignment_id}/free-slots`, { query: { limit: 12 } }));
                    }}>
                      Place it
                    </Button>
                  )}
                </div>
                {open === i && slots && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {slots.length === 0 && <span className="text-ink-soft">No free slot. Free up the teacher or a room first, or add a room of this type.</span>}
                    {slots.map((s, k) => (
                      <button key={k} className="rounded-[6px] border border-register/40 bg-register-wash px-2 py-1 text-[13px] text-register-dark"
                        onClick={async () => {
                          try {
                            await api(`${base}/entries`, { method: "POST", body: { assignment_id: u.assignment_id, day: s.day, period_index: s.period_index, room_id: s.room_id, locked: true } });
                            toast(`Placed on ${s.label}`);
                            setOpen(null);
                            await onPlaced();
                          } catch (e: any) {
                            toast(e.message, "error");
                          }
                        }}>
                        {s.label}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[13px] text-ink-faint">This list is from the last generation run; regenerate to refresh it.</p>
        </>
      )}
      {warnings.length > 0 && (
        <ul className={cx("text-sm text-ink-soft", rows.length > 0 && "mt-3 border-t border-rule-soft pt-3")}>
          {warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  );
}
