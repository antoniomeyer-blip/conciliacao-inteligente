"use client";

import { AlertCircle, CheckCircle2, Columns3, Eye, FileUp, Loader2, PlayCircle, RefreshCw, Trash2, Wand2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { DragEvent, useRef, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, Badge, Button, Field, Modal, inputCls } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { SOURCES, brl, bytes, cx, dateBR, dateTimeBR } from "@/lib/format";

type Slot = { file?: File; state: "idle" | "uploading" | "ok" | "mapping" | "error"; result?: any; error?: string };
const ORDER = ["erp", "bank", "machine", "acquirer"] as const;
const HINTS: Record<string, string> = {
  erp: "Lançamentos financeiros (contas pagas/recebidas). CSV, XLSX, XLS, TXT ou PDF.",
  bank: "Extrato da conta corrente. OFX (recomendado), XLSX, CSV ou PDF.",
  machine: "Vendas da maquininha (NSU, autorização, bandeira, valor). Opcional.",
  acquirer: "Relatório de vendas recebidas/liquidações da adquirente (bruto, taxa, líquido).",
};
const ACCEPT = ".xlsx,.xls,.xlsm,.csv,.ofx,.qfx,.txt,.pdf";
const STAGES = ["Lendo registros validados", "Verificando duplicidades", "Nível 1 · identificadores únicos",
  "Níveis 2 e 3 · valor e data", "Nível 4 · liquidações agrupadas", "Nível 5 · valor líquido e taxas", "Calculando totais e gravando histórico"];

export default function NovaConciliacao() {
  const router = useRouter();
  const [slots, setSlots] = useState<Record<string, Slot>>(Object.fromEntries(ORDER.map((k) => [k, { state: "idle" }])));
  const [mapFor, setMapFor] = useState<string | null>(null);
  const [previewFor, setPreviewFor] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState("");
  const [dup, setDup] = useState<any>(null);

  const update = (k: string, s: Partial<Slot>) => setSlots((p) => ({ ...p, [k]: { ...p[k], ...s } }));

  async function upload(source: string, file: File, extra?: { mapping?: any; header_row?: number; save?: boolean; name?: string }) {
    const prev = slots[source]?.result?.staged_id;
    update(source, { file, state: "uploading", error: undefined });
    const fd = new FormData();
    fd.append("source", source);
    fd.append("file", file);
    if (extra?.mapping) fd.append("mapping", JSON.stringify(extra.mapping));
    if (extra?.header_row !== undefined) fd.append("header_row", String(extra.header_row));
    if (extra?.save) { fd.append("save_template", "true"); fd.append("template_name", extra.name || ""); }
    if (prev) fd.append("replace_staged_id", String(prev));
    try {
      const res = await api("/api/files/parse", { method: "POST", body: fd });
      update(source, { state: res.needs_mapping ? "mapping" : "ok", result: res });
      if (res.needs_mapping) setMapFor(source);
    } catch (e: any) {
      update(source, { state: "error", error: e.message, result: undefined });
    }
  }

  function remove(source: string) {
    const id = slots[source]?.result?.staged_id;
    if (id) api(`/api/files/staged/${id}`, { method: "DELETE" }).catch(() => {});
    update(source, { file: undefined, state: "idle", result: undefined, error: undefined });
  }

  const ready = ORDER.filter((k) => slots[k].state === "ok");
  const canProcess = slots.bank.state === "ok" && ready.length >= 2 && !ORDER.some((k) => slots[k].state === "uploading");
  const step = processing ? 4 : canProcess ? 3 : ready.length ? 2 : 1;

  async function process(force = false) {
    setError(""); setDup(null); setProcessing(true); setStage(0);
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 450);
    try {
      const files = Object.fromEntries(ready.map((k) => [k, slots[k].result.staged_id]));
      const res = await api("/api/reconciliations", { method: "POST", json: { files, force } });
      setStage(STAGES.length);
      router.push(`/historico/${res.id}`);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409) setDup(e.detail);
      else setError(e.message);
      setProcessing(false);
    } finally {
      clearInterval(timer);
    }
  }

  return (
    <>
      <PageHeader title="Nova conciliação" subtitle="Carregue os arquivos, confira a leitura e clique em Processar." />
      <Steps current={step} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {ORDER.map((k, i) => (
          <SourceCard key={k} index={i + 1} source={k} slot={slots[k]} onFile={(f) => upload(k, f)} onRemove={() => remove(k)}
            onMap={() => setMapFor(k)} onPreview={() => setPreviewFor(k)} />
        ))}
      </div>

      <div className="mt-6 flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 shadow-card sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm text-ink-700">
          {canProcess ? <><b>{ready.length} arquivo(s)</b> validado(s). Pronto para processar.</> :
            <>Envie o <b>extrato bancário</b> e pelo menos mais um arquivo. A máquina de cartão é opcional quando o relatório da adquirente já traz as vendas.</>}
          <div className="mt-1 text-xs text-ink-500">Não tem arquivos agora? <Link className="text-brand-600 underline" href="/relatorios#demo">Baixe os arquivos de demonstração</Link>.</div>
        </div>
        <Button size="lg" onClick={() => process(false)} disabled={!canProcess} loading={processing}>
          <PlayCircle className="h-5 w-5" /> Processar conciliação
        </Button>
      </div>
      {error && <div className="mt-4"><Alert tone="error">{error}</Alert></div>}

      <Modal open={processing} onClose={() => {}} title="Processando conciliação">
        <ol className="space-y-2.5">
          {STAGES.map((s, i) => (
            <li key={s} className={cx("flex items-center gap-3 text-sm", i > stage ? "text-ink-400" : "text-ink-900")}>
              {i < stage ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : i === stage ? <Loader2 className="h-4 w-4 animate-spin text-brand-500" /> : <span className="h-4 w-4 rounded-full border border-slate-300" />}
              {s}
            </li>
          ))}
        </ol>
      </Modal>

      <Modal open={!!dup} onClose={() => setDup(null)} title="Arquivos já processados"
        footer={<><Button variant="secondary" onClick={() => router.push(`/historico/${dup?.existing?.id}`)}>Abrir processamento existente</Button>
          <Button onClick={() => process(true)}><RefreshCw className="h-4 w-4" /> Criar nova versão</Button></>}>
        <p className="text-sm text-ink-700">{dup?.message}</p>
        {dup?.existing && <p className="mt-3 text-sm text-ink-500">Processamento <b>{dup.existing.code}</b>, versão {dup.existing.version}, em {dateTimeBR(dup.existing.created_at)}.</p>}
      </Modal>

      {mapFor && slots[mapFor]?.result && (
        <MappingModal source={mapFor} result={slots[mapFor].result} onClose={() => setMapFor(null)}
          onApply={(mapping, header_row, save, name) => { const f = slots[mapFor].file!; setMapFor(null); upload(mapFor, f, { mapping, header_row, save, name }); }} />
      )}
      {previewFor && slots[previewFor]?.result && <PreviewModal result={slots[previewFor].result} onClose={() => setPreviewFor(null)} />}
    </>
  );
}

