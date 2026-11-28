// 웹 주문서 (/shop) — 손님용 작은 온라인 가게
//   /shop              홈 (공장 소개 · 이용 안내 · 상품)
//   /shop/item/:이름    상품 (규격별 수량 고르기)
//   /shop/cart         장바구니 · 주문하기
//   /shop/done         주문 완료
//   /shop/my           마이페이지 (로그인 안 했으면 로그인·가입)
//   /shop/lookup       비회원 주문 조회
//   /shop/pay/…        온라인 결제 (토스페이먼츠) — Pay.tsx
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CreditCard, Home as HomeIcon, MapPin, Package, Phone, RotateCcw, Search, ShoppingBasket, Truck, User } from "lucide-react";
import { errorMessage } from "../../api/client";
import { shopCancelOrder, shopGuestCode, shopGuestOrders, shopLookup, shopMe, shopMyOrders, shopReviews } from "../../api/endpoints";
import type { MyOrder, PublicOrder, ShopInfo, ShopReviewList } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Alert, Badge, Button, CopyButton, Field, Input, Stepper, cx } from "../../components/ui";
import { dateKo, telHref, won } from "../../lib/format";
import Cart from "./Cart";
import { POLICY_TITLE, PolicyBody, type PolicyKind } from "./Policy";
import My from "./My";
import { Pay, PayFail, PaySuccess } from "./Pay";
import { BackToTop, LabelTable, PayGuide, PayStatus, Price, ProductArt, ReviewsSection, Row, STATUS, ShareButton, ShopSkeleton, Stars, StatusSteps, arriveText, perKg, trackUrl } from "./parts";
import { LAST_KEY, MOBILE_RE, ShopProvider, digits, formatPhone, groupProducts, itemPath, store, useShop, type ProductGroup } from "./store";
import { SHOP_HOME, SP, isShopHost } from "../../lib/host";

export default function ShopApp() {
  return (
    <ShopProvider>
      <Shell />
    </ShopProvider>
  );
}

type Page =
  | { name: "home" }
  | { name: "item"; item: string }
  | { name: "cart" }
  | { name: "done" }
  | { name: "my" }
  | { name: "lookup" }
  | { name: "pay"; orderId: string }
  | { name: "pay-success" }
  | { name: "pay-fail" }
  | { name: "policy"; kind: PolicyKind };

function route(pathname: string, search: string): Page {
  // 손님 주소(gayeom.vercel.app)에서는 /shop 없이 들어와요 → 안에서는 같은 이름으로 맞춰서 읽어요
  let p = pathname.replace(/\/+$/, "");
  if (isShopHost() && p !== "/shop" && !p.startsWith("/shop/")) p = `/shop${p}`;
  const m = /^\/shop\/item\/(.+)$/.exec(p);
  if (m) return { name: "item", item: decodeURIComponent(m[1]) };
  const pol = /^\/shop\/policy\/(terms|privacy|refund)$/.exec(p);
  if (pol) return { name: "policy", kind: pol[1] as PolicyKind };
  if (p === "/shop/pay/success") return { name: "pay-success" };
  if (p === "/shop/pay/fail") return { name: "pay-fail" };
  const pm = /^\/shop\/pay\/([^/]+)$/.exec(p);
  if (pm) return { name: "pay", orderId: decodeURIComponent(pm[1]) };
  if (p === "/shop/cart") return { name: "cart" };
  if (p === "/shop/done") return { name: "done" };
  if (p === "/shop/my" || p === "/shop/login") return { name: "my" };
  if (p === "/shop/lookup" || new URLSearchParams(search).get("tab") === "lookup") return { name: "lookup" };
  return { name: "home" };
}

