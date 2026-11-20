import { useState } from "react";
import { Link } from "react-router-dom";
import { BellOff, ClipboardPaste, PhoneCall, RefreshCw } from "lucide-react";
import { reorderRecompute, reorderSnooze, reorderStats } from "../api/endpoints";
import type { ReorderStat } from "../api/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Empty, LoadState, PageHeader, Segmented } from "../components/ui";
import { dateKo, telHref } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

export default function Reorder() {
  const toast = useToast();
  const { busy, run } = useAction();
  const [tab, setTab] = useState<"due" | "all">("due");
  const stats = useAsync(reorderStats, []);
  const rows = (stats.data ?? []).filter((s) => (tab === "due" ? s.due : true));
  const fail = (m: string) => toast(m, "error");

  const replace = (s: ReorderStat) => stats.setData((xs) => xs?.map((x) => (x.customer_id === s.customer_id ? s : x)));

  return (
    <div>
      <PageHeader
        title="주문할 때 된 거래처"
        subtitle="평소 주문 간격보다 오래 소식이 없는 단골이에요. 안부 전화 한 통!"
        actions={
          <Button size="md" variant="ghost" icon={<RefreshCw className="h-5 w-5" />} loading={busy === "re"} onClick={() => run("re", async () => { const r = await reorderRecompute(); toast(`다시 계산했어요 (알림 ${r.due}곳)`); await stats.reload(); }, fail)}>
            다시 계산
          </Button>
        }
      />
      <Segmented className="mb-4" value={tab} onChange={setTab} options={[{ value: "due", label: `연락할 곳 ${stats.data?.filter((s) => s.due).length ?? ""}` }, { value: "all", label: "전체 거래처" }]} />
      <LoadState loading={stats.loading} error={stats.error} onRetry={stats.reload} />
      {!stats.loading && rows.length === 0 && <Empty>{tab === "due" ? "지금은 연락할 거래처가 없어요. 👍" : "거래처가 없어요."}</Empty>}
      {rows.map((s) => (
        <div key={s.customer_id} className={`mb-3 rounded-2xl border bg-white p-4 ${s.due ? "border-amber-300" : "border-line"}`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="text-lg font-extrabold">{s.customer_name}</div>
              <div className="text-sm text-stone-600">
                마지막 주문 {dateKo(s.last_order_date)}
                {s.days_since !== null && ` (${s.days_since}일 전)`}
                {s.avg_interval_days !== null && ` · 보통 ${s.avg_interval_days}일마다 · 주문 ${s.order_count}번`}
              </div>
              {s.last_items && <div className="mt-1 text-sm text-stone-500">지난번: {s.last_items}</div>}
            </div>
            {s.due ? <Badge tone="amber">{s.overdue_days > 0 ? `${s.overdue_days}일 늦음` : "연락 필요"}</Badge> : s.snoozed_until ? <Badge tone="gray">{dateKo(s.snoozed_until)}까지 보류</Badge> : null}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {s.phone && (
              <a href={telHref(s.phone)}>
                <Button size="md" icon={<PhoneCall className="h-5 w-5" />}>전화</Button>
              </a>
            )}
            <Link to={`/orders/new?customer=${s.customer_id}`}>
              <Button size="md" variant="ghost" icon={<ClipboardPaste className="h-5 w-5" />}>주문 넣기</Button>
            </Link>
            {s.due && (
              <Button size="md" variant="plain" icon={<BellOff className="h-5 w-5" />} loading={busy === s.customer_id} onClick={() => run(s.customer_id, async () => { replace(await reorderSnooze(s.customer_id, 7)); toast("일주일 뒤에 다시 알려 드릴게요."); }, fail)}>
                일주일 뒤에
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
