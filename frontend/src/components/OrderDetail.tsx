// 주문 한 건 자세히 보기 + 수정·출고·취소·알림톡
import { useState } from "react";
import { Bell, Banknote, PackageCheck, Pencil, Phone, RotateCcw, XCircle } from "lucide-react";
import { errorMessage } from "../api/client";
import { cancelOrder, getSettings, listCustomers, listMessages, listProducts, notifyResend, setOrderPaid, shipOrder, unshipOrder, updateOrder } from "../api/endpoints";
import type { Order } from "../api/types";
import { useFeatures } from "../lib/features";
import { dateKo, dateTimeKo, kg, telHref, won } from "../lib/format";
import { needsPayment, orderTotal } from "../lib/orders";
import { useAction, useAsync } from "../lib/hooks";
import OrderForm, { formToInput, orderToForm } from "./OrderForm";
import { useToast } from "./Toast";
import { Badge, Button, ConfirmButton, KV, MethodBadge, Modal, StatusBadge } from "./ui";

export default function OrderDetail({ order, onClose, onChanged }: { order: Order; onClose: () => void; onChanged: (o: Order) => void }) {
  const toast = useToast();
  const { has } = useFeatures();
  const { busy, run } = useAction();
  const [editing, setEditing] = useState(false);
  const masters = useAsync(() => (editing ? Promise.all([listCustomers(), listProducts(), getSettings()]) : Promise.resolve(null)), [editing]);
  const logs = useAsync(() => (has("q3_notify") || has("q2_briefing") ? listMessages(order.order_id, 20) : Promise.resolve([])), [order.order_id]);
  const fail = (m: string) => toast(m, "error");
  const act = (key: string, fn: () => Promise<Order>, msg: string) =>
    run(key, async () => {
      const o = await fn();
      onChanged(o);
      toast(msg);
    }, fail);

  const closed = order.status === "출고완료" || order.status === "취소";

  return (
    <Modal
      open
      onClose={onClose}
      wide={editing}
      title={
        <span className="flex flex-wrap items-center gap-2">
          {order.customer_name} <MethodBadge method={order.ship_method} /> <StatusBadge status={order.status} />
        </span>
      }
      footer={
        !editing && (
          <>
            {needsPayment(order) && (
              <Button variant="soft" icon={<Banknote className="h-5 w-5" />} loading={busy === "paid"} onClick={() => act("paid", () => setOrderPaid(order.order_id, true), "입금 확인했어요.")}>
                입금 확인
              </Button>
            )}
            {!closed && (
              <Button icon={<PackageCheck className="h-5 w-5" />} loading={busy === "ship"} onClick={() => act("ship", () => shipOrder(order.order_id), "출고 완료로 바꿨어요.")}>
                출고 완료
              </Button>
            )}
            {order.status === "출고완료" && (
              <Button variant="ghost" icon={<RotateCcw className="h-5 w-5" />} loading={busy === "unship"} onClick={() => act("unship", () => unshipOrder(order.order_id), "대기로 되돌렸어요.")}>
                대기로 되돌리기
              </Button>
            )}
            {!closed && (
              <Button variant="ghost" icon={<Pencil className="h-5 w-5" />} onClick={() => setEditing(true)}>
                수정
              </Button>
            )}
            {order.status === "접수" && (
              <Button variant="soft" loading={busy === "ready"} onClick={() => act("ready", () => updateOrder(order.order_id, { status: "출고대기" }), "생산 완료 · 출고대기로 바꿨어요.")}>
                생산 완료
              </Button>
            )}
            {has("q3_notify") && order.status === "출고완료" && (
              <Button
                variant="ghost"
                icon={<Bell className="h-5 w-5" />}
                loading={busy === "notify"}
                onClick={() =>
                  run("notify", async () => {
                    const r = await notifyResend(order.order_id);
                    toast(r.sent ? "알림톡을 보냈어요." : `못 보냈어요: ${r.reason}`, r.sent ? "ok" : "error");
                    void logs.reload();
                  }, fail)
                }
              >
                알림톡 다시 보내기
              </Button>
            )}
            {order.status !== "취소" && (
              <ConfirmButton variant="danger" icon={<XCircle className="h-5 w-5" />} confirmText="정말 취소할까요?" onConfirm={() => act("cancel", () => cancelOrder(order.order_id), "주문을 취소했어요.")}>
                주문 취소
              </ConfirmButton>
            )}
          </>
        )
      }
    >
      {editing ? (
        masters.data ? (
          <OrderForm
            initial={orderToForm(order)}
            customers={masters.data[0]}
            products={masters.data[1]}
            thresholdKg={masters.data[2].threshold_kg}
            submitLabel="수정 저장"
            onCancel={() => setEditing(false)}
            onSubmit={async (v) => {
              const input = formToInput(v);
              try {
                const o = await updateOrder(order.order_id, { ...input, auto_method: !v.ship_method });
                onChanged(o);
                setEditing(false);
                toast("수정했어요.");
              } catch (e) {
                throw new Error(errorMessage(e));
              }
            }}
          />
        ) : (
          <p className="text-stone-500">불러오는 중…</p>
        )
      ) : (
        <div>
          <div className="mb-4 rounded-2xl bg-white p-4">
            {order.lines.map((l) => (
              <div key={l.line_no} className="flex justify-between gap-3 border-b border-dashed border-line py-2 last:border-0">
                <span className="font-semibold">{l.product_name}</span>
                <span className="font-extrabold">{l.qty.toLocaleString("ko-KR")}개</span>
              </div>
            ))}
          </div>
          <KV k="주문번호" v={order.order_id} />
          <KV k="경로" v={order.source} />
          <KV k="받는 날" v={dateKo(order.due_date)} />
          <KV
            k="받는 분"
            v={
              <span>
                {order.recipient || "-"}{" "}
                {order.phone && (
                  <a href={telHref(order.phone)} className="inline-flex items-center gap-1 text-parcel underline">
                    <Phone className="h-4 w-4" />
                    {order.phone}
                  </a>
                )}
              </span>
            }
          />
          <KV k="주소" v={order.address || "-"} />
          <KV k="무게" v={`${kg(order.order_kg)}${order.ship_method === "화물" ? ` · 파레트 ${order.pallets}` : ` · 박스 ${order.boxes}`}`} />
          {order.total_amount !== null && <KV k={order.source === "웹주문서" ? "상품 금액" : "공급가"} v={won(order.total_amount)} />}
          {order.shipping_fee > 0 && <KV k="택배비" v={won(order.shipping_fee)} />}
          {order.source === "웹주문서" && orderTotal(order) !== null && <KV k="받을 돈" v={<b className="text-lg">{won(orderTotal(order)!)}</b>} />}
          {order.source === "웹주문서" && (
            <KV
              k="입금"
              v={
                order.paid_at ? (
                  <span>
                    {dateTimeKo(order.paid_at)} 확인{" "}
                    {order.status !== "취소" && (
                      <button className="ml-1 text-sm text-stone-500 underline" onClick={() => act("unpaid", () => setOrderPaid(order.order_id, false), "입금 확인을 취소했어요.")}>
                        취소
                      </button>
                    )}
                  </span>
                ) : (
                  <Badge tone="amber">아직 확인 안 함</Badge>
                )
              }
            />
          )}
          {order.note && <KV k="특이사항" v={order.note} />}
          {order.tracking_no && <KV k="송장" v={`${order.carrier} ${order.tracking_no}`} />}
          {order.truck_no && <KV k="차량" v={`${order.truck_no} ${order.driver_phone}`} />}
          {order.shipped_at && <KV k="출고" v={dateTimeKo(order.shipped_at)} />}
          {order.notified_at && <KV k="알림톡" v={dateTimeKo(order.notified_at)} />}
          {order.settlement_id && <KV k="정산" v={order.settlement_id} />}
          {order.raw_text && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-stone-500">카톡 원문 보기</summary>
              <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-white p-3 font-sans text-sm">{order.raw_text}</pre>
            </details>
          )}
          {(logs.data?.length ?? 0) > 0 && (
            <div className="mt-4">
              <h3 className="mb-2 font-bold">발송 기록</h3>
              {logs.data!.map((m, i) => (
                <div key={i} className="mb-2 rounded-xl bg-white p-3 text-sm">
                  <div className="flex justify-between gap-2">
                    <span>{m.ts} · {m.kind}</span>
                    <Badge tone={m.result === "성공" ? "green" : m.result === "실패" ? "red" : "gray"}>{m.result}</Badge>
                  </div>
                  {m.error && <div className="mt-1 text-red-700">{m.error}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
