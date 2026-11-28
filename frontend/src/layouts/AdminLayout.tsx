import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Boxes, ClipboardCheck, ClipboardPaste, Factory, Home, ListOrdered, Loader2, LogOut, Menu, PhoneCall, ReceiptText, Settings, ShoppingBag, Truck, Warehouse } from "lucide-react";
import { setToken } from "../api/client";
import { cx } from "../components/ui";
import { useFeatures } from "../lib/features";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  group: "work" | "manage" | "setup";
  module?: string;
  mobile?: boolean; // 아래 탭에 보일지
}

const NAV: NavItem[] = [
  { to: "/", label: "홈", icon: <Home className="h-5 w-5" />, group: "work", mobile: true },
  { to: "/today", label: "오늘 할당량", icon: <ClipboardCheck className="h-5 w-5" />, group: "work", mobile: true },
  { to: "/orders/new", label: "주문 넣기", icon: <ClipboardPaste className="h-5 w-5" />, group: "work", mobile: true },
  { to: "/shipping", label: "출고", icon: <Truck className="h-5 w-5" />, group: "work", mobile: true },
  { to: "/orders", label: "주문 목록", icon: <ListOrdered className="h-5 w-5" />, group: "work" },
  { to: "/inventory", label: "재고", icon: <Boxes className="h-5 w-5" />, group: "manage", module: "q4_inventory" },
  { to: "/tanks", label: "숙성 저장소", icon: <Warehouse className="h-5 w-5" />, group: "manage", module: "q4_inventory" },
  { to: "/settlements", label: "월말 정산", icon: <ReceiptText className="h-5 w-5" />, group: "manage", module: "q4_settlement" },
  { to: "/reorder", label: "리마인드", icon: <PhoneCall className="h-5 w-5" />, group: "manage", module: "q4_reorder" },
  { to: "/marketplace", label: "오픈마켓", icon: <ShoppingBag className="h-5 w-5" />, group: "manage", module: "q3_marketplace" },
  { to: "/settings", label: "기본 정보·카톡", icon: <Settings className="h-5 w-5" />, group: "setup" },
];

const GROUPS: { id: NavItem["group"]; label: string }[] = [
  { id: "work", label: "매일 하는 일" },
  { id: "manage", label: "재고·정산" },
  { id: "setup", label: "설정" },
];

