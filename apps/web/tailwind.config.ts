import type { Config } from "tailwindcss";

// Utility spacing/layout only — visual identity (color, radius, shadow) lives
// in globals.css as CSS variables ported directly from the original prototype
// so the palette stays exactly on-brand.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        green: "var(--green)",
        "green-light": "var(--green-light)",
        "green-hover": "var(--green-hover)",
        cream: "var(--cream)",
        peach: "var(--peach)",
        umber: "var(--umber)",
        "text-dark": "var(--text-dark)",
        "text-muted": "var(--text-muted)",
        border: "var(--border)",
        red: "var(--red)",
        "red-bg": "var(--red-bg)",
        orange: "var(--orange)",
        "orange-bg": "var(--orange-bg)",
        amber: "var(--amber)",
        "amber-bg": "var(--amber-bg)",
        "normal-green": "var(--normal-green)",
        "normal-bg": "var(--normal-bg)",
        blue: "var(--blue)",
        "blue-bg": "var(--blue-bg)",
        grey: "var(--grey)",
        "grey-bg": "var(--grey-bg)",
      },
      borderRadius: { emissiq: "14px" },
      boxShadow: { emissiq: "0 1px 3px rgba(29,69,51,0.08), 0 1px 2px rgba(29,69,51,0.06)" },
    },
  },
  plugins: [],
};
export default config;
