"use client";

import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { STATUS, SOURCES, brl, dateBR } from "@/lib/format";

const axis = { fontSize: 11, fill: "#5B6B6D" };
const money = (v: any) => brl(v);
const short = (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil` : String(v));

export function StatusDonut({ data }: { data: Record<string, { registros: number; valor: string }> }) {
  const rows = Object.entries(data).map(([k, v]) => ({ key: k, name: STATUS[k]?.label || k, value: v.registros, valor: v.valor }));
  return (
    <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-2">
      <div className="h-56">
        <ResponsiveContainer>
          <PieChart>
            <Pie isAnimationActive={false} data={rows} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="90%" paddingAngle={1.5} stroke="none">
              {rows.map((r) => <Cell key={r.key} fill={STATUS[r.key]?.color || "#999"} />)}
            </Pie>
            <Tooltip formatter={(v: any, _n: any, p: any) => [`${v} registro(s) · ${brl(p.payload.valor)}`, p.payload.name]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-1.5 text-sm">
        {rows.sort((a, b) => b.value - a.value).map((r) => (
          <li key={r.key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-ink-700"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: STATUS[r.key]?.color }} />{r.name}</span>
            <span className="tabular-nums text-ink-900">{r.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SourceBars({ data }: { data: Record<string, { registros: number; conciliados: number }> }) {
  const rows = ["erp", "bank", "machine", "acquirer"].filter((k) => data[k]).map((k) => ({
    name: SOURCES[k].label, Conciliados: data[k].conciliados, Pendentes: data[k].registros - data[k].conciliados,
  }));
  return (
    <div className="h-64">
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ left: -10, right: 8 }}>
          <CartesianGrid vertical={false} stroke="#EEF1F0" />
          <XAxis dataKey="name" tick={axis} axisLine={false} tickLine={false} />
          <YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip cursor={{ fill: "#F3F6F5" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar isAnimationActive={false} dataKey="Conciliados" stackId="a" fill="#1F7A70" radius={[0, 0, 0, 0]} />
          <Bar isAnimationActive={false} dataKey="Pendentes" stackId="a" fill="#E3C27A" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DailyBars({ data }: { data: { data: string; conciliado: string; nao_conciliado: string }[] }) {
  const rows = data.map((d) => ({ name: dateBR(d.data).slice(0, 5), Conciliado: Number(d.conciliado), "Não conciliado": Number(d.nao_conciliado) }));
  return (
    <div className="h-64">
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ left: 0, right: 8 }}>
          <CartesianGrid vertical={false} stroke="#EEF1F0" />
          <XAxis dataKey="name" tick={axis} axisLine={false} tickLine={false} />
          <YAxis tick={axis} axisLine={false} tickLine={false} tickFormatter={short} />
          <Tooltip formatter={money} cursor={{ fill: "#F3F6F5" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar isAnimationActive={false} dataKey="Conciliado" stackId="a" fill="#1F7A70" />
          <Bar isAnimationActive={false} dataKey="Não conciliado" stackId="a" fill="#C2415B" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DivergenceBars({ data }: { data: Record<string, number> }) {
  const rows = Object.entries(data).map(([k, v]) => ({ key: k, name: STATUS[k]?.label || k, Registros: v }));
  if (!rows.length) return <p className="py-16 text-center text-sm text-ink-500">Nenhuma divergência encontrada.</p>;
  return (
    <div className="h-64">
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ left: 40, right: 16 }}>
          <CartesianGrid horizontal={false} stroke="#EEF1F0" />
          <XAxis type="number" tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={axis} axisLine={false} tickLine={false} width={150} />
          <Tooltip cursor={{ fill: "#F3F6F5" }} />
          <Bar isAnimationActive={false} dataKey="Registros" radius={[0, 4, 4, 0]}>
            {rows.map((r) => <Cell key={r.key} fill={STATUS[r.key]?.color || "#999"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function HistoryLine({ data }: { data: { code: string; version: number; percentual: number }[] }) {
  const rows = data.map((d) => ({ name: `${d.code.slice(-5)} v${d.version}`, "% conciliado": d.percentual }));
  return (
    <div className="h-56">
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ left: -10, right: 8 }}>
          <CartesianGrid vertical={false} stroke="#EEF1F0" />
          <XAxis dataKey="name" tick={axis} axisLine={false} tickLine={false} />
          <YAxis domain={[0, 100]} tick={axis} axisLine={false} tickLine={false} />
          <Tooltip formatter={(v: any) => `${Number(v).toFixed(1)}%`} />
          <Line isAnimationActive={false} type="monotone" dataKey="% conciliado" stroke="#1F7A70" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
