"use client";

import { Pin } from "lucide-react";
import { useState } from "react";
import type { Entry, Slot, View } from "@/lib/types";
import { cx } from "./ui";

export const cellKey = (day: number, start: number) => `${day}|${start}`;

interface Props {
  view: View;
  editable?: boolean;
  masterDay?: number;
  highlight?: Set<string> | null;
  dragging?: Entry | null;
  focusId?: number | null;
  onSelect?: (e: Entry) => void;
  onDragStart?: (e: Entry) => void;
  onDragEnd?: () => void;
  onDrop?: (e: Entry, day: number, start: number) => void;
}

function Slip({
  e,
  view,
  editable,
  focus,
  compact,
  continued,
  onSelect,
  onDragStart,
  onDragEnd,
}: {
  e: Entry;
  view: View;
  editable?: boolean;
  focus?: boolean;
  compact?: boolean;
  continued?: boolean;
  onSelect?: (e: Entry) => void;
  onDragStart?: (e: Entry) => void;
  onDragEnd?: () => void;
}) {
  const conflict = e.conflicts.length > 0;
  const lines: string[] = [];
  if (view.view !== "class" && view.kind === "grid") lines.push(e.class_name);
  if (view.view !== "teacher") lines.push(e.teacher_name);
  if (view.view !== "room" && view.view !== "lab") lines.push(e.room_name);
  return (
    <button
      type="button"
      data-entry-id={e.id}
      draggable={editable && !continued}
      onDragStart={(ev) => {
        ev.dataTransfer.setData("text/plain", String(e.id));
        ev.dataTransfer.effectAllowed = "move";
        onDragStart?.(e);
      }}
      onDragEnd={() => onDragEnd?.()}
      onClick={() => onSelect?.(e)}
      title={`${e.subject_name}\n${e.class_name}\n${e.teacher_name}\n${e.room_name}\n${e.day_name} ${e.time}${conflict ? "\nConflict: " + e.conflicts.join(", ") : ""}`}
      className={cx(
        "slip group relative flex h-full w-full flex-col items-start overflow-hidden rounded-[4px] border-l-[3px] px-1.5 py-1 text-left",
        editable && !continued && "cursor-grab active:cursor-grabbing",
        conflict && "redpen-ring",
        focus && "outline outline-2 outline-offset-1 outline-ink",
      )}
      style={{ borderColor: e.color, background: `${e.color}17` }}
    >
      {continued ? (
        <span className="text-[11.5px] text-ink-faint">{e.subject_code} continues</span>
      ) : (
        <>
          <span className="flex w-full items-start justify-between gap-1">
            <span className={cx("font-semibold leading-tight text-ink", compact ? "text-[12px]" : "text-[13px]")}>
              {compact ? e.subject_code : e.subject_name}
            </span>
            {e.locked && (
              <span className="mt-[1px] shrink-0 rounded-[3px] bg-marker px-0.5 text-ink" aria-label="Pinned">
                <Pin size={10} />
              </span>
            )}
          </span>
          {lines.map((l, i) => (
            <span key={i} className={cx("truncate leading-tight text-ink-soft", compact ? "text-[11px]" : "text-[12px]")}>
              {l}
            </span>
          ))}
        </>
      )}
    </button>
  );
}

function Cell({
  day,
  start,
  editable,
  dragging,
  highlight,
  available,
  onDrop,
  rowSpan,
  children,
  rowClassId,
  asDiv,
}: {
  day: number;
  start: number;
  editable?: boolean;
  dragging?: Entry | null;
  highlight?: Set<string> | null;
  available: boolean;
  onDrop?: (e: Entry, day: number, start: number) => void;
  rowSpan?: number;
  children?: React.ReactNode;
  rowClassId?: number;
  asDiv?: boolean;
}) {
  const [over, setOver] = useState(false);
  const canTarget = !!(editable && dragging && available && (rowClassId === undefined || rowClassId === dragging.class_id));
  const ok = canTarget && highlight?.has(cellKey(day, start));
  const Tag = asDiv ? "div" : "td";
  return (
    <Tag
      data-day={day}
      data-start={start}
      data-class={rowClassId}
      rowSpan={asDiv ? undefined : rowSpan}
      className={cx(
        asDiv ? "h-full w-full border-r border-dashed border-rule" : "h-[64px] border-b border-l border-rule-soft p-1 align-top",
        !available && "bg-paper",
        ok && "drop-ok",
        canTarget && over && (ok ? "drop-hover" : "bg-redpen-wash"),
      )}
      onDragOver={(ev: React.DragEvent) => {
        if (!canTarget) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
      }}
      onDragEnter={() => canTarget && setOver(true)}
      onDragLeave={() => setOver(false)}
      onDrop={(ev: React.DragEvent) => {
        ev.preventDefault();
        setOver(false);
        if (canTarget && dragging) onDrop?.(dragging, day, start);
      }}
    >
      {available ? children : <span className="sr-only">No period</span>}
    </Tag>
  );
}

