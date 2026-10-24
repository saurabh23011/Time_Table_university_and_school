"use client";

import ResourcePage, { nameOf, optsFrom, type ResourceConfig } from "@/components/ResourcePage";
import { Pill } from "@/components/ui";

const ROOM_TYPES = [
  { value: "classroom", label: "Classroom" },
  { value: "lab", label: "Laboratory" },
  { value: "seminar_hall", label: "Seminar hall" },
  { value: "auditorium", label: "Auditorium" },
  { value: "tutorial_room", label: "Tutorial room" },
  { value: "other", label: "Other (ground, studio…)" },
];
const typeLabel = (t: string) => ROOM_TYPES.find((x) => x.value === t)?.label ?? t;

const cfg: ResourceConfig = {
  title: "Rooms & labs",
  singular: "Room",
  path: "/rooms",
  writeRole: "institution_admin",
  intro: "Classrooms, laboratories and halls. A subject that needs a lab is only placed in a lab of the right kind with enough seats.",
  lookups: ["departments"],
  sort: (a, b) => a.room_type.localeCompare(b.room_type) || a.name.localeCompare(b.name, undefined, { numeric: true }),
  fields: [
    { key: "name", label: "Name", required: true, half: true },
    { key: "code", label: "Code", half: true, nullable: true },
    { key: "room_type", label: "Type", type: "select", options: ROOM_TYPES, required: true, default: "classroom", half: true },
    { key: "capacity", label: "Seats", type: "number", required: true, default: 60, half: true },
    { key: "building", label: "Building", nullable: true, half: true },
    { key: "department_id", label: "Belongs to", type: "select", options: (l) => optsFrom(l.departments), half: true, placeholder: "Shared" },
    { key: "tags", label: "Lab kind / features", type: "tags", placeholder: "computer, projector", hint: "comma separated" },
    { key: "active", label: "Available for scheduling", type: "checkbox", default: true },
    { key: "unavailable", label: "Unavailable", type: "windows", hint: "maintenance, exams, events" },
  ],
  columns: [
    { label: "Room", render: (r) => <span className="font-semibold">{r.name}</span> },
    { label: "Type", render: (r) => typeLabel(r.room_type) },
    { label: "Seats", render: (r) => <span className="tnum">{r.capacity}</span>, className: "text-right" },
    { label: "Features", render: (r) => <span className="text-ink-soft">{r.tags.join(", ")}</span> },
    { label: "Building", render: (r, l) => <span className="text-ink-soft">{r.building}{r.department_id ? ` (${nameOf(l.departments, r.department_id)})` : ""}</span> },
    { label: "Status", render: (r) => (r.active ? <Pill tone="green">In use</Pill> : <Pill>Out of use</Pill>) },
  ],
};

export default function RoomsPage() {
  return <ResourcePage cfg={cfg} />;
}
