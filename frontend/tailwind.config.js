/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#f7f7f4",
        panel: "#ffffff",
        ink: "#1c1c1a",
        soft: "#55554e",
        line: "#dedad2",
        accent: "#0f5c56",
        "accent-soft": "#e4efed",
        warn: "#9a5b12",
        fail: "#a3392f",
      },
      fontFamily: {
        serif: ["Georgia", "Iowan Old Style", "Palatino Linotype", "serif"],
      },
      maxWidth: {
        content: "680px",
      },
    },
  },
  plugins: [],
};
