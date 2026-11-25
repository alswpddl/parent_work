// 웹 주문서 (/shop) — 누구나 링크로 들어와 주문. 로그인 없음, 휴대폰 우선, 큰 글씨.
// 순서: ① 품목 고르기 → ② 받는 분 정보 → ③ 개인정보 동의 → [주문 확인] → [이대로 주문하기] → 완료 화면
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, ChevronDown, MapPin, Package, Phone, Search, ShoppingBasket } from "lucide-react";
import { errorMessage } from "../../api/client";
import { shopInfo, shopLookup, shopPlaceOrder } from "../../api/endpoints";
import type { GuestOrderResult, PublicOrder, ShopInfo, ShopProduct } from "../../api/types";
import { Alert, Badge, Button, CopyButton, Field, Input, Modal, Segmented, Spinner, Stepper, Textarea, cx } from "../../components/ui";
import { dateKo, telHref, won } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { formatAddress, loadPostcode } from "../../lib/postcode";

type Tab = "order" | "lookup";

interface Me {
  name: string;
  company: string;
  phone: string;
  base: string;
  detail: string;
  zipcode: string;
}
const EMPTY_ME: Me = { name: "", company: "", phone: "", base: "", detail: "", zipcode: "" };
const ME_KEY = "shop.me";
const LAST_KEY = "shop.lastOrder";

