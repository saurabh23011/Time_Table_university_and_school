"use client";

import { useEffect, useState } from "react";
import WindowsEditor from "@/components/WindowsEditor";
import { Button, ErrorNote, Loading, PageHeader, Panel, useLoad, useToast } from "@/components/ui";
import { api, inst } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Window } from "@/lib/types";

export default function MyAvailability() {
  const { user, iid } = useAuth();
  const toast = useToast();
  const t = useLoad(
    () => (user?.teacher_id ? api<any>(inst(iid!, `/teachers/${user.teacher_id}`)) : Promise.resolve(null)),
    [iid, user?.teacher_id],
  );
  const [v, setV] = useState<{ unavailable: Window[]; preferred: Window[]; avoid: Window[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (t.data) setV({ unavailable: t.data.unavailable, preferred: t.data.preferred, avoid: t.data.avoid });
  }, [t.data]);

  if (!user?.teacher_id) return <p className="text-ink-soft">Your account isn't linked to a teacher profile. Ask your administrator to link it.</p>;
  if (!v) return <Loading />;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/auth/me/availability", { method: "PUT", body: v });
      toast("Availability saved. It applies from the next timetable your department generates.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-[720px]">
      <PageHeader
        title="My availability"
        intro="Tell the timetable when you cannot teach and what you prefer. Unavailable times are always respected; preferences are followed where the week allows."
        actions={<Button variant="primary" busy={busy} onClick={save}>Save availability</Button>}
      />
      <ErrorNote error={error ?? t.error} />
      <div className="space-y-5">
        <Panel title="I can't teach">
          <div className="p-4"><WindowsEditor value={v.unavailable} onChange={(x) => setV({ ...v, unavailable: x })} emptyText="You're available in every period." /></div>
        </Panel>
        <Panel title="I'd prefer to teach">
          <div className="p-4"><WindowsEditor value={v.preferred} onChange={(x) => setV({ ...v, preferred: x })} emptyText="No preference." /></div>
        </Panel>
        <Panel title="I'd rather not teach">
          <div className="p-4"><WindowsEditor value={v.avoid} onChange={(x) => setV({ ...v, avoid: x })} emptyText="No preference." /></div>
        </Panel>
      </div>
    </div>
  );
}
