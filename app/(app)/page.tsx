"use client";

import { ArrowRight, Download, Upload } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { HistoryLine } from "@/components/Charts";
import Summary from "@/components/Summary";
import { Alert, Button, Card, Empty, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { SOURCES, dateBR, dateTimeBR } from "@/lib/format";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => { api("/api/dashboard").then(setData).catch((e) => setError(e.message)); }, []);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data) return <Spinner />;
  const r = data.latest;
  if (!r)
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Visão geral da conciliação mais recente." />
        <Empty title="Nenhuma conciliação processada ainda"
          action={<div className="flex flex-wrap justify-center gap-2">
            <Link href="/nova"><Button><Upload className="h-4 w-4" /> Nova conciliação</Button></Link>
            <Link href="/relatorios#demo"><Button variant="secondary"><Download className="h-4 w-4" /> Arquivos de demonstração</Button></Link>
          </div>}>
          Carregue os arquivos do ERP, extrato bancário, máquina de cartão e adquirente para ver os indicadores aqui.
        </Empty>
      </>
    );
  return (
    <>
      <PageHeader title="Dashboard"
        subtitle={<>Última conciliação <b>{r.code}</b> (v{r.version}) · período {dateBR(r.period_start)} a {dateBR(r.period_end)} · {dateTimeBR(r.created_at)} · {r.user}</>}
        actions={<>
          <Link href={`/historico/${r.id}`}><Button variant="secondary">Analisar divergências <ArrowRight className="h-4 w-4" /></Button></Link>
          <Link href="/nova"><Button><Upload className="h-4 w-4" /> Nova conciliação</Button></Link>
        </>} />
      <div className="mb-4 flex flex-wrap gap-2 text-xs text-ink-500">
        {r.files.map((f: any) => <span key={f.source} className="rounded-md bg-white px-2 py-1 ring-1 ring-slate-200">{SOURCES[f.source]?.label}: {f.filename}</span>)}
      </div>
      <Summary totals={r.totals} />
      {data.history.length > 1 && <Card title="Evolução do percentual de conciliação" className="mt-6"><HistoryLine data={data.history} /></Card>}
    </>
  );
}