export default function TimetableGrid(p: Props) {
  if (p.view.kind === "master") return <MasterGrid {...p} />;
  const { view } = p;
  const days = view.days;
  const rows = view.slots;
  const periodRows = rows.map((r, i) => ({ r, i })).filter((x) => x.r.kind === "period");

  // per day: which row index each entry starts in, and rows covered by a row-span
  const spans: Record<number, Map<number, { e: Entry[]; span: number }>> = {};
  const covered: Record<number, Set<number>> = {};
  const continued: Record<number, Map<number, Entry[]>> = {};
  for (const d of days) {
    spans[d.day] = new Map();
    covered[d.day] = new Set();
    continued[d.day] = new Map();
    const dayEntries = view.entries.filter((e) => e.day === d.day);
    for (const e of dayEntries) {
      const startRow = rows.findIndex((r) => r.kind === "period" && r.start === e.start);
      const endRow = rows.findIndex((r) => r.kind === "period" && r.end === e.end);
      const contiguous =
        startRow >= 0 && endRow >= startRow && rows.slice(startRow, endRow + 1).every((r) => r.kind === "period");
      if (startRow >= 0 && contiguous) {
        const cur = spans[d.day].get(startRow);
        const span = endRow - startRow + 1;
        if (cur) cur.e.push(e);
        else spans[d.day].set(startRow, { e: [e], span });
      } else {
        // falls between rows of a mixed grid: show in every row it overlaps
        rows.forEach((r, i) => {
          if (r.kind === "period" && r.start < e.end && e.start < r.end) {
            const m = continued[d.day].get(i) ?? [];
            m.push(e);
            continued[d.day].set(i, m);
          }
        });
      }
    }
    for (const [startRow, s] of spans[d.day]) {
      // only span when every entry in the cell has the same length
      if (s.span > 1 && s.e.every((x) => x.end === s.e[0].end)) {
        for (let k = startRow + 1; k < startRow + s.span; k++) covered[d.day].add(k);
      } else s.span = 1;
    }
  }

  const available = (day: number, slot: Slot) => (view.day_slots[String(day)] ?? []).includes(slot.key);

  return (
    <div className="overflow-x-auto rounded-[8px] border border-rule bg-sheet print-full">
      <table className="w-full min-w-[720px] table-fixed border-collapse text-sm">
        <colgroup>
          <col className="w-[92px]" />
          {days.map((d) => (
            <col key={d.day} />
          ))}
        </colgroup>
        <thead>
          <tr className="bg-paper">
            <th className="border-b border-rule px-2 py-2 text-left text-[12px] font-semibold text-ink-faint">Period</th>
            {days.map((d) => (
              <th key={d.day} className="border-b border-l border-rule px-2 py-2 text-left font-display text-[14px] font-semibold">
                <span className="hidden sm:inline">{d.name}</span>
                <span className="sm:hidden">{d.short}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((slot, i) => {
            if (slot.kind !== "period") {
              return (
                <tr key={slot.key}>
                  <td className="hatch border-b border-rule-soft px-2 py-1 text-[12px] text-ink-faint tnum">{slot.time}</td>
                  {days.map((d) => (
                    <td key={d.day} className={cx("border-b border-l border-rule-soft px-2 py-1 text-[12px]", available(d.day, slot) ? "hatch text-ink-soft" : "")}>
                      {available(d.day, slot) ? slot.label : ""}
                    </td>
                  ))}
                </tr>
              );
            }
            return (
              <tr key={slot.key}>
                <td className="border-b border-rule-soft px-2 py-1.5 align-top">
                  <span className="block text-[13px] font-semibold">{slot.label}</span>
                  <span className="tnum block text-[12px] text-ink-faint">{slot.time}</span>
                </td>
                {days.map((d) => {
                  if (covered[d.day].has(i)) return null;
                  const s = spans[d.day].get(i);
                  const cont = continued[d.day].get(i) ?? [];
                  const items = s?.e ?? [];
                  return (
                    <Cell
                      key={d.day}
                      day={d.day}
                      start={slot.start}
                      rowSpan={s?.span}
                      available={available(d.day, slot) || items.length > 0}
                      editable={p.editable}
                      dragging={p.dragging}
                      highlight={p.highlight}
                      onDrop={p.onDrop}
                      rowClassId={view.view === "class" ? view.ref_id ?? undefined : undefined}
                    >
                      <div className="flex h-full flex-col gap-1">
                        {items.map((e) => (
                          <Slip key={e.id} e={e} view={view} editable={p.editable} focus={p.focusId === e.id} onSelect={p.onSelect} onDragStart={p.onDragStart} onDragEnd={p.onDragEnd} compact={items.length > 1} />
                        ))}
                        {cont.map((e) => (
                          <Slip key={`c${e.id}`} e={e} view={view} continued={e.start < slot.start} editable={p.editable} focus={p.focusId === e.id} onSelect={p.onSelect} onDragStart={p.onDragStart} onDragEnd={p.onDragEnd} compact />
                        ))}
                      </div>
                    </Cell>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {periodRows.length === 0 && <p className="p-4 text-ink-faint">No periods configured.</p>}
    </div>
  );
}

const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

/** Institution / school / department view: one row per class on a shared clock,
 *  so classes on different period lengths line up by real time. */
function MasterGrid(p: Props) {
  const { view } = p;
  const day = p.masterDay ?? view.days[0]?.day ?? 0;
  const rows = view.rows ?? [];
  const key = String(day);
  let lo = Infinity;
  let hi = -Infinity;
  for (const r of rows) {
    for (const [s, e] of r.periods[key] ?? []) {
      lo = Math.min(lo, s);
      hi = Math.max(hi, e);
    }
  }
  if (!isFinite(lo)) {
    lo = 9 * 60;
    hi = 17 * 60;
  }
  lo = Math.floor(lo / 60) * 60;
  hi = Math.ceil(hi / 60) * 60;
  const span = hi - lo;
  const pct = (m: number) => `${((m - lo) / span) * 100}%`;
  const hours = Array.from({ length: span / 60 + 1 }, (_, i) => lo + i * 60);

  return (
    <div className="overflow-x-auto rounded-[8px] border border-rule bg-sheet print-full">
      <div className="min-w-[1080px]">
        <div className="grid grid-cols-[190px_1fr] border-b border-rule bg-paper">
          <div className="px-2 py-2 text-[12px] font-semibold text-ink-faint">Class</div>
          <div className="relative h-9">
            {hours.map((h) => (
              <span key={h} className="tnum absolute top-2 -translate-x-1/2 text-[12px] font-semibold text-ink-soft" style={{ left: pct(h) }}>
                {h === hi ? "" : hhmm(h)}
              </span>
            ))}
          </div>
        </div>
        {rows.map((r) => {
          const periods = r.periods[key] ?? [];
          const breaks = r.breaks[key] ?? [];
          const items = view.entries.filter((e) => e.class_id === r.id && e.day === day);
          return (
            <div key={r.id} className="grid grid-cols-[190px_1fr] border-b border-rule-soft last:border-b-0">
              <div className="px-2 py-2">
                <p className="text-[13px] font-semibold leading-tight">{r.name}</p>
                <p className="text-[12px] text-ink-faint">{r.department}</p>
              </div>
              <div className="relative h-[78px] border-l border-rule-soft">
                {hours.map((h) => (
                  <span key={h} className="absolute inset-y-0 w-px bg-rule-soft" style={{ left: pct(h) }} />
                ))}
                {breaks.map(([s, e, name], i) => (
                  <span key={`b${i}`} className="hatch absolute inset-y-0 overflow-hidden px-1 pt-1 text-[10.5px] text-ink-faint" style={{ left: pct(s), width: `calc(${pct(e)} - ${pct(s)})` }} title={name}>
                    {e - s >= 30 ? name : ""}
                  </span>
                ))}
                {periods.length === 0 && <span className="absolute inset-0 bg-paper" />}
                {periods.map(([s, e]) => (
                  <div key={s} className="absolute inset-y-0" style={{ left: pct(s), width: `calc(${pct(e)} - ${pct(s)})` }}>
                    <Cell
                      day={day}
                      start={s}
                      available
                      editable={p.editable}
                      dragging={p.dragging}
                      highlight={p.highlight}
                      onDrop={p.onDrop}
                      rowClassId={r.id}
                      asDiv
                    />
                  </div>
                ))}
                {items.map((e) => (
                  <div
                    key={e.id}
                    className={cx("absolute inset-y-1 px-[2px]", p.dragging && "pointer-events-none")}
                    style={{ left: pct(e.start), width: `calc(${pct(e.end)} - ${pct(e.start)})` }}
                  >
                    <Slip e={e} view={view} compact editable={p.editable} focus={p.focusId === e.id} onSelect={p.onSelect} onDragStart={p.onDragStart} onDragEnd={p.onDragEnd} />
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {rows.length === 0 && <p className="p-4 text-ink-faint">No classes in this scope.</p>}
      </div>
    </div>
  );
}
