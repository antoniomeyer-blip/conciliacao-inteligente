"use client";

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    super(typeof detail === "string" ? detail : detail?.message || "Erro inesperado.");
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem("ci_token");
  } catch {
    return null;
  }
}

export function setSession(token: string, user: any) {
  try {
    localStorage.setItem("ci_token", token);
    localStorage.setItem("ci_user", JSON.stringify(user));
  } catch {}
}

export function clearSession() {
  try {
    localStorage.removeItem("ci_token");
    localStorage.removeItem("ci_user");
  } catch {}
}

export function getUser(): any | null {
  try {
    const u = localStorage.getItem("ci_user");
    return u ? JSON.parse(u) : null;
  } catch {
    return null;
  }
}

async function handle(res: Response) {
  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !location.pathname.startsWith("/login")) location.href = "/login";
  }
  if (!res.ok) {
    let detail: any = "Erro ao comunicar com o servidor.";
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res;
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: any } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = opts.body;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  const res = await handle(await fetch(path, { ...opts, headers, body }));
  return res.json();
}

export async function download(path: string) {
  const token = getToken();
  const res = await handle(await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} }));
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] || "relatorio";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function qs(params: Record<string, any>) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)));
    else p.append(k, String(v));
  });
  return p.toString();
}
