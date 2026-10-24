"use client";

import { Download, Printer } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import TimetableGrid from "@/components/TimetableGrid";
import { Button, ErrorNote, Loading, Select, cx, useLoad } from "@/components/ui";
import { api, download } from "@/lib/api";
import type { View } from "@/lib/types";

const TABS = [
  { key: "class", label: "Class", opt: "classes" },
  { key: "teacher", label: "Teacher", opt: "teachers" },
  { key: "room", label: "Room", opt: "rooms" },
  { key: "lab", label: "Laboratory", opt: "labs" },
  { key: "institution", label: "Everything" },
] as const;

export default function SharedTimetable() {
  const { token } = useParams<{ token: string }>();
  const base = `/api/public/share/${token}`;
  const meta = useLoad(() => api<any>(base, { auth: false }), [base]);
  const [type, setType] = useState<string>("class");
  const [ref, setRef] = useState<number | null>(null);
  const [view, setView] = useState<View | null>(null);
  const [day, setDay] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (meta.data && ref === null && type === "class") setRef(meta.data.options.classes[0]?.id ?? null);
  }, [meta.data, ref, type]);

  useEffect(() => {
    if (!meta.data || (type !== "institution" && ref == null)) return;
    api<View>(`${base}/view`, { auth: false, query: { view: type, ref: type === "institution" ? undefined : ref } })
      .then((v) => {
        setView(v);
        setErr(null);
        if (v.kind === "master") setDay((d) => (d != null && v.days.some((x) => x.day === d) ? d : v.days[0]?.day ?? 0));
      })
      .catch((e) => setErr(e.message));
  }, [base, meta.data, type, ref]);

  if (meta.error) {
    return (
      <div className="mx-auto max-w-xl px-6 py-20">
        <h1 className="font-display text-2xl font-semibold">This link doesn't work</h1>
        <p className="mt-2 text-ink-soft">{meta.error}. Ask whoever sent it for a new link.</p>
      </div>
    );
  }
  if (!meta.data) return <div className="p-8"><Loading /></div>;
  const m = meta.data;
  const tab = TABS.find((t) => t.key === type)!;
  const options: any[] = "opt" in tab ? m.options[tab.opt] : [];

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-8">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-ink-soft">{m.institution.name}</p>
          <h1 className="font-display text-[28px] font-semibold leading-tight">{m.name}</h1>
          <p className="text-ink-soft">
            {m.scope}
            {m.term ? `, ${m.term}` : ""}
            {m.status !== "published" && <span className="ml-2 text-[#7a5d00]">(draft, may still change)</span>}
          </p>
        </div>
        <div className="no-print flex gap-2">
          <Button onClick={() => download(`${base}/export`, { format: "pdf", view: type, ref: type === "institution" ? undefined : ref }, "timetable.pdf", false)}>
            <Download size={15} /> PDF
          </Button>
          <Button onClick={() => download(`${base}/export`, { format: "xlsx", view: type, ref: type === "institution" ? undefined : ref }, "timetable.xlsx", false)}>
            <Download size={15} /> Excel
          </Button>
          <Button onClick={() => window.print()}>
            <Printer size={15} /> Print
          </Button>
        </div>
      </header>
      <div className="no-print mb-4 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap rounded-[8px] border border-rule bg-sheet p-0.5">
          {TABS.filter((t) => !("opt" in t) || m.options[t.opt].length).map((t) => (
            <button
              key={t.key}
              aria-pressed={type === t.key}
              onClick={() => {
                setType(t.key);
                setRef("opt" in t ? m.options[t.opt][0]?.id ?? null : null);
              }}
              className={cx("rounded-[6px] px-3 py-1.5 text-sm", type === t.key ? "bg-ink font-semibold text-white" : "text-ink-soft")}
            >
              {t.label}
            </button>
          ))}
        </div>
        {options.length > 0 && (
          <Select aria-label={tab.label} className="w-72" value={ref ?? ""} onChange={(e) => setRef(Number(e.target.value))}>
            {options.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
        )}
        {view?.kind === "master" && (
          <div className="flex rounded-[8px] border border-rule bg-sheet p-0.5">
            {view.days.map((x) => (
              <button key={x.day} onClick={() => setDay(x.day)} aria-pressed={day === x.day}
                className={cx("rounded-[6px] px-2.5 py-1.5 text-sm", day === x.day ? "bg-register-wash font-semibold text-register-dark" : "text-ink-soft")}>
                {x.short}
              </button>
            ))}
          </div>
        )}
      </div>
      <ErrorNote error={err} />
      {view ? (
        <>
          <h2 className="mb-2 font-display text-xl font-semibold">{view.title}</h2>
          <TimetableGrid view={view} masterDay={day ?? undefined} />
        </>
      ) : (
        <Loading />
      )}
    </div>
  );
}
