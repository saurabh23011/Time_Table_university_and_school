"use client";

import ResourcePage, { nameOf, optsFrom, type ResourceConfig } from "@/components/ResourcePage";
import { Pill } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ROLE_LABEL, type Role } from "@/lib/types";

export default function UsersPage() {
  const { user } = useAuth();
  const roles: Role[] =
    user?.role === "super_admin"
      ? ["super_admin", "institution_admin", "department_admin", "teacher", "student"]
      : user?.role === "institution_admin"
        ? ["institution_admin", "department_admin", "teacher", "student"]
        : ["department_admin", "teacher", "student"];

  const cfg: ResourceConfig = {
    title: "Users",
    singular: "User",
    path: "/users",
    describe: (r) => r.email,
    intro: "Who can sign in and what they can do. Department admins manage their own department; teachers see published timetables and keep their availability up to date; students see their timetables.",
    lookups: ["departments", "teachers", "classes"],
    sort: (a, b) => a.role.localeCompare(b.role) || a.full_name.localeCompare(b.full_name),
    filter: (r, q) => `${r.full_name} ${r.email}`.toLowerCase().includes(q),
    fields: [
      { key: "full_name", label: "Full name", required: true },
      { key: "email", label: "Email", type: "email", required: true, createOnly: true },
      { key: "password", label: "Password", type: "password", hint: "at least 8 characters", required: true, createOnly: true },
      { key: "password", label: "New password", type: "password", hint: "leave blank to keep", showIf: (_f, editing) => editing },
      { key: "role", label: "Role", type: "select", required: true, default: "teacher", options: roles.map((r) => ({ value: r, label: ROLE_LABEL[r] })) },
      { key: "department_id", label: "Department", type: "select", options: (l) => optsFrom(l.departments) },
      { key: "teacher_id", label: "Teacher profile", type: "select", options: (l) => optsFrom(l.teachers), showIf: (f) => f.role === "teacher" },
      { key: "class_id", label: "Class", type: "select", options: (l) => optsFrom(l.classes), showIf: (f) => f.role === "student" },
      { key: "is_active", label: "Account active", type: "checkbox", default: true },
    ],
    columns: [
      {
        label: "User",
        render: (r) => (
          <>
            <p className="font-semibold">{r.full_name}</p>
            <p className="text-[13px] text-ink-faint">{r.email}</p>
          </>
        ),
      },
      { label: "Role", render: (r) => ROLE_LABEL[r.role as Role] },
      { label: "Department", render: (r, l) => nameOf(l.departments, r.department_id) },
      { label: "Linked to", render: (r, l) => <span className="text-ink-soft">{nameOf(l.teachers, r.teacher_id) || nameOf(l.classes, r.class_id)}</span> },
      { label: "Status", render: (r) => (r.is_active ? <Pill tone="green">Active</Pill> : <Pill>Disabled</Pill>) },
    ],
  };
  return <ResourcePage cfg={cfg} />;
}
