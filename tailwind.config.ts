import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#EEF6F5", 100: "#D5EAE7", 200: "#A9D3CE", 400: "#3E9C92", 500: "#1F7A70", 600: "#16625A", 700: "#0F4C46", 800: "#0F3D3E", 900: "#0A2B2C" },
        ink: { 400: "#7A8A8C", 500: "#5B6B6D", 700: "#2E3B3D", 900: "#152022" },
        paper: "#F6F7F5",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: { card: "0 1px 2px rgba(16,40,40,.06), 0 1px 1px rgba(16,40,40,.04)" },
    },
  },
  plugins: [],
} satisfies Config;
