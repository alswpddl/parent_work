import type { ReactNode } from "react";
import type { Order } from "../api/types";
import { dateKo, isPast, kg } from "../lib/format";
import { needsPayment } from "../lib/orders";
import { Badge, MethodBadge, StatusBadge, cx } from "./ui";

export default function OrderCard({ order, onOpen, children, showMethod = true }: { order: Order; onOpen?: () => void; children?: ReactNode; showMethod?: boolean }) {
  const late = order.status !== "출고완료" && order.status !== "취소" && isPast(order.due_date);
  return (
    <div className={cx("mb-3 rounded-2xl border bg-white p-4", late ? "border-red-300" : "border-line")}>
      <button type="button" onClick={onOpen} className="block w-full text-left">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-lg font-extrabold">{order.customer_name}</div>
            <div className="truncate text-sm text-stone-500">{order.address || "주소 없음"}</div>
          </div>
          <div className="flex flex-wrap gap-1">
            {showMethod && <MethodBadge method={order.ship_method} />}
            {order.source === "웹주문서" && <Badge tone="violet">웹 주문</Badge>}
            {needsPayment(order) && <Badge tone="amber">입금 전</Badge>}
            {order.source === "웹주문서" && order.paid_at && <Badge tone="green">입금 완료</Badge>}
            {order.status !== "접수" && <StatusBadge status={order.status} />}
            <Badge tone={late ? "red" : "gray"}>{dateKo(order.due_date)}{late ? " 지남" : ""}</Badge>
          </div>
        </div>
        <ul className="mt-2 space-y-0.5">
          {order.lines.map((l) => (
            <li key={l.line_no} className="flex justify-between gap-2">
              <span>{l.product_name}</span>
              <b>{l.qty.toLocaleString("ko-KR")}개</b>
            </li>
          ))}
        </ul>
        <div className="mt-2 text-sm text-stone-500">
          {kg(order.order_kg)}
          {order.ship_method === "화물" ? ` · 파레트 ${order.pallets}` : ` · 박스 ${order.boxes}`}
          {order.source !== "카톡" && order.source !== "웹주문서" && ` · ${order.source}`}
          {order.note && ` · ${order.note}`}
          {order.tracking_no && ` · 송장 ${order.tracking_no}`}
          {order.truck_no && ` · 차량 ${order.truck_no}`}
        </div>
      </button>
      {children && <div className="mt-3 flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}
