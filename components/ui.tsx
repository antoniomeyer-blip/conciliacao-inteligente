"use client";

import { Loader2, X } from "lucide-react";
import { ReactNode, useEffect } from "react";
import { STATUS, cx } from "@/lib/format";

export function Button({
  children, variant = "primary", size = "md", loading, className, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "success"; size?: "sm" | "md" | "lg"; loading?: boolean;
}) {
  const base = "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:opacity-50 disabled:cursor-not-allowed";
  const v = {
    primary: "bg-brand-800 text-white hover:bg-brand-700 shadow-sm",
    secondary: "bg-white text-ink-900 ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    ghost: "text-ink-700 hover:bg-slate-100",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
    success: "bg-emerald-600 text-white hover:bg-emerald-700",
  }[variant];
  const s = { sm: "px-2.5 py-1.5 text-xs", md: "px-3.5 py-2 text-sm", lg: "px-5 py-3 text-base" }[size];
  return (
    <button className={cx(base, v, s, className)} disabled={loading || props.disabled} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ children, className, title, action }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={cx("rounded-xl border border-slate-200 bg-white shadow-card", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] || { label: status, tone: "bg-slate-100 text-slate-700 ring-slate-500/20" };
  return <span className={cx("inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", s.tone)}>{s.label}</span>;
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "brand" | "amber" | "rose" | "emerald" }) {
  const t = {
    slate: "bg-slate-100 text-slate-700", brand: "bg-brand-50 text-brand-700", amber: "bg-amber-50 text-amber-800",
    rose: "bg-rose-50 text-rose-700", emerald: "bg-emerald-50 text-emerald-700",
  }[tone];
  return <span className={cx("inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium", t)}>{children}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-500">
      <Loader2 className="h-5 w-5 animate-spin" /> {label || "Carregando..."}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide, footer }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean; footer?: ReactNode;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-900/40 p-4 pt-[6vh]" onClick={onClose}>
      <div className={cx("w-full rounded-xl bg-white shadow-xl", wide ? "max-w-5xl" : "max-w-lg")} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="font-semibold text-ink-900">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-ink-400 hover:bg-slate-100" aria-label="Fechar"><X className="h-5 w-5" /></button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto p-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink-900/30" onClick={onClose}>
      <aside className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white px-6 py-4">
          <h3 className="font-semibold text-ink-900">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-ink-400 hover:bg-slate-100" aria-label="Fechar"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-6">{children}</div>
      </aside>
    </div>
  );
}

export function Kpi({ label, value, hint, tone = "default", icon }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "default" | "good" | "warn" | "bad"; icon?: ReactNode }) {
  const t = { default: "text-ink-900", good: "text-emerald-700", warn: "text-amber-700", bad: "text-rose-700" }[tone];
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-ink-500">
        {label} {icon && <span className="text-ink-400">{icon}</span>}
      </div>
      <div className={cx("mt-2 text-lg font-semibold tabular-nums sm:text-2xl", t)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-500">{hint}</div>}
    </div>
  );
}

export function Alert({ tone = "info", children }: { tone?: "info" | "warn" | "error" | "success"; children: ReactNode }) {
  const t = {
    info: "bg-sky-50 text-sky-900 border-sky-200", warn: "bg-amber-50 text-amber-900 border-amber-200",
    error: "bg-rose-50 text-rose-900 border-rose-200", success: "bg-emerald-50 text-emerald-900 border-emerald-200",
  }[tone];
  return <div className={cx("rounded-lg border px-4 py-3 text-sm", t)}>{children}</div>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-500">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-ink-900 placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100";

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      <h3 className="text-base font-semibold text-ink-900">{title}</h3>
      {children && <div className="mx-auto mt-2 max-w-md text-sm text-ink-500">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