function Shell() {
  const s = useShop();
  const loc = useLocation();
  const nav = useNavigate();
  const page = route(loc.pathname, loc.search);

  useEffect(() => {
    if (s.info) document.title = `${s.info.factory_name} 주문서`;
  }, [s.info]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [loc.pathname]);

  // 장바구니 숫자가 늘면 배지가 한 번 튀어요
  const [bump, setBump] = useState(0);
  const prev = useRef(s.cartCount);
  useEffect(() => {
    if (s.cartCount > prev.current) setBump((b) => b + 1);
    prev.current = s.cartCount;
  }, [s.cartCount]);

  if (s.infoLoading && !s.info) return <ShopSkeleton />;
  if (!s.info)
    return (
      <div className="mx-auto max-w-md p-6">
        <Alert tone="error">{s.infoError || "주문서를 열지 못했어요."}</Alert>
        <Button block onClick={s.reloadInfo}>다시 열기</Button>
      </div>
    );

  // 상품·장바구니·결제는 앱처럼 '← 제목' 머리, 나머지는 가게 이름 머리
  const subTitle =
    page.name === "item" ? page.item : page.name === "policy" ? POLICY_TITLE[page.kind] : page.name === "cart" ? "장바구니" : page.name === "pay" || page.name === "pay-success" || page.name === "pay-fail" ? "결제" : "";
  const back = () => (window.history.length > 1 ? window.history.back() : nav(SHOP_HOME));
  const cartIcon = (
    <Link to={`${SP}/cart`} className="relative flex h-10 w-10 items-center justify-center rounded hover:bg-white/10" aria-label={`장바구니 ${s.cartCount}개`}>
      <ShoppingBasket className="h-6 w-6" />
      {s.cartCount > 0 && (
        <span key={bump} className={cx("absolute -right-0.5 -top-0.5 min-w-[1.25rem] rounded-full bg-brine px-1 text-center text-xs font-bold leading-5 text-white", bump > 0 && "badge-bump")}>
          {s.cartCount}
        </span>
      )}
    </Link>
  );

  const showTabs = page.name !== "cart" && page.name !== "item";
  return (
    <div className="min-h-dvh bg-paper">
      <header className="safe-top sticky top-0 z-30 bg-brand text-white">
        <div className="mx-auto flex h-14 max-w-lg items-center justify-between gap-1 px-2 md:max-w-3xl lg:h-16 lg:max-w-6xl lg:px-4">
          {subTitle ? (
            <>
              <button type="button" onClick={back} aria-label="뒤로" className="flex h-10 w-10 shrink-0 items-center justify-center rounded hover:bg-white/10">
                <ChevronLeft className="h-7 w-7" />
              </button>
              <span className="min-w-0 flex-1 truncate text-center text-lg font-bold">{subTitle}</span>
              {page.name === "cart" ? (
                <Link to={SHOP_HOME} aria-label="홈" className="flex h-10 w-10 shrink-0 items-center justify-center rounded hover:bg-white/10">
                  <HomeIcon className="h-6 w-6" />
                </Link>
              ) : (
                cartIcon
              )}
            </>
          ) : (
            <>
              <Link to={SHOP_HOME} className="min-w-0 truncate px-2 font-serif text-xl font-bold">
                {s.info.factory_name}
              </Link>
              <div className="flex items-center gap-1">
                {/* 태블릿·컴퓨터: 아래 탭 대신 위에 메뉴 */}
                <nav className="mr-2 hidden items-center gap-1 md:flex" aria-label="메뉴">
                  <Link to={SHOP_HOME} className="rounded px-3 py-2 text-[15px] font-semibold text-white/85 hover:bg-white/10 hover:text-white">상품</Link>
                  {!s.auth && <Link to={`${SP}/lookup`} className="rounded px-3 py-2 text-[15px] font-semibold text-white/85 hover:bg-white/10 hover:text-white">주문 조회</Link>}
                  {s.info.factory_phone && <a href={telHref(s.info.factory_phone)} className="rounded px-3 py-2 text-[15px] font-semibold text-white/85 hover:bg-white/10 hover:text-white">전화 주문 {s.info.factory_phone}</a>}
                </nav>
                <Link to={`${SP}/my`} className="flex h-10 items-center gap-1 rounded px-3 text-sm font-bold text-white/90 hover:bg-white/10" aria-label="마이페이지">
                  <User className="h-5 w-5" />
                  {s.auth ? <span className="max-w-[5rem] truncate">{s.auth.profile.name}님</span> : "로그인"}
                </Link>
                {cartIcon}
              </div>
            </>
          )}
        </div>
      </header>

      <main
        className={cx(
          "mx-auto max-w-lg px-4",
          // 홈·상품은 컴퓨터에서 넓게, 장바구니·마이페이지 같은 입력 화면은 읽기 좋은 폭으로
          page.name === "home" || page.name === "item" ? "md:max-w-3xl lg:max-w-6xl" : "md:max-w-2xl",
          page.name === "item" ? "pt-0" : "pt-4 lg:pt-8",
          showTabs ? "pb-28 md:pb-12" : page.name === "item" ? "pb-44 lg:pb-12" : "pb-44",
        )}
      >
        {page.name === "home" && <Home />}
        {page.name === "item" && <Item name={page.item} />}
        {page.name === "cart" && <Cart />}
        {page.name === "done" && <Done />}
        {page.name === "my" && <My />}
        {page.name === "lookup" && <Lookup />}
        {page.name === "pay" && <Pay orderId={page.orderId} />}
        {page.name === "pay-success" && <PaySuccess />}
        {page.name === "pay-fail" && <PayFail />}
        {page.name === "policy" && <PolicyBody kind={page.kind} info={s.info} />}
        <ShopFooter />
      </main>

      {(page.name === "home" || page.name === "item") && <BackToTop raised={page.name === "item"} />}
      {showTabs && <TabBar active={page.name} />}
    </div>
  );
}

/** 맨 아래 사업자 정보 + 약관 링크 (쇼핑몰이면 있어야 하는 칸). 빈 값은 숨겨요 */
function ShopFooter() {
  const s = useShop();
  const info = s.info!;
  const b = info.business ?? {};
  const rows = (["대표자", "사업자등록번호", "통신판매업 신고번호", "주소", "전화"] as const)
    .map((k) => [k, k === "전화" && b[k] && info.contact_hours ? `${b[k]} (${info.contact_hours})` : b[k]] as const)
    .filter(([, v]) => v);
  return (
    <footer className="mt-12 border-t border-line pt-5 text-[13px] leading-relaxed text-stone-500">
      <nav className="mb-3 flex flex-wrap gap-x-4 gap-y-1 font-semibold text-stone-600" aria-label="약관">
        <Link to={`${SP}/policy/terms`}>이용약관</Link>
        <Link to={`${SP}/policy/privacy`} className="font-bold text-ink">개인정보처리방침</Link>
        <Link to={`${SP}/policy/refund`}>교환·반품</Link>
      </nav>
      <div className="font-serif text-sm font-bold text-stone-600">{b["상호"] || info.factory_name}</div>
      <dl className="mt-1">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <dt className="shrink-0">{k}</dt>
            <dd className="min-w-0 break-keep text-stone-600">{v}</dd>
          </div>
        ))}
      </dl>
      {info.pay_client_key && <p className="mt-2 text-stone-400">카드 결제는 토스페이먼츠가 처리해요.</p>}
    </footer>
  );
}

