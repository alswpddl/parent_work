// 웹 주문서 (/shop) — 손님용 작은 온라인 가게
//   /shop              홈 (공장 소개 · 이용 안내 · 상품)
//   /shop/item/:이름    상품 (규격별 수량 고르기)
//   /shop/cart         장바구니 · 주문하기
//   /shop/done         주문 완료
//   /shop/my           마이페이지 (로그인 안 했으면 로그인·가입)
//   /shop/lookup       비회원 주문 조회
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { CheckCircle2, ChevronLeft, Home as HomeIcon, MapPin, Package, Phone, Search, ShoppingBasket, User } from "lucide-react";
import { errorMessage } from "../../api/client";
import { shopLookup, shopMe } from "../../api/endpoints";
import type { PublicOrder } from "../../api/types";
import { Alert, Badge, Button, CopyButton, Field, Input, Spinner, Stepper, cx } from "../../components/ui";
import { dateKo, telHref, won } from "../../lib/format";
import Cart from "./Cart";
import My from "./My";
import { LabelTable, ProductArt, Row, STATUS, SectionTitle, StatusSteps, trackUrl } from "./parts";
import { LAST_KEY, ShopProvider, digits, groupProducts, itemPath, store, useShop, type ProductGroup } from "./store";

export default function ShopApp() {
  return (
    <ShopProvider>
      <Shell />
    </ShopProvider>
  );
}

type Page = { name: "home" } | { name: "item"; item: string } | { name: "cart" } | { name: "done" } | { name: "my" } | { name: "lookup" };

function route(pathname: string, search: string): Page {
  const p = pathname.replace(/\/+$/, "");
  const m = /^\/shop\/item\/(.+)$/.exec(p);
  if (m) return { name: "item", item: decodeURIComponent(m[1]) };
  if (p === "/shop/cart") return { name: "cart" };
  if (p === "/shop/done") return { name: "done" };
  if (p === "/shop/my" || p === "/shop/login") return { name: "my" };
  if (p === "/shop/lookup" || new URLSearchParams(search).get("tab") === "lookup") return { name: "lookup" };
  return { name: "home" };
}

function Shell() {
  const s = useShop();
  const loc = useLocation();
  const page = route(loc.pathname, loc.search);

  useEffect(() => {
    if (s.info) document.title = `${s.info.factory_name} 주문서`;
  }, [s.info]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [loc.pathname]);

  if (s.infoLoading && !s.info) return <Spinner label="주문서를 여는 중… (처음엔 1분쯤 걸릴 수 있어요)" />;
  if (!s.info)
    return (
      <div className="mx-auto max-w-md p-6">
        <Alert tone="error">{s.infoError || "주문서를 열지 못했어요."}</Alert>
        <Button block onClick={s.reloadInfo}>다시 열기</Button>
      </div>
    );

  const showTabs = page.name !== "cart" && page.name !== "item";
  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-30 bg-brand text-white">
        <div className="mx-auto flex h-14 max-w-lg items-center justify-between gap-2 px-4">
          <Link to="/shop" className="min-w-0 truncate font-serif text-xl font-bold">
            {s.info.factory_name}
          </Link>
          <div className="flex items-center gap-1">
            <Link to="/shop/my" className="flex h-10 items-center gap-1 rounded px-3 text-sm font-bold text-white/90 hover:bg-white/10" aria-label="마이페이지">
              <User className="h-5 w-5" />
              {s.auth ? <span className="max-w-[5rem] truncate">{s.auth.profile.name}님</span> : "로그인"}
            </Link>
            <Link to="/shop/cart" className="relative flex h-10 w-10 items-center justify-center rounded hover:bg-white/10" aria-label="장바구니">
              <ShoppingBasket className="h-6 w-6" />
              {s.cartCount > 0 && (
                <span className="absolute -right-0.5 -top-0.5 min-w-[1.25rem] rounded-full bg-brine px-1 text-center text-xs font-bold leading-5 text-white">{s.cartCount}</span>
              )}
            </Link>
          </div>
        </div>
      </header>

      <main className={cx("mx-auto max-w-lg px-4 pt-4", showTabs ? "pb-28" : "pb-40")}>
        {page.name === "home" && <Home />}
        {page.name === "item" && <Item name={page.item} />}
        {page.name === "cart" && <Cart />}
        {page.name === "done" && <Done />}
        {page.name === "my" && <My />}
        {page.name === "lookup" && <Lookup />}
        <footer className="mt-12 border-t border-line pt-4 text-xs leading-relaxed text-stone-500">
          <div className="font-serif text-sm font-bold text-stone-600">{s.info.factory_name}</div>
          {s.info.factory_phone && <div>전화 {s.info.factory_phone}{s.info.contact_hours && ` (${s.info.contact_hours})`}</div>}
        </footer>
      </main>

      {showTabs && <TabBar active={page.name} />}
    </div>
  );
}

