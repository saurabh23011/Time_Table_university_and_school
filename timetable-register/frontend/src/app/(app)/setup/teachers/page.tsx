"use client";

import ResourcePage, { nameOf, optsFrom, type ResourceConfig } from "@/components/ResourcePage";
import { Pill } from "@/components/ui";
import { DAY_SHORT, type Window } from "@/lib/types";

const fmtWindows = (ws: Window[]) => ws.map((w) => `${DAY_SHORT[w.day]} ${w.start}–${w.end}`).join(", ");

const cfg: ResourceConfig = {
  title: "Teachers",
  singular: "Teacher",
  path: "/teachers",
  intro: "Who teaches, when they can teach, and how much. Unavailable times and working hours are never broken by the generator; preferences are honoured where possible.",
  lookups: ["departments"],
  sort: (a, b) => a.name.localeCompare(b.name),
  filter: (r, q) => `${r.name} ${r.code ?? ""} ${r.designation ?? ""}`.toLowerCase().includes(q),
  fields: [
    { key: "name", label: "Full name", required: true },
    { key: "code", label: "Employee ID", half: true, nullable: true },
    { key: "designation", label: "Designation", half: true, nullable: true },
    { key: "email", label: "Email", type: "email", nullable: true },
    { key: "department_id", label: "Department", type: "select", options: (l) => optsFrom(l.departments) },
    { key: "work_start", label: "Works from", type: "time", half: true, nullable: true, hint: "optional" },
    { key: "work_end", label: "Works until", type: "time", half: true, nullable: true },
    { key: "max_per_day", label: "Max periods a day", type: "number", half: true },
    { key: "max_per_week", label: "Max periods a week", type: "number", half: true },
    { key: "max_consecutive", label: "Max back-to-back periods", type: "number", half: true, hint: "preference" },
    { key: "active", label: "Active (can be scheduled)", type: "checkbox", default: true, half: true },
    { key: "unavailable", label: "Unavailable", type: "windows", hint: "never scheduled at these times" },
    { key: "preferred", label: "Prefers to teach", type: "windows", hint: "soft preference" },
    { key: "avoid", label: "Prefers not to teach", type: "windows", hint: "soft preference" },
  ],
  columns: [
    {
      label: "Teacher",
      render: (r) => (
        <>
          <p className="font-semibold">{r.name}</p>
          <p className="text-[13px] text-ink-faint">{r.designation}</p>
        </>
      ),
    },
    { label: "Department", render: (r, l) => nameOf(l.departments, r.department_id) },
    {
      label: "Limits",
      render: (r) => (
        <span className="tnum text-ink-soft">
          {r.max_per_day ?? "–"}/day, {r.max_per_week ?? "–"}/week
          {r.work_start && <span className="block text-[13px]">Hours {r.work_start}–{r.work_end ?? "close"}</span>}
        </span>
      ),
    },
    {
      label: "Availability",
      render: (r) =>
        r.unavailable.length ? (
          <span className="text-[13px] text-ink-soft">Off: {fmtWindows(r.unavailable)}</span>
        ) : (
          <span className="text-[13px] text-ink-faint">Available all periods</span>
        ),
    },
    { label: "Status", render: (r) => (r.active ? <Pill tone="green">Active</Pill> : <Pill>Inactive</Pill>) },
  ],
};

export default function TeachersPage() {
  return <ResourcePage cfg={cfg} />;
}
