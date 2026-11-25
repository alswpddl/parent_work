// 장바구니 · 주문하기
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronDown, ShoppingBasket, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { shopPlaceOrderAs } from "../../api/endpoints";
import type { ShopInfo, ShopProduct } from "../../api/types";
import { Alert, Button, Field, Input, Modal, Stepper, Textarea, cx } from "../../components/ui";
import { dateKo, won } from "../../lib/format";
import { AddressField, ProductArt, Row, SectionTitle, joinAddress, type Address } from "./parts";
import { LAST_KEY, MOBILE_RE, WEEK, digits, formatPhone, itemPath, newToken, store, useShop, weekdayOf } from "./store";

const ME_KEY = "shop.me"; // 비회원이 '기억하기'를 고르면 받는 분 정보 저장

interface Guest {
  name: string;
  company: string;
  phone: string;
  address: Address;
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

export default function Cart() {
  const s = useShop();
  const nav = useNavigate();
  const shop = s.info!;
  const member = s.auth;

  const picked = useMemo(
    () => Object.entries(s.cart).filter(([sku, q]) => q > 0 && s.bySku[sku]).map(([sku, q]) => ({ p: s.bySku[sku] as ShopProduct, qty: q })),
    [s.cart, s.bySku],
  );
  const count = picked.reduce((a, x) => a + x.qty, 0);
  const subtotal = shop.show_prices && picked.every((x) => x.p.price !== null) ? picked.reduce((a, x) => a + x.qty * (x.p.price ?? 0), 0) : null;
  const ship = estimateShipping(shop, subtotal, picked.reduce((a, x) => a + x.qty * x.p.unit_kg, 0));
  const total = subtotal !== null && ship.fee !== null ? subtotal + ship.fee : null;

  // 받는 분: 로그인 손님은 내 정보로 채워 두고, 비회원은 이 휴대폰에 기억해 둔 정보
  const [who, setWho] = useState<Guest>(() => {
    if (member) {
      const p = member.profile;
      return { name: p.name, company: p.company, phone: p.phone, address: { base: p.address, detail: "", zipcode: p.zipcode } };
    }
    return store.get<Guest>(ME_KEY, { name: "", company: "", phone: "", address: { base: "", detail: "", zipcode: "" } });
  });
  const [remember, setRemember] = useState(true);
  const [password, setPassword] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [agree, setAgree] = useState(!!member);
  const [showPolicy, setShowPolicy] = useState(false);
  const [website, setWebsite] = useState(""); // 숨김 칸 (봇용)
  const [errors, setErrors] = useState<Partial<Record<"items" | "name" | "phone" | "address" | "due" | "password" | "agree", string>>>({});
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sendError, setSendError] = useState("");
  const tokenRef = useRef(newToken());
  const set = (p: Partial<Guest>) => setWho((w) => ({ ...w, ...p }));
  const address = joinAddress(who.address);
  const dueClosed = !!due && shop.closed_weekdays.includes(weekdayOf(due));

