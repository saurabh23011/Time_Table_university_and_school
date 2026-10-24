"use client";

import {
  BookOpen,
  Building2,
  CalendarClock,
  CalendarDays,
  DoorOpen,
  GraduationCap,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Network,
  UserCog,
  Users,
  UserRoundCheck,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { ROLE_LABEL, type Role } from "@/lib/types";
import { cx, Loading, Select } from "./ui";

interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
  min?: Role;
  only?: Role[];
}

const NAV: { group: string | null; items: NavItem[] }[] = [
  {
    group: null,
    items: [
      { href: "/dashboard", label: "Dashboard", icon: <LayoutDashboard size={17} /> },
      { href: "/timetables", label: "Timetables", icon: <CalendarDays size={17} /> },
      { href: "/my-availability", label: "My availability", icon: <UserRoundCheck size={17} />, only: ["teacher"] },
    ],
  },
  {
    group: "Set up",
    items: [
      { href: "/setup/schedules", label: "Working hours", icon: <CalendarClock size={17} />, min: "department_admin" },
      { href: "/setup/departments", label: "Departments", icon: <Network size={17} />, min: "department_admin" },
      { href: "/setup/teachers", label: "Teachers", icon: <Users size={17} />, min: "department_admin" },
      { href: "/setup/rooms", label: "Rooms & labs", icon: <DoorOpen size={17} />, min: "department_admin" },
      { href: "/setup/subjects", label: "Subjects", icon: <BookOpen size={17} />, min: "department_admin" },
      { href: "/setup/classes", label: "Classes", icon: <GraduationCap size={17} />, min: "department_admin" },
      { href: "/setup/curriculum", label: "Curriculum", icon: <ListChecks size={17} />, min: "department_admin" },
    ],
  },
  {
    group: "Administration",
    items: [
      { href: "/admin/users", label: "Users", icon: <UserCog size={17} />, min: "department_admin" },
      { href: "/admin/institutions", label: "Institutions", icon: <Building2 size={17} />, only: ["super_admin"] },
    ],
  },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const { ready, user, institution, institutions, setInstitutionId, can, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);
  useEffect(() => setOpen(false), [pathname]);

  if (!ready || !user) return <div className="p-8"><Loading /></div>;

  const visible = (i: NavItem) => (i.only ? i.only.includes(user.role) : i.min ? can(i.min) : true);

  const sidebar = (
    <nav className="flex h-full flex-col gap-5 px-3 py-5" aria-label="Main">
      <Link href="/dashboard" className="px-2">
        <span className="font-display text-[21px] font-bold leading-none tracking-tight">Timetable Register</span>
      </Link>
      <div className="px-2">
        {user.role === "super_admin" && institutions.length > 0 ? (
          <Select
            aria-label="Institution"
            value={institution?.id ?? ""}
            onChange={(e) => setInstitutionId(Number(e.target.value))}
            className="h-auto py-1.5 font-semibold"
          >
            {institutions.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </Select>
        ) : (
          <p className="text-sm font-semibold leading-snug text-ink">{institution?.name ?? "No institution"}</p>
        )}
        {institution && <p className="mt-0.5 text-[13px] capitalize text-ink-faint">{institution.kind}</p>}
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto">
        {NAV.map((g) => {
          const items = g.items.filter(visible);
          if (!items.length) return null;
          return (
            <div key={g.group ?? "main"}>
              {g.group && <p className="mb-1 px-2 text-[13px] font-semibold text-ink-faint">{g.group}</p>}
              <ul>
                {items.map((i) => {
                  const active = pathname === i.href || pathname.startsWith(i.href + "/");
                  return (
                    <li key={i.href}>
                      <Link
                        href={i.href}
                        aria-current={active ? "page" : undefined}
                        className={cx(
                          "relative flex items-center gap-2.5 rounded-[6px] px-2 py-1.5 text-[14.5px]",
                          active ? "bg-sheet font-semibold text-ink shadow-[inset_3px_0_0_var(--color-register)]" : "text-ink-soft hover:text-ink",
                        )}
                      >
                        <span className={active ? "text-register" : "text-ink-faint"}>{i.icon}</span>
                        {i.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
      <div className="border-t border-rule px-2 pt-3">
        <p className="truncate text-sm font-semibold">{user.full_name}</p>
        <p className="text-[13px] text-ink-faint">{ROLE_LABEL[user.role]}</p>
        <button onClick={logout} className="mt-2 inline-flex items-center gap-1.5 text-[13px] text-ink-soft hover:text-redpen">
          <LogOut size={14} /> Sign out
        </button>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[236px_1fr]">
      <aside className="no-print sticky top-0 hidden h-screen border-r border-rule bg-paper lg:block">{sidebar}</aside>
      <div className="no-print flex items-center justify-between border-b border-rule bg-paper px-4 py-3 lg:hidden">
        <span className="font-display text-lg font-bold">Timetable Register</span>
        <button onClick={() => setOpen(true)} aria-label="Open menu" className="p-1">
          <Menu size={20} />
        </button>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} />
          <aside className="relative h-full w-[260px] border-r border-rule bg-paper">{sidebar}</aside>
        </div>
      )}
      <main className="print-full min-w-0 px-4 py-6 sm:px-8 lg:py-8">{institution ? children : <NoInstitution />}</main>
    </div>
  );
}

function NoInstitution() {
  return (
    <div className="max-w-xl">
      <h1 className="font-display text-2xl font-semibold">No institution yet</h1>
      <p className="mt-2 text-ink-soft">
        Add the first university, college or school to start configuring timetables.
      </p>
      <Link href="/admin/institutions" className="mt-4 inline-block font-semibold text-register underline">
        Add an institution
      </Link>
    </div>
  );
}