function TabBar({ active }: { active: Page["name"] }) {
  const s = useShop();
  const tab = (to: string, on: boolean, icon: ReactNode, label: string, badge?: number) => (
    <Link to={to} className={cx("relative flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-bold", on ? "text-brand" : "text-stone-500")}>
      {icon}
      {label}
      {!!badge && <span className="absolute right-1/4 top-1 min-w-[1.1rem] rounded-full bg-brine px-1 text-center text-[11px] leading-[1.1rem] text-white">{badge}</span>}
    </Link>
  );
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-lg">
        {tab("/shop", active === "home", <HomeIcon className="h-6 w-6" />, "홈")}
        {tab("/shop/cart", false, <ShoppingBasket className="h-6 w-6" />, "장바구니", s.cartCount)}
        {s.auth
          ? tab("/shop/my", active === "my", <User className="h-6 w-6" />, "마이페이지")
          : tab("/shop/lookup", active === "lookup", <Search className="h-6 w-6" />, "주문 조회")}
        {s.info?.factory_phone ? (
          <a href={telHref(s.info.factory_phone)} className="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-bold text-stone-500">
            <Phone className="h-6 w-6" />
            전화 주문
          </a>
        ) : (
          tab("/shop/my", active === "my", <User className="h-6 w-6" />, "로그인")
        )}
      </div>
    </nav>
  );
}

