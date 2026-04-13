/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      colors: {
        surface: {
          DEFAULT: "#0f1117",
          card: "#161b22",
          border: "#21262d",
          hover: "#1c2129",
        },
        accent: {
          green: "#3fb950",
          blue: "#58a6ff",
          yellow: "#e3b341",
          red: "#f85149",
          purple: "#bc8cff",
          orange: "#f0883e",
        },
      },
      animation: {
        pulse_slow: "pulse 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
