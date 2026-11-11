"use client";

import { ExternalLink, RefreshCw, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, Badge, Button, Empty, Spinner, inputCls } from "@/components/ui";
import { api, getUser } from "@/lib/api";
import { SOURCES, brl, dateBR, dateTimeBR, pct } from "@/lib/format";

export default function Historico() {
  const router = useRouter();
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const isAdmin = getUser()?.role === "admin";
  const load = () => api("/api/reconciliations").then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => (rows || []).filter((r) => !q || [r.code, r.user, ...r.files.map((f: any) => f.filename)].join(" ").toLowerCase().includes(q.toLowerCase())), [rows, q]);

  async function reprocess(id: number) {
    if (!confirm("Reprocessar com as configurações atuais? Será criada uma nova versão; a anterior permanece no histórico.")) return;
    setBusy(id);
    try { const r = await api(`/api/reconciliations/${id}/reprocess`, { method: "POST" }); router.push(`/historico/${r.id}`); }
    catch (e: any) { setError(e.message); setBusy(null); }
  }
  async function remove(id: number, code: string) {
    if (!confirm(`Excluir definitivamente a conciliação ${code}?`)) return;
    try { await api(`/api/reconciliations/${id}`, { method: "DELETE" }); load(); } catch (e: any) { setError(e.message); }
  }

  return (
    <>
      <PageHeader title="Histórico" subtitle="Todas as conciliações processadas, com versões e responsáveis."
        actions={<Link href="/nova"><Button><Upload className="h-4 w-4" /> Nova conciliação</Button></Link>} />
      {error && <div className="mb-4"><Alert tone="error">{error}</Alert></div>}
      {!rows ? <Spinner /> : rows.length === 0 ? <Empty title="Nenhuma conciliação ainda" action={<Link href="/nova"><Button>Começar</Button></Link>} /> : (
        <div className="rounded-xl border border-slate-200 bg-white shadow-card">
          <div className="border-b border-slate-100 p-4"><input className={inputCls + " max-w-sm"} placeholder="Buscar por código, arquivo ou usuário" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-ink-500">
                <tr>
                  <th className="px-4 py-3">Identificação</th><th className="px-4 py-3">Processado em</th><th className="px-4 py-3">Período</th>
                  <th className="px-4 py-3">Arquivos</th><th className="px-4 py-3 text-right">Conciliado</th><th className="px-4 py-3 text-right">%</th>
                  <th className="px-4 py-3 text-right">Divergências</th><th className="px-4 py-3">Responsável</th><th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3"><Link href={`/historico/${r.id}`} className="font-medium text-brand-700 hover:underline">{r.code}</Link> <Badge tone={r.version > 1 ? "amber" : "slate"}>v{r.version}</Badge></td>
                    <td className="whitespace-nowrap px-4 py-3 text-ink-700">{dateTimeBR(r.created_at)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-ink-700">{dateBR(r.period_start)} a {dateBR(r.period_end)}</td>
                    <td className="px-4 py-3 text-xs text-ink-500">{r.files.map((f: any) => <div key={f.source} className="max-w-[16rem] truncate" title={f.filename}><b className="text-ink-700">{SOURCES[f.source]?.label}:</b> {f.filename} ({f.registros})</div>)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums">{brl(r.totals.total_conciliado)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{pct(r.totals.percentual_conciliacao)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{r.totals.total_divergencias}</td>
                    <td className="px-4 py-3 text-ink-700">{r.user}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <Link href={`/historico/${r.id}`}><Button size="sm" variant="ghost" title="Abrir"><ExternalLink className="h-4 w-4" /></Button></Link>
                      <Button size="sm" variant="ghost" title="Reprocessar (nova versão)" loading={busy === r.id} onClick={() => reprocess(r.id)}><RefreshCw className="h-4 w-4" /></Button>
                      {isAdmin && <Button size="sm" variant="ghost" title="Excluir" onClick={() => remove(r.id, r.code)}><Trash2 className="h-4 w-4 text-rose-600" /></Button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
