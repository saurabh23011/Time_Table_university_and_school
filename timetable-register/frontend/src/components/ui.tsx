"use client";

import { X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ Button */
type Variant = "primary" | "secondary" | "ghost" | "danger";
export function Button({
  variant = "secondary",
  size = "md",
  className,
  busy,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; busy?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: "bg-register text-white hover:bg-register-dark border border-register-dark",
    secondary: "bg-sheet text-ink border border-rule hover:border-ink-faint",
    ghost: "text-ink-soft hover:text-ink hover:bg-rule-soft border border-transparent",
    danger: "bg-sheet text-redpen border border-rule hover:border-redpen",
  };
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-[6px] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap",
        size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm",
        styles[variant],
        className,
      )}
    >
      {busy && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------- Fields */
export function Label({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <span className="mb-1 block text-[13px] font-semibold text-ink-soft">
      {children}
      {hint && <span className="ml-1.5 font-normal text-ink-faint">{hint}</span>}
    </span>
  );
}

const inputCls =
  "w-full h-9 rounded-[6px] border border-rule bg-sheet px-2.5 text-sm text-ink placeholder:text-ink-faint focus:border-register focus:outline-none focus:ring-2 focus:ring-register/15";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(inputCls, className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cx(inputCls, "pr-7", className)}>
      {children}
    </select>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <Label hint={hint}>{label}</Label>
      {children}
    </label>
  );
}

/* --------------------------------------------------------------- Page head */
export function PageHeader({ title, intro, actions }: { title: string; intro?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-display text-[28px] font-semibold leading-tight text-ink">{title}</h1>
        {intro && <p className="mt-1 max-w-[68ch] text-[15px] text-ink-soft">{intro}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ children, className, title, actions }: { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={cx("rounded-[8px] border border-rule bg-sheet", className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 border-b border-rule-soft px-4 py-3">
          <h2 className="font-display text-[17px] font-semibold">{title}</h2>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 px-5 py-10">
      <p className="font-display text-lg font-semibold">{title}</p>
      {children && <div className="max-w-[60ch] text-ink-soft">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Pill({ tone = "neutral", children }: { tone?: "neutral" | "green" | "red" | "yellow"; children: ReactNode }) {
  const t = {
    neutral: "bg-rule-soft text-ink-soft",
    green: "bg-register-wash text-register-dark",
    red: "bg-redpen-wash text-redpen",
    yellow: "bg-marker-wash text-[#7a5d00]",
  }[tone];
  return <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-[12px] font-semibold", t)}>{children}</span>;
}

export function StatusPill({ status }: { status: string }) {
  if (status === "published") return <Pill tone="green">Published</Pill>;
  if (status === "archived") return <Pill>Archived</Pill>;
  return <Pill tone="yellow">Draft</Pill>;
}

export function ErrorNote({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return <p className="rounded-[6px] border border-redpen/30 bg-redpen-wash px-3 py-2 text-sm text-redpen">{error}</p>;
}

/* ------------------------------------------------------------------ Drawer */
export function Drawer({
  open,
  onClose,
  title,
  children,
  footer,
  width = 520,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("input,select,textarea,button")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end no-print" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-ink/25" onClick={onClose} />
      <div
        ref={ref}
        className="relative flex h-full w-full flex-col border-l border-rule bg-sheet shadow-[-12px_0_32px_rgba(27,35,64,0.12)]"
        style={{ maxWidth: width }}
      >
        <div className="flex items-center justify-between border-b border-rule-soft px-5 py-4">
          <h2 className="font-display text-xl font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-ink-faint hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-rule-soft px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Toasts */
interface Toast {
  id: number;
  text: string;
  tone: "ok" | "error";
}
const ToastCtx = createContext<(text: string, tone?: "ok" | "error") => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 6000 : 3200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100vw-32px))] flex-col gap-2 no-print" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "rounded-[8px] border px-4 py-3 text-sm shadow-[0_8px_24px_rgba(27,35,64,0.14)]",
              t.tone === "error" ? "border-redpen/40 bg-sheet text-redpen" : "border-register/40 bg-sheet text-ink",
            )}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

/* ------------------------------------------------------------- Data hook */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    loader()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e.message ?? String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1), setData };
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="px-1 py-8 text-ink-faint">{label}</p>;
}
