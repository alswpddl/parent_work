/** @type {import('tailwindcss').Config} */
// 가염식품 — 통영 바다 남색 + 액젓 호박색.
// 기준: 범정부 디자인 시스템(KRDS)의 글자 크기·대비·포커스 규칙, 토스식 차가운 회색 단계.
// 글꼴은 Pretendard(국내 기업·공공 서비스 표준 고딕), 공장 이름만 명조로.
const gray = {
  50: "#f9fafb",
  100: "#f2f4f6",
  200: "#e5e8eb",
  300: "#d1d6db",
  400: "#b0b8c1",
  500: "#6b7684", // 흰 바탕 위 4.5:1 이상 — 안내 글자에 써도 읽혀요
  600: "#4e5968",
  700: "#333d4b",
  800: "#252c38",
  900: "#191f28",
};

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Pretendard Variable"', "Pretendard", "-apple-system", "BlinkMacSystemFont", '"Apple SD Gothic Neo"', '"Malgun Gothic"', '"Noto Sans KR"', "sans-serif"],
        serif: ['"Noto Serif KR"', '"Nanum Myeongjo"', "serif"],
      },
      fontWeight: {
        extrabold: "700", // 800은 화면이 무거워 보여서 700까지만
      },
      colors: {
        stone: gray, // 따뜻한 회색 대신 남색과 어울리는 차가운 회색
        paper: "#f2f4f6",
        ink: "#191f28",
        line: "#e1e5ea",
        brand: { DEFAULT: "#173a5e", soft: "#e8eef5", dark: "#0f2a45" },
        brine: { DEFAULT: "#94570f", soft: "#f6ede2" },
        parcel: { DEFAULT: "#0e6a70", soft: "#e2f1f1" },
        truck: { DEFAULT: "#9a4f0a", soft: "#f8ecdf" },
        ok: { DEFAULT: "#267337", soft: "#eaf6ec" },
        warn: { DEFAULT: "#8a5c00", soft: "#fff3db" },
        bad: { DEFAULT: "#bd2c0f", soft: "#fdefec", strong: "#de3412" },
      },
      borderRadius: {
        xl: "0.5rem", // 버튼·입력창 8px
        "2xl": "0.75rem", // 카드 12px
        "3xl": "1rem", // 대화상자 16px
        xl2: "0.5rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0, 23, 51, 0.04)",
        pop: "0 8px 24px rgba(0, 23, 51, 0.12)",
      },
    },
  },
  plugins: [],
};
