"use client";

import ResourcePage, { nameOf, optsFrom, type ResourceConfig } from "@/components/ResourcePage";
import { Select } from "@/components/ui";

const subjectLabel = (s: any) => `${s.code} ${s.name}`;

const cfg: ResourceConfig = {
  title: "Curriculum",
  singular: "Subject for a class",
  path: "/assignments",
  intro: "What each class studies, who teaches it and how many periods a week. Labs usually run as two back-to-back periods.",
  lookups: ["classes", "subjects", "teachers", "rooms"],
  describe: () => "this curriculum line",
  rowFilter: (r, f) => !f.class_id || String(r.class_id) === f.class_id,
  defaults: (f) => (f.class_id ? { class_id: f.class_id } : {}),
  filter: (r, q, l) =>
    `${nameOf(l.classes, r.class_id)} ${subjectLabel(l.subjects?.find((s: any) => s.id === r.subject_id) ?? { code: "", name: "" })} ${nameOf(l.teachers, r.teacher_id)}`
      .toLowerCase()
      .includes(q),
  toolbar: (l, setFilter, f) => (
    <Select aria-label="Class" className="w-64" value={f.class_id ?? ""} onChange={(e) => setFilter({ class_id: e.target.value })}>
      <option value="">All classes</option>
      {(l.classes ?? []).map((c: any) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </Select>
  ),
  fields: [
    { key: "class_id", label: "Class", type: "select", required: true, options: (l) => optsFrom(l.classes), createOnly: true },
    { key: "subject_id", label: "Subject", type: "select", required: true, options: (l) => optsFrom(l.subjects, subjectLabel), createOnly: true },
    { key: "teacher_id", label: "Teacher", type: "select", required: true, options: (l) => optsFrom(l.teachers?.filter((t: any) => t.active)) },
    { key: "lectures_per_week", label: "Periods per week", type: "number", required: true, default: 3, half: true },
    { key: "consecutive_periods", label: "Periods per session", type: "number", required: true, default: 1, half: true, hint: "2 for a double lab" },
    { key: "fixed_room_id", label: "Always in room", type: "select", options: (l) => optsFrom(l.rooms), placeholder: "Any suitable room" },
  ],
  sort: (a, b) => a.class_id - b.class_id || a.subject_id - b.subject_id,
  columns: [
    { label: "Class", render: (r, l) => <span className="font-semibold">{nameOf(l.classes, r.class_id)}</span> },
    {
      label: "Subject",
      render: (r, l) => {
        const s = l.subjects?.find((x: any) => x.id === r.subject_id);
        return s ? (
          <span>
            <span className="font-semibold">{s.code}</span> <span className="text-ink-soft">{s.name}</span>
          </span>
        ) : null;
      },
    },
    { label: "Teacher", render: (r, l) => nameOf(l.teachers, r.teacher_id) },
    {
      label: "Per week",
      className: "text-right",
      render: (r) => (
        <span className="tnum">
          {r.lectures_per_week}
          {r.consecutive_periods > 1 && <span className="text-ink-faint"> as {r.lectures_per_week / r.consecutive_periods}×{r.consecutive_periods}</span>}
        </span>
      ),
    },
    { label: "Room", render: (r, l) => <span className="text-ink-soft">{r.fixed_room_id ? nameOf(l.rooms, r.fixed_room_id) : "Any suitable"}</span> },
  ],
};

export default function CurriculumPage() {
  return <ResourcePage cfg={cfg} />;
}