function TabBar({ active }: { active: Page["name"] }) {
  const s = useShop();
  const tab = (to: string, on: boolean, icon: ReactNode, label: string, badge?: number) => (
    <Link to={to} aria-current={on ? "page" : undefined} className={cx("relative flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-bold", on ? "text-brand" : "text-stone-500")}>
      {icon}
      {label}
      {!!badge && <span className="absolute right-1/4 top-1 min-w-[1.1rem] rounded-full bg-brine px-1 text-center text-[11px] leading-[1.1rem] text-white">{badge}</span>}
    </Link>
  );
  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white/95 backdrop-blur md:hidden">
      <div className="mx-auto flex max-w-lg md:max-w-2xl">
        {tab(SHOP_HOME, active === "home", <HomeIcon className="h-6 w-6" />, "홈")}
        {tab(`${SP}/cart`, false, <ShoppingBasket className="h-6 w-6" />, "장바구니", s.cartCount)}
        {s.auth
          ? tab(`${SP}/my`, active === "my", <User className="h-6 w-6" />, "주문 내역")
          : tab(`${SP}/lookup`, active === "lookup", <Search className="h-6 w-6" />, "주문 조회")}
        {s.info?.factory_phone ? (
          <a href={telHref(s.info.factory_phone)} className="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-bold text-stone-500">
            <Phone className="h-6 w-6" />
            전화 주문
          </a>
        ) : (
          tab(`${SP}/my`, active === "my", <User className="h-6 w-6" />, "로그인")
        )}
      </div>
    </nav>
  );
}

/** 규격마다 1kg당 가격을 구해, 가장 싼 규격 하나를 '가장 알뜰'로 (규격이 둘 이상일 때만) */
function cheapestSku(g: ProductGroup): string {
  const rows = g.variants.filter((v) => !v.sold_out).map((v) => ({ sku: v.sku, k: perKg(v.price, v.spec || v.unit) })).filter((x) => x.k !== null) as { sku: string; k: number }[];
  if (rows.length < 2) return "";
  return rows.reduce((a, b) => (b.k < a.k ? b : a)).sku;
}

const shipLine = (info: ShopInfo) =>
  info.shipping_fee > 0
    ? `택배비 ${won(info.shipping_fee)}${info.free_shipping_over > 0 ? ` (${won(info.free_shipping_over)} 이상 무료)` : ""}`
    : info.free_shipping_over > 0
      ? `${won(info.free_shipping_over)} 이상 택배비 무료`
      : "택배비는 주문 확인 후 안내";

// ================================================================ 홈
function Home() {
  const s = useShop();
  const info = s.info!;
  const groups = useMemo(() => groupProducts(s.products), [s.products]);

  return (
    <div>
      <section className="pb-5 pt-2">
        {s.auth && <p className="mb-2 text-sm text-stone-600">{s.auth.profile.name}님, 다시 오셨네요.</p>}
        <p className="whitespace-pre-line break-keep text-[1.6rem] font-bold leading-[1.35] tracking-[-0.025em] text-ink">
          {info.intro || "정성껏 담근 젓갈을\n공장에서 바로 보내 드려요."}
        </p>
      </section>

      {info.notice && <p className="mb-4 whitespace-pre-line break-keep border-l-4 border-brine bg-brine-soft px-4 py-3">{info.notice}</p>}

      <div className="lg:grid lg:grid-cols-[1fr_360px] lg:items-start lg:gap-8">
      <div className="min-w-0">
      {s.auth && <LastOrder />}

      <h2 className="sr-only">상품</h2>
      {groups.length === 0 && <Alert tone="info">지금은 주문할 수 있는 상품이 없어요. 전화로 문의해 주세요.</Alert>}
      <div className={groups.length > 1 ? "space-y-4 md:grid md:grid-cols-2 md:gap-4 md:space-y-0" : "space-y-4"}>
        {groups.map((g) => (
          <ProductCard key={g.name} g={g} />
        ))}
      </div>

      </div>
      <aside className="lg:sticky lg:top-24">
      <dl className="mt-6 divide-y divide-line rounded-lg border border-line bg-white text-[15px] lg:mt-0">
        <InfoRow k="택배비" v={shipLine(info).replace(/^택배비 /, "")} />
        <InfoRow k="받는 날" v={`${dateKo(info.min_due_date)}부터${new Set(info.products.map((p) => p.lead_days)).size > 1 ? " (품목마다 달라요)" : ""}`} sub={info.closed_days_text ? `${info.closed_days_text}요일은 택배가 쉬어요` : ""} />
        <InfoRow k="결제" v={info.pay_client_key ? "카드·간편결제 또는 계좌 입금" : "계좌 입금 (주문 후 안내)"} />
        <InfoRow
          k="문의"
          v={info.factory_phone ? <a href={telHref(info.factory_phone)} className="font-bold text-brand underline underline-offset-2">{info.factory_phone}</a> : "-"}
          sub={info.contact_hours}
        />
      </dl>

      <details className="group mt-4 rounded-lg border border-line bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 font-bold">
          처음 주문하시나요?
          <ChevronDown className="h-5 w-5 text-stone-500 transition group-open:rotate-180" />
        </summary>
        <ol className="space-y-2 border-t border-line px-4 py-3">
          {[
            "상품을 골라 장바구니에 담아요",
            "받는 분·주소·받을 날을 적고 주문해요",
            info.pay_client_key ? "카드로 결제하거나 안내된 계좌로 입금해요" : "안내된 계좌로 입금해요",
            "입금을 확인하면 포장해서 보내 드려요",
          ].map((text, i) => (
            <li key={text} className="flex gap-3">
              <span className="w-4 shrink-0 font-bold text-brand">{i + 1}</span>
              <span className="break-keep">{text}</span>
            </li>
          ))}
        </ol>
        {!s.auth && (
          <p className="break-keep border-t border-line px-4 py-3 text-sm text-stone-600">
            가입하면 주소를 다시 적지 않아도 되고, 지난 주문을 그대로 다시 할 수 있어요.{" "}
            <Link to={`${SP}/my`} className="font-bold text-brand underline underline-offset-2">가입하기</Link>
          </p>
        )}
      </details>
      </aside>
      </div>
    </div>
  );
}