// ================================================================ 홈
function Home() {
  const s = useShop();
  const info = s.info!;
  const groups = useMemo(() => groupProducts(s.products), [s.products]);
  const shipText =
    info.shipping_fee > 0
      ? `${won(info.shipping_fee)}${info.free_shipping_over > 0 ? ` · ${won(info.free_shipping_over)} 이상 무료` : ""}`
      : info.free_shipping_over > 0
        ? `${won(info.free_shipping_over)} 이상 무료`
        : "주문 확인 후 안내";

  const hasPrice = (g: ProductGroup) => g.variants.some((v) => v.price !== null);
  const specRows = (g: ProductGroup) => (
    <ul>
      {g.variants.map((v) => (
        <li key={v.sku} className="flex justify-between gap-3">
          <span>{v.spec || v.unit}</span>
          {hasPrice(g) && <span className={cx("font-bold", v.sold_out ? "text-stone-400 line-through" : "text-brine")}>{v.price !== null ? won(v.price) : "문의"}</span>}
        </li>
      ))}
    </ul>
  );

  return (
    <div>
      <section className="pb-6 pt-3">
        {s.auth && <p className="mb-2 text-sm text-stone-600">{s.auth.profile.name}님, 다시 오셨네요.</p>}
        <p className="whitespace-pre-line break-keep font-serif text-[1.6rem] font-bold leading-snug text-brand-dark">
          {info.intro || "정성껏 담근 젓갈을\n공장에서 바로 보내 드려요."}
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <a href="#products">
            <Button size="md">상품 보기</Button>
          </a>
          <Link to="/shop/my">
            <Button size="md" variant="ghost">{s.auth ? "지난 주문 보기" : "로그인·가입"}</Button>
          </Link>
        </div>
      </section>

      {info.notice && <p className="mb-4 whitespace-pre-line break-keep border-l-4 border-brine bg-brine-soft px-4 py-3">{info.notice}</p>}

      <dl className="divide-y divide-line rounded-lg border border-line bg-white text-[15px]">
        <InfoRow k="택배비" v={shipText} />
        <InfoRow k="받는 날" v={`${dateKo(info.min_due_date)}부터${new Set(info.products.map((p) => p.lead_days)).size > 1 ? " (품목마다 달라요)" : ""}${info.closed_days_text ? `, ${info.closed_days_text}요일 제외` : ""}`} />
        <InfoRow k="결제" v="계좌 입금 (주문 후 안내)" />
        <InfoRow
          k="문의"
          v={info.factory_phone ? <a href={telHref(info.factory_phone)} className="font-bold text-brand underline underline-offset-2">{info.factory_phone}</a> : "-"}
          sub={info.contact_hours}
        />
      </dl>

      <div id="products" className="scroll-mt-16" />
      <SectionTitle>상품</SectionTitle>
      {groups.length === 0 && <Alert tone="info">지금은 주문할 수 있는 상품이 없어요. 전화로 문의해 주세요.</Alert>}
      <div className="space-y-4">
        {groups.map((g) => (
          <article key={g.name} className={cx("overflow-hidden rounded-lg border border-line bg-white", g.soldOut && "opacity-70")}>
            {g.image_url && (
              <div className="aspect-[16/9]">
                <ProductArt name={g.name} image={g.image_url} />
              </div>
            )}
            <div className="flex items-baseline justify-between gap-2 border-b-2 border-brand px-4 pb-2 pt-3">
              <h3 className="font-serif text-2xl font-bold text-brand-dark">{g.name}</h3>
              {g.soldOut && <Badge tone="red">품절</Badge>}
            </div>
            <LabelTable
              rows={[
                [hasPrice(g) ? "규격·가격" : "규격", specRows(g)],
                ...(hasPrice(g) ? [] : ([["가격", "주문 확인 후 안내해 드려요"]] as [string, string][])),
                ["소개", g.description],
              ]}
            />
            {!g.soldOut && (
              <div className="border-t border-line p-3">
                <Link to={itemPath(g.name)}>
                  <Button block size="md">규격·수량 고르기</Button>
                </Link>
              </div>
            )}
          </article>
        ))}
      </div>

      <SectionTitle>주문 순서</SectionTitle>
      <ol className="divide-y divide-line rounded-lg border border-line bg-white">
        {["상품을 골라 장바구니에 담아요", "받는 분·주소·받을 날을 적고 주문해요", "안내된 계좌로 입금해요", "입금을 확인하면 포장해서 보내 드려요"].map((text, i) => (
          <li key={text} className="flex gap-3 px-4 py-3">
            <span className="w-4 shrink-0 font-bold text-brand">{i + 1}</span>
            <span className="break-keep">{text}</span>
          </li>
        ))}
      </ol>
      {!s.auth && (
        <p className="mt-4 break-keep text-sm text-stone-600">
          가입하면 주소를 다시 적지 않아도 되고, 지난 주문을 그대로 다시 할 수 있어요.{" "}
          <Link to="/shop/my" className="font-bold text-brand underline underline-offset-2">가입하기</Link>
        </p>
      )}
    </div>
  );
}

function InfoRow({ k, v, sub }: { k: string; v: ReactNode; sub?: string }) {
  return (
    <div className="flex gap-3 px-4 py-2.5">
      <dt className="w-16 shrink-0 text-stone-500">{k}</dt>
      <dd className="min-w-0 break-keep font-semibold">
        {v}
        {sub && <div className="text-sm font-normal text-stone-500">{sub}</div>}
      </dd>
    </div>
  );
}

