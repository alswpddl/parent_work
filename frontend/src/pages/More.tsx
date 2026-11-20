import { Link } from "react-router-dom";
import { ChevronRight, LogOut } from "lucide-react";
import { setToken } from "../api/client";
import { PageHeader } from "../components/ui";
import { NAV } from "../layouts/AdminLayout";
import { useFeatures } from "../lib/features";

/** 휴대폰 아래 탭에 다 못 넣은 메뉴 */
export default function More({ onLogout }: { onLogout: () => void }) {
  const { has, features } = useFeatures();
  const items = NAV.filter((n) => !n.mobile && (!n.module || has(n.module)));
  return (
    <div>
      <PageHeader title="더보기" />
      <div className="overflow-hidden rounded-2xl border border-line bg-white">
        {items.map((n) => (
          <Link key={n.to} to={n.to} className="flex items-center gap-4 border-b border-line px-5 py-5 text-lg font-bold last:border-0">
            <span className="text-brand">{n.icon}</span>
            <span className="flex-1">{n.label}</span>
            <ChevronRight className="h-5 w-5 text-stone-400" />
          </Link>
        ))}
      </div>
      {features?.auth_required && (
        <button
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl border border-line bg-white px-5 py-5 text-lg font-bold text-red-700"
          onClick={() => {
            setToken(null);
            onLogout();
          }}
        >
          <LogOut className="h-5 w-5" /> 나가기
        </button>
      )}
    </div>
  );
}