/** 홈 상품 카드 — 카드 전체를 누르면 상품으로 (쇼핑몰 목록과 같은 동작) */
function ProductCard({ g }: { g: ProductGroup }) {
  const s = useShop();
  const info = s.info!;
  const best = cheapestSku(g);
  const lead = Math.min(...g.variants.filter((v) => !v.sold_out).map((v) => v.lead_days ?? 1));
  return (
    <Link to={itemPath(g.name)} className={cx("block overflow-hidden rounded-lg border border-line bg-white active:bg-stone-50", g.soldOut && "opacity-70")}>
      {g.image_url && (
        <div className="aspect-[16/9]">
          <ProductArt name={g.name} image={g.image_url} />
        </div>
      )}
      <div className="flex items-baseline justify-between gap-2 border-b-2 border-brand px-4 pb-2 pt-3">
        <h3 className="font-serif text-2xl font-bold text-brand-dark">{g.name}</h3>
        {g.soldOut ? (
          <Badge tone="red">품절</Badge>
        ) : (
          g.reviewCount > 0 &&
          g.reviewAvg !== null && (
            <span className="flex items-baseline gap-1 text-sm">
              <Stars value={g.reviewAvg} size="text-sm" />
              <span className="text-stone-500">({g.reviewCount})</span>
            </span>
          )
        )}
      </div>
      <ul className="divide-y divide-line">
        {g.variants.map((v) => {
          const k = perKg(v.price, v.spec || v.unit);
          return (
            <li key={v.sku} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <span className="min-w-0">
                <span className={cx("font-bold", v.sold_out && "text-stone-400")}>{v.spec || v.unit}</span>
                {v.sku === best && <span className="ml-2 rounded-sm bg-parcel-soft px-1.5 py-0.5 text-xs font-bold text-parcel">가장 알뜰</span>}
                {k !== null && !v.sold_out && <span className="block text-xs text-stone-500">1kg당 {won(k)}</span>}
              </span>
              {v.sold_out ? (
                <span className="text-sm font-bold text-stone-400">품절</span>
              ) : v.price !== null ? (
                <Price value={v.price} className="text-lg" />
              ) : (
                <span className="text-sm text-stone-500">가격 문의</span>
              )}
            </li>
          );
        })}
      </ul>
      {!g.soldOut && (
        <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2.5 text-sm">
          <span className="flex min-w-0 items-center gap-1.5 font-semibold text-parcel">
            <Truck className="h-4 w-4 shrink-0" />
            <span className="truncate">{arriveText(info, lead)} 받을 수 있어요</span>
          </span>
          <ChevronRight className="h-5 w-5 shrink-0 text-stone-400" />
        </div>
      )}
      {g.description && <p className="break-keep border-t border-line px-4 py-2.5 text-[15px] text-stone-600">{g.description}</p>}
    </Link>
  );
}

