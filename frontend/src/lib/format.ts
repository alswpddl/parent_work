const DOW = ["일", "월", "화", "수", "목", "금", "토"];

export function won(n: number | null | undefined): string {
  if (n === null || n === undefined) return "-";
  return `${n.toLocaleString("ko-KR")}원`;
}

export function kg(n: number | null | undefined): string {
  if (n === null || n === undefined) return "-";
  return `${(Math.round(n * 10) / 10).toLocaleString("ko-KR")}kg`;
}

export function num(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString("ko-KR");
}

function parseDate(s: string): Date {
  // 'YYYY-MM-DD' 는 로컬 날짜로 해석 (UTC 로 밀리지 않게)
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, d] = s.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(s);
}

export function dateKo(s: string | null | undefined): string {
  if (!s) return "날짜 미정";
  const d = parseDate(s);
  if (Number.isNaN(d.getTime())) return s;
  return `${d.getMonth() + 1}/${d.getDate()}(${DOW[d.getDay()]})`;
}

export function dateTimeKo(s: string | null | undefined): string {
  if (!s) return "-";
  const d = parseDate(s);
  if (Number.isNaN(d.getTime())) return s;
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function todayIso(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return iso(d);
}

export function monthIso(offsetMonths = 0): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() + offsetMonths);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function isPast(s: string | null | undefined): boolean {
  return !!s && s < todayIso();
}

export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^0-9+]/g, "")}`;
}