const DOW = "일월화수목금토";
function todayLabel(d = new Date()) {
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 ${DOW[d.getDay()]}요일`;
}

/** 남색 바탕의 작은 표식 + 이름 (회사 관리 화면 왼쪽 위의 그 자리) */
function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className={cx("flex shrink-0 items-center justify-center rounded-lg bg-brand text-white", compact ? "h-8 w-8" : "h-9 w-9")}>
        <Factory className={compact ? "h-[18px] w-[18px]" : "h-5 w-5"} />
      </span>
      <span className="leading-tight">
        <span className={cx("block font-bold text-ink", compact ? "text-[17px]" : "text-lg")}>공장 관리</span>
        {!compact && <span className="block text-[13px] text-stone-500">주문 · 출고 · 재고</span>}
      </span>
    </div>
  );
}

export default function AdminLayout({ onLogout }: { onLogout: () => void }) {
  const { has, features } = useFeatures();
  const items = NAV.filter((n) => !n.module || has(n.module));
  const mobileItems = items.filter((n) => n.mobile);
  const [slow, setSlow] = useState(false);
  const loc = useLocation();
  const current = [...items].sort((a, b) => b.to.length - a.to.length).find((n) => (n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to)));

  useEffect(() => {
    const on = (e: Event) => setSlow(!!(e as CustomEvent<boolean>).detail);
    window.addEventListener("api:slow", on);
    return () => window.removeEventListener("api:slow", on);
  }, []);

  const logout = () => {
    setToken(null);
    onLogout();
  };

  return (
    <div className="min-h-dvh md:flex">
      {/* 데스크톱 왼쪽 메뉴 — 흰 바탕, 묶음별 제목 */}
      <aside className="no-print sticky top-0 hidden h-dvh w-56 shrink-0 lg:w-64 flex-col border-r border-line bg-white md:flex">
        <div className="flex h-16 items-center border-b border-line px-5">
          <Brand />
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="메뉴">
          {GROUPS.map((g) => {
            const list = items.filter((n) => n.group === g.id);
            if (!list.length) return null;
            return (
              <div key={g.id} className="mb-5">
                <div className="mb-1.5 px-3 text-[13px] font-semibold text-stone-400">{g.label}</div>
                <ul className="space-y-0.5">
                  {list.map((n) => (
                    <li key={n.to}>
                      <NavLink
                        to={n.to}
                        end={n.to === "/" || n.to === "/orders"}
                        className={({ isActive }) =>
                          cx(
                            "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[16px] transition-colors",
                            isActive ? "bg-brand-soft font-bold text-brand before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:bg-brand" : "font-medium text-stone-600 hover:bg-stone-100 hover:text-ink",
                          )
                        }
                      >
                        {n.icon}
                        {n.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </nav>
        {features?.auth_required && (
          <div className="border-t border-line p-3">
            <button onClick={logout} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 font-medium text-stone-600 hover:bg-stone-100 hover:text-ink">
              <LogOut className="h-5 w-5" /> 나가기
            </button>
          </div>
        )}
      </aside>

      <div className="min-w-0 flex-1">
        {/* 위 막대: 휴대폰은 표식, 컴퓨터는 지금 화면 이름 + 오늘 날짜 */}
        <header className="no-print safe-top sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-5xl items-center 2xl:max-w-6xl justify-between gap-3 px-4 md:h-16 md:px-8">
            <div className="md:hidden">
              <Brand compact />
            </div>
            <div className="hidden items-center gap-2 text-[15px] md:flex">
              <span className="text-stone-400">공장 관리</span>
              <span className="text-stone-300" aria-hidden>/</span>
              <span className="font-semibold text-ink">{current?.label ?? "더보기"}</span>
            </div>
            <span className="whitespace-nowrap text-[15px] text-stone-500">
              <span className="md:hidden">{todayLabel().replace(/^\d+년 /, "")}</span>
              <span className="hidden md:inline">{todayLabel()}</span>
            </span>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl px-4 pb-28 pt-5 md:px-6 md:pb-12 md:pt-8 lg:px-8 2xl:max-w-6xl">
          {slow && (
            <div className="no-print sticky top-16 z-40 mb-3 flex items-center gap-2 rounded-xl bg-ink px-4 py-3 font-semibold text-white shadow-pop">
              <Loader2 className="h-5 w-5 animate-spin" /> 서버를 깨우는 중이에요. 잠시만 기다려 주세요…
            </div>
          )}
          <Outlet />
        </main>
      </div>

      {/* 휴대폰 아래 탭 */}
      <nav className="no-print safe-bottom fixed inset-x-0 bottom-0 z-40 grid border-t border-line bg-white md:hidden" style={{ gridTemplateColumns: `repeat(${mobileItems.length + 1}, minmax(0, 1fr))` }}>
        {mobileItems.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) => cx("flex flex-col items-center gap-1 pb-1.5 pt-2 text-[12px]", isActive ? "font-bold text-brand" : "font-medium text-stone-500")}
          >
            <span className="[&>svg]:h-6 [&>svg]:w-6">{n.icon}</span>
            {n.label}
          </NavLink>
        ))}
        <NavLink to="/more" className={({ isActive }) => cx("flex flex-col items-center gap-1 pb-1.5 pt-2 text-[12px]", isActive ? "font-bold text-brand" : "font-medium text-stone-500")}>
          <Menu className="h-6 w-6" />
          더보기
        </NavLink>
      </nav>
    </div>
  );
}

export { GROUPS, NAV };
