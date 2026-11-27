// 토스페이먼츠 결제위젯 v2 — 스크립트는 결제 화면에 들어갈 때만 불러온다.
// 카드 번호·CVC·계좌 같은 결제 정보는 이 위젯(토스 화면) 안에서만 입력되고, 우리 서버로는 오지 않는다.

/* eslint-disable @typescript-eslint/no-explicit-any */
export interface TossWidgets {
  setAmount(a: { currency: "KRW"; value: number }): Promise<void>;
  renderPaymentMethods(o: { selector: string; variantKey?: string }): Promise<unknown>;
  renderAgreement(o: { selector: string; variantKey?: string }): Promise<unknown>;
  requestPayment(o: {
    orderId: string;
    orderName: string;
    successUrl: string;
    failUrl: string;
    customerName?: string;
    customerMobilePhone?: string;
  }): Promise<void>;
}

declare global {
  interface Window {
    TossPayments?: any;
  }
}

const SDK = "https://js.tosspayments.com/v2/standard";
let loading: Promise<void> | null = null;

export function loadToss(): Promise<void> {
  if (window.TossPayments) return Promise.resolve();
  if (loading) return loading;
  loading = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SDK;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      loading = null;
      reject(new Error("결제창을 불러오지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요."));
    };
    document.head.appendChild(s);
  });
  return loading;
}

export async function makeWidgets(clientKey: string): Promise<TossWidgets> {
  await loadToss();
  const toss = window.TossPayments!(clientKey);
  return toss.widgets({ customerKey: window.TossPayments!.ANONYMOUS }) as TossWidgets;
}

/** 결제창을 연 주문의 결제 표를 잠깐 기억 (실패 → 다시 결제할 때 씀) */
const KEY = "shop.pay.";
export const rememberPayAccess = (orderId: string, q: string) => {
  try {
    sessionStorage.setItem(KEY + orderId, q);
  } catch {
    /* 저장 못 해도 결제는 됨 */
  }
};
export const recallPayAccess = (orderId: string): string => {
  try {
    return sessionStorage.getItem(KEY + orderId) || "";
  } catch {
    return "";
  }
};
