import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Conciliação Inteligente",
  description: "Conciliação financeira automática entre ERP, extrato bancário, máquina de cartão e adquirente.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
