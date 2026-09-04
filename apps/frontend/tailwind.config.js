/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        relay: {
          ink: "#0b0d0c",
          surface: "#111411",
          raised: "#171a17",
          paper: "#f4f3ec",
          muted: "#9ca199",
          acid: "#b9ff66",
          coral: "#ff7657",
          gold: "#e6bd5e",
          aqua: "#65dac1",
          line: "rgba(241, 241, 230, 0.12)",
          "line-strong": "rgba(241, 241, 230, 0.20)",
        },
      },
      fontFamily: {
        display: ["Georgia", "Times New Roman", "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
