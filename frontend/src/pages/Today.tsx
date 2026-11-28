// 오늘의 할당량 — 부모님이 아침에 열어 보는 화면
// 1) 품목별로 몇 통 만들지 (크게)  2) 주문별 체크리스트 (다 만들면 체크 → 출고대기)  3) 출고 화면으로
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, Globe, Printer, Truck } from "lucide-react";
import { getSettings, listOrders, stockNeeds, updateOrder } from "../api/endpoints";
import type { Order } from "../api/types";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Card, Empty, LoadState, MethodBadge, PageHeader, cx } from "../components/ui";
import { dateKo, kg, num, todayIso } from "../lib/format";
import { useFeatures } from "../lib/features";
import { useAction, useAsync, useAutoRefresh } from "../lib/hooks";
import { needsPayment } from "../lib/orders";


interface Line {
  key: string;
  name: string;
  qty: number;
  kg: number;
  orders: number;
  doneQty: number;
}

export default function Today() {
  const toast = useToast();
  const { busy, run } = useAction();
  const list = useAsync(() => listOrders({ status: "접수,출고대기" }), []);
  const { has } = useFeatures();
  const needs = useAsync(
    () => (has("q4_inventory") ? stockNeeds(undefined) : Promise.resolve([])),
    [],
  );
  const settings = useAsync(() => getSettings().catch(() => null), []);
  useAutoRefresh(() => Promise.all([list.refresh(), needs.refresh()]));
  const all = useMemo(() => list.data ?? [], [list.data]);
  const today = todayIso();

  const orders = useMemo(() => {
    // 받는 날(희망 배송일) 빠른 순 → 날짜 미정은 맨 아래
    return [...all].sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999") || a.order_id.localeCompare(b.order_id));
  }, [all]);

  const lines = useMemo(() => {
    const m = new Map<string, Line>();
    for (const o of orders)
      for (const l of o.lines) {
        const key = l.sku || l.product_name;
        const cur = m.get(key) ?? { key, name: l.product_name, qty: 0, kg: 0, orders: 0, doneQty: 0 };
        cur.qty += l.qty;
        cur.kg += l.line_kg;
        cur.orders += 1;
        if (o.status === "출고대기") cur.doneQty += l.qty;
        m.set(key, cur);
      }
    return [...m.values()].sort((a, b) => b.qty - a.qty);
  }, [orders]);

  const ready = orders.filter((o) => o.status === "출고대기").length;
  const totalKg = orders.reduce((a, o) => a + o.order_kg, 0);
  // 하루 최대 작업량 — 아직 안 만든(접수) 주문 무게가 넘치면 경고
  const capacity = settings.data?.daily_capacity_kg ?? 0;
  // 받는 날까지 남은 일수 × 하루 최대치보다 아직 안 만든 양이 많아지는 첫 날
  const overload = useMemo(() => {
    if (capacity <= 0) return null;
    let left = 0;
    for (const o of orders) {
      if (!o.due_date) break;
      if (o.status === "접수") left += o.order_kg;
      const days = Math.max(1, Math.round((Date.parse(o.due_date) - Date.parse(today)) / 86400000) + 1);
      if (left > capacity * days) return { date: o.due_date, kg: left, days };
    }
    return null;
  }, [orders, capacity, today]);

  const toggle = (o: Order) =>
    run(o.order_id, async () => {
      const next = o.status === "출고대기" ? "접수" : "출고대기";
      const updated = await updateOrder(o.order_id, { status: next });
      list.setData((d) => d?.map((x) => (x.order_id === o.order_id ? updated : x)));
      toast(next === "출고대기" ? `${o.customer_name} 다 만들었어요` : `${o.customer_name} 체크를 풀었어요`);
    }, (m) => toast(m, "error"));

  const d = new Date();
  const title = `${d.getMonth() + 1}월 ${d.getDate()}일 오늘의 할당량`;

  return (
    <div>
      <PageHeader
        title={title}
        subtitle="받는 날 기준으로 만들 물량이에요. 다 만든 주문은 체크해 두면 출고 화면에서 바로 보내요."
        actions={
          <Button size="md" variant="ghost" className="no-print" icon={<Printer className="h-5 w-5" />} onClick={() => window.print()}>
            인쇄
          </Button>
        }
      />

      <LoadState loading={list.loading} error={list.error} onRetry={list.reload} />

      {list.data && (
        <>
          {orders.some(needsPayment) && (
            <Alert tone="warn" action={<Link to="/orders"><Button size="sm" variant="ghost">주문 목록</Button></Link>}>
              입금 확인 안 된 웹 주문 {orders.filter(needsPayment).length}건 — 입금 확인 후 보내 주세요. (주문 목록에서 눌러 [입금 확인])
            </Alert>
          )}
          {overload && (
            <Alert tone="warn">
              {dateKo(overload.date)}까지 남은 작업 {kg(overload.kg)} — 하루 최대 {kg(capacity)}
              {overload.days > 1 ? ` × ${overload.days}일` : ""}보다 많아요. 미리 만들어 두거나 받는 날을 조정해 주세요.
            </Alert>
          )}

          <Card title="품목별로 만들 양">
            {lines.length === 0 ? (
              <Empty>만들 주문이 없어요. 푹 쉬세요.</Empty>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {lines.map((l) => (
                  <div key={l.key} className={cx("rounded-2xl border-2 bg-white p-4", l.doneQty >= l.qty ? "border-brand" : "border-line")}>
                    <div className="text-lg font-extrabold">{l.name}</div>
                    <div className="mt-1 flex items-baseline gap-2">
                      <span className="text-4xl font-extrabold text-brand">{num(l.qty)}</span>
                      <span className="text-lg font-bold">개</span>
                    </div>
                    <div className="text-sm text-stone-500">
                      {l.orders}건 · {kg(l.kg)}
                      {l.doneQty > 0 && <span className="font-semibold text-brand-dark"> · {num(l.doneQty)}개 완료</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {(needs.data?.length ?? 0) > 0 && (
            <Card
              title="저장고·자재 확인"
              actions={<Link to="/inventory" className="no-print"><Button size="sm" variant="ghost">재고 보기</Button></Link>}
            >
              {needs.data!.some((n) => n.short > 0) ? (
                <Alert tone="error">모자라는 게 있어요. 미리 담그거나 주문해 주세요.</Alert>
              ) : (
                <p className="mb-2 text-brand-dark">이 주문들을 다 보내도 재고가 충분해요.</p>
              )}
              <div className="divide-y divide-dashed divide-line">
                {needs.data!.map((n) => (
                  <div key={n.item_id} className="py-2">
                    <div className="flex items-center justify-between gap-2">
                      <b className="min-w-0 break-keep">{n.name}</b>
                      {n.short > 0 ? <Badge tone="red">{num(n.short)}{n.unit} 부족</Badge> : <span className="text-sm text-stone-400">{n.category}</span>}
                    </div>
                    <div className="text-sm text-stone-600">필요 {num(n.need)}{n.unit} · 남음 {num(n.stock)}{n.unit}</div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-sm text-stone-500">출고하면 자동으로 빠져요. 받는 날이 안 정해진 주문도 포함해서 계산해요.</p>
            </Card>
          )}

          {orders.length > 0 && (
            <Card
              title={`주문별 체크 (${ready}/${orders.length} 완료)`}
              actions={
                <Link to="/shipping" className="no-print">
                  <Button size="sm" variant="ghost" icon={<Truck className="h-4 w-4" />}>출고하러 가기</Button>
                </Link>
              }
            >
              <div className="mb-3 h-3 overflow-hidden rounded-full bg-stone-200">
                <div className="h-full bg-brand transition-all" style={{ width: `${orders.length ? (ready / orders.length) * 100 : 0}%` }} />
              </div>
              <p className="mb-3 text-sm text-stone-500">총 {orders.length}건 · {kg(totalKg)}</p>
              <div className="space-y-2">
                {orders.map((o) => {
                  const done = o.status === "출고대기";
                  const late = !!o.due_date && o.due_date < today;
                  return (
                    <button
                      key={o.order_id}
                      disabled={busy === o.order_id}
                      onClick={() => toggle(o)}
                      className={cx(
                        "block w-full rounded-2xl border-2 p-4 text-left transition disabled:opacity-60",
                        done ? "border-brand bg-brand-soft/60" : late ? "border-red-300 bg-red-50" : "border-line bg-white",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        {done ? <CheckCircle2 className="h-8 w-8 shrink-0 text-brand" /> : <Circle className="h-8 w-8 shrink-0 text-stone-300" />}
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className={cx("mr-1 text-lg font-extrabold", done && "line-through decoration-2 opacity-70")}>{o.customer_name}</span>
                            <MethodBadge method={o.ship_method} />
                            {o.source === "웹주문서" && <Badge tone="violet"><Globe className="mr-1 inline h-3.5 w-3.5" />웹 주문</Badge>}
                            {needsPayment(o) && <Badge tone="amber">입금 전</Badge>}
                            {late && <Badge tone="red">늦음</Badge>}
                          </div>
                          <ul className="mt-2 space-y-0.5">
                            {o.lines.map((l) => (
                              <li key={l.line_no} className="flex justify-between gap-3 text-[17px] font-semibold">
                                <span>{l.product_name}</span>
                                <span className="whitespace-nowrap">{num(l.qty)}개</span>
                              </li>
                            ))}
                          </ul>
                          <div className="mt-1 text-sm text-stone-500">
                            받는 날 {dateKo(o.due_date)} · {kg(o.order_kg)}
                          </div>
                          {o.note && <div className="mt-1 text-sm font-semibold text-amber-700">요청: {o.note}</div>}
                        </div>
                      </div>
                      <div className={cx("no-print mt-3 rounded-xl py-2.5 text-center font-bold", done ? "bg-white text-brand-dark" : "bg-brand text-white")}>
                        {done ? "완료 (다시 누르면 풀려요)" : "다 만들었으면 누르기"}
                      </div>
                    </button>
                  );
                })}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
