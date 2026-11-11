"use client";

import { ArrowDown, ArrowUp, Check, ChevronLeft, ChevronRight, RefreshCw, Search, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import ExportButtons from "@/components/ExportButtons";
import Summary from "@/components/Summary";
import { Alert, Badge, Button, Drawer, Field, Spinner, StatusBadge, inputCls } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { LEVELS, SOURCES, STATUS, brl, cx, dateBR, dateTimeBR } from "@/lib/format";

export default function Detalhe() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [rec, setRec] = useState<any>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"resumo" | "transacoes" | "sugestoes">("resumo");
  const [openTx, setOpenTx] = useState<number | null>(null);
  const [preset, setPreset] = useState<any>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api(`/api/reconciliations/${id}`).then(setRec).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); setReloadKey((k) => k + 1); };

  async function reprocess() {
    if (!confirm("Reprocessar com as configurações atuais? Será criada uma nova versão.")) return;
    setBusy(true);
    try { const r = await api(`/api/reconciliations/${id}/reprocess`, { method: "POST" }); router.push(`/historico/${r.id}`); }
    catch (e: any) { setError(e.message); setBusy(false); }
  }

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!rec) return <Spinner />;
  const nSug = rec.suggestions.length;

  return (
    <>
      <PageHeader title={`Conciliação ${rec.code}`}
        subtitle={<>Período {dateBR(rec.period_start)} a {dateBR(rec.period_end)} · processado em {dateTimeBR(rec.created_at)} por {rec.user} · {rec.duration_ms} ms</>}
        actions={<>
          {rec.versions.length > 1 && (
            <select className={inputCls + " w-auto"} value={rec.id} onChange={(e) => router.push(`/historico/${e.target.value}`)}>
              {rec.versions.map((v: any) => <option key={v.id} value={v.id}>Versão {v.version} · {dateTimeBR(v.created_at)}</option>)}
            </select>
          )}
          <Button variant="secondary" onClick={reprocess} loading={busy}><RefreshCw className="h-4 w-4" /> Reprocessar</Button>
        </>} />
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm">
          {([["resumo", "Resumo"], ["transacoes", "Transações"], ["sugestoes", `Aprovações pendentes${nSug ? ` (${nSug})` : ""}`]] as const).map(([k, l]) => (
            <button key={k} onClick={() => { setTab(k); if (k === "transacoes") setPreset(null); }} className={cx("rounded-md px-3 py-1.5 font-medium", tab === k ? "bg-white shadow-sm" : "text-ink-500")}>{l}</button>
          ))}
        </div>
        <ExportButtons id={rec.id} compact />
      </div>

      {tab === "resumo" && (
        <>
          {nSug > 0 && <div className="mb-4"><Alert tone="warn"><b>{nSug} conciliação(ões) sugerida(s)</b> aguardam sua aprovação. <button className="underline" onClick={() => setTab("sugestoes")}>Revisar agora</button></Alert></div>}
          <Summary totals={rec.totals} />
          <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {Object.entries(STATUS).filter(([k]) => rec.totals.por_status?.[k]).map(([k, s]) => (
              <button key={k} onClick={() => { setPreset({ status: [k] }); setTab("transacoes"); }}
                className="rounded-lg border border-slate-200 bg-white p-3 text-left text-xs shadow-card hover:border-brand-400">
                <StatusBadge status={k} />
                <div className="mt-2 text-lg font-semibold tabular-nums">{rec.totals.por_status[k].registros}</div>
                <div className="text-ink-500">{brl(rec.totals.por_status[k].valor)}</div>
              </button>
            ))}
          </div>
        </>
      )}
      {tab === "transacoes" && <TxTable key={JSON.stringify(preset) + reloadKey} rid={rec.id} preset={preset} onOpen={setOpenTx} />}
      {tab === "sugestoes" && <Suggestions rec={rec} onChanged={refresh} onOpenMatch={(code) => { setPreset({ match: code }); setTab("transacoes"); }} />}
      {openTx && <TxDrawer rid={rec.id} tid={openTx} onClose={() => setOpenTx(null)} onOpen={setOpenTx} onChanged={refresh} />}
    </>
  );
}

const COLS = [
  { key: "date", label: "Data" }, { key: "identifier", label: "Identificação" }, { key: "description", label: "Descrição" },
  { key: "source", label: "Origem" }, { key: "amount", label: "Valor original", right: true }, { key: "found_amount", label: "Valor encontrado", right: true },
  { key: "difference", label: "Diferença", right: true }, { key: "status", label: "Status" }, { key: "justification", label: "Justificativa", nosort: true },
];

