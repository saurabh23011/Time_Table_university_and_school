"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Drawer, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Pill, Select, StatusPill, useLoad, useToast } from "@/components/ui";
import { api, inst } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Timetable } from "@/lib/types";

export default function TimetablesPage() {
  const { iid, can, user } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const list = useLoad(() => api<Timetable[]>(inst(iid!, "/timetables")), [iid]);
  const depts = useLoad(() => api<any[]>(inst(iid!, "/departments")), [iid]);
  const [open, setOpen] = useState(false);
  const isInstAdmin = can("institution_admin");
  const [form, setForm] = useState({ name: "", term: "", department_id: "", time_limit: "15" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deptName = (id: number | null) => (id == null ? "Whole institution" : depts.data?.find((d) => d.id === id)?.name ?? "");

  function openForm() {
    setError(null);
    setForm({
      name: `Timetable ${new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`,
      term: "",
      department_id: isInstAdmin ? "" : String(user?.department_id ?? ""),
      time_limit: "15",
    });
    setOpen(true);
  }

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const tt = await api<Timetable>(inst(iid!, "/timetables"), {
        method: "POST",
        body: {
          name: form.name,
          term: form.term || null,
          department_id: form.department_id ? Number(form.department_id) : null,
          time_limit: Number(form.time_limit),
        },
      });
      const g = tt.generation;
      toast(
        g.complete
          ? `Generated: all ${g.stats.placed} sessions placed with no conflicts`
          : `Generated with ${g.unscheduled.length} session(s) that could not be placed`,
        g.complete ? "ok" : "error",
      );
      router.push(`/timetables/${tt.id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-[1100px]">
      <PageHeader
        title="Timetables"
        intro={
          can("department_admin")
            ? "Generate a draft for the whole institution or one school or department, review and adjust it, then publish it for teachers and students."
            : "Published timetables for your institution."
        }
        actions={
          can("department_admin") && (
            <Button variant="primary" onClick={openForm}>
              <Plus size={16} /> Generate timetable
            </Button>
          )
        }
      />
      <ErrorNote error={list.error} />
      <Panel>
        {list.loading && !list.data ? (
          <div className="px-4"><Loading /></div>
        ) : (list.data ?? []).length === 0 ? (
          <Empty
            title={can("department_admin") ? "No timetables yet" : "Nothing published yet"}
            action={can("department_admin") ? <Button onClick={openForm}>Generate the first timetable</Button> : undefined}
          >
            {can("department_admin")
              ? "Once working hours, rooms, teachers, classes and the curriculum are in place, the generator builds a conflict-free week in a few seconds."
              : "Your administrators haven't published a timetable for you yet."}
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-[13px] text-ink-soft">
                  <th className="px-4 py-2 font-semibold">Timetable</th>
                  <th className="px-4 py-2 font-semibold">Covers</th>
                  <th className="px-4 py-2 text-right font-semibold">Sessions</th>
                  <th className="px-4 py-2 font-semibold">Checks</th>
                  <th className="px-4 py-2 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {(list.data ?? []).map((t) => {
                  const unplaced = t.generation?.unscheduled?.length ?? 0;
                  return (
                    <tr key={t.id} className="border-b border-rule-soft last:border-0 hover:bg-paper/70">
                      <td className="px-4 py-3">
                        <Link href={`/timetables/${t.id}`} className="font-semibold hover:text-register">{t.name}</Link>
                        <p className="text-[13px] text-ink-faint">
                          {t.term ? `${t.term}, ` : ""}created {new Date(t.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-ink-soft">{deptName(t.department_id)}</td>
                      <td className="tnum px-4 py-3 text-right">{t.entry_count}</td>
                      <td className="px-4 py-3">
                        <span className="flex flex-wrap gap-1">
                          {t.conflict_summary?.major ? <Pill tone="red">{t.conflict_summary.major} conflicts</Pill> : <Pill tone="green">Conflict-free</Pill>}
                          {unplaced > 0 && <Pill tone="red">{unplaced} unplaced</Pill>}
                          {!!t.conflict_summary?.minor && <Pill>{t.conflict_summary.minor} warnings</Pill>}
                        </span>
                      </td>
                      <td className="px-4 py-3"><StatusPill status={t.status} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Drawer
        open={open}
        onClose={() => !busy && setOpen(false)}
        title="Generate a timetable"
        footer={
          <>
            <Button variant="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" busy={busy} onClick={generate}>{busy ? "Generating…" : "Generate"}</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Term" hint="optional"><Input value={form.term} placeholder="Odd semester 2026–27" onChange={(e) => setForm({ ...form, term: e.target.value })} /></Field>
          <Field label="Covers">
            <Select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
              {isInstAdmin && <option value="">Whole institution</option>}
              {(depts.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Search time" hint="seconds; larger institutions benefit from more">
            <Select value={form.time_limit} onChange={(e) => setForm({ ...form, time_limit: e.target.value })}>
              {["5", "15", "30", "60", "120"].map((s) => <option key={s} value={s}>{s} seconds</option>)}
            </Select>
          </Field>
          <div className="rounded-[8px] bg-paper p-3 text-sm text-ink-soft">
            <p className="font-semibold text-ink">What the generator guarantees</p>
            <p className="mt-1">
              No teacher, class or room is ever booked twice at the same time, availability and working hours are respected,
              labs go only to matching labs, and every subject gets its weekly lectures. Within those rules it spreads subjects
              across the week, balances workload, avoids long runs and idle gaps for teachers, and follows their preferences.
            </p>
            <p className="mt-2">Sessions already published in other departments are treated as busy, so shared teachers and rooms stay clash-free.</p>
          </div>
          <ErrorNote error={error} />
        </div>
      </Drawer>
    </div>
  );
}
