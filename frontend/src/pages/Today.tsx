// 오늘의 할당량 — 부모님이 아침에 열어 보는 화면
// 1) 품목별로 몇 통 만들지 (크게)  2) 주문별 체크리스트 (다 만들면 체크 → 출고대기)  3) 출고 화면으로
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, Globe, Printer, Truck } from "lucide-react";
import { listOrders, stockNeeds, updateOrder } from "../api/endpoints";
import type { Order } from "../api/types";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Card, Empty, LoadState, MethodBadge, PageHeader, Segmented, cx } from "../components/ui";
import { dateKo, kg, num, todayIso } from "../lib/format";
import { useFeatures } from "../lib/features";
import { useAction, useAsync, useAutoRefresh } from "../lib/hooks";
import { needsPayment } from "../lib/orders";

type Range = "today" | "tomorrow" | "all";

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
  const [range, setRange] = useState<Range>("today");
  const list = useAsync(() => listOrders({ status: "접수,출고대기" }), []);
  const { has } = useFeatures();
  const needs = useAsync(
    () => (has("q4_inventory") ? stockNeeds(range === "today" ? todayIso() : range === "tomorrow" ? todayIso(1) : undefined) : Promise.resolve([])),
    [range],
  );
  useAutoRefresh(() => Promise.all([list.refresh(), needs.refresh()]));
  const all = useMemo(() => list.data ?? [], [list.data]);
  const today = todayIso();
  const until = range === "today" ? today : range === "tomorrow" ? todayIso(1) : null;

  const orders = useMemo(() => {
    const picked = all.filter((o) => (until === null ? true : o.due_date !== null && o.due_date <= until));
    // 늦은 것 → 날짜 빠른 것 → 날짜 미정 순서
    return [...picked].sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999") || a.order_id.localeCompare(b.order_id));
  }, [all, until]);
  const undated = all.filter((o) => !o.due_date).length;

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

  const toggle = (o: Order) =>
    run(o.order_id, async () => {
      const next = o.status === "출고대기" ? "접수" : "출고대기";
      const updated = await updateOrder(o.order_id, { status: next });
      list.setData((d) => d?.map((x) => (x.order_id === o.order_id ? updated : x)));
      toast(next === "출고대기" ? `${o.customer_name} 다 만들었어요 ✔` : `${o.customer_name} 체크를 풀었어요`);
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

      <Segmented
        className="no-print mb-4"
        value={range}
        onChange={setRange}
        options={[
          { value: "today", label: "오늘까지" },
          { value: "tomorrow", label: "내일까지" },
          { value: "all", label: "전부" },
        ]}
      />

      <LoadState loading={list.loading} error={list.error} onRetry={list.reload} />

      {list.data && (
        <>
          {orders.some(needsPayment) && (
            <Alert tone="warn" action={<Link to="/orders"><Button size="sm" variant="ghost">주문 목록</Button></Link>}>
              💰 입금 확인 안 된 웹 주문 {orders.filter(needsPayment).length}건 — 입금 확인 후 보내 주세요. (주문 목록에서 눌러 [입금 확인])
            </Alert>
          )}
          {range !== "all" && undated > 0 && (
            <Alert tone="info" action={<Button size="sm" variant="ghost" onClick={() => setRange("all")}>전부 보기</Button>}>
              받는 날이 안 정해진 주문 {undated}건은 '전부'에서 보여요.
            </Alert>
          )}

          <Card title="🔨 품목별로 만들 양">
            {lines.length === 0 ? (
              <Empty>{range === "today" ? "오늘 보낼 주문이 없어요. 푹 쉬세요 🙂" : "만들 주문이 없어요."}</Empty>
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
              title="🫙 저장고·자재 확인"
              actions={<Link to="/inventory" className="no-print"><Button size="sm" variant="ghost">재고 보기</Button></Link>}
            >
              {needs.data!.some((n) => n.short > 0) ? (
                <Alert tone="error">모자라는 게 있어요. 미리 담그거나 주문해 주세요.</Alert>
              ) : (
                <p className="mb-2 text-brand-dark">이 주문들을 다 보내도 재고가 충분해요 ✔</p>
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
              title={`📋 주문별 체크 (${ready}/${orders.length} 완료)`}
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
                          {o.note && <div className="mt-1 text-sm font-semibold text-amber-700">📝 {o.note}</div>}
                        </div>
                      </div>
                      <div className={cx("no-print mt-3 rounded-xl py-2.5 text-center font-bold", done ? "bg-white text-brand-dark" : "bg-brand text-white")}>
                        {done ? "완료 ✔ (다시 누르면 풀려요)" : "다 만들었으면 누르기"}
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
