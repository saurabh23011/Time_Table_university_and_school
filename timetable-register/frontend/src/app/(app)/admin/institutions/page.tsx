"use client";

import { Plus } from "lucide-react";
import { useState } from "react";
import { Button, Drawer, ErrorNote, Field, Input, PageHeader, Panel, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function InstitutionsPage() {
  const { institutions, refreshInstitutions, setInstitutionId, user } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", kind: "university", address: "" });
  const [admin, setAdmin] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user?.role !== "super_admin") return <p>Only a super admin can manage institutions.</p>;

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const created = await api<any>("/api/institutions", { method: "POST", body: { ...form, address: form.address || null } });
      if (admin.email) {
        await api(`/api/institutions/${created.id}/users`, {
          method: "POST",
          body: { ...admin, role: "institution_admin" },
        });
      }
      await refreshInstitutions();
      setInstitutionId(created.id);
      toast(`${created.name} added. Set up its working hours next.`);
      setOpen(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-[900px]">
      <PageHeader
        title="Institutions"
        intro="Each university, college or school keeps its own departments, teachers, rooms, working hours and timetables."
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Plus size={16} /> Add institution
          </Button>
        }
      />
      <Panel>
        <ul className="divide-y divide-rule-soft">
          {institutions.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div>
                <p className="font-semibold">{i.name}</p>
                <p className="text-[13px] capitalize text-ink-faint">
                  {i.kind}, code {i.code}
                  {i.address ? `, ${i.address}` : ""}
                </p>
              </div>
              <Button size="sm" onClick={() => setInstitutionId(i.id)}>
                Switch to
              </Button>
            </li>
          ))}
        </ul>
      </Panel>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title="Add institution"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" busy={busy} onClick={create}>Add institution</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Short code"><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></Field>
            <Field label="Type">
              <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="university">University</option>
                <option value="college">College</option>
                <option value="school">School</option>
              </Select>
            </Field>
          </div>
          <Field label="Address"><Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
          <div className="border-t border-rule-soft pt-4">
            <p className="font-semibold">First administrator</p>
            <p className="mb-3 text-[13px] text-ink-faint">Optional. They can add departments, teachers and other users.</p>
            <div className="space-y-3">
              <Field label="Full name"><Input value={admin.full_name} onChange={(e) => setAdmin({ ...admin, full_name: e.target.value })} /></Field>
              <Field label="Email"><Input type="email" value={admin.email} onChange={(e) => setAdmin({ ...admin, email: e.target.value })} /></Field>
              <Field label="Password" hint="at least 8 characters"><Input type="password" value={admin.password} onChange={(e) => setAdmin({ ...admin, password: e.target.value })} /></Field>
            </div>
          </div>
          <ErrorNote error={error} />
        </div>
      </Drawer>
    </div>
  );
}
