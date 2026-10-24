"use client";

import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, ErrorNote, Field, Input, Loading, PageHeader, Panel, Pill, Select, cx, useLoad, useToast } from "@/components/ui";
import { api, inst } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { DAY_SHORT } from "@/lib/types";

interface Brk {
  name: string;
  kind: "break" | "lunch";
  after_period: number;
  minutes: number;
}
interface Config {
  working_days: number[];
  day_start: string;
  day_end: string;
  lecture_minutes: number;
  periods_per_day: number;
  breaks: Brk[];
  day_overrides: Record<string, { periods_per_day?: number; day_start?: string; day_end?: string }>;
}

const BLANK: Config = {
  working_days: [0, 1, 2, 3, 4],
  day_start: "09:00",
  day_end: "17:00",
  lecture_minutes: 60,
  periods_per_day: 7,
  breaks: [
    { name: "Short break", kind: "break", after_period: 2, minutes: 15 },
    { name: "Lunch", kind: "lunch", after_period: 4, minutes: 45 },
  ],
  day_overrides: {},
};

export default function SchedulesPage() {
  const { iid, institution, can, refreshInstitutions } = useAuth();
  const toast = useToast();
  const list = useLoad(() => api<any[]>(inst(iid!, "/schedules")), [iid]);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [name, setName] = useState("");
  const [cfg, setCfg] = useState<Config>(BLANK);
  const [preview, setPreview] = useState<any>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canWrite = can("institution_admin");

  useEffect(() => {
    if (selected === null && list.data?.length) setSelected(list.data[0].id);
  }, [list.data, selected]);

  useEffect(() => {
    if (selected === "new") {
      setName("New schedule");
      setCfg(BLANK);
    } else if (selected != null) {
      const s = list.data?.find((x) => x.id === selected);
      if (s) {
        setName(s.name);
        setCfg({ ...BLANK, ...s.config, day_overrides: s.config.day_overrides ?? {} });
      }
    }
    setError(null);
  }, [selected, list.data]);

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        setPreview(await api(inst(iid!, "/schedules/preview"), { method: "POST", body: cfg }));
        setPreviewErr(null);
      } catch (e: any) {
        setPreviewErr(e.message);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [cfg, iid]);

  const set = (patch: Partial<Config>) => setCfg((c) => ({ ...c, ...patch }));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (selected === "new") {
        const s = await api<any>(inst(iid!, "/schedules"), { method: "POST", body: { name, config: cfg } });
        setSelected(s.id);
      } else {
        await api(inst(iid!, `/schedules/${selected}`), { method: "PATCH", body: { name, config: cfg } });
      }
      toast("Working hours saved");
      list.reload();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function makeDefault(id: number) {
    await api(inst(iid!, ""), { method: "PATCH", body: { default_schedule_id: id } });
    await refreshInstitutions();
    toast("Default working hours updated");
  }

  async function remove(id: number) {
    if (!window.confirm("Delete these working hours? Departments and classes using them fall back to the institution default.")) return;
    await api(inst(iid!, `/schedules/${id}`), { method: "DELETE" });
    setSelected(null);
    list.reload();
  }

  return (
    <div className="max-w-[1180px]">
      <PageHeader
        title="Working hours"
        intro="Days, hours, period length, breaks and lunch. Create one per pattern you need (for example engineering vs. sciences, or a Saturday half-day) and assign them to departments or classes."
        actions={
          canWrite && (
            <Button onClick={() => setSelected("new")}>
              <Plus size={16} /> New schedule
            </Button>
          )
        }
      />
      {list.loading && !list.data ? (
        <Loading />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
          <Panel>
            <ul className="p-1.5">
              {(list.data ?? []).map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => setSelected(s.id)}
                    className={cx("w-full rounded-[6px] px-3 py-2 text-left", selected === s.id ? "bg-paper font-semibold" : "hover:bg-paper/60")}
                  >
                    <span className="block text-sm">{s.name}</span>
                    {institution?.default_schedule_id === s.id && <span className="text-[12px] text-register">Institution default</span>}
                  </button>
                </li>
              ))}
              {selected === "new" && <li className="rounded-[6px] bg-paper px-3 py-2 text-sm font-semibold">New schedule</li>}
            </ul>
          </Panel>

          <div className="grid min-w-0 gap-6 2xl:grid-cols-[minmax(480px,1fr)_1fr]">
            <Panel
              className="min-w-0"
              title="Settings"
              actions={
                canWrite && typeof selected === "number" && (
                  <div className="flex gap-1">
                    {institution?.default_schedule_id !== selected && (
                      <Button size="sm" variant="ghost" onClick={() => makeDefault(selected)}>
                        Make default
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => remove(selected)} aria-label="Delete schedule">
                      <Trash2 size={14} />
                    </Button>
                  </div>
                )
              }
            >
              <fieldset disabled={!canWrite} className="space-y-4 p-4">
                <Field label="Name">
                  <Input value={name} onChange={(e) => setName(e.target.value)} />
                </Field>
                <div>
                  <p className="mb-1 text-[13px] font-semibold text-ink-soft">Working days</p>
                  <div className="flex flex-wrap gap-1.5">
                    {DAY_SHORT.map((d, i) => {
                      const on = cfg.working_days.includes(i);
                      return (
                        <button
                          key={d}
                          type="button"
                          aria-pressed={on}
                          onClick={() =>
                            set({ working_days: on ? cfg.working_days.filter((x) => x !== i) : [...cfg.working_days, i].sort() })
                          }
                          className={cx(
                            "h-8 w-12 rounded-[6px] border text-sm font-semibold",
                            on ? "border-register bg-register-wash text-register-dark" : "border-rule text-ink-faint",
                          )}
                        >
                          {d}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Day starts"><Input type="time" value={cfg.day_start} onChange={(e) => set({ day_start: e.target.value })} /></Field>
                  <Field label="Day ends by"><Input type="time" value={cfg.day_end} onChange={(e) => set({ day_end: e.target.value })} /></Field>
                  <Field label="Lecture length" hint="minutes">
                    <Input type="number" min={10} value={cfg.lecture_minutes} onChange={(e) => set({ lecture_minutes: Number(e.target.value) })} />
                  </Field>
                  <Field label="Periods per day">
                    <Input type="number" min={1} value={cfg.periods_per_day} onChange={(e) => set({ periods_per_day: Number(e.target.value) })} />
                  </Field>
                </div>

                <div>
                  <p className="mb-1 text-[13px] font-semibold text-ink-soft">Breaks and lunch</p>
                  <div className="space-y-2">
                    {cfg.breaks.map((b, i) => (
                      <div key={i} className="grid grid-cols-[minmax(0,1fr)_100px_116px_76px_28px] items-center gap-2">
                        <Input aria-label="Break name" value={b.name} onChange={(e) => set({ breaks: cfg.breaks.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
                        <Select aria-label="Kind" value={b.kind} onChange={(e) => set({ breaks: cfg.breaks.map((x, j) => (j === i ? { ...x, kind: e.target.value as Brk["kind"] } : x)) })}>
                          <option value="break">Break</option>
                          <option value="lunch">Lunch</option>
                        </Select>
                        <Select aria-label="After period" value={b.after_period} onChange={(e) => set({ breaks: cfg.breaks.map((x, j) => (j === i ? { ...x, after_period: Number(e.target.value) } : x)) })}>
                          {Array.from({ length: Math.max(1, cfg.periods_per_day - 1) }, (_, k) => (
                            <option key={k + 1} value={k + 1}>after P{k + 1}</option>
                          ))}
                        </Select>
                        <Input aria-label="Minutes" type="number" min={1} value={b.minutes} onChange={(e) => set({ breaks: cfg.breaks.map((x, j) => (j === i ? { ...x, minutes: Number(e.target.value) } : x)) })} />
                        <button type="button" aria-label="Remove break" onClick={() => set({ breaks: cfg.breaks.filter((_, j) => j !== i) })} className="text-ink-faint hover:text-redpen">
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))}
                    <Button type="button" size="sm" variant="ghost" onClick={() => set({ breaks: [...cfg.breaks, { name: "Break", kind: "break", after_period: 1, minutes: 10 }] })}>
                      <Plus size={14} /> Add a break
                    </Button>
                  </div>
                </div>

                <div>
                  <p className="mb-1 text-[13px] font-semibold text-ink-soft">Days that differ</p>
                  <p className="mb-2 text-[13px] text-ink-faint">For example a Saturday with fewer periods.</p>
                  <div className="space-y-2">
                    {Object.entries(cfg.day_overrides).map(([day, o]) => (
                      <div key={day} className="grid grid-cols-[72px_1fr_1fr_28px] items-center gap-2">
                        <span className="text-sm font-semibold">{DAY_SHORT[Number(day)]}</span>
                        <Input aria-label="Periods that day" type="number" min={1} placeholder="periods" value={o.periods_per_day ?? ""}
                          onChange={(e) => set({ day_overrides: { ...cfg.day_overrides, [day]: { ...o, periods_per_day: e.target.value ? Number(e.target.value) : undefined } } })} />
                        <Input aria-label="Starts at" type="time" value={o.day_start ?? ""}
                          onChange={(e) => set({ day_overrides: { ...cfg.day_overrides, [day]: { ...o, day_start: e.target.value || undefined } } })} />
                        <button type="button" aria-label="Remove" className="text-ink-faint hover:text-redpen"
                          onClick={() => { const n = { ...cfg.day_overrides }; delete n[day]; set({ day_overrides: n }); }}>
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))}
                    <Select aria-label="Add a day that differs" value="" onChange={(e) => e.target.value && set({ day_overrides: { ...cfg.day_overrides, [e.target.value]: { periods_per_day: Math.max(1, Math.floor(cfg.periods_per_day / 2)) } } })} className="w-56">
                      <option value="">Add a day that differs…</option>
                      {cfg.working_days.filter((d) => !(String(d) in cfg.day_overrides)).map((d) => (
                        <option key={d} value={d}>{DAY_SHORT[d]}</option>
                      ))}
                    </Select>
                  </div>
                </div>
                <ErrorNote error={error} />
                {canWrite && (
                  <Button variant="primary" busy={busy} onClick={save} disabled={!!previewErr}>
                    Save working hours
                  </Button>
                )}
              </fieldset>
            </Panel>

            <Panel className="min-w-0" title="The day this produces" actions={preview && <Pill>{preview.total_periods} periods a week</Pill>}>
              <div className="p-4">
                {previewErr ? (
                  <ErrorNote error={previewErr} />
                ) : !preview ? (
                  <Loading />
                ) : (
                  <div className="flex gap-2 overflow-x-auto">
                    {preview.days.map((d: any) => (
                      <div key={d.day} className="min-w-[92px] flex-1">
                        <p className="mb-1.5 text-center text-sm font-semibold">{DAY_SHORT[d.day]}</p>
                        <div className="space-y-1">
                          {d.items.map((it: any, i: number) =>
                            it.type === "period" ? (
                              <div key={i} className="rounded-[4px] border border-rule bg-sheet px-1.5 py-1 text-center">
                                <p className="text-[12px] font-semibold">{it.label}</p>
                                <p className="tnum text-[11.5px] text-ink-soft">{it.time}</p>
                              </div>
                            ) : (
                              <div key={i} className="hatch rounded-[4px] px-1.5 py-0.5 text-center text-[11.5px] text-ink-soft">
                                {it.name}
                              </div>
                            ),
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
