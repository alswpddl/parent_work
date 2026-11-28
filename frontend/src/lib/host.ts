// 주소 나누기: 손님 주문서 전용 주소(gayeom.vercel.app)와 관리자 주소(gayeom-admin.vercel.app)
// 손님 주소로 들어오면 관리자 화면은 아예 없고, 첫 화면이 바로 주문서예요. 주소 뒤에 /shop 도 붙지 않아요.
// 관리자 주소에서는 예전처럼 /shop 으로 주문서가 열려요 (옛 링크도 그대로 동작).
const DEFAULT_SHOP_HOSTS = "gayeom.vercel.app";

export const SHOP_HOSTS: string[] = String((import.meta.env as Record<string, unknown>)?.VITE_SHOP_HOSTS || DEFAULT_SHOP_HOSTS)
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

export const isShopHost = (): boolean => typeof window !== "undefined" && SHOP_HOSTS.includes(window.location.hostname);

/** 주문서 안의 주소 앞부분: 손님 주소면 "", 관리자 주소면 "/shop" */
export const SP = isShopHost() ? "" : "/shop";
/** 주문서 첫 화면 */
export const SHOP_HOME = SP || "/";