// 브라우저 저장소는 막혀 있을 수 있으니 항상 try
const store = {
  get<T>(k: string, fallback: T): T {
    try {
      const v = window.localStorage.getItem(k);
      return v ? ({ ...fallback, ...JSON.parse(v) } as T) : fallback;
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

const MOBILE_RE = /^01[016789]\d{7,8}$/;
const WEEK = "월화수목금토일";

/** 같은 주문서를 두 번 보내도 주문이 1건만 생기게 하는 표 (서버가 기억함) */
function newToken(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  } catch {
    /* 오래된 브라우저 */
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** 'YYYY-MM-DD' → 0=월 … 6=일 */
function weekdayOf(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return (new Date(y, m - 1, d).getDay() + 6) % 7;
}

/** 서버와 같은 규칙으로 택배비 미리 계산 (null = 확인 후 안내) */
function estimateShipping(shop: ShopInfo, subtotal: number | null, kg: number): { fee: number | null; note: string } {
  if (shop.threshold_kg > 0 && kg >= shop.threshold_kg) return { fee: null, note: "양이 많아 화물로 보내요 (운임은 확인 후 안내)" };
  if (shop.free_shipping_over > 0 && subtotal !== null && subtotal >= shop.free_shipping_over) return { fee: 0, note: "택배비 무료" };
  if (shop.shipping_fee > 0) {
    const left = shop.free_shipping_over > 0 && subtotal !== null ? shop.free_shipping_over - subtotal : 0;
    return { fee: shop.shipping_fee, note: left > 0 ? `${won(left)} 더 담으면 택배비 무료` : `택배비 ${won(shop.shipping_fee)}` };
  }
  return { fee: null, note: "택배비는 확인 후 안내드려요" };
}
const digits = (s: string) => s.replace(/\D/g, "");
function formatPhone(s: string): string {
  const d = digits(s).slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  if (d.length === 10) return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
}

export default function Shop() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "lookup" ? "lookup" : "order";
  const info = useAsync(shopInfo, []);
  const [done, setDone] = useState<GuestOrderResult | null>(null);

  useEffect(() => {
    if (info.data) document.title = `${info.data.factory_name} 주문서`;
  }, [info.data]);

  if (info.loading) return <Spinner label="주문서를 여는 중… (처음엔 1분쯤 걸릴 수 있어요)" />;
  if (info.error || !info.data)
    return (
      <div className="mx-auto max-w-md p-6">
        <Alert tone="error">{info.error || "주문서를 열지 못했어요."}</Alert>
        <Button block onClick={info.reload}>다시 열기</Button>
      </div>
    );
  const s = info.data;

  return (
    <div className="mx-auto min-h-screen max-w-lg px-4 pb-36 pt-5">
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-brand">주문서</div>
          <h1 className="text-3xl font-extrabold tracking-tight">{s.factory_name}</h1>
        </div>
        {s.factory_phone && (
          <a href={telHref(s.factory_phone)} className="flex shrink-0 items-center gap-1 rounded-xl2 border-2 border-line bg-white px-3 py-2 font-bold">
            <Phone className="h-4 w-4" /> 전화 주문
          </a>
        )}
      </header>
      {s.notice && <p className="mb-4 whitespace-pre-line rounded-xl bg-brand-soft px-4 py-3 text-brand-dark">{s.notice}</p>}

      {!done && (
        <Segmented
          className="mb-5"
          value={tab}
          onChange={(t) => setParams(t === "lookup" ? { tab: "lookup" } : {}, { replace: true })}
          options={[
            { value: "order", label: "주문하기" },
            { value: "lookup", label: "주문 조회" },
          ]}
        />
      )}

      {done ? (
        <Done
          r={done}
          shop={s}
          onAgain={() => {
            setDone(null);
            window.scrollTo({ top: 0 });
          }}
          onLookup={() => {
            setDone(null);
            setParams({ tab: "lookup" });
          }}
        />
      ) : tab === "order" ? (
        <OrderForm
          shop={s}
          onDone={(r) => {
            setDone(r);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      ) : (
        <Lookup />
      )}

      <footer className="mt-10 text-center text-xs text-stone-400">
        {s.factory_name}
        {s.factory_phone && ` · ${s.factory_phone}`}
      </footer>
    </div>
  );
}

// ================================================================ 주문서
function Section({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 flex items-center gap-2 text-xl font-extrabold">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand text-base text-white">{n}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function OrderForm({ shop, onDone }: { shop: ShopInfo; onDone: (r: GuestOrderResult) => void }) {
  const [qty, setQty] = useState<Record<string, number>>({});
  const [me, setMe] = useState<Me>(() => store.get(ME_KEY, EMPTY_ME));
  const [remember, setRemember] = useState(true);
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [agree, setAgree] = useState(false);
  const [showPolicy, setShowPolicy] = useState(false);
  const [website, setWebsite] = useState(""); // 숨김 칸 (봇용)
  const [errors, setErrors] = useState<Partial<Record<"items" | "name" | "phone" | "address" | "due" | "agree", string>>>({});
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sendError, setSendError] = useState("");
  const [postOpen, setPostOpen] = useState(false);
  const detailRef = useRef<HTMLInputElement>(null);

  const set = (p: Partial<Me>) => setMe((m) => ({ ...m, ...p }));
  const pmap = useMemo(() => Object.fromEntries(shop.products.map((p) => [p.sku, p])), [shop.products]);
  const picked = useMemo(
    () => Object.entries(qty).filter(([sku, q]) => q > 0 && pmap[sku]).map(([sku, q]) => ({ p: pmap[sku] as ShopProduct, qty: q })),
    [qty, pmap],
  );
  const count = picked.reduce((a, x) => a + x.qty, 0);
  const subtotal = shop.show_prices && picked.every((x) => x.p.price !== null) ? picked.reduce((a, x) => a + x.qty * (x.p.price ?? 0), 0) : null;
  const totalKg = picked.reduce((a, x) => a + x.qty * x.p.unit_kg, 0);
  const ship = estimateShipping(shop, subtotal, totalKg);
  const total = subtotal !== null && ship.fee !== null ? subtotal + ship.fee : null;
  const tokenRef = useRef(newToken());
  const dueClosed = !!due && shop.closed_weekdays.includes(weekdayOf(due));
  const address = `${me.base} ${me.detail}`.trim();

  const check = (): boolean => {
    const e: typeof errors = {};
    if (!picked.length) e.items = "주문할 품목의 수량을 넣어 주세요.";
    if (!me.name.trim()) e.name = "받는 분 성함을 적어 주세요.";
    if (!MOBILE_RE.test(digits(me.phone))) e.phone = "휴대폰 번호를 확인해 주세요. 예) 010-1234-5678";
    if (address.length < 5) e.address = "받는 주소를 적어 주세요.";
    if (due && due < shop.min_due_date) e.due = `${dateKo(shop.min_due_date)}부터 고를 수 있어요.`;
    else if (dueClosed) e.due = `${WEEK[weekdayOf(due)]}요일은 택배가 쉬어요. 다른 날을 골라 주세요.`;
    if (!agree) e.agree = "개인정보 수집·이용에 동의해 주세요.";
    setErrors(e);
    const first = (["items", "name", "phone", "address", "due", "agree"] as const).find((k) => e[k]);
    if (first) document.getElementById(`f-${first}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    return !first;
  };

  const openPostcode = async () => {
    try {
      await loadPostcode();
      setPostOpen(true);
    } catch {
      setErrors((e) => ({ ...e, address: "주소 찾기를 열지 못했어요. 주소를 직접 적어 주세요." }));
    }
  };

  const submit = async () => {
    setBusy(true);
    setSendError("");
    try {
      const r = await shopPlaceOrder({
        name: me.name.trim(),
        company: me.company.trim(),
        phone: formatPhone(me.phone),
        address,
        zipcode: me.zipcode.trim(),
        due_date: due || null,
        note: note.trim(),
        items: picked.map((x) => ({ sku: x.p.sku, qty: x.qty })),
        agree_privacy: agree,
        website,
        client_token: tokenRef.current,
      });
      if (remember) store.set(ME_KEY, me);
      else store.del(ME_KEY);
      store.set(LAST_KEY, { order_id: r.order_id, phone4: digits(me.phone).slice(-4) });
      setConfirm(false);
      onDone(r);
    } catch (e) {
      setSendError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Section n={1} title="무엇을 몇 개 드릴까요?">
        <div id="f-items" className="space-y-3">
          {shop.products.length === 0 && <Alert tone="info">지금은 주문할 수 있는 품목이 없어요. 전화로 문의해 주세요.</Alert>}
          {shop.products.map((p) => {
            const q = qty[p.sku] ?? 0;
            return (
              <div key={p.sku} className={cx("rounded-2xl border-2 bg-white p-4 transition", p.sold_out ? "border-line opacity-60" : q ? "border-brand shadow-sm" : "border-line")}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-lg font-extrabold leading-tight">
                      {p.name} <span className="whitespace-nowrap text-brand">{p.spec}</span>
                    </div>
                    {p.description && <div className="mt-0.5 text-sm text-stone-600">{p.description}</div>}
                    {p.price !== null && (
                      <div className="mt-1 font-bold">
                        {won(p.price)} <span className="text-sm font-normal text-stone-500">/ 1{p.unit}</span>
                      </div>
                    )}
                  </div>
                  {p.sold_out ? <Badge tone="red">품절</Badge> : q > 0 && <Badge tone="green">{q}{p.unit}</Badge>}
                </div>
                {!p.sold_out && (
                  <div className="mt-3 flex items-center justify-between gap-3">
                    <span className="text-sm text-stone-500">{q > 0 && p.price !== null ? `${won(q * p.price)}` : `단위: ${p.unit}`}</span>
                    <Stepper value={q} onChange={(v) => { setQty({ ...qty, [p.sku]: v }); setErrors((e) => ({ ...e, items: undefined })); }} max={999} />
                  </div>
                )}
              </div>
            );
          })}
          {errors.items && <p className="font-semibold text-red-700">{errors.items}</p>}
        </div>
      </Section>

      <Section n={2} title="받는 분">
        <div id="f-name">
          <Field label="성함 *" hint={errors.name && <span className="text-red-700">{errors.name}</span>}>
            <Input value={me.name} autoComplete="name" placeholder="홍길동" onChange={(e) => set({ name: e.target.value })} />
          </Field>
        </div>
        <Field label="상호 (가게·식당이면)" hint="개인이시면 비워 두세요">
          <Input value={me.company} autoComplete="organization" placeholder="예) 바다식당" onChange={(e) => set({ company: e.target.value })} />
        </Field>
        <div id="f-phone">
          <Field label="휴대폰 번호 *" hint={errors.phone ? <span className="text-red-700">{errors.phone}</span> : "주문 확인·배송 안내를 보내 드려요"}>
            <Input value={me.phone} type="tel" inputMode="numeric" autoComplete="tel" placeholder="010-1234-5678" onChange={(e) => set({ phone: formatPhone(e.target.value) })} />
          </Field>
        </div>
        <div id="f-address">
          <Field label="받는 주소 *" hint={errors.address && <span className="text-red-700">{errors.address}</span>}>
            <div className="flex gap-2">
              <Input value={me.base} placeholder="주소 찾기를 눌러 주세요" autoComplete="street-address" onChange={(e) => set({ base: e.target.value })} />
              <Button size="md" variant="soft" className="shrink-0" icon={<Search className="h-5 w-5" />} onClick={openPostcode}>
                주소 찾기
              </Button>
            </div>
          </Field>
          <div className="grid grid-cols-[1fr_7rem] gap-2">
            <Field label="상세 주소">
              <Input ref={detailRef} value={me.detail} placeholder="동·호수" onChange={(e) => set({ detail: e.target.value })} />
            </Field>
            <Field label="우편번호">
              <Input value={me.zipcode} inputMode="numeric" maxLength={6} onChange={(e) => set({ zipcode: digits(e.target.value) })} />
            </Field>
          </div>
        </div>
        <div id="f-due">
          <Field
            label="받고 싶은 날"
            hint={
              errors.due || dueClosed ? (
                <span className="text-red-700">{errors.due || `${WEEK[weekdayOf(due)]}요일은 택배가 쉬어요. 다른 날을 골라 주세요.`}</span>
              ) : (
                `${dateKo(shop.min_due_date)}부터 고를 수 있어요${shop.closed_days_text ? ` (${shop.closed_days_text}요일 제외)` : ""}. 비워 두면 가장 빠른 날로 보내 드려요.`
              )
            }
          >
            <Input type="date" min={shop.min_due_date} value={due} onChange={(e) => { setDue(e.target.value); setErrors((x) => ({ ...x, due: undefined })); }} />
          </Field>
        </div>
        <Field label="요청사항">
          <Textarea rows={2} className="min-h-[84px]" value={note} maxLength={300} placeholder="예) 문 앞에 두세요 / 오전에 받고 싶어요" onChange={(e) => setNote(e.target.value)} />
        </Field>
        {/* 사람은 안 보이는 칸 — 자동 등록 프로그램만 채운다 */}
        <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
          <label>
            website
            <input tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
          </label>
        </div>
        <label className="flex items-center gap-2 text-stone-600">
          <input type="checkbox" className="h-5 w-5 accent-brand" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          이 휴대폰에 받는 분 정보 기억하기
        </label>
      </Section>

      <Section n={3} title="개인정보 동의">
        <div id="f-agree" className={cx("rounded-2xl border-2 bg-white p-4", errors.agree ? "border-red-300" : "border-line")}>
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-0.5 h-6 w-6 shrink-0 accent-brand"
              checked={agree}
              onChange={(e) => {
                setAgree(e.target.checked);
                setErrors((x) => ({ ...x, agree: undefined }));
              }}
            />
            <span className="text-lg font-bold">주문·배송을 위한 개인정보 수집·이용에 동의해요 (필수)</span>
          </label>
          <button className="mt-2 flex items-center gap-1 text-sm font-semibold text-stone-500" onClick={() => setShowPolicy(!showPolicy)}>
            내용 보기 <ChevronDown className={cx("h-4 w-4 transition", showPolicy && "rotate-180")} />
          </button>
          {showPolicy && <p className="mt-2 whitespace-pre-line rounded-xl bg-paper p-3 text-sm text-stone-600">{shop.privacy_text}</p>}
          {errors.agree && <p className="mt-2 font-semibold text-red-700">{errors.agree}</p>}
        </div>
      </Section>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-paper/95 px-4 pt-3 backdrop-blur">
        <div className="mx-auto max-w-lg">
          {count > 0 && (
            <div className="mb-2 flex items-baseline justify-between gap-2 text-sm">
              <span className="font-semibold">
                {picked.length}가지 · {count}개
                {shop.show_prices && <span className="block text-xs font-normal text-stone-500">{ship.note}</span>}
              </span>
              {subtotal !== null && <span className="whitespace-nowrap text-lg font-extrabold">{won(total ?? subtotal)}</span>}
            </div>
          )}
          <Button size="xl" block icon={<ShoppingBasket className="h-6 w-6" />} onClick={() => check() && setConfirm(true)}>
            {count ? "주문 확인하기" : "수량을 넣어 주세요"}
          </Button>
        </div>
      </div>

      <Modal open={postOpen} onClose={() => setPostOpen(false)} title="주소 찾기">
        {postOpen && (
          <PostcodeEmbed
            onPick={(addr, zip) => {
              set({ base: addr, zipcode: zip });
              setErrors((e) => ({ ...e, address: undefined }));
              setPostOpen(false);
              window.setTimeout(() => detailRef.current?.focus(), 100);
            }}
          />
        )}
      </Modal>

      <Modal
        open={confirm}
        onClose={() => !busy && setConfirm(false)}
        title="이대로 주문할까요?"
        footer={
          <div className="grid w-full grid-cols-[auto_1fr] gap-2">
            <Button variant="ghost" disabled={busy} onClick={() => setConfirm(false)}>고치기</Button>
            <Button loading={busy} onClick={submit}>이대로 주문하기</Button>
          </div>
        }
      >
        <div className="mb-4 divide-y divide-line rounded-2xl border border-line bg-white">
          {picked.map((x) => (
            <div key={x.p.sku} className="flex items-center justify-between gap-3 px-4 py-3">
              <span className="font-bold">{x.p.name} {x.p.spec}</span>
              <span className="whitespace-nowrap">
                {x.qty}{x.p.unit}
                {x.p.price !== null && <span className="ml-2 text-stone-500">{won(x.qty * x.p.price)}</span>}
              </span>
            </div>
          ))}
          {subtotal !== null && (
            <div className="space-y-1 px-4 py-3">
              <div className="flex justify-between"><span>상품 금액</span><span>{won(subtotal)}</span></div>
              <div className="flex justify-between"><span>택배비</span><span>{ship.fee === null ? "확인 후 안내" : ship.fee === 0 ? "무료" : won(ship.fee)}</span></div>
              <div className="flex justify-between pt-1 text-lg font-extrabold">
                <span>{total !== null ? "합계" : "상품 합계"}</span>
                <span>{won(total ?? subtotal)}</span>
              </div>
            </div>
          )}
        </div>
        <dl className="space-y-1 text-[15px]">
          <Row k="받는 분" v={`${me.name}${me.company ? ` (${me.company})` : ""}`} />
          <Row k="휴대폰" v={formatPhone(me.phone)} />
          <Row k="주소" v={`${address}${me.zipcode ? ` [${me.zipcode}]` : ""}`} />
          <Row k="받는 날" v={due ? dateKo(due) : "가장 빠른 날"} />
          {note.trim() && <Row k="요청사항" v={note.trim()} />}
        </dl>
        {subtotal !== null && <p className="mt-3 text-sm text-stone-500">{total !== null ? "입금 확인 후 보내 드려요." : `${ship.note}. 최종 금액은 문자로 알려 드려요.`}</p>}
        {sendError && <div className="mt-3"><Alert tone="error">{sendError}</Alert></div>}
      </Modal>
    </>
  );
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-[5.5rem] shrink-0 whitespace-nowrap text-stone-500">{k}</dt>
      <dd className="min-w-0 break-keep font-semibold">{v}</dd>
    </div>
  );
}

function PostcodeEmbed({ onPick }: { onPick: (address: string, zipcode: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !window.daum?.Postcode) return;
    ref.current.innerHTML = "";
    new window.daum.Postcode({
      width: "100%",
      height: "100%",
      oncomplete: (d) => onPick(formatAddress(d), d.zonecode),
    }).embed(ref.current, { autoClose: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div ref={ref} className="h-[460px] w-full overflow-hidden rounded-xl border border-line" />;
}

// ================================================================ 완료
function Done({ r, shop, onAgain, onLookup }: { r: GuestOrderResult; shop: ShopInfo; onAgain: () => void; onLookup: () => void }) {
  return (
    <div>
      <div className="mb-5 rounded-2xl bg-brand p-6 text-center text-white">
        <CheckCircle2 className="mx-auto mb-2 h-14 w-14" />
        <div className="text-2xl font-extrabold">주문이 들어갔어요!</div>
        <div className="mt-1 opacity-90">확인하고 연락드릴게요. 감사합니다 🙏</div>
      </div>

      <div className="mb-4 rounded-2xl border-2 border-line bg-white p-5">
        <div className="text-sm text-stone-500">주문번호 (조회할 때 필요해요)</div>
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="whitespace-nowrap text-xl font-extrabold sm:text-2xl">{r.order_id}</span>
          <CopyButton size="sm" text={r.order_id} />
        </div>
        <dl className="space-y-1">
          <Row k="품목" v={r.items} />
          <Row k="받는 날" v={r.due_date} />
          <Row k="보내는 방법" v={r.ship_method} />
          {r.subtotal !== null && <Row k="상품 금액" v={won(r.subtotal)} />}
          {r.subtotal !== null && <Row k="택배비" v={r.shipping_fee === null ? r.shipping_note : r.shipping_fee === 0 ? "무료" : won(r.shipping_fee)} />}
          {r.estimated_total !== null && <Row k="입금할 금액" v={<span className="text-lg text-brand-dark">{won(r.estimated_total)}</span>} />}
        </dl>
      </div>

      {r.bank_account && (
        <div className="mb-4 rounded-2xl border-2 border-amber-200 bg-amber-50 p-5">
          <div className="mb-1 font-extrabold">입금 계좌</div>
          <div className="mb-3 break-keep text-lg font-bold">{r.bank_account}</div>
          <CopyButton size="sm" label="계좌 복사" text={r.bank_account} />
          <p className="mt-3 text-sm text-stone-600">
            {r.estimated_total !== null ? `${won(r.estimated_total)}을 보내 주세요. 입금이 확인되면 바로 준비해요. ` : "금액은 확인 후 문자로 안내드려요. "}
            입금자명은 주문하신 분 성함으로 해 주세요.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Button variant="ghost" icon={<Package className="h-5 w-5" />} onClick={onLookup}>주문 조회</Button>
        <Button variant="soft" onClick={onAgain}>또 주문하기</Button>
      </div>
      {shop.factory_phone && (
        <a href={telHref(shop.factory_phone)} className="mt-3 flex items-center justify-center gap-2 py-3 font-bold text-stone-600">
          <Phone className="h-4 w-4" /> 바꾸실 게 있으면 {shop.factory_phone}
        </a>
      )}
    </div>
  );
}

// ================================================================ 조회
const STATUS_LABEL: Record<string, { label: string; tone: "violet" | "amber" | "green" | "red"; step: number }> = {
  접수: { label: "주문 확인·준비 중", tone: "violet", step: 1 },
  출고대기: { label: "포장 끝, 곧 보내요", tone: "amber", step: 2 },
  출고완료: { label: "보냈어요", tone: "green", step: 3 },
  취소: { label: "취소된 주문", tone: "red", step: 0 },
};

function Lookup() {
  const last = store.get<{ order_id: string; phone4: string }>(LAST_KEY, { order_id: "", phone4: "" });
  const [orderId, setOrderId] = useState(last.order_id);
  const [phone4, setPhone4] = useState(last.phone4);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [r, setR] = useState<PublicOrder | null>(null);

  const find = async () => {
    setError("");
    setR(null);
    if (!orderId.trim() || digits(phone4).length !== 4) return setError("주문번호와 전화번호 뒤 4자리를 넣어 주세요.");
    setBusy(true);
    try {
      setR(await shopLookup(orderId.trim(), digits(phone4)));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const st = r ? STATUS_LABEL[r.status] ?? { label: r.status, tone: "violet" as const, step: 1 } : null;

  return (
    <div>
      <Field label="주문번호" hint="주문 완료 화면에 나온 번호예요. 예) O-20261124-003">
        <Input value={orderId} autoCapitalize="characters" placeholder="O-20261124-001" onChange={(e) => setOrderId(e.target.value.toUpperCase())} />
      </Field>
      <Field label="주문할 때 쓴 휴대폰 번호 뒤 4자리">
        <Input value={phone4} inputMode="numeric" maxLength={4} placeholder="5678" onChange={(e) => setPhone4(digits(e.target.value))} />
      </Field>
      {error && <Alert tone="error">{error}</Alert>}
      <Button size="xl" block loading={busy} icon={<Search className="h-6 w-6" />} onClick={find}>
        조회하기
      </Button>

      {r && st && (
        <div className="mt-5 rounded-2xl border-2 border-line bg-white p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="font-extrabold">{r.order_id}</span>
            <Badge tone={st.tone}>{st.label}</Badge>
          </div>
          {st.step > 0 && (
            <ol className="mb-4 grid grid-cols-3 gap-1 text-center text-sm font-semibold">
              {["접수", "포장", "출발"].map((label, i) => (
                <li key={label} className={cx("rounded-lg py-2", i < st.step ? "bg-brand text-white" : "bg-stone-100 text-stone-400")}>
                  {label}
                </li>
              ))}
            </ol>
          )}
          <dl className="space-y-1">
            <Row k="주문일" v={r.created_at} />
            <Row k="품목" v={r.items} />
            <Row k="받는 날" v={r.due_date === "날짜 미정" ? "정해지면 알려 드려요" : r.due_date} />
            <Row k="보내는 방법" v={r.ship_method} />
            <Row k="입금" v={r.paid ? "확인됐어요 ✔" : "확인 전이에요"} />
            {r.tracking_no && <Row k="송장" v={`${r.carrier} ${r.tracking_no}`} />}
            {r.truck_no && <Row k="화물차" v={r.truck_no} />}
          </dl>
          {r.tracking_no && (
            <a
              className="mt-4 flex items-center justify-center gap-2 rounded-xl2 bg-parcel px-4 py-3 font-bold text-white"
              href={`https://search.naver.com/search.naver?query=${encodeURIComponent(`${r.carrier} ${r.tracking_no}`)}`}
              target="_blank"
              rel="noreferrer"
            >
              <MapPin className="h-5 w-5" /> 배송 위치 보기
            </a>
          )}
        </div>
      )}
    </div>
  );
}