/** 로그인 손님: 지난 주문 한 번에 다시 담기 */
function LastOrder() {
  const s = useShop();
  const toast = useToast();
  const nav = useNavigate();
  const [o, setO] = useState<MyOrder | null>(null);
  useEffect(() => {
    if (!s.auth) return;
    shopMyOrders(s.auth.token)
      .then((list) => setO(list.find((x) => x.status !== "취소") ?? null))
      .catch(() => undefined);
  }, [s.auth]);
  if (!o) return null;
  const again = () => {
    const n = s.addMany(o.lines.map((l) => ({ sku: l.sku, qty: l.qty })));
    if (!n) return toast("지금은 주문할 수 없는 품목이에요 (품절이거나 판매 중지).", "error");
    toast(n < o.lines.length ? `${n}가지를 담았어요. 품절된 품목은 뺐어요.` : "지난 주문을 장바구니에 담았어요.", "ok", { label: "장바구니 보기", onClick: () => nav(`${SP}/cart`) });
  };
  return (
    <section className="mb-4 rounded-lg border border-line bg-white px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-bold">지난번 주문</h2>
        <span className="text-sm text-stone-500">{o.created_at.slice(0, 10)}</span>
      </div>
      <p className="mt-1 break-keep text-[15px] text-stone-700">{o.lines.map((l) => `${l.name} ${l.qty}개`).join(", ")}</p>
      <Button size="sm" variant="soft" className="mt-2" icon={<RotateCcw className="h-4 w-4" />} onClick={again}>
        그대로 다시 담기
      </Button>
    </section>
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
type ItemTab = "info" | "reviews" | "delivery";

/** 화면에 보이는 칸에 맞춰 위 탭을 바꿔 줘요 (쇼핑몰 상품 페이지의 따라오는 탭) */
function useScrollSpy(ids: ItemTab[]): [ItemTab, (id: ItemTab) => void] {
  const [active, setActive] = useState<ItemTab>(ids[0]);
  const lock = useRef(0);
  useEffect(() => {
    const els = ids.map((id) => document.getElementById(`sec-${id}`)).filter(Boolean) as HTMLElement[];
    if (!els.length || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        if (Date.now() < lock.current) return;
        const hit = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (hit) setActive(hit.target.id.replace("sec-", "") as ItemTab);
      },
      { rootMargin: "-120px 0px -55% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join()]);
  const go = (id: ItemTab) => {
    setActive(id);
    lock.current = Date.now() + 700; // 눌러서 내려가는 동안엔 탭이 흔들리지 않게
    const el = document.getElementById(`sec-${id}`);
    if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 104, behavior: "smooth" });
  };
  return [active, go];
}

function Item({ name }: { name: string }) {
  const s = useShop();
  const nav = useNavigate();
  const toast = useToast();
  const info = s.info!;
  const g = useMemo(() => groupProducts(s.products).find((x) => x.name === name), [s.products, name]);
  const [pick, setPick] = useState<Record<string, number>>({});
  const [nudge, setNudge] = useState(false);
  const [reviews, setReviews] = useState<ShopReviewList | null>(null);
  useEffect(() => {
    // 규격이 하나면 1개로 시작
    if (g && g.variants.length === 1 && !g.variants[0].sold_out) setPick({ [g.variants[0].sku]: 1 });
  }, [g]);
  useEffect(() => {
    shopReviews(name).then(setReviews).catch(() => setReviews({ average: null, count: 0, items: [] }));
  }, [name]);
  const [tab, go] = useScrollSpy(["info", "reviews", "delivery"]);

  if (!g)
    return (
      <div className="py-10 text-center">
        <p className="mb-4 text-stone-600">상품을 찾지 못했어요.</p>
        <Link to={SHOP_HOME}><Button>홈으로</Button></Link>
      </div>
    );

  const count = Object.values(pick).reduce((a, b) => a + b, 0);
  const sum = g.variants.reduce((a, v) => a + (pick[v.sku] ?? 0) * (v.price ?? 0), 0);
  const hasPrice = g.variants.some((v) => v.price !== null);
  const best = cheapestSku(g);
  const open = g.variants.filter((v) => !v.sold_out);
  const lead = open.length ? Math.min(...open.map((v) => v.lead_days ?? 1)) : 1;
  const priced = open.filter((v) => v.price !== null).map((v) => v.price as number);
  const reviewCount = reviews?.count ?? g.reviewCount;

  const add = (): boolean => {
    if (!count) {
      setNudge(true);
      document.getElementById("options")?.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => setNudge(false), 1200);
      toast("규격과 수량을 먼저 골라 주세요.", "info");
      return false;
    }
    s.addMany(Object.entries(pick).map(([sku, qty]) => ({ sku, qty })));
    setPick(g.variants.length === 1 ? { [g.variants[0].sku]: 1 } : {});
    try {
      navigator.vibrate?.(12);
    } catch {
      /* 진동 없는 기기 */
    }
    return true;
  };

  // 장바구니·바로 구매 칸 — 휴대폰·태블릿은 아래 고정, 컴퓨터는 규격 고르는 칸 바로 밑
  const buyBox = (
    <>
          {count > 0 && (
            <div className="mb-2 flex items-baseline justify-between text-sm">
              <span className="text-stone-600">고른 상품 {count}개</span>
              {hasPrice && <Price value={sum} className="text-lg" />}
            </div>
          )}
          {g.soldOut ? (
            <Button size="xl" block disabled>품절</Button>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <Button
                size="xl"
                variant="ghost"
                onClick={() => add() && toast("장바구니에 담았어요.", "ok", { label: "장바구니 보기", onClick: () => nav(`${SP}/cart`) })}
              >
                장바구니
              </Button>
              <Button size="xl" onClick={() => add() && nav(`${SP}/cart`)}>
                바로 구매
              </Button>
            </div>
          )}
    </>
  );

  return (
    <div>
      {/* 컴퓨터: 왼쪽 사진·설명, 오른쪽 규격·구매 (쇼핑몰 PC 상품 화면처럼) */}
      <div className="lg:grid lg:grid-cols-2 lg:items-start lg:gap-10 lg:pt-6">
      <div>
      {g.image_url && (
        <div className="relative -mx-4 aspect-[4/3] overflow-hidden border-b border-line lg:mx-0 lg:rounded-xl lg:border">
          <ProductArt name={g.name} image={g.image_url} big />
        </div>
      )}
      <div className="pt-4">
        <div className="flex items-start justify-between gap-2">
          <h1 className="font-serif text-3xl font-bold text-brand-dark">{g.name}</h1>
          <ShareButton title={`${info.factory_name} ${g.name}`.trim()} text={g.description || g.name} />
        </div>
        {reviewCount > 0 && g.reviewAvg !== null && (
          <button type="button" onClick={() => go("reviews")} className="mt-1 flex items-baseline gap-1.5">
            <Stars value={reviews?.average ?? g.reviewAvg} />
            <b>{(reviews?.average ?? g.reviewAvg).toFixed(1)}</b>
            <span className="text-sm text-stone-500 underline underline-offset-2">후기 {reviewCount}개</span>
          </button>
        )}
        {g.description && <p className="mt-2 break-keep text-[17px] text-stone-700">{g.description}</p>}
        {priced.length > 0 && (
          <div className="mt-3 flex items-baseline gap-1">
            <Price value={Math.min(...priced)} className="text-[1.75rem] text-ink" />
            {priced.length > 1 && <span className="text-stone-500">부터</span>}
          </div>
        )}
      </div>

      {open.length > 0 && (
        <div className="mt-4 rounded-lg border border-line bg-white px-4 py-3 text-[15px]">
          <div className="flex items-center gap-2 font-bold text-parcel">
            <Truck className="h-5 w-5 shrink-0" />
            오늘 주문하면 {arriveText(info, lead)} 받을 수 있어요
          </div>
          <div className="mt-1 pl-7 text-stone-600">{shipLine(info)}</div>
        </div>
      )}

      </div>
      <div className="lg:sticky lg:top-20">
      <h2 className="mb-2 mt-6 text-lg font-extrabold text-brand-dark lg:mt-0">규격·수량</h2>
      <div id="options" className={cx("scroll-mt-28 divide-y divide-line overflow-hidden rounded-lg border bg-white transition-colors", nudge ? "border-brine ring-2 ring-brine/40" : "border-line")}>
        {g.variants.map((v) => {
          const q = pick[v.sku] ?? 0;
          const inCart = s.cart[v.sku] ?? 0;
          const k = perKg(v.price, v.spec || v.unit);
          return (
            <div key={v.sku} className={cx("px-4 py-3", v.sold_out && "opacity-60", q > 0 && "bg-brand-soft/60")}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-2 text-lg font-extrabold">
                    {v.spec || v.unit}
                    {v.sku === best && <span className="rounded-sm bg-parcel-soft px-1.5 py-0.5 text-xs font-bold text-parcel">가장 알뜰</span>}
                    {v.sold_out && <Badge tone="red">품절</Badge>}
                  </div>
                  {k !== null && !v.sold_out && <div className="text-xs text-stone-500">1kg당 {won(k)}</div>}
                  {!v.sold_out && (v.lead_days ?? 1) > lead && <div className="text-sm text-stone-500">{arriveText(info, v.lead_days)}부터 받아요</div>}
                  {inCart > 0 && <div className="text-sm text-brand">장바구니에 {inCart}{v.unit} 있어요</div>}
                </div>
                {v.price !== null ? <Price value={v.price} className="text-lg" /> : <span className="text-sm text-stone-500">가격 문의</span>}
              </div>
              {!v.sold_out && (
                <div className="mt-2 flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-stone-600">{q > 0 && v.price !== null ? won(q * v.price) : ""}</span>
                  <Stepper value={q} onChange={(x) => setPick({ ...pick, [v.sku]: x })} max={999} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-4 hidden rounded-lg border border-line bg-white p-4 lg:block">{buyBox}</div>
      </div>
      </div>

      {/* 따라오는 탭: 상품 정보 · 후기 · 배송·문의 */}
      <nav className="sticky top-14 z-20 -mx-4 mt-8 flex border-b border-line bg-paper/95 backdrop-blur" aria-label="상품 안내">
        {(
          [
            ["info", "상품 정보"],
            ["reviews", `후기${reviewCount ? ` ${reviewCount}` : ""}`],
            ["delivery", "배송·문의"],
          ] as [ItemTab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => go(id)}
            aria-current={tab === id ? "true" : undefined}
            className={cx("flex-1 border-b-[3px] py-3 text-[15px] font-bold", tab === id ? "border-brand text-brand" : "border-transparent text-stone-500")}
          >
            {label}
          </button>
        ))}
      </nav>

      <section id="sec-info" className="pt-5">
        <h2 className="sr-only">상품 정보</h2>
        {g.detail && <p className="mb-4 whitespace-pre-line break-keep leading-relaxed text-stone-800">{g.detail}</p>}
        <div className="overflow-hidden rounded-lg border border-line bg-white">
          <LabelTable
            rows={[
              ["품명", g.name],
              ["규격", g.variants.map((v) => v.spec || v.unit).join(" / ")],
              ["소개", g.description],
              ["만든 곳", `${info.factory_name}${info.factory_address ? ` (${info.factory_address})` : ""}`],
            ]}
          />
        </div>
      </section>

      <section id="sec-reviews" className="pt-8">
        <h2 className="mb-3 text-lg font-extrabold text-brand-dark">구매 후기</h2>
        <ReviewsSection name={g.name} data={reviews} />
      </section>

      <section id="sec-delivery" className="pt-8">
        <h2 className="mb-3 text-lg font-extrabold text-brand-dark">배송·문의</h2>
        <dl className="divide-y divide-line rounded-lg border border-line bg-white text-[15px]">
          <InfoRow k="택배비" v={shipLine(info).replace(/^택배비 /, "")} />
          <InfoRow k="받는 날" v={`오늘 주문하면 ${arriveText(info, lead)}부터`} sub={info.closed_days_text ? `${info.closed_days_text}요일은 택배가 쉬어요` : ""} />
          {info.threshold_kg > 0 && <InfoRow k="큰 주문" v={`${info.threshold_kg}kg 넘으면 화물로 보내요`} sub="운임은 확인 후 알려 드려요" />}
          <InfoRow k="교환·반품" v="받으신 상품에 문제가 있으면 전화로 알려 주세요" />
          <InfoRow
            k="문의"
            v={info.factory_phone ? <a href={telHref(info.factory_phone)} className="font-bold text-brand underline underline-offset-2">{info.factory_phone}</a> : "-"}
            sub={info.contact_hours}
          />
        </dl>
      </section>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white px-4 pt-2 lg:hidden">
        <div className="mx-auto max-w-2xl">{buyBox}</div>
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
        <Link to={SHOP_HOME}><Button>홈으로</Button></Link>
      </div>
    );
  return (
    <div>
      <div className="mb-5 border-b-2 border-brand pb-4 text-center">
        <CheckCircle2 className="mx-auto mb-2 h-12 w-12 text-brand" />
        <div className="text-2xl font-bold text-ink">주문이 접수됐어요</div>
        <div className="mt-1 break-keep text-stone-600">아래 계좌로 입금해 주시면 확인하고 바로 준비해요.</div>
      </div>
      <div className="mb-4"><StatusSteps status="접수" paid={false} /></div>
      {joined && <Alert tone="ok">가입도 끝났어요. 다음부터는 휴대폰 번호와 비밀번호로 로그인하면 돼요.</Alert>}

      <div className="mb-4 rounded-2xl border border-line bg-white p-5">
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

      {s.info?.pay_client_key && r.estimated_total !== null && r.pay_token && (
        <div className="mb-3">
          <Link to={`${SP}/pay/${encodeURIComponent(r.order_id)}?t=${encodeURIComponent(r.pay_token)}`}>
            <Button size="xl" block icon={<CreditCard className="h-6 w-6" />}>
              카드·간편결제로 {won(r.estimated_total)} 결제하기
            </Button>
          </Link>
          <p className="mt-2 text-center text-sm text-stone-500">또는 아래 계좌로 입금해 주세요</p>
        </div>
      )}
      <div className="mb-4">
        <PayGuide amount={r.estimated_total} account={r.bank_account} note={r.shipping_note || undefined} />
      </div>

      <div className="grid grid-cols-2 gap-2">
        {s.auth ? (
          <Link to={`${SP}/my`}><Button block variant="ghost" icon={<Package className="h-5 w-5" />}>내 주문 보기</Button></Link>
        ) : (
          <Link to={`${SP}/lookup`}><Button block variant="ghost" icon={<Package className="h-5 w-5" />}>주문 조회</Button></Link>
        )}
        <Link to={SHOP_HOME}><Button block variant="soft">홈으로</Button></Link>
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
// 문자 인증이 켜져 있으면: 이름 + 휴대폰 번호 + 인증번호 → 그 이름·번호로 한 주문 전부
// 꺼져 있으면(솔라피 발신번호 없음): 예전처럼 주문번호 + 전화번호 뒤 4자리
function Lookup() {
  const s = useShop();
  const sms = !!s.info?.sms_verify;
  const [mode, setMode] = useState<"sms" | "order">(sms ? "sms" : "order");
  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold">비회원 주문 조회</h1>
      <p className="mb-5 break-keep text-stone-600">
        {mode === "sms" ? "주문할 때 적은 성함과 휴대폰 번호로 찾아요. 문자로 받은 인증번호를 넣어 주세요." : "주문 완료 화면에 나온 주문번호로 찾아요."}{" "}
        {s.auth ? (
          <>로그인하셨으면 <Link to={`${SP}/my`} className="font-bold text-brand underline">마이페이지</Link>에서 볼 수 있어요.</>
        ) : (
          <>카카오·구글로 <Link to={`${SP}/my`} className="font-bold text-brand underline">로그인</Link>하면 한 번에 볼 수 있어요.</>
        )}
      </p>
      {mode === "sms" ? <SmsLookup /> : <OrderNoLookup />}
      {sms && (
        <button type="button" className="mt-5 w-full text-center text-[15px] font-semibold text-stone-500 underline underline-offset-2" onClick={() => setMode(mode === "sms" ? "order" : "sms")}>
          {mode === "sms" ? "주문번호로 조회하기" : "이름·휴대폰 번호로 조회하기"}
        </button>
      )}
    </div>
  );
}

function SmsLookup() {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [token, setToken] = useState("");
  const [left, setLeft] = useState(0); // 인증번호 남은 초
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [list, setList] = useState<PublicOrder[] | null>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (left <= 0) return;
    const t = window.setTimeout(() => setLeft((x) => x - 1), 1000);
    return () => window.clearTimeout(t);
  }, [left]);

  const send = async () => {
    setError("");
    if (!name.trim()) return setError("주문하신 분 성함을 적어 주세요.");
    if (!MOBILE_RE.test(digits(phone))) return setError("휴대폰 번호를 확인해 주세요. 예) 010-1234-5678");
    setBusy("send");
    try {
      const r = await shopGuestCode(name.trim(), formatPhone(phone));
      setToken(r.verify_token);
      setLeft(r.expires_in);
      setCode("");
      setList(null);
      window.setTimeout(() => codeRef.current?.focus(), 50);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  };
  const check = async () => {
    setError("");
    if (!token || left <= 0) return setError("인증번호를 먼저 받아 주세요.");
    if (digits(code).length !== 6) return setError("문자로 받은 인증번호 6자리를 넣어 주세요.");
    setBusy("check");
    try {
      setList(await shopGuestOrders({ name: name.trim(), phone: formatPhone(phone), code: digits(code), verify_token: token }));
      setLeft(0);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  };
  const mmss = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;

  if (list)
    return (
      <div>
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="font-semibold">{name}님 주문 {list.length}건</span>
          <button type="button" className="text-sm text-stone-500 underline" onClick={() => { setList(null); setToken(""); }}>
            다시 조회
          </button>
        </div>
        {list.length === 0 && <Alert tone="info">이 성함과 번호로 들어온 주문이 없어요. 주문할 때 적은 성함인지 확인해 주세요.</Alert>}
        <div className="space-y-3">
          {list.map((o) => (
            <GuestOrderCard key={o.order_id} initial={o} phone4={digits(phone).slice(-4)} />
          ))}
        </div>
      </div>
    );

  return (
    <div>
      <Field label="주문하신 분 성함">
        <Input value={name} autoComplete="name" placeholder="홍길동" onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="휴대폰 번호">
        <div className="flex gap-2">
          <Input type="tel" inputMode="numeric" autoComplete="tel" value={phone} placeholder="010-1234-5678" onChange={(e) => { setPhone(formatPhone(e.target.value)); setToken(""); setLeft(0); }} />
          <Button size="md" variant={token ? "ghost" : "primary"} className="shrink-0" loading={busy === "send"} disabled={left > 270} onClick={send}>
            {token ? "다시 받기" : "인증번호 받기"}
          </Button>
        </div>
      </Field>
      {token && (
        <Field
          label="인증번호"
          hint={left > 0 ? <span>문자로 보낸 6자리를 넣어 주세요. <b className="text-bad tabular-nums">{mmss}</b> 남음</span> : <span className="text-bad">시간이 지났어요. 다시 받아 주세요.</span>}
        >
          <Input ref={codeRef} value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="6자리" onChange={(e) => setCode(digits(e.target.value).slice(0, 6))} />
        </Field>
      )}
      {error && <Alert tone="error">{error}</Alert>}
      <Button size="xl" block loading={busy === "check"} disabled={!token || left <= 0} icon={<Search className="h-6 w-6" />} onClick={check}>
        조회하기
      </Button>
    </div>
  );
}

function OrderNoLookup() {
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
  return (
    <div>
      <Field label="주문번호" hint="주문 완료 화면에 나온 번호예요. 예) 20261126-K7Q3">
        <Input value={orderId} autoCapitalize="characters" placeholder="20261126-K7Q3" onChange={(e) => setOrderId(e.target.value.toUpperCase())} />
      </Field>
      <Field label="주문할 때 쓴 휴대폰 번호 뒤 4자리">
        <Input value={phone4} inputMode="numeric" maxLength={4} placeholder="5678" onChange={(e) => setPhone4(digits(e.target.value))} />
      </Field>
      {error && <Alert tone="error">{error}</Alert>}
      <Button size="xl" block loading={busy} icon={<Search className="h-6 w-6" />} onClick={find}>
        조회하기
      </Button>
      {r && (
        <div className="mt-5">
          <GuestOrderCard key={r.order_id} initial={r} phone4={digits(phone4)} />
        </div>
      )}
    </div>
  );
}

/** 비회원 주문 한 건: 상태 · 입금 · 취소 · 카드 결제 · 배송 위치 */
function GuestOrderCard({ initial, phone4 }: { initial: PublicOrder; phone4: string }) {
  const s = useShop();
  const [r, setR] = useState(initial);
  const [error, setError] = useState("");
  const st = STATUS[r.status] ?? { label: r.status, tone: "violet" as const, step: 1 };
  return (
    <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
      <div className="mb-3">
        <div className="text-sm text-stone-500 tabular-nums">주문번호 {r.order_id} · {r.created_at}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-lg font-extrabold text-brand-dark">{st.label}</span>
          <PayStatus paid={r.paid} status={r.status} />
        </div>
      </div>
      <div className="mb-4"><StatusSteps status={r.status} paid={r.paid} /></div>
      <dl className="space-y-1">
        <Row k="품목" v={r.items} />
        <Row k="받는 날" v={r.due_date === "날짜 미정" ? "정해지면 알려 드려요" : r.due_date} />
        <Row k="보내는 방법" v={r.ship_method} />
        {r.tracking_no && <Row k="송장" v={`${r.carrier} ${r.tracking_no}`} />}
        {r.truck_no && <Row k="화물차" v={r.truck_no} />}
      </dl>
      {error && <div className="mt-3"><Alert tone="error">{error}</Alert></div>}
      {r.status === "접수" && (
        <Button
          block
          size="md"
          variant="ghost"
          className="mt-3"
          onClick={async () => {
            if (!window.confirm(`주문 ${r.order_id}을(를) 취소할까요?`)) return;
            try {
              setR(await shopCancelOrder(r.order_id, { phone4 }));
            } catch (e) {
              setError(errorMessage(e));
            }
          }}
        >
          주문 취소
        </Button>
      )}
      {!r.paid && r.status !== "취소" && s.info?.pay_client_key && (
        <Link to={`${SP}/pay/${encodeURIComponent(r.order_id)}?p=${phone4}`} className="mt-3 block">
          <Button block size="lg" icon={<CreditCard className="h-5 w-5" />}>카드·간편결제로 결제하기</Button>
        </Link>
      )}
      {r.tracking_no && (
        <a className="mt-4 flex items-center justify-center gap-2 rounded-xl bg-parcel px-4 py-3 font-bold text-white" href={trackUrl(r.carrier, r.tracking_no)} target="_blank" rel="noreferrer">
          <MapPin className="h-5 w-5" /> 배송 위치 보기
        </a>
      )}
    </div>
  );
}
