"use client";

import { BarChart3, FileSpreadsheet, History, LayoutDashboard, LogOut, Menu, Settings, Upload, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { clearSession, getToken, getUser } from "@/lib/api";
import { cx } from "@/lib/format";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/nova", label: "Nova Conciliação", icon: Upload },
  { href: "/historico", label: "Histórico", icon: History },
  { href: "/relatorios", label: "Relatórios", icon: FileSpreadsheet },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cx("flex items-center gap-2.5", className)}>
      <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500 text-white">
        <BarChart3 className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold">Conciliação</div>
        <div className="text-[11px] font-medium uppercase tracking-[0.14em] opacity-70">Inteligente</div>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setUser(getUser());
    setReady(true);
  }, [router]);

  useEffect(() => setOpen(false), [path]);

  if (!ready) return null;

  const nav = (
    <nav className="flex flex-1 flex-col gap-1 px-3">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link key={href} href={href}
            className={cx("flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition",
              active ? "bg-white/10 text-white" : "text-brand-100/80 hover:bg-white/5 hover:text-white")}>
            <Icon className="h-[18px] w-[18px]" /> {label}
          </Link>
        );
      })}
    </nav>
  );

  const footer = (
    <div className="border-t border-white/10 p-4">
      <div className="text-sm font-medium text-white">{user?.name}</div>
      <div className="truncate text-xs text-brand-100/70">{user?.company?.name} · {user?.role === "admin" ? "Administrador" : "Analista"}</div>
      <button onClick={() => { clearSession(); router.replace("/login"); }}
        className="mt-3 flex items-center gap-2 text-xs text-brand-100/80 hover:text-white">
        <LogOut className="h-3.5 w-3.5" /> Sair
      </button>
    </div>
  );

  return (
    <div className="min-h-screen bg-paper">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col bg-brand-800 text-white lg:flex">
        <div className="px-5 py-6"><Logo /></div>
        {nav}
        {footer}
      </aside>
      <div className="sticky top-0 z-20 flex items-center justify-between bg-brand-800 px-4 py-3 text-white lg:hidden">
        <Logo />
        <button onClick={() => setOpen(true)} aria-label="Abrir menu"><Menu className="h-6 w-6" /></button>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 bg-ink-900/40 lg:hidden" onClick={() => setOpen(false)}>
          <aside className="flex h-full w-72 flex-col bg-brand-800 text-white" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-5"><Logo /><button onClick={() => setOpen(false)} aria-label="Fechar"><X className="h-5 w-5" /></button></div>
            {nav}
            {footer}
          </aside>
        </div>
      )}
      <main className="lg:pl-64">
        <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
