const fmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function brl(v: any): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? fmt.format(n) : "—";
}

export function dateBR(v?: string | null): string {
  if (!v) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : v;
}

export function dateTimeBR(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function pct(v: any): string {
  const n = Number(v ?? 0);
  return `${n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1).replace(".", ",")} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

export const STATUS: Record<string, { label: string; tone: string; color: string }> = {
  conciliado: { label: "Conciliado", tone: "bg-emerald-50 text-emerald-800 ring-emerald-600/20", color: "#1F7A70" },
  divergencia_valor: { label: "Divergência de valor", tone: "bg-amber-50 text-amber-800 ring-amber-600/20", color: "#D08C1F" },
  divergencia_data: { label: "Divergência de data", tone: "bg-sky-50 text-sky-800 ring-sky-600/20", color: "#3B82C4" },
  taxa_divergente: { label: "Taxa divergente", tone: "bg-orange-50 text-orange-800 ring-orange-600/20", color: "#E0702A" },
  pendente_liquidacao: { label: "Pendente de liquidação", tone: "bg-slate-100 text-slate-700 ring-slate-500/20", color: "#8A9AA0" },
  nao_localizado_banco: { label: "Não localizado no banco", tone: "bg-rose-50 text-rose-800 ring-rose-600/20", color: "#C2415B" },
  nao_localizado_sistema: { label: "Não localizado no sistema", tone: "bg-fuchsia-50 text-fuchsia-800 ring-fuchsia-600/20", color: "#9B4DB5" },
  duplicidade: { label: "Duplicidade", tone: "bg-red-50 text-red-800 ring-red-600/20", color: "#B42318" },
  estorno_cancelamento: { label: "Estorno/cancelamento", tone: "bg-violet-50 text-violet-800 ring-violet-600/20", color: "#6D5BD0" },
  analise_manual: { label: "Necessita análise manual", tone: "bg-yellow-50 text-yellow-900 ring-yellow-600/30", color: "#B59B00" },
};

export const SOURCES: Record<string, { label: string; long: string }> = {
  erp: { label: "ERP", long: "Sistema financeiro/ERP" },
  bank: { label: "Banco", long: "Extrato bancário" },
  machine: { label: "Máquina", long: "Máquina de cartão" },
  acquirer: { label: "Adquirente", long: "Adquirente/liquidação" },
};

export const LEVELS: Record<number, string> = {
  1: "Identificador único",
  2: "Valor e data exatos",
  3: "Valor com tolerância de data",
  4: "Valores agrupados",
  5: "Valor líquido (taxas)",
};

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}
