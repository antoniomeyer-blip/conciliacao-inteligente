"use client";

import { FileDown, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui";
import { download } from "@/lib/api";

export const EXPORTS = [
  { type: "xlsx", label: "Excel (.xlsx)", desc: "Abas separadas por status, resumo e trilha de vínculos para auditoria.", icon: FileSpreadsheet },
  { type: "pdf", label: "PDF executivo", desc: "Indicadores, resultado por status e principais divergências.", icon: FileText },
  { type: "divergencias", label: "Divergências (PDF)", desc: "Relatório detalhado de cada divergência, pendência e não localizado.", icon: FileText },
  { type: "csv", label: "CSV completo", desc: "Todas as transações com status e justificativa (separador ;).", icon: FileDown },
  { type: "resumo", label: "Resumo financeiro (CSV)", desc: "Totais e indicadores da conciliação.", icon: FileDown },
];

export default function ExportButtons({ id, compact }: { id: number; compact?: boolean }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  async function go(type: string) {
    setBusy(type); setErr("");
    try { await download(`/api/reconciliations/${id}/export?type=${type}`); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  }
  if (compact)
    return (
      <div className="flex flex-wrap gap-2">
        {EXPORTS.slice(0, 3).map((e) => <Button key={e.type} size="sm" variant="secondary" loading={busy === e.type} onClick={() => go(e.type)}><e.icon className="h-4 w-4" />{e.label}</Button>)}
        {err && <span className="text-xs text-rose-700">{err}</span>}
      </div>
    );
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {EXPORTS.map((e) => (
        <button key={e.type} onClick={() => go(e.type)} disabled={!!busy}
          className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-card transition hover:border-brand-400 disabled:opacity-60">
          <e.icon className="mt-0.5 h-5 w-5 text-brand-600" />
          <span><span className="block text-sm font-semibold text-ink-900">{busy === e.type ? "Gerando..." : e.label}</span><span className="text-xs text-ink-500">{e.desc}</span></span>
        </button>
      ))}
      {err && <p className="text-sm text-rose-700">{err}</p>}
    </div>
  );
}
