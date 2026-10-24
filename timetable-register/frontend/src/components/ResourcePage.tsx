"use client";

import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { api, inst } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";
import WindowsEditor from "./WindowsEditor";
import { Button, Drawer, Empty, ErrorNote, Field, Input, Loading, PageHeader, Panel, Select, useLoad, useToast } from "./ui";

export type Lookups = Record<string, any[]>;
type Opt = { value: string | number; label: string };

export interface FieldDef {
  key: string;
  label: string;
  type?: "text" | "number" | "select" | "tags" | "windows" | "time" | "checkbox" | "email" | "password";
  options?: Opt[] | ((l: Lookups, form: any) => Opt[]);
  required?: boolean;
  hint?: string;
  placeholder?: string;
  nullable?: boolean; // empty select/number -> null
  default?: any;
  showIf?: (form: any, editing: boolean) => boolean;
  half?: boolean;
  createOnly?: boolean;
}

export interface Column {
  label: string;
  render: (row: any, l: Lookups) => ReactNode;
  className?: string;
}

export interface ResourceConfig {
  title: string;
  intro: ReactNode;
  path: string; // e.g. "/teachers"
  singular: string;
  fields: FieldDef[];
  columns: Column[];
  lookups?: string[]; // resource paths to preload, e.g. ["departments"]
  writeRole?: Role;
  sort?: (a: any, b: any) => number;
  filter?: (row: any, q: string, l: Lookups) => boolean;
  toolbar?: (l: Lookups, setFilter: (f: Record<string, string>) => void, filter: Record<string, string>) => ReactNode;
  rowFilter?: (row: any, filter: Record<string, string>) => boolean;
  listPath?: (iid: number) => string;
  describe?: (row: any) => string;
  defaults?: (filter: Record<string, string>) => Record<string, any>;
}

export const optsFrom = (rows: any[] | undefined, label = (r: any) => r.name): Opt[] =>
  (rows ?? []).map((r) => ({ value: r.id, label: label(r) }));

export const nameOf = (rows: any[] | undefined, id: number | null | undefined) =>
  id == null ? "" : (rows ?? []).find((r) => r.id === id)?.name ?? "";

function emptyForm(fields: FieldDef[]) {
  const f: any = {};
  for (const d of fields) {
    if (d.default !== undefined) f[d.key] = d.default;
    else if (d.type === "tags" || d.type === "windows") f[d.key] = [];
    else if (d.type === "checkbox") f[d.key] = false;
    else f[d.key] = "";
  }
  return f;
}

