// 마이페이지: 로그인 안 했으면 로그인·가입, 했으면 주문 내역 · 다시 주문 · 내 정보
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronDown, CreditCard, LogOut, MapPin, PenLine, RotateCcw, XCircle } from "lucide-react";
import { apiUrl, errorMessage } from "../../api/client";
import {
  shopCancelOrder,
  shopChangePassword,
  shopKakaoComplete,
  shopLogin,
  shopMe,
  shopMyOrders,
  shopSignup,
  shopUpdateMe,
  shopWriteReview,
} from "../../api/endpoints";
import type { MyOrder } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Alert, Button, Empty, Field, Input, Modal, Segmented, Spinner, Textarea, cx } from "../../components/ui";
import { won } from "../../lib/format";
import { AddressField, PayGuide, PayStatus, STATUS, StarPicker, StatusSteps, joinAddress, trackUrl, type Address } from "./parts";
import { MOBILE_RE, digits, formatPhone, useShop } from "./store";
import { SHOP_HOME, SP } from "../../lib/host";

export default function My() {
  const s = useShop();
  const kakao = useKakaoReturn();
  if (kakao.ticket) return <KakaoComplete ticket={kakao.ticket} nickname={kakao.nickname} onCancel={kakao.clear} />;
  if (!s.auth) return <Auth kakaoError={kakao.error} />;
  return <MyPage />;
}

