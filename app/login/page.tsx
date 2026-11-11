"use client";

import { CheckCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Logo } from "@/components/AppShell";
import { Alert, Button, Field, inputCls } from "@/components/ui";
import { api, setSession } from "@/lib/api";
import { cx } from "@/lib/format";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ company: "", name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api(mode === "login" ? "/api/auth/login" : "/api/auth/register", {
        method: "POST", json: mode === "login" ? { email: form.email, password: form.password } : form,
      });
      setSession(res.token, res.user);
      router.replace("/");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-brand-800 p-12 text-white lg:flex">
        <Logo />
        <div className="max-w-md">
          <h1 className="text-3xl font-semibold leading-tight">Do extrato ao relatório em poucos cliques.</h1>
          <p className="mt-3 text-brand-100/80">Envie os arquivos do ERP, do banco, da máquina e da adquirente. O sistema cruza tudo por regras auditáveis e mostra o que bateu, o que divergiu e o que falta receber.</p>
          <ul className="mt-8 space-y-3 text-sm text-brand-100">
            {["OFX, XLSX, XLS, CSV, TXT e PDF tabular", "5 níveis de correspondência, sem conciliações ambíguas", "Taxas, parcelas, antecipações, estornos e PIX", "Exportação em Excel, CSV e PDF"].map((t) => (
              <li key={t} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-brand-200" />{t}</li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-brand-100/60">Regras determinísticas e rastreáveis. Nenhuma conciliação é inventada.</p>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <div className="mb-6 lg:hidden"><Logo className="text-brand-800" /></div>
          <div className="flex rounded-lg bg-slate-100 p-1 text-sm">
            {(["login", "register"] as const).map((m) => (
              <button type="button" key={m} onClick={() => setMode(m)}
                className={cx("flex-1 rounded-md py-2 font-medium", mode === m ? "bg-white shadow-sm" : "text-ink-500")}>
                {m === "login" ? "Entrar" : "Criar conta"}
              </button>
            ))}
          </div>
          {mode === "register" && (
            <>
              <Field label="Empresa"><input className={inputCls} value={form.company} onChange={set("company")} required /></Field>
              <Field label="Seu nome"><input className={inputCls} value={form.name} onChange={set("name")} required /></Field>
            </>
          )}
          <Field label="E-mail"><input type="email" autoComplete="email" className={inputCls} value={form.email} onChange={set("email")} required /></Field>
          <Field label="Senha" hint={mode === "register" ? "Mínimo de 8 caracteres." : undefined}>
            <input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} className={inputCls} value={form.password} onChange={set("password")} required minLength={mode === "register" ? 8 : undefined} />
          </Field>
          {error && <Alert tone="error">{error}</Alert>}
          <Button type="submit" className="w-full" size="lg" loading={loading}>{mode === "login" ? "Entrar" : "Criar conta e entrar"}</Button>
          {mode === "register" && <p className="text-xs text-ink-500">O primeiro usuário da empresa é o administrador. Os dados de cada empresa ficam isolados.</p>}
        </form>
      </div>
    </div>
  );
}
