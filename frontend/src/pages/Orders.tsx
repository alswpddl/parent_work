import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { listOrders } from "../api/endpoints";
import type { Order } from "../api/types";
import OrderCard from "../components/OrderCard";
import OrderDetail from "../components/OrderDetail";
import { Button, Empty, Input, LoadState, PageHeader, Segmented } from "../components/ui";
import { useAsync, useAutoRefresh } from "../lib/hooks";

type Tab = "open" | "done" | "cancel" | "all";
const QUERY: Record<Tab, { status?: string; include_cancelled?: boolean }> = {
  open: { status: "접수,출고대기" },
  done: { status: "출고완료" },
  cancel: { status: "취소" },
  all: { include_cancelled: true },
};

export default function Orders() {
  const [tab, setTab] = useState<Tab>("open");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Order | null>(null);
  const orders = useAsync(() => listOrders(QUERY[tab]), [tab]);
  useAutoRefresh(() => !open && orders.refresh());  // 주문을 열어 보는 동안엔 멈춤

  const shown = useMemo(() => {
    const list = [...(orders.data ?? [])];
    if (tab !== "open") list.sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
    const nq = q.trim().replace(/\s/g, "");
    if (!nq) return list;
    return list.filter((o) => `${o.customer_name}${o.order_id}${o.recipient}${o.phone}${o.lines.map((l) => l.product_name).join("")}`.replace(/\s/g, "").includes(nq));
  }, [orders.data, q, tab]);

  const replace = (o: Order) => {
    orders.setData((xs) => xs?.map((x) => (x.order_id === o.order_id ? o : x)));
    setOpen(o);
  };

  return (
    <div>
      <PageHeader
        title="주문 목록"
        subtitle="주문을 누르면 수정·출고·취소할 수 있어요."
        actions={
          <Link to="/orders/new">
            <Button size="md" icon={<Plus className="h-5 w-5" />}>주문 넣기</Button>
          </Link>
        }
      />
      <Segmented
        className="mb-3"
        value={tab}
        onChange={setTab}
        options={[
          { value: "open", label: "출고 전" },
          { value: "done", label: "완료" },
          { value: "cancel", label: "취소" },
          { value: "all", label: "전체" },
        ]}
      />
      <div className="relative mb-4">
        <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-stone-400" />
        <Input className="pl-12" placeholder="거래처·품목·주문번호 찾기" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <LoadState loading={orders.loading} error={orders.error} onRetry={orders.reload} />
      {!orders.loading && shown.length === 0 && <Empty>해당하는 주문이 없어요.</Empty>}
      {shown.map((o) => (
        <OrderCard key={o.order_id} order={o} onOpen={() => setOpen(o)} />
      ))}
      {open && <OrderDetail order={open} onClose={() => setOpen(null)} onChanged={(o) => (tab === "open" && o.status === "출고완료" ? (orders.reload(), setOpen(o)) : replace(o))} />}
    </div>
  );
}
