"use client";

import { Plus, Trash2 } from "lucide-react";
import { DAY_NAMES, type Window } from "@/lib/types";
import { Button, Input, Select } from "./ui";

export default function WindowsEditor({
  value,
  onChange,
  days = [0, 1, 2, 3, 4, 5],
  emptyText = "None",
}: {
  value: Window[];
  onChange: (v: Window[]) => void;
  days?: number[];
  emptyText?: string;
}) {
  const update = (i: number, patch: Partial<Window>) => onChange(value.map((w, j) => (j === i ? { ...w, ...patch } : w)));
  return (
    <div className="space-y-2">
      {value.length === 0 && <p className="text-[13px] text-ink-faint">{emptyText}</p>}
      {value.map((w, i) => (
        <div key={i} className="grid grid-cols-[1fr_96px_96px_32px] items-center gap-2">
          <Select aria-label="Day" value={w.day} onChange={(e) => update(i, { day: Number(e.target.value) })}>
            {[0, 1, 2, 3, 4, 5, 6].map((d) => (
              <option key={d} value={d}>
                {DAY_NAMES[d]}
              </option>
            ))}
          </Select>
          <Input aria-label="From" type="time" value={w.start} onChange={(e) => update(i, { start: e.target.value })} />
          <Input aria-label="Until" type="time" value={w.end} onChange={(e) => update(i, { end: e.target.value })} />
          <button
            type="button"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
            className="flex h-8 w-8 items-center justify-center rounded text-ink-faint hover:text-redpen"
            aria-label="Remove"
          >
            <Trash2 size={15} />
          </button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => onChange([...value, { day: days[0] ?? 0, start: "09:00", end: "17:00" }])}
      >
        <Plus size={14} /> Add a time window
      </Button>
    </div>
  );
}