function TxTable({ rid, preset, onOpen }: { rid: number; preset: any; onOpen: (id: number) => void }) {
  const [f, setF] = useState({ q: "", status: [] as string[], source: [] as string[], date_from: "", date_to: "", match: "", ...preset });
  const [qInput, setQInput] = useState("");
  const [sort, setSort] = useState({ key: "date", dir: "asc" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const size = 50;

  useEffect(() => { const t = setTimeout(() => { setF((p: any) => ({ ...p, q: qInput })); setPage(1); }, 350); return () => clearTimeout(t); }, [qInput]);
  useEffect(() => {
    api(`/api/reconciliations/${rid}/transactions?${qs({ ...f, sort: sort.key, dir: sort.dir, page, size })}`).then(setData).catch((e) => setErr(e.message));
  }, [rid, f, sort, page]);

  const toggle = (k: "status" | "source", v: string) => { setF((p: any) => ({ ...p, [k]: p[k].includes(v) ? p[k].filter((x: string) => x !== v) : [...p[k], v] })); setPage(1); };
  const pages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-card">
      <div className="space-y-3 border-b border-slate-100 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="relative min-w-[16rem] flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-400" />
            <input className={inputCls + " pl-9"} placeholder="Pesquisar por nome, NSU, código, documento ou valor (ex.: 157,14)" value={qInput} onChange={(e) => setQInput(e.target.value)} />
          </div>
          <Field label="De"><input type="date" className={inputCls} value={f.date_from} onChange={(e) => { setF({ ...f, date_from: e.target.value }); setPage(1); }} /></Field>
          <Field label="Até"><input type="date" className={inputCls} value={f.date_to} onChange={(e) => { setF({ ...f, date_to: e.target.value }); setPage(1); }} /></Field>
          <Button variant="ghost" onClick={() => { setF({ q: "", status: [], source: [], date_from: "", date_to: "", match: "" }); setQInput(""); setPage(1); }}><X className="h-4 w-4" /> Limpar</Button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(SOURCES).map(([k, s]) => (
            <button key={k} onClick={() => toggle("source", k)} className={cx("rounded-full px-3 py-1 text-xs ring-1", f.source.includes(k) ? "bg-brand-800 text-white ring-brand-800" : "bg-white text-ink-700 ring-slate-300")}>{s.label}</button>
          ))}
          <span className="mx-1 w-px bg-slate-200" />
          {Object.entries(STATUS).map(([k, s]) => (
            <button key={k} onClick={() => toggle("status", k)} className={cx("rounded-full px-3 py-1 text-xs ring-1", f.status.includes(k) ? "bg-brand-800 text-white ring-brand-800" : "bg-white text-ink-700 ring-slate-300")}>{s.label}</button>
          ))}
          {f.match && <Badge tone="amber">Vínculo {f.match} <button className="ml-1" onClick={() => setF({ ...f, match: "" })}>×</button></Badge>}
        </div>
      </div>
      {err && <div className="p-4"><Alert tone="error">{err}</Alert></div>}
      {!data ? <Spinner /> : (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-ink-500">
                <tr>
                  {COLS.map((c) => (
                    <th key={c.key} className={cx("whitespace-nowrap px-3 py-2.5", c.right && "text-right")}>
                      {c.nosort ? c.label : (
                        <button className="inline-flex items-center gap-1 hover:text-ink-900" onClick={() => setSort({ key: c.key, dir: sort.key === c.key && sort.dir === "asc" ? "desc" : "asc" })}>
                          {c.label}{sort.key === c.key && (sort.dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                        </button>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((t: any) => (
                  <tr key={t.id} onClick={() => onOpen(t.id)} className="cursor-pointer hover:bg-brand-50/50">
                    <td className="whitespace-nowrap px-3 py-2">{dateBR(t.date)}</td>
                    <td className="max-w-[9rem] truncate px-3 py-2 font-mono text-xs text-ink-500" title={t.identifier}>{t.identifier || "—"}</td>
                    <td className="max-w-[18rem] px-3 py-2"><div className="truncate" title={t.description}>{t.description}</div><div className="truncate text-xs text-ink-500">{t.counterparty}</div></td>
                    <td className="px-3 py-2"><Badge>{SOURCES[t.source]?.label}</Badge></td>
                    <td className={cx("whitespace-nowrap px-3 py-2 text-right tabular-nums", Number(t.amount) < 0 && "text-rose-700")}>{brl(t.amount)}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-ink-700">{brl(t.found_amount)}</td>
                    <td className={cx("whitespace-nowrap px-3 py-2 text-right tabular-nums", t.difference && Number(t.difference) !== 0 && "font-medium text-amber-700")}>{t.difference && Number(t.difference) !== 0 ? brl(t.difference) : "—"}</td>
                    <td className="px-3 py-2"><StatusBadge status={t.status} /></td>
                    <td className="max-w-[22rem] px-3 py-2 text-xs text-ink-500"><div className="line-clamp-2">{t.justification}</div>{t.note && <div className="mt-0.5 truncate text-brand-700">Obs.: {t.note}</div>}</td>
                  </tr>
                ))}
                {!data.items.length && <tr><td colSpan={9} className="px-3 py-10 text-center text-ink-500">Nenhum lançamento com esses filtros.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-ink-500">
            <span>{data.total} lançamento(s)</span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
              <span>Página {page} de {pages}</span>
              <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function MatchCard({ m, rid, onDecided }: { m: any; rid: number; onDecided: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  async function decide(decision: string) {
    setBusy(decision); setErr("");
    try { await api(`/api/reconciliations/${rid}/matches/${m.id}/decision`, { method: "POST", json: { decision, note } }); onDecided(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  }
  const tone = { auto: "emerald", aprovado: "emerald", sugerido: "amber", rejeitado: "rose" }[m.state as string] as any;
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="brand">{m.code}</Badge>
        <Badge>Nível {m.level} · {LEVELS[m.level]}</Badge>
        <Badge tone={tone}>{{ auto: "Automático", aprovado: "Aprovado", sugerido: "Sugestão: requer aprovação", rejeitado: "Rejeitado" }[m.state as string]}</Badge>
        <span className="text-ink-500">Confiança {Math.round(m.confidence * 100)}%</span>
        <StatusBadge status={m.status} />
      </div>
      <p className="mt-2 text-sm text-ink-700">{m.justification}</p>
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
        <div><div className="text-ink-500">Lado A ({m.left.length})</div><div className="font-medium tabular-nums">{brl(m.left_total)}</div></div>
        <div><div className="text-ink-500">Lado B ({m.right.length})</div><div className="font-medium tabular-nums">{brl(m.right_total)}</div></div>
        <div><div className="text-ink-500">Diferença</div><div className={cx("font-medium tabular-nums", Number(m.difference) !== 0 && "text-amber-700")}>{brl(m.difference)}</div></div>
      </div>
      <div className="mt-1 font-mono text-[11px] text-ink-400">Regra: {m.rule}</div>
      {m.note && <div className="mt-2 text-xs text-ink-700">Observação da decisão: {m.note}</div>}
      {m.state === "sugerido" && (
        <div className="mt-3 space-y-2">
          <input className={inputCls} placeholder="Observação (opcional): ex. juros por atraso, pagamento parcial..." value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <Button size="sm" variant="success" loading={busy === "aprovar"} onClick={() => decide("aprovar")}><Check className="h-4 w-4" /> Aprovar conciliação</Button>
            <Button size="sm" variant="secondary" loading={busy === "rejeitar"} onClick={() => decide("rejeitar")}><X className="h-4 w-4" /> Rejeitar</Button>
          </div>
          {err && <div className="text-xs text-rose-700">{err}</div>}
        </div>
      )}
    </div>
  );
}

function Suggestions({ rec, onChanged, onOpenMatch }: { rec: any; onChanged: () => void; onOpenMatch: (code: string) => void }) {
  if (!rec.suggestions.length) return <Alert tone="success">Não há conciliações sugeridas aguardando aprovação.</Alert>;
  return (
    <div className="space-y-3">
      <Alert tone="info">Estas correspondências <b>não foram conciliadas automaticamente</b> porque apresentam diferença de valor ou exigem confirmação. Aprove ou rejeite cada uma; a decisão fica registrada na auditoria.</Alert>
      {rec.suggestions.map((m: any) => (
        <div key={m.id} className="rounded-xl bg-white shadow-card">
          <MatchCard m={m} rid={rec.id} onDecided={onChanged} />
          <div className="border-t border-slate-100 px-4 py-2 text-right"><button className="text-xs text-brand-700 underline" onClick={() => onOpenMatch(m.code)}>Ver lançamentos relacionados</button></div>
        </div>
      ))}
    </div>
  );
}

function TxDrawer({ rid, tid, onClose, onOpen, onChanged }: { rid: number; tid: number; onClose: () => void; onOpen: (id: number) => void; onChanged: () => void }) {
  const [d, setD] = useState<any>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const load = useCallback(() => api(`/api/reconciliations/${rid}/transactions/${tid}`).then((x) => { setD(x); setNote((x.transaction.note || "").replace(/\s\([^)]*\)$/, "")); }), [rid, tid]);
  useEffect(() => { setD(null); load(); }, [load]);
  async function saveNote() {
    setSaving(true);
    try { await api(`/api/reconciliations/${rid}/transactions/${tid}/note`, { method: "POST", json: { note } }); await load(); onChanged(); } finally { setSaving(false); }
  }
  const t = d?.transaction;
  return (
    <Drawer open onClose={onClose} title="Detalhes do lançamento">
      {!d ? <Spinner /> : (
        <div className="space-y-6">
          <div>
            <div className="flex flex-wrap items-center gap-2"><Badge>{SOURCES[t.source]?.long}</Badge><StatusBadge status={t.status} />{t.row && <span className="text-xs text-ink-500">linha {t.row} do arquivo</span>}</div>
            <div className="mt-3 text-lg font-semibold">{t.description || "—"}</div>
            <div className="text-sm text-ink-500">{t.counterparty}</div>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3">
              <div><dt className="text-xs text-ink-500">Data</dt><dd>{dateBR(t.date)}</dd></div>
              <div><dt className="text-xs text-ink-500">Liquidação</dt><dd>{dateBR(t.settle_date)}</dd></div>
              <div><dt className="text-xs text-ink-500">Identificação</dt><dd className="font-mono text-xs">{t.identifier || "—"}</dd></div>
              <div><dt className="text-xs text-ink-500">Valor original</dt><dd className="tabular-nums">{brl(t.amount)}</dd></div>
              <div><dt className="text-xs text-ink-500">Valor encontrado</dt><dd className="tabular-nums">{brl(t.found_amount)}</dd></div>
              <div><dt className="text-xs text-ink-500">Diferença</dt><dd className="tabular-nums">{brl(t.difference)}</dd></div>
              {t.gross && <div><dt className="text-xs text-ink-500">Bruto / taxa</dt><dd className="tabular-nums">{brl(t.gross)} / {brl(t.fee)}</dd></div>}
              {t.brand && <div><dt className="text-xs text-ink-500">Bandeira / modalidade</dt><dd className="capitalize">{t.brand} {t.modality}</dd></div>}
              {t.level && <div><dt className="text-xs text-ink-500">Nível / confiança</dt><dd>{t.level} · {Math.round(t.confidence * 100)}%</dd></div>}
            </dl>
            <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-ink-700"><div className="mb-1 text-xs font-medium text-ink-500">Justificativa</div>{t.justification}</div>
          </div>
          {d.matches.length > 0 && (
            <section>
              <h4 className="mb-2 text-sm font-semibold">Regras aplicadas</h4>
              <div className="space-y-2">{d.matches.map((m: any) => <MatchCard key={m.id} m={m} rid={rid} onDecided={() => { load(); onChanged(); }} />)}</div>
            </section>
          )}
          {d.related.length > 0 && (
            <section>
              <h4 className="mb-2 text-sm font-semibold">Lançamentos relacionados ({d.related.length})</h4>
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
                {d.related.map((r: any) => (
                  <li key={r.id}><button onClick={() => onOpen(r.id)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-slate-50">
                    <span className="min-w-0 flex-1 truncate"><Badge>{SOURCES[r.source]?.label}</Badge> <span className="text-ink-500">{dateBR(r.date)}</span> {r.description} {r.counterparty}</span>
                    <span className="shrink-0 tabular-nums">{brl(r.amount)}</span>
                  </button></li>
                ))}
              </ul>
            </section>
          )}
          <section>
            <h4 className="mb-2 text-sm font-semibold">Observações</h4>
            <textarea className={inputCls} rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anote a análise feita, contato com o banco, etc." />
            <div className="mt-2 flex items-center justify-between"><span className="text-xs text-ink-500">{t.note}</span><Button size="sm" onClick={saveNote} loading={saving}>Salvar observação</Button></div>
          </section>
          {Object.keys(t.raw || {}).length > 0 && (
            <section>
              <h4 className="mb-2 text-sm font-semibold">Dados originais do arquivo</h4>
              <dl className="grid grid-cols-1 gap-x-4 gap-y-1 rounded-lg border border-slate-200 p-3 text-xs sm:grid-cols-2">
                {Object.entries(t.raw).map(([k, v]: any) => <div key={k} className="flex gap-2"><dt className="shrink-0 text-ink-500">{k}:</dt><dd className="break-all">{v}</dd></div>)}
              </dl>
            </section>
          )}
          <p className="text-xs text-ink-400">Prefere ver o processamento completo? <Link className="underline" href={`/relatorios`}>Exportar relatórios</Link></p>
        </div>
      )}
    </Drawer>
  );
}