  const check = (): boolean => {
    const e: typeof errors = {};
    if (!picked.length) e.items = "장바구니가 비어 있어요.";
    if (!who.name.trim()) e.name = "받는 분 성함을 적어 주세요.";
    if (!MOBILE_RE.test(digits(who.phone))) e.phone = "휴대폰 번호를 확인해 주세요. 예) 010-1234-5678";
    if (address.length < 5) e.address = "받는 주소를 적어 주세요.";
    if (due && due < shop.min_due_date) e.due = `${dateKo(shop.min_due_date)}부터 고를 수 있어요.`;
    else if (dueClosed) e.due = `${WEEK[weekdayOf(due)]}요일은 택배가 쉬어요. 다른 날을 골라 주세요.`;
    if (!member && password && password.length < 4) e.password = "비밀번호는 4자리 이상으로 만들어 주세요.";
    if (!agree) e.agree = "개인정보 수집·이용에 동의해 주세요.";
    setErrors(e);
    const first = (["items", "name", "phone", "address", "due", "password", "agree"] as const).find((k) => e[k]);
    if (first) document.getElementById(`f-${first}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    return !first;
  };

  const submit = async () => {
    setBusy(true);
    setSendError("");
    try {
      const r = await shopPlaceOrderAs(
        {
          name: who.name.trim(),
          company: who.company.trim(),
          phone: formatPhone(who.phone),
          address,
          zipcode: who.address.zipcode.trim(),
          due_date: due || null,
          note: note.trim(),
          items: picked.map((x) => ({ sku: x.p.sku, qty: x.qty })),
          agree_privacy: agree,
          website,
          client_token: tokenRef.current,
          password: member ? "" : password,
        },
        member?.token ?? "",
      );
      if (!member) {
        if (remember) store.set(ME_KEY, who);
        else store.del(ME_KEY);
      }
      store.set(LAST_KEY, { order_id: r.order_id, phone4: digits(who.phone).slice(-4) });
      s.setLastResult(r);
      s.clearCart();
      setConfirm(false);
      nav("/shop/done");
    } catch (e) {
      setSendError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (!picked.length)
    return (
      <div className="py-12 text-center">
        <ShoppingBasket className="mx-auto mb-3 h-16 w-16 text-stone-300" />
        <p className="mb-5 text-lg text-stone-600">장바구니가 비어 있어요.</p>
        <Link to="/shop"><Button size="lg">상품 보러 가기</Button></Link>
      </div>
    );

  return (
    <div>
      <h1 className="text-2xl font-extrabold">장바구니</h1>
      <div id="f-items" className="mt-3 space-y-2">
        {picked.map(({ p, qty }) => (
          <div key={p.sku} className="rounded-2xl border border-line bg-white p-3">
            <div className="flex gap-3">
              <Link to={itemPath(p.name)} className="h-16 w-16 shrink-0 overflow-hidden rounded-xl">
                <ProductArt name={p.name} image={p.image_url} />
              </Link>
              <div className="min-w-0 flex-1">
                <div className="font-extrabold leading-tight">
                  {p.name} <span className="text-brand">{p.spec}</span>
                </div>
                <div className="mt-1 text-lg font-bold">{p.price !== null ? won(qty * p.price) : `${qty}${p.unit}`}</div>
              </div>
              <button aria-label="빼기" className="self-start p-1 text-stone-400" onClick={() => s.setQty(p.sku, 0)}>
                <Trash2 className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="whitespace-nowrap text-sm text-stone-500">{p.price !== null ? `${won(p.price)}×${qty}` : p.unit}</span>
              <Stepper value={qty} min={1} max={999} onChange={(v) => s.setQty(p.sku, v)} />
            </div>
          </div>
        ))}
        <Link to="/shop" className="block py-2 text-center font-semibold text-brand">+ 다른 상품 더 담기</Link>
      </div>

      {subtotal !== null && (
        <div className="mt-2 space-y-1 rounded-2xl bg-white p-4">
          <div className="flex justify-between"><span>상품 금액</span><span>{won(subtotal)}</span></div>
          <div className="flex justify-between"><span>택배비</span><span>{ship.fee === null ? "확인 후 안내" : ship.fee === 0 ? "무료" : won(ship.fee)}</span></div>
          <div className="flex justify-between border-t border-dashed border-line pt-2 text-lg font-extrabold">
            <span>{total !== null ? "합계" : "상품 합계"}</span>
            <span>{won(total ?? subtotal)}</span>
          </div>
          <div className="text-sm text-stone-500">{ship.note}</div>
        </div>
      )}

      <SectionTitle right={member && <span className="text-sm text-stone-500">내 정보로 채웠어요</span>}>받는 분</SectionTitle>
      {!member && (
        <p className="mb-3 rounded-xl bg-brand-soft px-3 py-2 text-sm text-brand-dark">
          가입했다면 <Link to="/shop/my" className="font-bold underline">로그인</Link>하고 주문하면 주소가 자동으로 채워져요.
        </p>
      )}
      <div id="f-name">
        <Field label="성함 *" hint={errors.name && <span className="text-red-700">{errors.name}</span>}>
          <Input value={who.name} autoComplete="name" placeholder="홍길동" onChange={(e) => set({ name: e.target.value })} />
        </Field>
      </div>
      <Field label="상호 (가게·식당이면)" hint="개인이시면 비워 두세요">
        <Input value={who.company} autoComplete="organization" placeholder="예) 바다식당" onChange={(e) => set({ company: e.target.value })} />
      </Field>
      <div id="f-phone">
        <Field label="휴대폰 번호 *" hint={errors.phone ? <span className="text-red-700">{errors.phone}</span> : "주문 확인·배송 안내를 보내 드려요"}>
          <Input value={who.phone} type="tel" inputMode="numeric" autoComplete="tel" placeholder="010-1234-5678" onChange={(e) => set({ phone: formatPhone(e.target.value) })} />
        </Field>
      </div>
      <div id="f-address">
        <AddressField value={who.address} onChange={(a) => set({ address: a })} error={errors.address} />
      </div>

      <SectionTitle>받는 날·요청사항</SectionTitle>
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

      {!member && (
        <>
          <SectionTitle>다음부터 편하게 (선택)</SectionTitle>
          <div id="f-password" className="rounded-2xl bg-white p-4">
            <Field
              label="비밀번호 만들기"
              hint={errors.password ? <span className="text-red-700">{errors.password}</span> : "적으면 주문과 함께 가입돼요. 다음부터 휴대폰 번호 + 비밀번호로 로그인 (4자리 이상)"}
            >
              <Input type="password" autoComplete="new-password" value={password} placeholder="비워 두면 비회원 주문" onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <label className="flex items-center gap-2 text-stone-600">
              <input type="checkbox" className="h-5 w-5 accent-brand" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              이 휴대폰에 받는 분 정보 기억하기
            </label>
          </div>

          <SectionTitle>개인정보 동의</SectionTitle>
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
        </>
      )}

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-paper/95 px-4 pt-3 backdrop-blur">
        <div className="mx-auto max-w-lg">
          <div className="mb-2 flex items-baseline justify-between gap-2 text-sm">
            <span className="font-semibold">
              {picked.length}가지 · {count}개
              {shop.show_prices && <span className="block text-xs font-normal text-stone-500">{ship.note}</span>}
            </span>
            {subtotal !== null && <span className="whitespace-nowrap text-lg font-extrabold">{won(total ?? subtotal)}</span>}
          </div>
          <Button size="xl" block icon={<ShoppingBasket className="h-6 w-6" />} onClick={() => check() && setConfirm(true)}>
            주문하기
          </Button>
        </div>
      </div>

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
            <div className="flex justify-between px-4 py-3 text-lg font-extrabold">
              <span>{total !== null ? "합계 (택배비 포함)" : "상품 합계"}</span>
              <span>{won(total ?? subtotal)}</span>
            </div>
          )}
        </div>
        <dl className="space-y-1 text-[15px]">
          <Row k="받는 분" v={`${who.name}${who.company ? ` (${who.company})` : ""}`} />
          <Row k="휴대폰" v={formatPhone(who.phone)} />
          <Row k="주소" v={`${address}${who.address.zipcode ? ` [${who.address.zipcode}]` : ""}`} />
          <Row k="받는 날" v={due ? dateKo(due) : "가장 빠른 날"} />
          {note.trim() && <Row k="요청사항" v={note.trim()} />}
          {!member && password && <Row k="가입" v="주문과 함께 가입해요" />}
        </dl>
        {subtotal !== null && <p className="mt-3 text-sm text-stone-500">{total !== null ? "입금 확인 후 보내 드려요." : `${ship.note}. 최종 금액은 문자로 알려 드려요.`}</p>}
        {sendError && <div className="mt-3"><Alert tone="error">{sendError}</Alert></div>}
      </Modal>
    </div>
  );
}