function Steps({ current }: { current: number }) {
  const steps = ["Carregar arquivos", "Validar e visualizar", "Processar", "Acompanhar", "Dashboard e divergências"];
  return (
    <ol className="mb-6 grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
      {steps.map((s, i) => (
        <li key={s} className={cx("flex items-center gap-2 rounded-lg px-3 py-2 ring-1",
          i + 1 < current ? "bg-brand-50 text-brand-700 ring-brand-100" : i + 1 === current ? "bg-brand-800 text-white ring-brand-800" : "bg-white text-ink-500 ring-slate-200")}>
          <span className="font-semibold">{i + 1}</span> {s}
        </li>
      ))}
    </ol>
  );
}

function SourceCard({ index, source, slot, onFile, onRemove, onMap, onPreview }: {
  index: number; source: string; slot: Slot; onFile: (f: File) => void; onRemove: () => void; onMap: () => void; onPreview: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const r = slot.result;
  const drop = (e: DragEvent) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f); };
  return (
    <div className={cx("rounded-xl border bg-white p-5 shadow-card transition",
      slot.state === "ok" ? "border-emerald-200" : slot.state === "error" ? "border-rose-200" : slot.state === "mapping" ? "border-amber-200" : "border-slate-200")}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-ink-500">Arquivo {index}{source === "machine" && " · opcional"}</div>
          <h3 className="font-semibold text-ink-900">{SOURCES[source].long}</h3>
          <p className="mt-0.5 text-xs text-ink-500">{HINTS[source]}</p>
        </div>
        {slot.state === "ok" && <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-600" />}
        {slot.state === "error" && <AlertCircle className="h-6 w-6 shrink-0 text-rose-600" />}
        {slot.state === "mapping" && <Columns3 className="h-6 w-6 shrink-0 text-amber-600" />}
      </div>
      <input ref={input} type="file" accept={ACCEPT} className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      {!slot.file ? (
        <button type="button" onClick={() => input.current?.click()} onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)} onDrop={drop}
          className={cx("mt-4 flex w-full flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-sm transition",
            over ? "border-brand-400 bg-brand-50" : "border-slate-300 hover:border-brand-400 hover:bg-slate-50")}>
          <FileUp className="mb-2 h-7 w-7 text-ink-400" />
          <span className="font-medium text-ink-700">Arraste o arquivo aqui ou clique para selecionar</span>
          <span className="mt-1 text-xs text-ink-500">XLSX, XLS, CSV, OFX, TXT ou PDF · até 10 MB</span>
        </button>
      ) : (
        <div className="mt-4 rounded-lg bg-slate-50 p-3" onDragOver={(e) => e.preventDefault()} onDrop={drop}>
          <div className="flex items-center justify-between gap-2 text-sm">
            <div className="min-w-0">
              <div className="truncate font-medium text-ink-900" title={slot.file.name}>{slot.file.name}</div>
              <div className="text-xs text-ink-500">{bytes(slot.file.size)}{r?.format && ` · ${r.format.toUpperCase()}`}</div>
            </div>
            <div className="flex shrink-0 gap-1">
              <Button size="sm" variant="ghost" onClick={() => input.current?.click()} title="Substituir"><RefreshCw className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" onClick={onRemove} title="Remover"><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
          {slot.state === "uploading" && <div className="mt-2 flex items-center gap-2 text-xs text-ink-500"><Loader2 className="h-3.5 w-3.5 animate-spin" />Validando conteúdo e identificando colunas...</div>}
          {slot.state === "error" && <div className="mt-2 text-xs text-rose-700">{slot.error}</div>}
          {slot.state === "mapping" && (
            <div className="mt-2 text-xs text-amber-800">
              Não identificamos automaticamente: {r?.missing?.join("; ") || "colunas obrigatórias"}.
              <Button size="sm" variant="secondary" className="ml-2" onClick={onMap}><Columns3 className="h-3.5 w-3.5" /> Mapear colunas</Button>
            </div>
          )}
          {slot.state === "ok" && r && (
            <div className="mt-2 space-y-1.5 text-xs text-ink-700">
              <div className="flex flex-wrap gap-1.5">
                <Badge tone="emerald">{r.count} registros</Badge>
                {r.meta?.periodo_inicio && <Badge>{dateBR(r.meta.periodo_inicio)} a {dateBR(r.meta.periodo_fim)}</Badge>}
                <Badge>Total {brl(r.meta?.valor_total)}</Badge>
                {r.meta?.banco && <Badge tone="brand">{r.meta.banco}{r.meta.conta ? ` · conta ${r.meta.conta}` : ""}</Badge>}
                {r.template && <Badge tone="amber"><Wand2 className="mr-1 h-3 w-3" />Modelo: {r.template.name}</Badge>}
              </div>
              {r.warnings?.map((w: string) => <div key={w} className="text-amber-700">{w}</div>)}
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="secondary" onClick={onPreview}><Eye className="h-3.5 w-3.5" /> Visualizar dados</Button>
                {r.columns?.length > 0 && <Button size="sm" variant="ghost" onClick={onMap}><Columns3 className="h-3.5 w-3.5" /> Ajustar colunas</Button>}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PreviewModal({ result, onClose }: { result: any; onClose: () => void }) {
  const rows = result.records_preview || [];
  return (
    <Modal open onClose={onClose} wide title={`Pré-visualização · ${result.source_label} · ${result.filename}`}>
      <p className="mb-3 text-xs text-ink-500">Primeiros {rows.length} de {result.count} registros, já normalizados (datas DD/MM/AAAA, valores em BRL; positivo = entrada, negativo = saída).</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead className="bg-slate-50 text-left text-ink-500">
            <tr><th className="px-2 py-2">Linha</th><th className="px-2 py-2">Data</th><th className="px-2 py-2">Liquidação</th><th className="px-2 py-2">Descrição</th><th className="px-2 py-2">Favorecido/Cartão</th><th className="px-2 py-2">Identificadores</th><th className="px-2 py-2 text-right">Valor</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r: any, i: number) => (
              <tr key={i}>
                <td className="px-2 py-1.5 text-ink-500">{r.row}</td>
                <td className="px-2 py-1.5">{dateBR(r.date)}</td>
                <td className="px-2 py-1.5">{dateBR(r.settle_date)}</td>
                <td className="max-w-xs truncate px-2 py-1.5">{r.description}</td>
                <td className="max-w-[12rem] truncate px-2 py-1.5">{r.counterparty}</td>
                <td className="px-2 py-1.5 font-mono text-[11px] text-ink-500">{Object.entries(r.ids || {}).map(([k, v]) => `${k}:${v}`).join(" ")}</td>
                <td className={cx("px-2 py-1.5 text-right tabular-nums", Number(r.amount) < 0 && "text-rose-700")}>{brl(r.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

function MappingModal({ source, result, onClose, onApply }: {
  source: string; result: any; onClose: () => void; onApply: (m: any, hr: number, save: boolean, name: string) => void;
}) {
  const grid: string[][] = result.raw_grid_head || [];
  const [hr, setHr] = useState<number>(result.header_row ?? 0);
  const [mapping, setMapping] = useState<Record<string, number | "">>({ ...result.mapping });
  const [save, setSave] = useState(true);
  const [name, setName] = useState(`Modelo ${SOURCES[source].long} · ${result.filename}`.slice(0, 120));
  const cols = (grid[hr] || []).map((c, i) => c || `Coluna ${i + 1}`);
  const fields: any[] = result.fields || [];
  return (
    <Modal open onClose={onClose} wide title={`Mapeamento de colunas · ${SOURCES[source].long}`}
      footer={<><Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => onApply(Object.fromEntries(Object.entries(mapping).filter(([, v]) => v !== "")), hr, save, name)}>Aplicar mapeamento</Button></>}>
      <p className="text-sm text-ink-700">1. Clique na linha que contém os <b>cabeçalhos</b>. 2. Indique qual coluna corresponde a cada campo. Campos com * são obrigatórios (basta um de cada grupo).</p>
      <div className="mt-3 max-h-56 overflow-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-xs">
          <tbody>
            {grid.map((row, i) => (
              <tr key={i} onClick={() => setHr(i)} className={cx("cursor-pointer", i === hr ? "bg-brand-50 font-semibold text-brand-800" : i < hr ? "text-ink-400" : "hover:bg-slate-50")}>
                <td className="sticky left-0 bg-inherit px-2 py-1 text-ink-400">{i + 1}</td>
                {row.map((c, j) => <td key={j} className="max-w-[10rem] truncate whitespace-nowrap px-2 py-1">{c}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map((f) => (
          <Field key={f.key} label={`${f.label}${f.required ? " *" : ""}`}>
            <select className={inputCls} value={mapping[f.key] ?? ""} onChange={(e) => setMapping({ ...mapping, [f.key]: e.target.value === "" ? "" : Number(e.target.value) })}>
              <option value="">— não usar —</option>
              {cols.map((c, i) => <option key={i} value={i}>{c}</option>)}
            </select>
          </Field>
        ))}
      </div>
      <div className="mt-4 rounded-lg bg-slate-50 p-3">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} /> Salvar como modelo para próximas importações deste layout</label>
        {save && <input className={cx(inputCls, "mt-2")} value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do modelo" />}
      </div>
    </Modal>
  );
}
