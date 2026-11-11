"use client";

import { Plus, Save, Trash2 } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, Badge, Button, Card, Field, Spinner, inputCls } from "@/components/ui";
import { api, getUser } from "@/lib/api";
import { SOURCES, cx, dateTimeBR } from "@/lib/format";

const RULES: [string, string][] = [
  ["nivel1_identificador", "Nível 1 · Identificador único (NSU, FITID, autorização, documento, ordem de pagamento)"],
  ["nivel2_valor_data", "Nível 2 · Valor e data exatos"],
  ["nivel3_tolerancia_data", "Nível 3 · Valor com tolerância de data"],
  ["nivel4_agrupado", "Nível 4 · Valores agrupados (várias vendas = uma liquidação)"],
  ["nivel5_liquido", "Nível 5 · Valor líquido (bruto − taxa esperada)"],
  ["sugerir_divergencia_valor", "Sugerir divergências de valor para aprovação manual"],
];

export default function Configuracoes() {
  const isAdmin = getUser()?.role === "admin";
  const [s, setS] = useState<any>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState("regras");
  useEffect(() => { api("/api/settings").then((r) => setS(r.settings)).catch((e) => setMsg({ tone: "error", text: e.message })); }, []);

  async function save() {
    setSaving(true); setMsg(null);
    try { const r = await api("/api/settings", { method: "PUT", json: s }); setS(r.settings); setMsg({ tone: "success", text: "Configurações salvas. Use “Reprocessar” no histórico para aplicá-las a conciliações anteriores." }); }
    catch (e: any) { setMsg({ tone: "error", text: e.message }); } finally { setSaving(false); }
  }
  if (!s) return msg ? <Alert tone="error">{msg.text}</Alert> : <Spinner />;
  const set = (k: string, v: any) => setS({ ...s, [k]: v });
  const TABS: [string, string][] = [["regras", "Tolerâncias e regras"], ["taxas", "Taxas esperadas"], ["bandeiras", "Bandeiras e adquirentes"], ["contas", "Contas bancárias"], ["modelos", "Modelos de importação"], ["usuarios", "Usuários"], ["auditoria", "Auditoria"]];

  return (
    <>
      <PageHeader title="Configurações" subtitle={isAdmin ? "Parâmetros usados pelo motor de conciliação da sua empresa." : "Somente administradores podem alterar as configurações."}
        actions={isAdmin && ["regras", "taxas", "bandeiras", "contas"].includes(tab) ? <Button onClick={save} loading={saving}><Save className="h-4 w-4" /> Salvar alterações</Button> : null} />
      {msg && <div className="mb-4"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      <div className="mb-5 flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1 text-sm">
        {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={cx("rounded-md px-3 py-1.5 font-medium", tab === k ? "bg-white shadow-sm" : "text-ink-500")}>{l}</button>)}
      </div>
      <fieldset disabled={!isAdmin} className="contents">
        {tab === "regras" && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card title="Tolerâncias">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Tolerância de valor (centavos)" hint="0 = exige valor exato."><input type="number" min={0} className={inputCls} value={s.tolerancia_valor_centavos} onChange={(e) => set("tolerancia_valor_centavos", Number(e.target.value))} /></Field>
                <Field label="Tolerância de dias" hint="Diferença máxima entre datas (venda/pagamento × extrato)."><input type="number" min={0} max={60} className={inputCls} value={s.tolerancia_dias} onChange={(e) => set("tolerancia_dias", Number(e.target.value))} /></Field>
                <Field label="Divergência de valor sugerida até (%)" hint="Acima disso, não sugere vínculo."><input type="number" min={0} max={50} step={0.5} className={inputCls} value={s.divergencia_valor_max_percentual} onChange={(e) => set("divergencia_valor_max_percentual", Number(e.target.value))} /></Field>
                <Field label="Tolerância de taxa (centavos)" hint="Diferença aceita entre taxa cobrada e esperada."><input type="number" min={0} className={inputCls} value={s.tolerancia_taxa_centavos} onChange={(e) => set("tolerancia_taxa_centavos", Number(e.target.value))} /></Field>
                <Field label="Máx. de itens por agrupamento" hint="Limite para busca de combinações (nível 4)."><input type="number" min={2} max={60} className={inputCls} value={s.max_itens_agrupamento} onChange={(e) => set("max_itens_agrupamento", Number(e.target.value))} /></Field>
              </div>
            </Card>
            <Card title="Regras de correspondência">
              <ul className="space-y-3">
                {RULES.map(([k, l]) => (
                  <li key={k}><label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-0.5" checked={!!s.regras[k]} onChange={(e) => set("regras", { ...s.regras, [k]: e.target.checked })} />{l}</label></li>
                ))}
              </ul>
              <p className="mt-4 text-xs text-ink-500">Quando há mais de um candidato possível, o sistema nunca concilia automaticamente: o lançamento vai para análise manual.</p>
            </Card>
          </div>
        )}
        {tab === "taxas" && (
          <Card title="Taxas esperadas por operadora, bandeira e modalidade" action={isAdmin && <Button size="sm" variant="secondary" onClick={() => set("taxas", [...s.taxas, { operadora: "", bandeira: "*", modalidade: "credito", parcelas_min: 1, parcelas_max: 1, taxa: 0 }])}><Plus className="h-4 w-4" /> Adicionar</Button>}>
            <p className="mb-3 text-xs text-ink-500">Usadas para apontar “Taxa divergente” e para o nível 5 (valor líquido). Bandeira “*” vale para todas; a regra mais específica prevalece. Valores iniciais foram observados no relatório SIPAG de exemplo: confirme com seu contrato.</p>
            <Table head={["Operadora", "Bandeira", "Modalidade", "Parcelas de", "até", "Taxa (%)", ""]}>
              {s.taxas.map((t: any, i: number) => {
                const up = (k: string, v: any) => set("taxas", s.taxas.map((x: any, j: number) => (j === i ? { ...x, [k]: v } : x)));
                return (
                  <tr key={i}>
                    <td className="p-1"><input className={inputCls} value={t.operadora} onChange={(e) => up("operadora", e.target.value)} /></td>
                    <td className="p-1"><select className={inputCls} value={t.bandeira} onChange={(e) => up("bandeira", e.target.value)}><option value="*">Todas (*)</option>{s.bandeiras.map((b: any) => <option key={b.chave} value={b.chave}>{b.nome}</option>)}</select></td>
                    <td className="p-1"><select className={inputCls} value={t.modalidade} onChange={(e) => up("modalidade", e.target.value)}>{["debito", "credito", "voucher", "pix", "prepago"].map((m) => <option key={m} value={m}>{m}</option>)}</select></td>
                    <td className="p-1"><input type="number" min={1} className={inputCls} value={t.parcelas_min} onChange={(e) => up("parcelas_min", Number(e.target.value))} /></td>
                    <td className="p-1"><input type="number" min={1} className={inputCls} value={t.parcelas_max} onChange={(e) => up("parcelas_max", Number(e.target.value))} /></td>
                    <td className="p-1"><input type="number" step={0.01} min={0} className={inputCls} value={t.taxa} onChange={(e) => up("taxa", Number(e.target.value))} /></td>
                    <td className="p-1 text-right"><Button size="sm" variant="ghost" onClick={() => set("taxas", s.taxas.filter((_: any, j: number) => j !== i))}><Trash2 className="h-4 w-4" /></Button></td>
                  </tr>
                );
              })}
            </Table>
          </Card>
        )}
        {tab === "bandeiras" && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card title="Bandeiras de cartão" action={isAdmin && <Button size="sm" variant="secondary" onClick={() => set("bandeiras", [...s.bandeiras, { nome: "", chave: "", padroes: [] }])}><Plus className="h-4 w-4" /> Adicionar</Button>}>
              <p className="mb-3 text-xs text-ink-500">Padrões de texto que identificam a bandeira nos arquivos (separados por vírgula).</p>
              <Table head={["Nome", "Chave", "Padrões", ""]}>
                {s.bandeiras.map((b: any, i: number) => {
                  const up = (k: string, v: any) => set("bandeiras", s.bandeiras.map((x: any, j: number) => (j === i ? { ...x, [k]: v } : x)));
                  return (
                    <tr key={i}>
                      <td className="p-1"><input className={inputCls} value={b.nome} onChange={(e) => up("nome", e.target.value)} /></td>
                      <td className="p-1"><input className={inputCls} value={b.chave} onChange={(e) => up("chave", e.target.value.toLowerCase())} /></td>
                      <td className="p-1"><input className={inputCls} value={b.padroes.join(", ")} onChange={(e) => up("padroes", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></td>
                      <td className="p-1"><Button size="sm" variant="ghost" onClick={() => set("bandeiras", s.bandeiras.filter((_: any, j: number) => j !== i))}><Trash2 className="h-4 w-4" /></Button></td>
                    </tr>
                  );
                })}
              </Table>
            </Card>
            <Card title="Identificação de créditos de adquirente no extrato">
              <Field label="Descritores (separados por vírgula)" hint="Textos do histórico do extrato que indicam repasse de cartão (ex.: SIPAG, CIELO, REDE, STONE).">
                <textarea rows={4} className={inputCls} value={s.descritores_cartao_banco.join(", ")} onChange={(e) => set("descritores_cartao_banco", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} />
              </Field>
            </Card>
          </div>
        )}
        {tab === "contas" && (
          <Card title="Contas bancárias" action={isAdmin && <Button size="sm" variant="secondary" onClick={() => set("contas_bancarias", [...s.contas_bancarias, { apelido: "", banco: "", agencia: "", conta: "" }])}><Plus className="h-4 w-4" /> Adicionar</Button>}>
            <p className="mb-3 text-xs text-ink-500">Cadastro de referência das contas conciliadas. Os extratos importados exibem apenas os últimos dígitos da conta.</p>
            {s.contas_bancarias.length === 0 ? <p className="text-sm text-ink-500">Nenhuma conta cadastrada.</p> : (
              <Table head={["Apelido", "Banco", "Agência", "Conta", ""]}>
                {s.contas_bancarias.map((c: any, i: number) => {
                  const up = (k: string, v: any) => set("contas_bancarias", s.contas_bancarias.map((x: any, j: number) => (j === i ? { ...x, [k]: v } : x)));
                  return (
                    <tr key={i}>
                      {["apelido", "banco", "agencia", "conta"].map((k) => <td key={k} className="p-1"><input className={inputCls} value={c[k]} onChange={(e) => up(k, e.target.value)} /></td>)}
                      <td className="p-1"><Button size="sm" variant="ghost" onClick={() => set("contas_bancarias", s.contas_bancarias.filter((_: any, j: number) => j !== i))}><Trash2 className="h-4 w-4" /></Button></td>
                    </tr>
                  );
                })}
              </Table>
            )}
          </Card>
        )}
      </fieldset>
      {tab === "modelos" && <Templates isAdmin={isAdmin} />}
      {tab === "usuarios" && <Users isAdmin={isAdmin} />}
      {tab === "auditoria" && <Audit isAdmin={isAdmin} />}
    </>
  );
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs text-ink-500"><tr>{head.map((h, i) => <th key={i} className="px-1 py-1 font-medium">{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Templates({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const load = () => api("/api/templates").then(setRows);
  useEffect(() => { load(); }, []);
  if (!rows) return <Spinner />;
  return (
    <Card title="Modelos de importação por origem">
      <p className="mb-3 text-xs text-ink-500">Criados ao salvar um mapeamento manual de colunas. São aplicados automaticamente quando um arquivo com o mesmo layout de cabeçalho é carregado.</p>
      {rows.length === 0 ? <p className="text-sm text-ink-500">Nenhum modelo salvo ainda.</p> : (
        <ul className="divide-y divide-slate-100">
          {rows.map((t) => (
            <li key={t.id} className="flex items-center justify-between py-2.5 text-sm">
              <span><Badge>{SOURCES[t.source]?.label}</Badge> <b className="ml-1">{t.name}</b> <span className="text-xs text-ink-500">· {Object.keys(t.mapping).length} campos · cabeçalho na linha {t.header_row + 1} · {dateTimeBR(t.created_at)}</span></span>
              {isAdmin && <Button size="sm" variant="ghost" onClick={async () => { if (confirm("Excluir modelo?")) { await api(`/api/templates/${t.id}`, { method: "DELETE" }); load(); } }}><Trash2 className="h-4 w-4" /></Button>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Users({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [f, setF] = useState({ name: "", email: "", password: "", role: "analista" });
  const [err, setErr] = useState("");
  const load = () => api("/api/users").then(setRows);
  useEffect(() => { load(); }, []);
  async function add() {
    setErr("");
    try { await api("/api/users", { method: "POST", json: f }); setF({ name: "", email: "", password: "", role: "analista" }); load(); } catch (e: any) { setErr(e.message); }
  }
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card title="Usuários da empresa">
        {!rows ? <Spinner /> : <ul className="divide-y divide-slate-100 text-sm">{rows.map((u) => <li key={u.id} className="flex justify-between py-2"><span>{u.name} <span className="text-ink-500">· {u.email}</span></span><Badge tone={u.role === "admin" ? "brand" : "slate"}>{u.role === "admin" ? "Administrador" : "Analista"}</Badge></li>)}</ul>}
      </Card>
      {isAdmin && (
        <Card title="Adicionar usuário">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Nome"><input className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="E-mail"><input className={inputCls} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
            <Field label="Senha inicial" hint="Mínimo 8 caracteres."><input type="password" className={inputCls} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
            <Field label="Papel"><select className={inputCls} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="analista">Analista</option><option value="admin">Administrador</option></select></Field>
          </div>
          {err && <div className="mt-3"><Alert tone="error">{err}</Alert></div>}
          <Button className="mt-4" onClick={add}><Plus className="h-4 w-4" /> Adicionar</Button>
        </Card>
      )}
    </div>
  );
}

const ACTIONS: Record<string, string> = {
  login: "Login", cadastro_empresa: "Cadastro da empresa", arquivo_validado: "Arquivo validado", arquivo_rejeitado: "Arquivo rejeitado",
  processar_conciliacao: "Conciliação processada", reprocessar_conciliacao: "Reprocessamento", vinculo_aprovado: "Sugestão aprovada",
  vinculo_rejeitado: "Sugestão rejeitada", observacao: "Observação", exportar: "Exportação", alterar_configuracoes: "Configurações alteradas",
  salvar_modelo_importacao: "Modelo de importação salvo", excluir_modelo_importacao: "Modelo excluído", criar_usuario: "Usuário criado", excluir_conciliacao: "Conciliação excluída",
};

function Audit({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { if (isAdmin) api("/api/audit?limit=300").then(setRows); }, [isAdmin]);
  if (!isAdmin) return <Alert tone="info">Somente administradores podem consultar o log de auditoria.</Alert>;
  if (!rows) return <Spinner />;
  return (
    <Card title="Log de auditoria (últimos 300 eventos)">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs text-ink-500"><tr><th className="py-2 pr-4">Data</th><th className="py-2 pr-4">Usuário</th><th className="py-2 pr-4">Ação</th><th className="py-2">Detalhes</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.id}><td className="whitespace-nowrap py-1.5 pr-4 text-ink-500">{dateTimeBR(r.created_at)}</td><td className="py-1.5 pr-4">{r.user}</td><td className="py-1.5 pr-4">{ACTIONS[r.action] || r.action}</td>
                <td className="max-w-xl truncate py-1.5 font-mono text-xs text-ink-500" title={JSON.stringify(r.details)}>{Object.entries(r.details || {}).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("|") : v}`).join("  ")}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
