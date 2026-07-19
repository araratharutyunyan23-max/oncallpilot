import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0B0E14", // page background (near-black)
        surface: "#131722", // panels
        surface2: "#0F1420", // insets / inputs
        border: "#1F2733",
        fg: "#E5E9F0",
        muted: "#8B93A7",
        faint: "#5A6377",
        accent: "#2DD4BF", // teal — the single accent
        p1: "#F43F5E", // severity red
        p2: "#F59E0B", // severity amber
        p3: "#38BDF8", // severity sky
        ok: "#34D399", // success green
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "JetBrains Mono",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
