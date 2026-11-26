/** @type {import('tailwindcss').Config} */
// 가염식품 — 통영 바다 남색 + 액젓 호박색. 둥근 모서리는 작게, 그림자 대신 선.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Noto Sans KR"', "system-ui", "sans-serif"],
        serif: ['"Noto Serif KR"', '"Nanum Myeongjo"', "serif"],
      },
      colors: {
        paper: "#f1f3f5",
        ink: "#17202a",
        line: "#d3dae1",
        brand: { DEFAULT: "#173a5e", soft: "#e6edf4", dark: "#0f2a45" },
        brine: { DEFAULT: "#94570f", soft: "#f6ede2" },
        parcel: { DEFAULT: "#0e6a70", soft: "#e0efef" },
        truck: { DEFAULT: "#9a4f0a", soft: "#f7ebdd" },
      },
      borderRadius: {
        xl: "0.5rem",
        "2xl": "0.5rem",
        "3xl": "0.75rem",
        xl2: "0.375rem",
      },
    },
  },
  plugins: [],
};