export default function ResourcePage({ cfg }: { cfg: ResourceConfig }) {
  const { iid, can } = useAuth();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<any | null>(null);
  const [form, setForm] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const list = useLoad(() => api<any[]>(cfg.listPath ? cfg.listPath(iid!) : inst(iid!, cfg.path)), [iid, cfg.path]);
  const lk = useLoad(async () => {
    const out: Lookups = {};
    await Promise.all(
      (cfg.lookups ?? []).map(async (p) => {
        out[p] = await api<any[]>(inst(iid!, `/${p}`));
      }),
    );
    return out;
  }, [iid]);
  const lookups = lk.data ?? {};
  const canWrite = can(cfg.writeRole ?? "department_admin");

  const rows = useMemo(() => {
    let r = [...(list.data ?? [])];
    if (cfg.rowFilter) r = r.filter((x) => cfg.rowFilter!(x, filter));
    if (q.trim()) {
      const s = q.toLowerCase();
      r = r.filter((x) => (cfg.filter ? cfg.filter(x, s, lookups) : JSON.stringify(x).toLowerCase().includes(s)));
    }
    if (cfg.sort) r.sort(cfg.sort);
    return r;
  }, [list.data, q, filter, cfg, lookups]);

  function open(row: any | null) {
    setError(null);
    if (row) {
      const f: any = {};
      for (const d of cfg.fields) f[d.key] = row[d.key] ?? (d.type === "tags" || d.type === "windows" ? [] : "");
      setForm(f);
      setEditing(row);
    } else {
      setForm({ ...emptyForm(cfg.fields), ...(cfg.defaults?.(filter) ?? {}) });
      setEditing({});
    }
  }

  function payload() {
    const out: any = {};
    const isNew = !editing?.id;
    for (const d of cfg.fields) {
      if (d.showIf && !d.showIf(form, !isNew)) continue;
      if (d.createOnly && !isNew) continue;
      let v = form[d.key];
      if (d.type === "number" || d.type === "select") {
        if (v === "" || v == null) v = null;
        else if (typeof v === "string" && /^-?\d+$/.test(v)) v = Number(v);
      } else if (d.type === "password") {
        if (!v) continue;
      } else if (typeof v === "string") {
        v = v.trim();
        if (v === "" && d.nullable) v = null;
      }
      out[d.key] = v;
    }
    return out;
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body = payload();
      if (editing?.id) {
        await api(inst(iid!, `${cfg.path}/${editing.id}`), { method: "PATCH", body });
        toast(`${cfg.singular} updated`);
      } else {
        await api(inst(iid!, cfg.path), { method: "POST", body });
        toast(`${cfg.singular} added`);
      }
      setEditing(null);
      list.reload();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(row: any) {
    const name = cfg.describe ? cfg.describe(row) : row.name ?? `#${row.id}`;
    if (!window.confirm(`Delete ${name}? This can't be undone.`)) return;
    try {
      await api(inst(iid!, `${cfg.path}/${row.id}`), { method: "DELETE" });
      toast(`${cfg.singular} deleted`);
      list.reload();
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  const isNew = !editing?.id;

  return (
    <div className="max-w-[1180px]">
      <PageHeader
        title={cfg.title}
        intro={cfg.intro}
        actions={
          canWrite && (
            <Button variant="primary" onClick={() => open(null)}>
              <Plus size={16} /> Add {cfg.singular.toLowerCase()}
            </Button>
          )
        }
      />
      <Panel>
        <div className="flex flex-wrap items-center gap-3 border-b border-rule-soft px-4 py-3">
          <div className="relative w-full max-w-[280px]">
            <Search size={15} className="pointer-events-none absolute left-2.5 top-2.5 text-ink-faint" />
            <Input aria-label="Search" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" />
          </div>
          {cfg.toolbar?.(lookups, setFilter, filter)}
          <span className="ml-auto text-[13px] text-ink-faint">{rows.length} shown</span>
        </div>
        <ErrorNote error={list.error} />
        {list.loading && !list.data ? (
          <div className="px-4"><Loading /></div>
        ) : rows.length === 0 ? (
          <Empty
            title={q ? "Nothing matches that search" : `No ${cfg.title.toLowerCase()} yet`}
            action={canWrite && !q ? <Button onClick={() => open(null)}>Add the first one</Button> : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-[13px] text-ink-soft">
                  {cfg.columns.map((c) => (
                    <th key={c.label} className={`px-4 py-2 font-semibold ${c.className ?? ""}`}>
                      {c.label}
                    </th>
                  ))}
                  {canWrite && <th className="w-[84px]" />}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-rule-soft last:border-0 hover:bg-paper/70">
                    {cfg.columns.map((c) => (
                      <td key={c.label} className={`px-4 py-2.5 align-top ${c.className ?? ""}`}>
                        {c.render(row, lookups)}
                      </td>
                    ))}
                    {canWrite && (
                      <td className="px-2 py-1.5 text-right align-top">
                        <button onClick={() => open(row)} className="rounded p-1.5 text-ink-faint hover:text-ink" aria-label="Edit">
                          <Pencil size={15} />
                        </button>
                        <button onClick={() => remove(row)} className="rounded p-1.5 text-ink-faint hover:text-redpen" aria-label="Delete">
                          <Trash2 size={15} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={isNew ? `Add ${cfg.singular.toLowerCase()}` : `Edit ${cfg.singular.toLowerCase()}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button variant="primary" busy={saving} onClick={save}>
              {isNew ? `Add ${cfg.singular.toLowerCase()}` : "Save changes"}
            </Button>
          </>
        }
      >
        <form
          className="grid grid-cols-2 gap-x-3 gap-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          {cfg.fields
            .filter((d) => (!d.showIf || d.showIf(form, !isNew)) && !(d.createOnly && !isNew))
            .map((d) => (
              <FieldInput key={d.key} d={d} form={form} setForm={setForm} lookups={lookups} />
            ))}
          <div className="col-span-2">
            <ErrorNote error={error} />
          </div>
          <button type="submit" hidden />
        </form>
      </Drawer>
    </div>
  );
}

function FieldInput({ d, form, setForm, lookups }: { d: FieldDef; form: any; setForm: (f: any) => void; lookups: Lookups }) {
  const v = form[d.key];
  const set = (val: any) => setForm({ ...form, [d.key]: val });
  const span = d.half ? "col-span-1" : "col-span-2";
  const opts = typeof d.options === "function" ? d.options(lookups, form) : d.options ?? [];
  if (d.type === "windows") {
    return (
      <div className={span}>
        <p className="mb-1 text-[13px] font-semibold text-ink-soft">
          {d.label}
          {d.hint && <span className="ml-1.5 font-normal text-ink-faint">{d.hint}</span>}
        </p>
        <WindowsEditor value={v ?? []} onChange={set} />
      </div>
    );
  }
  if (d.type === "checkbox") {
    return (
      <label className={`${span} flex items-center gap-2 text-sm`}>
        <input type="checkbox" checked={!!v} onChange={(e) => set(e.target.checked)} className="h-4 w-4 accent-[var(--color-register)]" />
        {d.label}
      </label>
    );
  }
  return (
    <Field label={d.label + (d.required ? "" : "")} hint={d.hint} className={span}>
      {d.type === "select" ? (
        <Select value={v ?? ""} required={d.required} onChange={(e) => set(e.target.value)}>
          {(!d.required || v === "") && <option value="">{d.placeholder ?? "None"}</option>}
          {opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      ) : d.type === "tags" ? (
        <Input
          value={(v ?? []).join(", ")}
          placeholder={d.placeholder}
          onChange={(e) =>
            set(
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter((s, i, arr) => s || i === arr.length - 1),
            )
          }
          onBlur={() => set((v ?? []).filter(Boolean))}
        />
      ) : (
        <Input
          type={d.type === "number" ? "number" : d.type === "time" ? "time" : d.type === "email" ? "email" : d.type === "password" ? "password" : "text"}
          value={v ?? ""}
          required={d.required}
          placeholder={d.placeholder}
          min={d.type === "number" ? 0 : undefined}
          onChange={(e) => set(e.target.value)}
        />
      )}
    </Field>
  );
}
