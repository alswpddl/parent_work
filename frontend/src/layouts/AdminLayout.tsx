import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Boxes, ClipboardPaste, Home, LogOut, Menu, ReceiptText, Settings, ShoppingBag, Truck, ListOrdered, PhoneCall, Loader2 } from "lucide-react";
import { setToken } from "../api/client";
import { cx } from "../components/ui";
import { useFeatures } from "../lib/features";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  module?: string;
  mobile?: boolean; // 아래 탭에 보일지
}

const NAV: NavItem[] = [
  { to: "/", label: "홈", icon: <Home className="h-6 w-6" />, mobile: true },
  { to: "/orders/new", label: "주문 넣기", icon: <ClipboardPaste className="h-6 w-6" />, mobile: true },
  { to: "/shipping", label: "출고", icon: <Truck className="h-6 w-6" />, mobile: true },
  { to: "/orders", label: "주문 목록", icon: <ListOrdered className="h-6 w-6" /> },
  { to: "/inventory", label: "자재 재고", icon: <Boxes className="h-6 w-6" />, module: "q4_inventory", mobile: true },
  { to: "/settlements", label: "월말 정산", icon: <ReceiptText className="h-6 w-6" />, module: "q4_settlement" },
  { to: "/reorder", label: "리마인드", icon: <PhoneCall className="h-6 w-6" />, module: "q4_reorder" },
  { to: "/marketplace", label: "오픈마켓", icon: <ShoppingBag className="h-6 w-6" />, module: "q3_marketplace" },
  { to: "/settings", label: "기본 정보·카톡", icon: <Settings className="h-6 w-6" /> },
];

export default function AdminLayout({ onLogout }: { onLogout: () => void }) {
  const { has, features } = useFeatures();
  const items = NAV.filter((n) => !n.module || has(n.module));
  const mobileItems = items.filter((n) => n.mobile);
  const [slow, setSlow] = useState(false);

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
    <div className="min-h-screen md:flex">
      {/* 데스크톱 왼쪽 메뉴 */}
      <aside className="hidden w-60 shrink-0 flex-col bg-brand px-3 py-5 text-white md:flex">
        <div className="mb-6 px-3 text-xl font-extrabold">🏭 공장 도우미</div>
        <nav className="flex flex-1 flex-col gap-1">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) => cx("flex items-center gap-3 rounded-xl px-3 py-3 font-semibold", isActive ? "bg-white text-brand" : "hover:bg-white/10")}
            >
              {n.icon}
              {n.label}
            </NavLink>
          ))}
        </nav>
        {features?.auth_required && (
          <button onClick={logout} className="mt-4 flex items-center gap-3 rounded-xl px-3 py-3 font-semibold hover:bg-white/10">
            <LogOut className="h-6 w-6" /> 나가기
          </button>
        )}
      </aside>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-28 pt-4 md:px-8 md:pb-10 md:pt-8">
        {slow && (
          <div className="no-print sticky top-2 z-40 mb-3 flex items-center gap-2 rounded-xl2 bg-parcel px-4 py-3 font-semibold text-white shadow">
            <Loader2 className="h-5 w-5 animate-spin" /> 서버를 깨우는 중이에요. 잠시만 기다려 주세요…
          </div>
        )}
        <Outlet />
      </main>

      {/* 휴대폰 아래 탭 */}
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 grid border-t border-line bg-white md:hidden" style={{ gridTemplateColumns: `repeat(${mobileItems.length + 1}, minmax(0, 1fr))` }}>
        {mobileItems.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) => cx("flex flex-col items-center gap-0.5 py-2 text-xs font-bold", isActive ? "text-brand" : "text-stone-500")}
          >
            {n.icon}
            {n.label}
          </NavLink>
        ))}
        <NavLink to="/more" className={({ isActive }) => cx("flex flex-col items-center gap-0.5 py-2 text-xs font-bold", isActive ? "text-brand" : "text-stone-500")}>
          <Menu className="h-6 w-6" />
          더보기
        </NavLink>
      </nav>
    </div>
  );
}

export { NAV };
