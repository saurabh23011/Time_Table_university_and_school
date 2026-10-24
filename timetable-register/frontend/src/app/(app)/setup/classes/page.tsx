"use client";

import ResourcePage, { nameOf, optsFrom, type ResourceConfig } from "@/components/ResourcePage";

const cfg: ResourceConfig = {
  title: "Classes",
  singular: "Class",
  path: "/classes",
  intro: "Classes, sections, semesters and batches that attend lectures together. A class follows its department's working hours unless you choose a different schedule here.",
  lookups: ["departments", "schedules"],
  sort: (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }),
  fields: [
    { key: "name", label: "Name", required: true, placeholder: "B.Tech CSE Sem 3 A" },
    { key: "department_id", label: "Department", type: "select", options: (l) => optsFrom(l.departments) },
    { key: "program", label: "Programme", nullable: true, half: true },
    { key: "term", label: "Semester / year / grade", nullable: true, half: true },
    { key: "section", label: "Section", nullable: true, half: true },
    { key: "batch", label: "Batch", nullable: true, half: true, placeholder: "2024–28" },
    { key: "strength", label: "Students", type: "number", required: true, default: 40, half: true },
    { key: "schedule_id", label: "Working hours", type: "select", options: (l) => optsFrom(l.schedules), placeholder: "Inherit from department", half: true },
    { key: "unavailable", label: "Class unavailable", type: "windows", hint: "assemblies, field trips, exams" },
  ],
  columns: [
    { label: "Class", render: (r) => <span className="font-semibold">{r.name}</span> },
    { label: "Department", render: (r, l) => nameOf(l.departments, r.department_id) },
    { label: "Students", render: (r) => <span className="tnum">{r.strength}</span>, className: "text-right" },
    { label: "Batch", render: (r) => <span className="text-ink-soft">{r.batch}</span> },
    { label: "Working hours", render: (r, l) => <span className="text-ink-soft">{r.schedule_id ? nameOf(l.schedules, r.schedule_id) : "From department"}</span> },
  ],
};

export default function ClassesPage() {
  return <ResourcePage cfg={cfg} />;
}
