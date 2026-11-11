"use client";

import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import ExportButtons from "@/components/ExportButtons";
import { Alert, Card, Empty, Spinner, inputCls } from "@/components/ui";
import { api } from "@/lib/api";
import { brl, dateBR, dateTimeBR, pct } from "@/lib/format";

const DEMO = [
  { file: "1_sistema_erp_DEMO.csv", label: "Arquivo 1 · Sistema financeiro/ERP (CSV, Windows-1252)" },
  { file: "2_extrato_bancario_DEMO.ofx", label: "Arquivo 2 · Extrato bancário (OFX SGML 1.02)" },
  { file: "3_maquina_cartao_DEMO.csv", label: "Arquivo 3 · Máquina de cartão (CSV)" },
  { file: "4_adquirente_DEMO.csv", label: "Arquivo 4 · Adquirente/liquidação (CSV)" },
];

export default function Relatorios() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/reconciliations").then((r) => { setRows(r); if (r.length) setSel(r[0].id); }).catch((e) => setError(e.message));
  }, []);
  const cur = rows?.find((r) => r.id === sel);
  return (
    <>
      <PageHeader title="Relatórios" subtitle="Exporte os resultados em Excel, CSV ou PDF." />
      {error && <Alert tone="error">{error}</Alert>}
      {!rows ? <Spinner /> : rows.length === 0 ? <Empty title="Nenhuma conciliação para exportar">Processe uma conciliação primeiro.</Empty> : (
        <Card title="Conciliação" className="mb-6">
          <select className={inputCls + " max-w-xl"} value={sel ?? ""} onChange={(e) => setSel(Number(e.target.value))}>
            {rows.map((r) => <option key={r.id} value={r.id}>{r.code} v{r.version} · {dateBR(r.period_start)} a {dateBR(r.period_end)} · {dateTimeBR(r.created_at)}</option>)}
          </select>
          {cur && <p className="mt-2 text-sm text-ink-500">Conciliado {brl(cur.totals.total_conciliado)} · {pct(cur.totals.percentual_conciliacao)} dos registros · {cur.totals.total_divergencias} divergência(s) · responsável {cur.user}</p>}
          {sel && <div className="mt-5"><ExportButtons id={sel} /></div>}
        </Card>
      )}
      <Card title="Arquivos de demonstração" className="scroll-mt-6">
        <div id="demo" />
        <p className="mb-4 text-sm text-ink-700">Dados <b>fictícios</b>, gerados para testar o fluxo completo (inclui divergência de valor, de data, taxa divergente, estorno, duplicidade, pendências e itens não localizados). Baixe os quatro e carregue-os em <b>Nova conciliação</b>.</p>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {DEMO.map((d) => (
            <li key={d.file}><a href={`/demo/${d.file}`} download className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2.5 text-sm hover:border-brand-400">
              <Download className="h-4 w-4 text-brand-600" /><span><span className="block font-medium">{d.file}</span><span className="text-xs text-ink-500">{d.label}</span></span>
            </a></li>
          ))}
        </ul>
      </Card>
    </>
  );
}
