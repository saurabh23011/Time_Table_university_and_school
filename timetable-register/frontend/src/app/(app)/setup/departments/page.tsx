"use client";

import ResourcePage, { nameOf, optsFrom, type ResourceConfig } from "@/components/ResourcePage";

const KINDS = [
  { value: "school", label: "School / faculty" },
  { value: "department", label: "Department" },
  { value: "wing", label: "Wing (for schools)" },
];

const cfg: ResourceConfig = {
  title: "Departments",
  singular: "Department",
  path: "/departments",
  writeRole: "institution_admin",
  intro: "Organise the institution into schools and departments. Each can run on its own working hours; departments inherit their school's hours unless set.",
  lookups: ["departments", "schedules"],
  sort: (a, b) => (a.parent_id ?? 0) - (b.parent_id ?? 0) || a.name.localeCompare(b.name),
  fields: [
    { key: "name", label: "Name", required: true },
    { key: "code", label: "Code", required: true, half: true },
    { key: "kind", label: "Level", type: "select", options: KINDS, required: true, default: "department", half: true },
    { key: "parent_id", label: "Part of", type: "select", options: (l) => optsFrom(l.departments), placeholder: "Top level" },
    { key: "schedule_id", label: "Working hours", type: "select", options: (l) => optsFrom(l.schedules), placeholder: "Inherit" },
  ],
  columns: [
    { label: "Name", render: (r) => <span className="font-semibold">{r.name}</span> },
    { label: "Code", render: (r) => r.code },
    { label: "Level", render: (r) => KINDS.find((k) => k.value === r.kind)?.label ?? r.kind },
    { label: "Part of", render: (r, l) => nameOf(l.departments, r.parent_id) },
    { label: "Working hours", render: (r, l) => <span className="text-ink-soft">{r.schedule_id ? nameOf(l.schedules, r.schedule_id) : "Inherited"}</span> },
  ],
};

export default function DepartmentsPage() {
  return <ResourcePage cfg={cfg} />;
}