// ================================================================ 카카오 로그인에서 돌아왔을 때
// 서버가 /shop/my#kt=토큰 (바로 로그인) · #kn=표 (처음 → 이름·번호 입력) · #kerr=이유 로 보내 준다
function useKakaoReturn() {
  const s = useShop();
  const toast = useToast();
  const [state] = useState(() => new URLSearchParams(window.location.hash.replace(/^#/, "")));
  const [ticket, setTicket] = useState(state.get("kn") || "");
  const nickname = state.get("nick") || "";
  const error = state.get("kerr") || "";
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname + window.location.search);
    const token = state.get("kt");
    if (token) {
      shopMe(token)
        .then((profile) => {
          s.signIn({ token, profile });
          toast("카카오로 로그인했어요.");
        })
        .catch((e) => toast(errorMessage(e), "error"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { ticket, nickname, error, clear: () => setTicket("") };
}

function KakaoButton() {
  const s = useShop();
  if (!s.info?.kakao_login) return null;
  return (
    <a
      href={apiUrl("/api/public/shop/auth/kakao/start")}
      className="mb-5 flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-[#FEE500] text-lg font-bold text-[#191600]"
    >
      <svg aria-hidden viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor">
        <path d="M12 3C6.48 3 2 6.58 2 11c0 2.84 1.86 5.33 4.66 6.75l-.95 3.5a.4.4 0 0 0 .6.44l4.1-2.72c.52.06 1.05.1 1.59.1 5.52 0 10-3.58 10-8.07S17.52 3 12 3Z" />
      </svg>
      카카오로 시작하기
    </a>
  );
}

function KakaoComplete({ ticket, nickname, onCancel }: { ticket: string; nickname: string; onCancel: () => void }) {
  const s = useShop();
  const nav = useNavigate();
  const [v, setV] = useState({ name: nickname, phone: "", company: "", password: "" });
  const [agree, setAgree] = useState(false);
  const [needPw, setNeedPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    setErr("");
    if (!v.name.trim()) return setErr("성함을 적어 주세요.");
    if (!MOBILE_RE.test(digits(v.phone))) return setErr("휴대폰 번호를 확인해 주세요 (예: 010-1234-5678).");
    if (!agree) return setErr("개인정보 수집·이용에 동의해 주세요.");
    setBusy(true);
    try {
      s.signIn(await shopKakaoComplete({ ticket, name: v.name.trim(), phone: formatPhone(v.phone), company: v.company.trim(), password: v.password, agree_privacy: true }));
      onCancel();
      nav(`${SP}/my`);
    } catch (e) {
      const msg = errorMessage(e);
      if (msg.includes("비밀번호")) setNeedPw(true);
      setErr(msg);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold">카카오로 가입</h1>
      <p className="mb-4 break-keep text-stone-600">처음 한 번만 성함과 휴대폰 번호를 적어 주세요. 다음부터는 카카오 버튼 하나로 들어와요.</p>
      {err && <Alert tone="error">{err}</Alert>}
      <Field label="성함">
        <Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} />
      </Field>
      <Field label="휴대폰 번호" hint="주문·배송 연락에 써요">
        <Input inputMode="tel" value={v.phone} placeholder="010-1234-5678" onChange={(e) => setV({ ...v, phone: formatPhone(e.target.value) })} />
      </Field>
      <Field label="상호 (가게·식당이면)">
        <Input value={v.company} onChange={(e) => setV({ ...v, company: e.target.value })} />
      </Field>
      {needPw && (
        <Field label="이 번호로 가입할 때 정한 비밀번호" hint="맞으면 원래 계정에 카카오가 연결돼요">
          <Input type="password" value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} />
        </Field>
      )}
      <label className="mb-2 flex items-start gap-2">
        <input type="checkbox" className="mt-1 h-5 w-5" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
        <span className="text-sm">개인정보 수집·이용에 동의해요</span>
      </label>
      {s.info?.privacy_text && <p className="mb-4 whitespace-pre-line text-xs text-stone-500">{s.info.privacy_text}</p>}
      <Button block size="xl" disabled={busy} onClick={submit}>가입하고 시작하기</Button>
      <button type="button" className="mt-3 w-full text-center text-sm text-stone-500 underline" onClick={onCancel}>
        그만두기
      </button>
    </div>
  );
}

// ================================================================ 로그인 · 가입
function Auth({ kakaoError }: { kakaoError: string }) {
  const s = useShop();
  const nav = useNavigate();
  const [tab, setTab] = useState<"login" | "signup">("login");
  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold">{tab === "login" ? "로그인" : "처음이에요 (가입)"}</h1>
      <p className="mb-4 text-stone-600">가입하면 주소를 다시 안 적어도 되고, 지난 주문을 한 번에 다시 할 수 있어요.</p>
      {kakaoError && <Alert tone="error">{kakaoError}</Alert>}
      <KakaoButton />
      {s.info?.kakao_login && <p className="mb-3 text-center text-sm text-stone-500">또는 휴대폰 번호와 비밀번호로</p>}
      <Segmented
        className="mb-5"
        value={tab}
        onChange={setTab}
        options={[
          { value: "login", label: "로그인" },
          { value: "signup", label: "처음이에요" },
        ]}
      />
      {tab === "login" ? <LoginForm onDone={() => nav(`${SP}/my`)} /> : <SignupForm onDone={() => nav(`${SP}/my`)} privacy={s.info?.privacy_text ?? ""} />}
      <p className="mt-6 text-center text-sm text-stone-500">
        가입 없이 주문했다면 <Link to={`${SP}/lookup`} className="font-bold text-brand underline">주문번호로 조회</Link>
        {s.info?.factory_phone && <> · 비밀번호를 잊었으면 {s.info.factory_phone}로 전화 주세요</>}
      </p>
    </div>
  );
}

function LoginForm({ onDone }: { onDone: () => void }) {
  const s = useShop();
  const [phone, setPhone] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => {
    setErr("");
    if (!MOBILE_RE.test(digits(phone))) return setErr("휴대폰 번호를 확인해 주세요.");
    if (!pw) return setErr("비밀번호를 넣어 주세요.");
    setBusy(true);
    try {
      s.signIn(await shopLogin(formatPhone(phone), pw));
      onDone();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={(e: { preventDefault: () => void }) => { e.preventDefault(); void go(); }}>
      <Field label="휴대폰 번호">
        <Input type="tel" inputMode="numeric" autoComplete="tel" value={phone} placeholder="010-1234-5678" onChange={(e) => setPhone(formatPhone(e.target.value))} />
      </Field>
      <Field label="비밀번호">
        <Input type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} />
      </Field>
      {err && <Alert tone="error">{err}</Alert>}
      <Button size="xl" block loading={busy} type="submit">로그인</Button>
    </form>
  );
}

function SignupForm({ onDone, privacy }: { onDone: () => void; privacy: string }) {
  const s = useShop();
  const [v, setV] = useState({ name: "", company: "", phone: "", pw: "", pw2: "" });
  const [addr, setAddr] = useState<Address>({ base: "", detail: "", zipcode: "" });
  const [agree, setAgree] = useState(false);
  const [showPolicy, setShowPolicy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  const go = async () => {
    setErr("");
    if (!v.name.trim()) return setErr("성함을 적어 주세요.");
    if (!MOBILE_RE.test(digits(v.phone))) return setErr("휴대폰 번호를 확인해 주세요.");
    if (v.pw.length < 4) return setErr("비밀번호는 4자리 이상으로 만들어 주세요.");
    if (v.pw !== v.pw2) return setErr("비밀번호 확인이 달라요.");
    if (!agree) return setErr("개인정보 수집·이용에 동의해 주세요.");
    setBusy(true);
    try {
      s.signIn(await shopSignup({
        name: v.name.trim(), company: v.company.trim(), phone: formatPhone(v.phone), password: v.pw,
        address: joinAddress(addr), zipcode: addr.zipcode, agree_privacy: true,
      }));
      onDone();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={(e: { preventDefault: () => void }) => { e.preventDefault(); void go(); }}>
      <Field label="성함 *"><Input autoComplete="name" value={v.name} onChange={(e) => set({ name: e.target.value })} /></Field>
      <Field label="상호 (가게·식당이면)" hint="개인이시면 비워 두세요"><Input value={v.company} onChange={(e) => set({ company: e.target.value })} /></Field>
      <Field label="휴대폰 번호 *" hint="로그인할 때 아이디로 써요">
        <Input type="tel" inputMode="numeric" autoComplete="tel" value={v.phone} placeholder="010-1234-5678" onChange={(e) => set({ phone: formatPhone(e.target.value) })} />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="비밀번호 *" hint="4자리 이상"><Input type="password" autoComplete="new-password" value={v.pw} onChange={(e) => set({ pw: e.target.value })} /></Field>
        <Field label="비밀번호 확인 *"><Input type="password" autoComplete="new-password" value={v.pw2} onChange={(e) => set({ pw2: e.target.value })} /></Field>
      </div>
      <p className="mb-1 text-sm font-semibold text-stone-500">받는 주소 (나중에 적어도 돼요)</p>
      <AddressField value={addr} onChange={setAddr} />
      <div className="mb-4 rounded-2xl border border-line bg-white p-4">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-0.5 h-6 w-6 shrink-0 accent-brand" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          <span className="font-bold">주문·배송을 위한 개인정보 수집·이용에 동의해요 (필수)</span>
        </label>
        <button type="button" className="mt-2 flex items-center gap-1 text-sm font-semibold text-stone-500" onClick={() => setShowPolicy(!showPolicy)}>
          내용 보기 <ChevronDown className={cx("h-4 w-4 transition", showPolicy && "rotate-180")} />
        </button>
        {showPolicy && <p className="mt-2 whitespace-pre-line rounded-xl bg-paper p-3 text-sm text-stone-600">{privacy}</p>}
      </div>
      {err && <Alert tone="error">{err}</Alert>}
      <Button size="xl" block loading={busy} type="submit">가입하고 시작하기</Button>
    </form>
  );
}

// ================================================================ 마이페이지
function MyPage() {
  const s = useShop();
  const nav = useNavigate();
  const [tab, setTab] = useState<"orders" | "info">("orders");
  const p = s.auth!.profile;
  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-3 border-b-2 border-brand pb-3">
        <div className="min-w-0">
          {p.company && <div className="text-sm text-stone-500">{p.company}</div>}
          <div className="truncate text-2xl font-bold text-ink">{p.name}님</div>
          <div className="text-sm text-stone-500">{p.phone}</div>
        </div>
        <Button size="sm" variant="ghost" className="shrink-0" icon={<LogOut className="h-4 w-4" />} onClick={() => { s.signOut(); nav(SHOP_HOME); }}>
          로그아웃
        </Button>
      </div>
      <Segmented
        className="mb-4"
        value={tab}
        onChange={setTab}
        options={[
          { value: "orders", label: "주문 내역" },
          { value: "info", label: "내 정보" },
        ]}
      />
      {tab === "orders" ? <Orders /> : <Info />}
    </div>
  );
}

type OrderFilter = "all" | "unpaid" | "preparing" | "sent" | "review" | "canceled";
/** 주문 목록 위 상태 칩 (쿠팡 주문목록의 '배송 중·배송 완료' 거르기와 같은 역할) */
const FILTERS: { value: OrderFilter; label: string; test: (o: MyOrder) => boolean }[] = [
  { value: "all", label: "전체", test: () => true },
  { value: "unpaid", label: "입금 전", test: (o) => !o.paid && o.status !== "취소" },
  { value: "preparing", label: "준비 중", test: (o) => o.paid && (o.status === "접수" || o.status === "출고대기") },
  { value: "sent", label: "보냄", test: (o) => o.status === "출고완료" },
  { value: "review", label: "후기 쓸 주문", test: (o) => o.reviewable.length > 0 },
  { value: "canceled", label: "취소", test: (o) => o.status === "취소" },
];

function Orders() {
  const s = useShop();
  const nav = useNavigate();
  const toast = useToast();
  const [list, setList] = useState<MyOrder[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    shopMyOrders(s.auth!.token)
      .then(setList)
      .catch((e: { status?: number }) => {
        if (e?.status === 401) s.signOut();
        else setErr(errorMessage(e));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [reviewing, setReviewing] = useState<{ order: MyOrder; sku: string; name: string } | null>(null);
  const [filter, setFilter] = useState<OrderFilter>("all");
  const reload = () => shopMyOrders(s.auth!.token).then(setList).catch(() => undefined);
  const cancel = async (o: MyOrder) => {
    if (!window.confirm(`주문 ${o.order_id}을(를) 취소할까요?${o.paid ? " 카드 결제는 자동으로 환불돼요." : ""}`)) return;
    try {
      await shopCancelOrder(o.order_id, { token: s.auth!.token });
      toast("주문을 취소했어요.");
      void reload();
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  const reorder = (o: MyOrder) => {
    const n = s.addMany(o.lines.map((l) => ({ sku: l.sku, qty: l.qty })));
    if (!n) return toast("지금은 주문할 수 없는 품목이에요 (품절이거나 판매 중지).", "error");
    toast(n < o.lines.length ? `${n}가지를 담았어요. 품절된 품목은 뺐어요.` : "장바구니에 담았어요.");
    nav(`${SP}/cart`);
  };

  if (err) return <Alert tone="error">{err}</Alert>;
  if (!list) return <Spinner />;
  if (!list.length)
    return (
      <Empty>
        아직 주문이 없어요.
        <div className="mt-3"><Link to={SHOP_HOME}><Button>상품 보러 가기</Button></Link></div>
      </Empty>
    );
  const counts = Object.fromEntries(FILTERS.map((f) => [f.value, list.filter(f.test).length]));
  const shown = list.filter(FILTERS.find((f) => f.value === filter)?.test ?? (() => true));
  return (
    <div className="space-y-3">
      <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="주문 상태로 보기">
        {FILTERS.filter((f) => f.value === "all" || counts[f.value] > 0).map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={filter === f.value}
            onClick={() => setFilter(f.value)}
            className={cx(
              "shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-bold",
              filter === f.value ? "border-brand bg-brand text-white" : "border-line bg-white text-stone-600",
            )}
          >
            {f.label} <span className={filter === f.value ? "text-white/80" : "text-stone-400"}>{counts[f.value]}</span>
          </button>
        ))}
      </div>
      {shown.length === 0 && <Empty>이 상태의 주문은 없어요.</Empty>}
      {shown.map((o) => {
        const st = STATUS[o.status] ?? { label: o.status, tone: "violet" as const, step: 1 };
        return (
          <div key={o.order_id} className={cx("rounded-lg border bg-white p-4", !o.paid && o.status !== "취소" ? "border-red-200" : "border-line")}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className={cx("text-lg font-extrabold", o.status === "취소" ? "text-stone-400" : "text-brand-dark")}>{st.label}</span>
              <PayStatus paid={o.paid} status={o.status} />
            </div>
            <div className="mt-0.5 text-sm text-stone-500">
              주문 {o.created_at} · 받는 날 {o.due_date} · {o.order_id}
            </div>
            {o.status !== "취소" && <div className="mt-3"><StatusSteps status={o.status} paid={o.paid} /></div>}
            <ul className="mt-3 space-y-0.5">
              {o.lines.map((l) => (
                <li key={l.sku + l.name} className="flex justify-between gap-2">
                  <span>{l.name}</span>
                  <span className="whitespace-nowrap font-semibold">{l.qty}개{l.amount !== null && <span className="ml-2 font-normal text-stone-500">{won(l.amount)}</span>}</span>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-dashed border-line pt-2">
              <span className="text-sm text-stone-500">
                {o.recipient !== s.auth!.profile.name && `받는 분 ${o.recipient} · `}
                {o.ship_method}
                {o.shipping_fee > 0 && ` · 택배비 ${won(o.shipping_fee)}`}
              </span>
              {o.total !== null && <b>합계 {won(o.total)}</b>}
            </div>
            {!o.paid && o.status !== "취소" && (
              <div className="mt-3 space-y-2">
                {s.info?.pay_client_key && o.total !== null && (
                  <Link to={`${SP}/pay/${encodeURIComponent(o.order_id)}`} className="block">
                    <Button block size="lg" icon={<CreditCard className="h-5 w-5" />}>카드·간편결제로 {won(o.total)} 결제하기</Button>
                  </Link>
                )}
                <PayGuide amount={o.total} account={s.info?.bank_account ?? ""} />
              </div>
            )}
            {o.reviewable.length > 0 && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                <div className="mb-2 text-sm font-bold text-amber-900">받아 보신 상품은 어떠셨어요?</div>
                <div className="flex flex-wrap gap-2">
                  {o.lines
                    .filter((l) => o.reviewable.includes(l.sku))
                    .map((l) => (
                      <Button key={l.sku} size="sm" variant="ghost" icon={<PenLine className="h-4 w-4" />} onClick={() => setReviewing({ order: o, sku: l.sku, name: l.name })}>
                        {l.name} 후기 쓰기
                      </Button>
                    ))}
                </div>
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="soft" icon={<RotateCcw className="h-4 w-4" />} onClick={() => reorder(o)}>다시 주문하기</Button>
              {o.can_cancel && (
                <Button size="sm" variant="ghost" icon={<XCircle className="h-4 w-4" />} onClick={() => cancel(o)}>주문 취소</Button>
              )}
              {o.tracking_no && (
                <a href={trackUrl(o.carrier, o.tracking_no)} target="_blank" rel="noreferrer">
                  <Button size="sm" variant="ghost" icon={<MapPin className="h-4 w-4" />}>배송 위치 ({o.carrier})</Button>
                </a>
              )}
            </div>
            {o.cancel_note && !o.can_cancel && <p className="mt-2 break-keep text-sm text-stone-500">{o.cancel_note}</p>}
          </div>
        );
      })}
      {reviewing && (
        <ReviewModal
          {...reviewing}
          onClose={() => setReviewing(null)}
          onDone={() => {
            setReviewing(null);
            toast("후기 고마워요! 다른 손님들께 큰 도움이 돼요.");
            void reload();
          }}
        />
      )}
    </div>
  );
}

function ReviewModal({ order, sku, name, onClose, onDone }: { order: MyOrder; sku: string; name: string; onClose: () => void; onDone: () => void }) {
  const s = useShop();
  const [rating, setRating] = useState(5);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const send = async () => {
    setBusy(true);
    setErr("");
    try {
      await shopWriteReview(s.auth!.token, { order_id: order.order_id, sku, rating, text: text.trim() });
      onDone();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title={`${name} 후기`}
      footer={<Button block size="lg" disabled={busy} onClick={send}>후기 남기기</Button>}
    >
      {err && <Alert tone="error">{err}</Alert>}
      <Field label="별점">
        <StarPicker value={rating} onChange={setRating} />
      </Field>
      <Field label="한 줄 후기 (선택)" hint={`${text.length}/300`}>
        <Textarea value={text} maxLength={300} placeholder="감칠맛이 진하고 비린내가 없어요" onChange={(e) => setText(e.target.value)} className="min-h-[96px]" />
      </Field>
      <p className="text-sm text-stone-500">이름은 가운데 글자를 가려서 보여 드려요.</p>
    </Modal>
  );
}

function Info() {
  const s = useShop();
  const toast = useToast();
  const p = s.auth!.profile;
  const [v, setV] = useState({ name: p.name, company: p.company });
  const [addr, setAddr] = useState<Address>({ base: p.address, detail: "", zipcode: p.zipcode });
  const [pw, setPw] = useState({ old: "", next: "", next2: "" });
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [pwErr, setPwErr] = useState("");

  const save = async () => {
    setErr("");
    if (!v.name.trim()) return setErr("성함을 적어 주세요.");
    setBusy("info");
    try {
      s.setProfile(await shopUpdateMe(s.auth!.token, { name: v.name.trim(), company: v.company.trim(), address: joinAddress(addr), zipcode: addr.zipcode }));
      setAddr((a) => ({ ...a, base: joinAddress(a), detail: "" }));
      toast("저장했어요. 다음 주문부터 이 주소로 채워져요.");
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy("");
    }
  };
  const changePw = async () => {
    setPwErr("");
    if (pw.next.length < 4) return setPwErr("새 비밀번호는 4자리 이상으로 만들어 주세요.");
    if (pw.next !== pw.next2) return setPwErr("새 비밀번호 확인이 달라요.");
    setBusy("pw");
    try {
      s.signIn(await shopChangePassword(s.auth!.token, pw.old, pw.next));
      setPw({ old: "", next: "", next2: "" });
      toast("비밀번호를 바꿨어요.");
    } catch (e) {
      setPwErr(errorMessage(e));
    } finally {
      setBusy("");
    }
  };

  return (
    <div>
      <div className="rounded-2xl bg-white p-4">
        <h2 className="mb-3 text-lg font-extrabold">기본 정보·배송지</h2>
        <Field label="성함"><Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} /></Field>
        {p.company && <Field label="상호"><Input value={v.company} onChange={(e) => setV({ ...v, company: e.target.value })} /></Field>}
        <Field label="휴대폰 번호" hint="번호를 바꾸려면 공장으로 전화 주세요"><Input value={p.phone} disabled /></Field>
        <AddressField value={addr} onChange={setAddr} />
        {err && <Alert tone="error">{err}</Alert>}
        <Button block loading={busy === "info"} onClick={save}>저장</Button>
      </div>
      <div className="mt-4 rounded-2xl bg-white p-4">
        <h2 className="mb-3 text-lg font-extrabold">비밀번호 바꾸기</h2>
        <Field label="지금 비밀번호" hint="카카오로 가입했으면 비워 두고 새 비밀번호만 넣으세요"><Input type="password" autoComplete="current-password" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="새 비밀번호"><Input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></Field>
          <Field label="새 비밀번호 확인"><Input type="password" autoComplete="new-password" value={pw.next2} onChange={(e) => setPw({ ...pw, next2: e.target.value })} /></Field>
        </div>
        {pwErr && <Alert tone="error">{pwErr}</Alert>}
        <Button block variant="ghost" loading={busy === "pw"} disabled={!pw.next} onClick={changePw}>비밀번호 바꾸기</Button>
      </div>
    </div>
  );
}
