// 웹 주문서 공용 상태: 주문서 정보 · 장바구니 · 로그인
// 장바구니와 로그인은 이 휴대폰(브라우저)에만 저장된다. 저장이 막힌 브라우저에서도 화면은 동작한다.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { shopInfo, shopMe } from "../../api/endpoints";
import type { GuestOrderResult, ShopAuth, ShopInfo, ShopProduct, ShopProfile } from "../../api/types";
import { useAsync } from "../../lib/hooks";

export const store = {
  get<T>(k: string, fallback: T): T {
    try {
      const v = window.localStorage.getItem(k);
      return v ? (JSON.parse(v) as T) : fallback;
    } catch {
      return fallback;
    }
  },
  set(k: string, v: unknown) {
    try {
      window.localStorage.setItem(k, JSON.stringify(v));
    } catch {
      /* 저장 못 해도 주문에는 지장 없음 */
    }
  },
  del(k: string) {
    try {
      window.localStorage.removeItem(k);
    } catch {
      /* noop */
    }
  },
};

const CART_KEY = "shop.cart";
const AUTH_KEY = "shop.auth";
export const LAST_KEY = "shop.lastOrder";

export type Cart = Record<string, number>; // sku → 수량

interface ShopState {
  info: ShopInfo | undefined;
  infoError: string;
  infoLoading: boolean;
  reloadInfo: () => void;
  products: ShopProduct[];
  bySku: Record<string, ShopProduct>;
  cart: Cart;
  setQty: (sku: string, qty: number) => void;
  addMany: (items: { sku: string; qty: number }[]) => number;
  clearCart: () => void;
  cartCount: number;
  auth: ShopAuth | null;
  signIn: (a: ShopAuth) => void;
  signOut: () => void;
  setProfile: (p: ShopProfile) => void;
  lastResult: GuestOrderResult | null;
  setLastResult: (r: GuestOrderResult | null) => void;
}

const Ctx = createContext<ShopState | null>(null);

export function ShopProvider({ children }: { children: ReactNode }) {
  const info = useAsync(shopInfo, []);
  const [cart, setCart] = useState<Cart>(() => store.get<Cart>(CART_KEY, {}));
  const [auth, setAuth] = useState<ShopAuth | null>(() => store.get<ShopAuth | null>(AUTH_KEY, null));
  const [lastResult, setLastResult] = useState<GuestOrderResult | null>(null);

  const products = useMemo(() => info.data?.products ?? [], [info.data]);
  const bySku = useMemo(() => Object.fromEntries(products.map((p) => [p.sku, p])), [products]);

  // 장바구니에서 이제 없는 품목·품절 품목은 빼 둔다
  useEffect(() => {
    if (!info.data) return;
    setCart((c) => {
      const next = Object.fromEntries(Object.entries(c).filter(([sku, q]) => q > 0 && bySku[sku] && !bySku[sku].sold_out));
      return Object.keys(next).length === Object.keys(c).length ? c : next;
    });
  }, [info.data, bySku]);
  useEffect(() => {
    store.set(CART_KEY, cart);
  }, [cart]);

  // 저장된 로그인이 아직 유효한지 한 번 확인 (비밀번호 바꿈·초기화면 로그아웃)
  useEffect(() => {
    if (!auth) return;
    shopMe(auth.token)
      .then((p) => setAuth((a) => (a ? { ...a, profile: p } : a)))
      .catch((e: { status?: number }) => {
        if (e?.status === 401) {
          store.del(AUTH_KEY);
          setAuth(null);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signIn = useCallback((a: ShopAuth) => {
    store.set(AUTH_KEY, a);
    setAuth(a);
  }, []);
  const signOut = useCallback(() => {
    store.del(AUTH_KEY);
    setAuth(null);
  }, []);
  const setProfile = useCallback((p: ShopProfile) => {
    setAuth((a) => {
      const next = a ? { ...a, profile: p } : a;
      if (next) store.set(AUTH_KEY, next);
      return next;
    });
  }, []);

  const value: ShopState = {
    info: info.data,
    infoError: info.error,
    infoLoading: info.loading,
    reloadInfo: () => void info.reload(),
    products,
    bySku,
    cart,
    setQty: (sku, qty) => setCart((c) => ({ ...c, [sku]: Math.max(0, Math.min(999, qty)) })),
    addMany: (items) => {
      const ok = items.filter((it) => bySku[it.sku] && !bySku[it.sku].sold_out && it.qty > 0);
      setCart((c) => {
        const next = { ...c };
        for (const it of ok) next[it.sku] = Math.min(999, (next[it.sku] ?? 0) + it.qty);
        return next;
      });
      return ok.length;
    },
    clearCart: () => setCart({}),
    cartCount: Object.values(cart).reduce((a, b) => a + (b > 0 ? b : 0), 0),
    auth,
    signIn,
    signOut,
    setProfile,
    lastResult,
    setLastResult,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useShop(): ShopState {
  const v = useContext(Ctx);
  if (!v) throw new Error("ShopProvider 밖에서 useShop");
  return v;
}

// ---------------------------------------------------------------- 품목 묶기 (이름이 같으면 규격만 다른 한 상품)
export interface ProductGroup {
  name: string;
  variants: ShopProduct[];
  description: string;
  image_url: string;
  minPrice: number | null;
  soldOut: boolean;
}

export function groupProducts(products: ShopProduct[]): ProductGroup[] {
  const m = new Map<string, ShopProduct[]>();
  for (const p of products) m.set(p.name, [...(m.get(p.name) ?? []), p]);
  return [...m.entries()].map(([name, vs]) => {
    const variants = [...vs].sort((a, b) => a.unit_kg - b.unit_kg);
    const prices = variants.filter((v) => !v.sold_out && v.price !== null).map((v) => v.price as number);
    return {
      name,
      variants,
      description: variants.find((v) => v.description)?.description ?? "",
      image_url: variants.find((v) => v.image_url)?.image_url ?? "",
      minPrice: prices.length ? Math.min(...prices) : null,
      soldOut: variants.every((v) => v.sold_out),
    };
  });
}

export const itemPath = (name: string) => `/shop/item/${encodeURIComponent(name)}`;

// ---------------------------------------------------------------- 공용 계산
export const MOBILE_RE = /^01[016789]\d{7,8}$/;
export const WEEK = "월화수목금토일";
export const digits = (s: string) => s.replace(/\D/g, "");

export function formatPhone(s: string): string {
  const d = digits(s).slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  if (d.length === 10) return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
}

/** 'YYYY-MM-DD' → 0=월 … 6=일 */
export function weekdayOf(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return (new Date(y, m - 1, d).getDay() + 6) % 7;
}

export function newToken(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  } catch {
    /* 오래된 브라우저 */
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
