// fetch 래퍼: 토큰, 한국어 오류 메시지, 서버 깨우는 중 표시, 파일 받기

const BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "").replace(/\/$/, "");
const TOKEN_KEY = "fo_token";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(message: string, status: number, code = "") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let token: string | null = null;
try {
  token = localStorage.getItem(TOKEN_KEY);
} catch {
  token = null;
}

export function getToken(): string | null {
  return token;
}

export function setToken(t: string | null): void {
  token = t;
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 저장 불가 환경 무시 */
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  query?: Query;
  auth?: boolean;
  headers?: Record<string, string>;
}

function buildUrl(path: string, query?: Query): string {
  const url = `${BASE}${path}`;
  if (!query) return url;
  const qs = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return qs ? `${url}?${qs}` : url;
}

let inflight = 0;
function slowStart(): () => void {
  inflight += 1;
  const timer = window.setTimeout(() => window.dispatchEvent(new CustomEvent("api:slow", { detail: true })), 3500);
  return () => {
    window.clearTimeout(timer);
    inflight -= 1;
    if (inflight <= 0) window.dispatchEvent(new CustomEvent("api:slow", { detail: false }));
  };
}

async function raw(path: string, opts: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (opts.auth !== false && token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const done = slowStart();
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError("서버에 연결하지 못했어요. 인터넷을 확인하고 다시 눌러 주세요.", 0, "network");
  } finally {
    done();
  }
  if (res.status === 401 && opts.auth !== false) {
    setToken(null);
    window.dispatchEvent(new Event("api:unauthorized"));
  }
  if (!res.ok) {
    let message = `오류가 났어요 (${res.status})`;
    let code = "";
    try {
      const data = await res.json();
      message = data.message || data.detail || message;
      code = data.error || "";
    } catch {
      /* 본문 없음 */
    }
    throw new ApiError(message, res.status, code);
  }
  return res;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await raw(path, opts);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get("Content-Disposition") || "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1] : fallback;
}

export async function apiBlob(path: string, opts: RequestOptions = {}, fallback = "download"): Promise<{ blob: Blob; filename: string; res: Response }> {
  const res = await raw(path, opts);
  return { blob: await res.blob(), filename: filenameFrom(res, fallback), res };
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/** 팝업 차단을 피하려고 클릭 순간 창을 먼저 열고, 파일을 받은 뒤 주소를 넣는다. */
export async function openBlobInNewTab(load: () => Promise<{ blob: Blob }>): Promise<void> {
  const w = window.open("", "_blank");
  try {
    const { blob } = await load();
    const url = URL.createObjectURL(blob);
    if (w) w.location.href = url;
    else window.location.href = url;
  } catch (e) {
    w?.close();
    throw e;
  }
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "알 수 없는 오류가 났어요.";
}
