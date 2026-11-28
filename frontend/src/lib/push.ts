// 관리자 앱 휴대폰 알림 (웹 푸시)
// 아침 브리핑·새 주문·재고 경고가 카톡 '나와의 채팅'(울리지 않음)과 함께 이 휴대폰에도 '띵' 하고 와요.
import { pushStatus, pushSubscribe, pushUnsubscribe } from "../api/endpoints";

export type PushState =
  | "unsupported" // 이 브라우저는 알림을 못 받음
  | "ios-install" // 아이폰: 홈 화면에 추가한 앱에서만 됨
  | "denied" // 알림을 '차단'으로 눌렀음 → 휴대폰 설정에서 풀어야 함
  | "off"
  | "on";

const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isStandalone = () => window.matchMedia?.("(display-mode: standalone)").matches || (navigator as unknown as { standalone?: boolean }).standalone === true;

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration("/");
  if (existing) return existing;
  await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  return navigator.serviceWorker.ready;
}

function keyBytes(b64: string): Uint8Array {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return isIOS() && !isStandalone() ? "ios-install" : "unsupported";
  if (Notification.permission === "denied") return "denied";
  try {
    const reg = await navigator.serviceWorker.getRegistration("/");
    const sub = await reg?.pushManager.getSubscription();
    if (!sub) return "off";
    const st = await pushStatus(sub.endpoint);
    return st.subscribed ? "on" : "off";
  } catch {
    return "off";
  }
}

function deviceLabel(): string {
  const ua = navigator.userAgent;
  if (/iphone/i.test(ua)) return "아이폰";
  if (/ipad/i.test(ua)) return "아이패드";
  if (/android/i.test(ua)) return /mobile/i.test(ua) ? "안드로이드 폰" : "안드로이드 태블릿";
  return "컴퓨터";
}

/** 알림 켜기. 허락 창이 뜨고, '허용'을 누르면 서버에 이 휴대폰을 등록해요 */
export async function enablePush(): Promise<PushState> {
  if (!pushSupported()) return pushState();
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return perm === "denied" ? "denied" : "off";
  const reg = await registration();
  const { public_key } = await pushStatus("");
  let sub = await reg.pushManager.getSubscription();
  if (sub && sub.options.applicationServerKey) {
    // 서버 키가 바뀌었으면 새로 구독
    const cur = new Uint8Array(sub.options.applicationServerKey);
    const want = keyBytes(public_key);
    if (cur.length !== want.length || cur.some((v, i) => v !== want[i])) {
      await sub.unsubscribe();
      sub = null;
    }
  }
  sub = sub ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) as BufferSource }));
  const j = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
  await pushSubscribe({ endpoint: j.endpoint, keys: j.keys, label: deviceLabel() });
  return "on";
}

export async function disablePush(): Promise<PushState> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  const sub = await reg?.pushManager.getSubscription();
  if (sub) {
    await pushUnsubscribe(sub.endpoint).catch(() => undefined);
    await sub.unsubscribe();
  }
  return "off";
}