// ================================================================ 상품
function Item({ name }: { name: string }) {
  const s = useShop();
  const nav = useNavigate();
  const g = useMemo(() => groupProducts(s.products).find((x) => x.name === name), [s.products, name]);
  const [pick, setPick] = useState<Record<string, number>>({});
  const [added, setAdded] = useState(false);
  useEffect(() => {
    // 규격이 하나면 1개로 시작
    if (g && g.variants.length === 1 && !g.variants[0].sold_out) setPick({ [g.variants[0].sku]: 1 });
  }, [g]);

  if (!g)
    return (
      <div className="py-10 text-center">
        <p className="mb-4 text-stone-600">상품을 찾지 못했어요.</p>
        <Link to="/shop"><Button>홈으로</Button></Link>
      </div>
    );

  const count = Object.values(pick).reduce((a, b) => a + b, 0);
  const sum = g.variants.reduce((a, v) => a + (pick[v.sku] ?? 0) * (v.price ?? 0), 0);
  const hasPrice = g.variants.some((v) => v.price !== null);

  return (
    <div>
      <button onClick={() => (window.history.length > 1 ? window.history.back() : nav("/shop"))} className="mb-2 flex items-center gap-1 font-semibold text-stone-600">
        <ChevronLeft className="h-5 w-5" /> 뒤로
      </button>
      {g.image_url ? (
        <div className="relative mb-4 aspect-[4/3] overflow-hidden rounded-lg border border-line">
          <ProductArt name={g.name} image={g.image_url} big />
        </div>
      ) : null}
      <h1 className="border-b-2 border-brand pb-2 font-serif text-3xl font-bold text-brand-dark">{g.name}</h1>
      {g.description && <p className="mt-3 break-keep text-lg text-stone-700">{g.description}</p>}

      <SectionTitle>규격·수량 고르기</SectionTitle>
      <div className="space-y-3">
        {g.variants.map((v) => {
          const q = pick[v.sku] ?? 0;
          const inCart = s.cart[v.sku] ?? 0;
          return (
            <div key={v.sku} className={cx("rounded-2xl border-2 bg-white p-4", v.sold_out ? "border-line opacity-60" : q ? "border-brand" : "border-line")}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xl font-extrabold">{v.spec || v.unit}</div>
                  {v.price !== null && <div className="font-bold text-brine">{won(v.price)} <span className="text-sm font-normal text-stone-500">/ 1{v.unit}</span></div>}
                  {!v.sold_out && v.lead_days > 0 && <div className="text-sm text-stone-500">주문하고 {v.lead_days}일 뒤부터 받아요</div>}
                  {inCart > 0 && <div className="text-sm text-stone-500">장바구니에 {inCart}{v.unit} 있어요</div>}
                </div>
                {v.sold_out && <Badge tone="red">품절</Badge>}
              </div>
              {!v.sold_out && (
                <div className="mt-3 flex items-center justify-between gap-3">
                  <span className="text-sm text-stone-500">{q > 0 && v.price !== null ? won(q * v.price) : `단위: ${v.unit}`}</span>
                  <Stepper value={q} onChange={(x) => { setPick({ ...pick, [v.sku]: x }); setAdded(false); }} max={999} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-paper/95 px-4 pt-3 backdrop-blur">
        <div className="mx-auto max-w-lg">
          {added ? (
            <div className="grid grid-cols-2 gap-2">
              <Link to="/shop"><Button block variant="ghost">계속 둘러보기</Button></Link>
              <Link to="/shop/cart"><Button block icon={<ShoppingBasket className="h-5 w-5" />}>장바구니 보기</Button></Link>
            </div>
          ) : (
            <Button
              size="xl"
              block
              disabled={!count}
              icon={<ShoppingBasket className="h-6 w-6" />}
              onClick={() => {
                s.addMany(Object.entries(pick).map(([sku, qty]) => ({ sku, qty })));
                setPick({});
                setAdded(true);
              }}
            >
              {count ? `장바구니 담기 · ${count}개${hasPrice ? ` ${won(sum)}` : ""}` : "수량을 골라 주세요"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ================================================================ 주문 완료
function Done() {
  const s = useShop();
  const r = s.lastResult;
  const [joined, setJoined] = useState(false);
  useEffect(() => {
    // 주문하면서 가입했으면 바로 로그인 상태로
    if (r?.token && !s.auth) {
      shopMe(r.token)
        .then((profile) => {
          s.signIn({ token: r.token, profile });
          setJoined(true);
        })
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [r?.token]);

  if (!r)
    return (
      <div className="py-10 text-center">
        <Link to="/shop"><Button>홈으로</Button></Link>
      </div>
    );
  return (
    <div>
      <div className="mb-5 rounded-3xl bg-brand p-6 text-center text-white">
        <CheckCircle2 className="mx-auto mb-2 h-14 w-14" />
        <div className="text-2xl font-extrabold">주문이 들어갔어요!</div>
        <div className="mt-1 opacity-90">확인하고 연락드릴게요. 감사합니다 🙏</div>
      </div>
      {joined && <Alert tone="ok">가입도 끝났어요. 다음부터는 휴대폰 번호와 비밀번호로 로그인하면 돼요.</Alert>}

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
        {s.auth ? (
          <Link to="/shop/my"><Button block variant="ghost" icon={<Package className="h-5 w-5" />}>내 주문 보기</Button></Link>
        ) : (
          <Link to="/shop/lookup"><Button block variant="ghost" icon={<Package className="h-5 w-5" />}>주문 조회</Button></Link>
        )}
        <Link to="/shop"><Button block variant="soft">홈으로</Button></Link>
      </div>
      {r.factory_phone && (
        <a href={telHref(r.factory_phone)} className="mt-3 flex items-center justify-center gap-2 py-3 font-bold text-stone-600">
          <Phone className="h-4 w-4" /> 바꾸실 게 있으면 {r.factory_phone}
        </a>
      )}
    </div>
  );
}

// ================================================================ 비회원 주문 조회
function Lookup() {
  const s = useShop();
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
  const st = r ? STATUS[r.status] ?? { label: r.status, tone: "violet" as const, step: 1 } : null;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold">주문 조회</h1>
      <p className="mb-4 text-stone-600">
        {s.auth ? (
          <>가입하셨으면 <Link to="/shop/my" className="font-bold text-brand underline">마이페이지</Link>에서 모든 주문을 볼 수 있어요.</>
        ) : (
          <>비회원 주문은 주문번호로 찾아요. 가입하면 <Link to="/shop/my" className="font-bold text-brand underline">마이페이지</Link>에서 한 번에 볼 수 있어요.</>
        )}
      </p>
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
          <div className="mb-4"><StatusSteps status={r.status} /></div>
          <dl className="space-y-1">
            <Row k="주문일" v={r.created_at} />
            <Row k="품목" v={r.items} />
            <Row k="받는 날" v={r.due_date === "날짜 미정" ? "정해지면 알려 드려요" : r.due_date} />
            <Row k="보내는 방법" v={r.ship_method} />
            <Row k="입금" v={r.paid ? "확인됐어요" : "확인 전이에요"} />
            {r.tracking_no && <Row k="송장" v={`${r.carrier} ${r.tracking_no}`} />}
            {r.truck_no && <Row k="화물차" v={r.truck_no} />}
          </dl>
          {r.tracking_no && (
            <a className="mt-4 flex items-center justify-center gap-2 rounded-xl2 bg-parcel px-4 py-3 font-bold text-white" href={trackUrl(r.carrier, r.tracking_no)} target="_blank" rel="noreferrer">
              <MapPin className="h-5 w-5" /> 배송 위치 보기
            </a>
          )}
        </div>
      )}
    </div>
  );
}
