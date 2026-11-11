"use client";

import { AlertTriangle, BadgeCheck, Banknote, Clock, Percent, Receipt, Scale, ShoppingCart } from "lucide-react";
import { Card, Kpi } from "@/components/ui";
import { DailyBars, DivergenceBars, SourceBars, StatusDonut } from "@/components/Charts";
import { SOURCES, brl, pct } from "@/lib/format";

export default function Summary({ totals }: { totals: any }) {
  const diff = Number(totals.diferencas_financeiras);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="% Conciliação" icon={<Percent className="h-4 w-4" />} value={pct(totals.percentual_conciliacao)}
          tone={totals.percentual_conciliacao >= 80 ? "good" : totals.percentual_conciliacao >= 50 ? "warn" : "bad"}
          hint={`${totals.conciliadas} de ${totals.transacoes} registros · ${pct(totals.percentual_conciliacao_valor_banco)} do valor do extrato`} />
        <Kpi label="Total conciliado" icon={<BadgeCheck className="h-4 w-4" />} value={brl(totals.total_conciliado)} hint="Créditos + débitos do extrato" />
        <Kpi label="Valor de vendas" icon={<ShoppingCart className="h-4 w-4" />} value={brl(totals.valor_total_vendas)} hint={`Taxas de adquirência: ${brl(totals.taxas_adquirencia)}`} />
        <Kpi label="Total recebido" icon={<Banknote className="h-4 w-4" />} value={brl(totals.valor_total_recebido)} hint="Créditos no extrato bancário" />
        <Kpi label="Divergências" icon={<AlertTriangle className="h-4 w-4" />} value={totals.total_divergencias}
          tone={totals.total_divergencias ? "warn" : "good"} hint={`${totals.sugestoes_pendentes} sugestão(ões) aguardando aprovação`} />
        <Kpi label="Total pendente" icon={<Clock className="h-4 w-4" />} value={brl(totals.total_pendente)} hint="Aguardando liquidação" />
        <Kpi label="Diferenças financeiras" icon={<Scale className="h-4 w-4" />} value={brl(diff)} tone={diff ? "warn" : "good"} hint={`${brl(totals.valor_divergencias)} em valor absoluto`} />
        <Kpi label="Registros importados" icon={<Receipt className="h-4 w-4" />} value={totals.transacoes}
          hint={Object.entries(totals.registros_por_fonte || {}).map(([k, v]: any) => `${SOURCES[k]?.label}: ${v.registros}`).join(" · ")} />
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card title="Resultado por status"><StatusDonut data={totals.por_status || {}} /></Card>
        <Card title="Registros por origem"><SourceBars data={totals.registros_por_fonte || {}} /></Card>
        <Card title="Movimentação do extrato por dia"><DailyBars data={totals.por_dia || []} /></Card>
        <Card title="Divergências por tipo"><DivergenceBars data={totals.por_divergencia || {}} /></Card>
      </div>
    </div>
  );
}
