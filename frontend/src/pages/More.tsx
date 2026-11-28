import { Link } from "react-router-dom";
import { ChevronRight, LogOut } from "lucide-react";
import { setToken } from "../api/client";
import { PageHeader } from "../components/ui";
import { GROUPS, NAV } from "../layouts/AdminLayout";
import { useFeatures } from "../lib/features";

/** 휴대폰 아래 탭에 다 못 넣은 메뉴 — 컴퓨터 왼쪽 메뉴와 같은 묶음으로 */
export default function More({ onLogout }: { onLogout: () => void }) {
  const { has, features } = useFeatures();
  const items = NAV.filter((n) => !n.mobile && (!n.module || has(n.module)));
  return (
    <div>
      <PageHeader title="더보기" />
      {GROUPS.map((g) => {
        const list = items.filter((n) => n.group === g.id);
        if (!list.length) return null;
        return (
          <section key={g.id} className="mb-5">
            <h2 className="mb-2 px-1 text-[14px] font-semibold text-stone-500">{g.label}</h2>
            <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-card">
              {list.map((n) => (
                <Link key={n.to} to={n.to} className="flex items-center gap-4 border-b border-line px-5 py-4 text-[17px] font-semibold last:border-0 active:bg-stone-50">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">{n.icon}</span>
                  <span className="flex-1">{n.label}</span>
                  <ChevronRight className="h-5 w-5 text-stone-400" />
                </Link>
              ))}
            </div>
          </section>
        );
      })}
      {features?.auth_required && (
        <button
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-2xl border border-line bg-white px-5 py-4 text-[17px] font-semibold text-bad"
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
