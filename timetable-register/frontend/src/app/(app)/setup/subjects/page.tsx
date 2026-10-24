"use client";

import ResourcePage, { nameOf, optsFrom, type ResourceConfig } from "@/components/ResourcePage";

const ROOM_NEEDS = [
  { value: "classroom", label: "Classroom" },
  { value: "lab", label: "Laboratory" },
  { value: "seminar_hall", label: "Seminar hall" },
  { value: "tutorial_room", label: "Tutorial room" },
  { value: "other", label: "Other" },
  { value: "any", label: "Any room" },
];

const cfg: ResourceConfig = {
  title: "Subjects",
  singular: "Subject",
  path: "/subjects",
  intro: "Courses taught across the institution. Lab subjects are placed only in labs, and in a lab with the matching feature when one is given.",
  lookups: ["departments"],
  sort: (a, b) => a.code.localeCompare(b.code),
  filter: (r, q) => `${r.code} ${r.name}`.toLowerCase().includes(q),
  describe: (r) => `${r.code} ${r.name}`,
  fields: [
    { key: "code", label: "Code", required: true, half: true },
    { key: "kind", label: "Kind", type: "select", required: true, default: "theory", half: true,
      options: [{ value: "theory", label: "Theory" }, { value: "lab", label: "Lab / practical" }, { value: "tutorial", label: "Tutorial" }] },
    { key: "name", label: "Name", required: true },
    { key: "department_id", label: "Department", type: "select", options: (l) => optsFrom(l.departments) },
    { key: "room_type", label: "Needs room type", type: "select", options: ROOM_NEEDS, placeholder: "Match the kind", half: true },
    { key: "room_tag", label: "Lab feature", nullable: true, placeholder: "e.g. computer", half: true },
    { key: "color", label: "Colour on the timetable", nullable: true, placeholder: "#2563eb", hint: "optional" },
  ],
  columns: [
    {
      label: "Subject",
      render: (r) => (
        <span className="flex items-center gap-2">
          <span className="h-3 w-3 shrink-0 rounded-[3px]" style={{ background: r.color ?? "#94a3b8" }} />
          <span>
            <span className="font-semibold">{r.code}</span> <span className="text-ink-soft">{r.name}</span>
          </span>
        </span>
      ),
    },
    { label: "Kind", render: (r) => <span className="capitalize">{r.kind}</span> },
    { label: "Room", render: (r) => <span className="text-ink-soft">{r.room_type.replace("_", " ")}{r.room_tag ? ` (${r.room_tag})` : ""}</span> },
    { label: "Department", render: (r, l) => nameOf(l.departments, r.department_id) },
  ],
};

export default function SubjectsPage() {
  return <ResourcePage cfg={cfg} />;
}
