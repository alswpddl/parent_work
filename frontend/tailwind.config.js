/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Noto Sans KR"', "system-ui", "sans-serif"],
      },
      colors: {
        paper: "#f5f2ea",
        ink: "#1d1b16",
        line: "#e2dccd",
        brand: { DEFAULT: "#1f6b47", soft: "#e3f0e8", dark: "#15503a" },
        parcel: { DEFAULT: "#1d5fa8", soft: "#e3edf8" },
        truck: { DEFAULT: "#b45f06", soft: "#fbeedd" },
      },
      borderRadius: { xl2: "1.1rem" },
    },
  },
  plugins: [],
};
