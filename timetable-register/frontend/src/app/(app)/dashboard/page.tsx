"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, ErrorNote, Loading, PageHeader, Panel, Pill, Select, StatusPill, cx, useLoad } from "@/components/ui";
import { api, inst } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CONFLICT_LABEL } from "@/lib/types";

export default function Dashboard() {
  const { iid, can } = useAuth();
  const [dept, setDept] = useState<string>("");
  const depts = useLoad(() => api<any[]>(inst(iid!, "/departments")), [iid]);
  const { data, error, loading } = useLoad(
    () => api<any>(inst(iid!, "/dashboard"), { query: { department_id: dept || undefined } }),
    [iid, dept],
  );

  return (
    <div className="max-w-[1180px]">
      <PageHeader
        title="Dashboard"
        intro={data ? `${data.institution.name}. Figures use the timetables currently in force.` : undefined}
        actions={
          can("department_admin") && (
            <Select aria-label="Filter by department" value={dept} onChange={(e) => setDept(e.target.value)} className="w-60">
              <option value="">Whole institution</option>
              {(depts.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          )
        }
      />
      <ErrorNote error={error} />
      {loading && !data ? (
        <Loading />
      ) : data ? (
        <>
          <Stats t={data.totals} />
          <div className="mt-6 grid gap-6 lg:grid-cols-[1.25fr_1fr]">
            <Workload rows={data.teacher_workload} />
            <div className="flex flex-col gap-6">
              <Panel title="Conflicts">
                <div className="px-4 py-3">
                  {data.totals.conflicts === 0 ? (
                    <p className="text-ink-soft">
                      No conflicts in the timetables in use{data.totals.unscheduled ? "" : ", and every lecture is placed"}.
                    </p>
                  ) : (
                    <ul className="space-y-1.5">
                      {Object.entries(data.conflicts_by_type as Record<string, number>).map(([k, n]) => (
                        <li key={k} className="flex justify-between text-sm">
                          <span>{CONFLICT_LABEL[k] ?? k}</span>
                          <span className="tnum font-semibold text-redpen">{n}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {data.totals.unscheduled > 0 && (
                    <p className="mt-2 text-sm text-redpen">{data.totals.unscheduled} session(s) could not be placed by the generator.</p>
                  )}
                </div>
              </Panel>
              <DailyLoad days={data.daily_load} />
              <Recent rows={data.recent_timetables} />
            </div>
          </div>
          <div className="mt-6">
            <Rooms rows={data.room_utilization} avg={data.avg_room_utilization} />
          </div>
        </>
      ) : null}
    </div>
  );
}

function Stats({ t }: { t: any }) {
  const items: [string, number, string?][] = [
    ["Teachers", t.teachers],
    ["Classes", t.classes],
    ["Subjects", t.subjects],
    ["Classrooms", t.classrooms],
    ["Laboratories", t.laboratories],
    ["Timetables", t.timetables],
    ["Conflicts", t.conflicts, t.conflicts ? "text-redpen" : "text-register"],
  ];
  return (
    <div className="grid grid-cols-2 overflow-hidden rounded-[8px] border border-rule bg-sheet sm:grid-cols-4 lg:grid-cols-7">
      {items.map(([label, n, tone], i) => (
        <div key={label} className={cx("px-4 py-4", i > 0 && "border-l border-rule-soft", "border-b border-rule-soft lg:border-b-0")}>
          <p className={cx("font-display tnum text-[32px] font-semibold leading-none", tone)}>{n}</p>
          <p className="mt-1.5 text-sm text-ink-soft">{label}</p>
        </div>
      ))}
    </div>
  );
}

function Bar({ pct, tone = "green" }: { pct: number; tone?: "green" | "red" | "ink" }) {
  const color = tone === "red" ? "bg-redpen" : tone === "ink" ? "bg-ink-soft" : "bg-register";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-rule-soft">
      <div className={cx("h-full rounded-full", color)} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </div>
  );
}

function Workload({ rows }: { rows: any[] }) {
  const max = Math.max(1, ...rows.map((r) => Math.max(r.scheduled, r.max_per_week ?? 0, r.assigned)));
  return (
    <Panel title="Teacher workload" actions={<span className="text-[13px] text-ink-faint">periods per week</span>}>
      {rows.length === 0 ? (
        <Empty title="No teachers yet">Add teachers under Set up to see their weekly load.</Empty>
      ) : (
        <ul className="divide-y divide-rule-soft">
          {rows.slice(0, 14).map((r) => {
            const over = r.max_per_week != null && r.scheduled > r.max_per_week;
            return (
              <li key={r.teacher_id} className="grid grid-cols-[minmax(0,1fr)_120px_64px] items-center gap-3 px-4 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{r.name}</p>
                  <p className="truncate text-[13px] text-ink-faint">{r.department}</p>
                </div>
                <div className="relative">
                  <Bar pct={(100 * r.scheduled) / max} tone={over ? "red" : "green"} />
                  {r.max_per_week && (
                    <span
                      className="absolute -top-1 h-4 w-[2px] bg-ink"
                      style={{ left: `${(100 * r.max_per_week) / max}%` }}
                      title={`Limit ${r.max_per_week}`}
                    />
                  )}
                </div>
                <p className="tnum text-right text-sm">
                  <span className="font-semibold">{r.scheduled}</span>
                  <span className="text-ink-faint">/{r.max_per_week ?? "—"}</span>
                </p>
              </li>
            );
          })}
        </ul>
      )}
      {rows.length > 14 && <p className="border-t border-rule-soft px-4 py-2 text-[13px] text-ink-faint">Showing the 14 busiest of {rows.length} teachers.</p>}
    </Panel>
  );
}

function Rooms({ rows, avg }: { rows: any[]; avg: number }) {
  return (
    <Panel title="Room utilisation" actions={<span className="text-[13px] text-ink-faint">average {avg}% of teaching periods</span>}>
      <ul className="grid gap-x-8 px-4 py-2 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((r) => (
          <li key={r.room_id} className="py-2">
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
              <span className="truncate font-semibold">
                {r.name}
                {r.room_type === "lab" && <span className="ml-1.5 font-normal text-ink-faint">lab</span>}
              </span>
              <span className="tnum text-ink-soft">
                {r.used}/{r.available}
              </span>
            </div>
            <Bar pct={r.utilization} tone={r.room_type === "lab" ? "ink" : "green"} />
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function DailyLoad({ days }: { days: { name: string; periods: number }[] }) {
  const max = Math.max(1, ...days.map((d) => d.periods));
  return (
    <Panel title="Periods taught each day">
      <div className="flex h-[132px] items-end gap-3 px-4 pb-3 pt-4">
        {days.map((d) => (
          <div key={d.name} className="flex flex-1 flex-col items-center gap-1.5">
            <span className="tnum text-[12px] text-ink-soft">{d.periods}</span>
            <div className="w-full max-w-[38px] rounded-t-[3px] bg-register" style={{ height: `${(70 * d.periods) / max}px` }} />
            <span className="text-[12px] font-semibold text-ink-soft">{d.name}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Recent({ rows }: { rows: any[] }) {
  return (
    <Panel title="Recent timetables" actions={<Link href="/timetables" className="text-sm font-semibold text-register">All timetables</Link>}>
      {rows.length === 0 ? (
        <Empty title="Nothing generated yet" action={<Link href="/timetables" className="font-semibold text-register">Generate a timetable</Link>} />
      ) : (
        <ul className="divide-y divide-rule-soft">
          {rows.map((t) => (
            <li key={t.id}>
              <Link href={`/timetables/${t.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-paper">
                <span className="truncate text-sm font-semibold">{t.name}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {t.conflicts > 0 && <Pill tone="red">{t.conflicts} conflicts</Pill>}
                  <StatusPill status={t.status} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
