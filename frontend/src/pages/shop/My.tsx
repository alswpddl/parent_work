// 마이페이지: 로그인 안 했으면 로그인·가입, 했으면 주문 내역 · 다시 주문 · 내 정보
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronDown, LogOut, MapPin, RotateCcw } from "lucide-react";
import { errorMessage } from "../../api/client";
import { shopChangePassword, shopLogin, shopMyOrders, shopSignup, shopUpdateMe } from "../../api/endpoints";
import type { MyOrder } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Alert, Badge, Button, Empty, Field, Input, Segmented, Spinner, cx } from "../../components/ui";
import { won } from "../../lib/format";
import { AddressField, STATUS, StatusSteps, joinAddress, trackUrl, type Address } from "./parts";
import { MOBILE_RE, digits, formatPhone, useShop } from "./store";

export default function My() {
  const s = useShop();
  if (!s.auth) return <Auth />;
  return <MyPage />;
}

// ================================================================ 로그인 · 가입
function Auth() {
  const s = useShop();
  const nav = useNavigate();
  const [tab, setTab] = useState<"login" | "signup">("login");
  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold">{tab === "login" ? "로그인" : "처음이에요 (가입)"}</h1>
      <p className="mb-4 text-stone-600">휴대폰 번호와 비밀번호로 들어와요. 가입하면 주소를 다시 안 적어도 되고, 지난 주문을 한 번에 다시 할 수 있어요.</p>
      <Segmented
        className="mb-5"
        value={tab}
        onChange={setTab}
        options={[
          { value: "login", label: "로그인" },
          { value: "signup", label: "처음이에요" },
        ]}
      />
      {tab === "login" ? <LoginForm onDone={() => nav("/shop/my")} /> : <SignupForm onDone={() => nav("/shop/my")} privacy={s.info?.privacy_text ?? ""} />}
      <p className="mt-6 text-center text-sm text-stone-500">
        가입 없이 주문했다면 <Link to="/shop/lookup" className="font-bold text-brand underline">주문번호로 조회</Link>
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
      <div className="mb-4 rounded-2xl border-2 border-line bg-white p-4">
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
          <div className="truncate font-serif text-2xl font-bold text-brand-dark">{p.name}님</div>
          <div className="text-sm text-stone-500">{p.phone}</div>
        </div>
        <Button size="sm" variant="ghost" className="shrink-0" icon={<LogOut className="h-4 w-4" />} onClick={() => { s.signOut(); nav("/shop"); }}>
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

  const reorder = (o: MyOrder) => {
    const n = s.addMany(o.lines.map((l) => ({ sku: l.sku, qty: l.qty })));
    if (!n) return toast("지금은 주문할 수 없는 품목이에요 (품절이거나 판매 중지).", "error");
    toast(n < o.lines.length ? `${n}가지를 담았어요. 품절된 품목은 뺐어요.` : "장바구니에 담았어요.");
    nav("/shop/cart");
  };

  if (err) return <Alert tone="error">{err}</Alert>;
  if (!list) return <Spinner />;
  if (!list.length)
    return (
      <Empty>
        아직 주문이 없어요.
        <div className="mt-3"><Link to="/shop"><Button>상품 보러 가기</Button></Link></div>
      </Empty>
    );
  return (
    <div className="space-y-3">
      {list.map((o) => {
        const st = STATUS[o.status] ?? { label: o.status, tone: "violet" as const, step: 1 };
        return (
          <div key={o.order_id} className="rounded-2xl border border-line bg-white p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm text-stone-500">{o.created_at} · {o.order_id}</div>
                <div className="font-extrabold">받는 날 {o.due_date}</div>
              </div>
              <Badge tone={st.tone}>{st.label}</Badge>
            </div>
            {o.status !== "취소" && <div className="mt-3"><StatusSteps status={o.status} /></div>}
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
              {o.total !== null && <b>{won(o.total)}</b>}
            </div>
            {o.status !== "취소" && (
              <div className="mt-1 text-sm">{o.paid ? <span className="text-brand-dark">입금 확인됐어요</span> : <span className="text-amber-700">입금 확인 전이에요</span>}</div>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="soft" icon={<RotateCcw className="h-4 w-4" />} onClick={() => reorder(o)}>다시 주문하기</Button>
              {o.tracking_no && (
                <a href={trackUrl(o.carrier, o.tracking_no)} target="_blank" rel="noreferrer">
                  <Button size="sm" variant="ghost" icon={<MapPin className="h-4 w-4" />}>배송 위치 ({o.carrier})</Button>
                </a>
              )}
            </div>
          </div>
        );
      })}
    </div>
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
        <Field label="지금 비밀번호"><Input type="password" autoComplete="current-password" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="새 비밀번호"><Input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></Field>
          <Field label="새 비밀번호 확인"><Input type="password" autoComplete="new-password" value={pw.next2} onChange={(e) => setPw({ ...pw, next2: e.target.value })} /></Field>
        </div>
        {pwErr && <Alert tone="error">{pwErr}</Alert>}
        <Button block variant="ghost" loading={busy === "pw"} disabled={!pw.old || !pw.next} onClick={changePw}>비밀번호 바꾸기</Button>
      </div>
    </div>
  );
}
