// 카카오(다음) 우편번호 서비스 — 무료, 키 필요 없음. 스크립트를 필요할 때만 불러온다.
// https://postcode.map.daum.net/guide

export interface PostcodeResult {
  zonecode: string; // 새 우편번호 5자리
  roadAddress: string;
  jibunAddress: string;
  buildingName: string;
  userSelectedType: "R" | "J";
}

interface DaumPostcode {
  embed: (el: HTMLElement, opts?: { autoClose?: boolean }) => void;
}
declare global {
  interface Window {
    daum?: { Postcode: new (opts: { oncomplete: (d: PostcodeResult) => void; width?: string; height?: string }) => DaumPostcode };
  }
}

const SRC = "https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js";
let loading: Promise<void> | null = null;

export function loadPostcode(): Promise<void> {
  if (window.daum?.Postcode) return Promise.resolve();
  if (loading) return loading;
  loading = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SRC;
    s.async = true;
    s.onload = () => (window.daum?.Postcode ? resolve() : reject(new Error("postcode")));
    s.onerror = () => {
      loading = null;
      reject(new Error("postcode"));
    };
    document.head.appendChild(s);
  });
  return loading;
}

/** 고른 주소를 '도로명 주소 (건물명)' 한 줄로 */
export function formatAddress(d: PostcodeResult): string {
  const base = d.userSelectedType === "J" ? d.jibunAddress : d.roadAddress;
  return d.buildingName ? `${base} (${d.buildingName})` : base;
}
