import type { Order } from "../api/types";

/** 웹 주문처럼 먼저 입금받는 주문인데 아직 입금 확인을 안 한 것 */
export function needsPayment(o: Order): boolean {
  return o.source === "웹주문서" && !o.paid_at && o.status !== "취소";
}

/** 상품 금액 + 배송비 (단가가 빠진 품목이 있으면 null) */
export function orderTotal(o: Order): number | null {
  return o.total_amount === null ? null : o.total_amount + (o.shipping_fee || 0);
}
