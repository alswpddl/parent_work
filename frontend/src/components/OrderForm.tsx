// 주문 확인·수정 폼 (카톡 정리 결과 / 직접 입력 / 주문 수정 공용)
import { useMemo, useState } from "react";
import { AlertTriangle, Plus, Sparkles, Trash2 } from "lucide-react";
import type { Candidate, Customer, Order, OrderDraft, OrderInput, Product, ShipMethod } from "../api/types";
import { kg } from "../lib/format";
import { Alert, Badge, Button, Field, Input, Segmented, Select, Stepper, cx } from "./ui";

export interface FormItem {
  key: string;
  sku: string;
  qty: number;
  hint?: string; // 메시지에 적힌 원래 표현
  candidates?: Candidate[];
}

export interface OrderFormValue {
  customer_id: string;
  customer_name: string;
  recipient: string;
  phone: string;
  address: string;
  zipcode: string;
  due_date: string;
  note: string;
  items: FormItem[];
  ship_method: "" | ShipMethod; // "" = 자동
  raw_text: string;
}

let keySeq = 0;
const newKey = () => `i${++keySeq}`;

export function emptyForm(customer?: Customer): OrderFormValue {
  return {
    customer_id: customer?.customer_id ?? "",
    customer_name: customer?.name ?? "",
    recipient: customer ? customer.contact_name || customer.name : "",
    phone: customer?.phone ?? "",
    address: customer?.address ?? "",
    zipcode: customer?.zipcode ?? "",
    due_date: "",
    note: "",
    items: [{ key: newKey(), sku: "", qty: 1 }],
    ship_method: "",
    raw_text: "",
  };
}

export function draftToForm(d: OrderDraft): OrderFormValue {
  return {
    customer_id: d.customer.customer_id ?? "",
    customer_name: d.customer.name,
    recipient: d.recipient,
    phone: d.phone,
    address: d.address,
    zipcode: d.zipcode,
    due_date: d.due_date ?? "",
    note: d.note,
    items: d.items.length
      ? d.items.map((it) => ({ key: newKey(), sku: it.sku ?? "", qty: it.qty || 1, hint: it.matched ? undefined : it.raw_name, candidates: it.candidates }))
      : [{ key: newKey(), sku: "", qty: 1 }],
    ship_method: "",
    raw_text: d.raw_text,
  };
}

export function orderToForm(o: Order): OrderFormValue {
  return {
    customer_id: o.customer_id,
    customer_name: o.customer_name,
    recipient: o.recipient,
    phone: o.phone,
    address: o.address,
    zipcode: o.zipcode,
    due_date: o.due_date ?? "",
    note: o.note,
    items: o.lines.map((l) => ({ key: newKey(), sku: l.sku, qty: l.qty })),
    ship_method: o.method_by === "수동" ? o.ship_method : "",
    raw_text: o.raw_text,
  };
}

export function formToInput(v: OrderFormValue): OrderInput {
  return {
    customer_id: v.customer_id || null,
    customer_name: v.customer_name.trim(),
    recipient: v.recipient.trim(),
    phone: v.phone.trim(),
    address: v.address.trim(),
    zipcode: v.zipcode.trim(),
    due_date: v.due_date || null,
    note: v.note.trim(),
    items: v.items.filter((i) => i.sku && i.qty > 0).map((i) => ({ sku: i.sku, qty: i.qty })),
    ship_method: v.ship_method || null,
    raw_text: v.raw_text,
  };
}

export default function OrderForm({
  initial,
  customers,
  products,
  thresholdKg,
  submitLabel = "💾 주문 저장",
  onSubmit,
  onCancel,
  warnings = [],
  parser,
}: {
  initial: OrderFormValue;
  customers: Customer[];
  products: Product[];
  thresholdKg: number;
  submitLabel?: string;
  onSubmit: (v: OrderFormValue) => Promise<void>;
  onCancel?: () => void;
  warnings?: string[];
  parser?: string;
}) {
  const [v, setV] = useState<OrderFormValue>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pmap = useMemo(() => new Map(products.map((p) => [p.sku, p])), [products]);
  const customer = customers.find((c) => c.customer_id === v.customer_id);

  const totalKg = v.items.reduce((s, i) => s + i.qty * (pmap.get(i.sku)?.unit_kg ?? 0), 0);
  const autoMethod: ShipMethod =
    customer && customer.default_method !== "자동" ? customer.default_method : totalKg >= thresholdKg ? "화물" : "택배";
  const method = v.ship_method || autoMethod;
  const missingWeight = v.items.some((i) => i.sku && !(pmap.get(i.sku)?.unit_kg ?? 0));
  const totalAmount = v.items.reduce((s, i) => s + i.qty * (pmap.get(i.sku)?.unit_price ?? 0), 0);

  const set = (patch: Partial<OrderFormValue>) => setV((x) => ({ ...x, ...patch }));
  const setItem = (key: string, patch: Partial<FormItem>) => setV((x) => ({ ...x, items: x.items.map((i) => (i.key === key ? { ...i, ...patch } : i)) }));

  const pickCustomer = (id: string) => {
    const c = customers.find((x) => x.customer_id === id);
    if (!c) {
      set({ customer_id: "" });
      return;
    }
    set({
      customer_id: c.customer_id,
      customer_name: c.name,
      recipient: c.contact_name || c.name,
      phone: c.phone || v.phone,
      address: v.address && v.customer_id === "" && v.address !== c.address ? v.address : c.address,
      zipcode: c.zipcode,
    });
  };

  const submit = async () => {
    setError("");
    if (!v.customer_id && !v.customer_name.trim()) return setError("거래처를 골라 주세요.");
    if (!v.items.some((i) => i.sku && i.qty > 0)) return setError("품목과 수량을 넣어 주세요.");
    if (v.items.some((i) => !i.sku && i.qty > 0)) return setError("품목을 고르지 않은 줄이 있어요. 고르거나 지워 주세요.");
    setBusy(true);
    try {
      await onSubmit(v);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장하지 못했어요.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {parser === "ai" && (
        <Badge tone="violet" className="mb-3">
          <Sparkles className="h-4 w-4" /> AI가 정리했어요 — 틀린 곳만 고쳐 주세요
        </Badge>
      )}
      {warnings.map((w) => (
        <Alert key={w} tone="warn">
          <AlertTriangle className="mr-1 inline h-5 w-5" /> {w}
        </Alert>
      ))}

      <Field label="거래처">
        <Select value={v.customer_id} onChange={(e) => pickCustomer(e.target.value)}>
          <option value="">{v.customer_name && !v.customer_id ? `새 거래처: ${v.customer_name}` : "— 거래처 고르기 —"}</option>
          {customers.map((c) => (
            <option key={c.customer_id} value={c.customer_id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>
      {!v.customer_id && <Field label="거래처 이름 (등록 안 된 곳)"><Input value={v.customer_name} onChange={(e) => set({ customer_name: e.target.value })} /></Field>}

      <div className="grid gap-x-3 md:grid-cols-2">
        <Field label="받는 분">
          <Input value={v.recipient} onChange={(e) => set({ recipient: e.target.value })} />
        </Field>
        <Field label="전화번호">
          <Input inputMode="tel" value={v.phone} onChange={(e) => set({ phone: e.target.value })} />
        </Field>
      </div>
      <Field label="배송지 주소">
        <Input value={v.address} onChange={(e) => set({ address: e.target.value })} />
      </Field>
      <div className="grid gap-x-3 md:grid-cols-2">
        <Field label="받는 날 (납기)">
          <Input type="date" value={v.due_date} onChange={(e) => set({ due_date: e.target.value })} />
        </Field>
        <Field label="우편번호">
          <Input inputMode="numeric" value={v.zipcode} onChange={(e) => set({ zipcode: e.target.value })} />
        </Field>
      </div>
      <Field label="특이사항">
        <Input value={v.note} placeholder="예) 오전 배송, 문 앞에 두기" onChange={(e) => set({ note: e.target.value })} />
      </Field>

      <h3 className="mb-2 mt-5 text-lg font-extrabold">품목·수량</h3>
      {v.items.map((it) => (
        <div key={it.key} className="mb-3 rounded-2xl border border-line bg-white p-3">
          <div className="flex flex-col gap-2 md:flex-row md:items-center">
            <Select className={cx("min-w-0 md:flex-1", !it.sku && "border-amber-400")} value={it.sku} onChange={(e) => setItem(it.key, { sku: e.target.value, hint: undefined })}>
              <option value="">— 품목 고르기 —</option>
              {products.map((p) => (
                <option key={p.sku} value={p.sku}>
                  {p.name} {p.spec}
                </option>
              ))}
            </Select>
            <div className="flex items-center justify-between gap-2">
            <Stepper value={it.qty} onChange={(q) => setItem(it.key, { qty: q })} />
            <button aria-label="이 줄 지우기" className="rounded-xl p-3 text-stone-500 hover:bg-red-50 hover:text-red-700" onClick={() => setV((x) => ({ ...x, items: x.items.length > 1 ? x.items.filter((i) => i.key !== it.key) : x.items }))}>
              <Trash2 className="h-5 w-5" />
            </button>
            </div>
          </div>
          {it.hint && !it.sku && (
            <div className="mt-2 text-sm text-amber-800">
              메시지에 적힌 품목: “{it.hint}”
              {it.candidates && it.candidates.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {it.candidates.map((c) => (
                    <Button key={c.id} size="sm" variant="soft" onClick={() => setItem(it.key, { sku: c.id, hint: undefined })}>
                      {c.label}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
      <Button variant="ghost" size="md" icon={<Plus className="h-5 w-5" />} onClick={() => set({ items: [...v.items, { key: newKey(), sku: "", qty: 1 }] })}>
        품목 추가
      </Button>

      <div className="my-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-brand-soft px-4 py-4">
        <div>
          <div className="text-sm text-stone-600">총 무게</div>
          <div className="text-2xl font-extrabold">{kg(totalKg)}</div>
          {totalAmount > 0 && <div className="text-sm text-stone-600">공급가 {totalAmount.toLocaleString("ko-KR")}원</div>}
          {missingWeight && <div className="text-sm text-red-700">개당중량이 없는 품목이 있어요 (기본 정보 → 품목)</div>}
        </div>
        <Badge tone={method === "화물" ? "truck" : "parcel"} className="px-4 py-2 text-lg">
          {method === "화물" ? "🚚 화물 트럭" : "📦 택배"}
        </Badge>
      </div>
      <Segmented
        value={(v.ship_method || "auto") as "auto" | ShipMethod}
        onChange={(m) => set({ ship_method: m === "auto" ? "" : (m as ShipMethod) })}
        options={[
          { value: "auto", label: "자동" },
          { value: "택배", label: "📦 택배" },
          { value: "화물", label: "🚚 화물" },
        ]}
      />
      <p className="mb-5 mt-2 text-sm text-stone-500">
        {v.ship_method
          ? "직접 골랐어요."
          : customer && customer.default_method !== "자동"
            ? `${customer.name}은(는) 항상 ${customer.default_method}로 보내요.`
            : `${thresholdKg}kg 이상이면 화물로 자동 분류해요.`}
      </p>

      {error && <Alert tone="error">{error}</Alert>}
      <div className="flex gap-2">
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            취소
          </Button>
        )}
        <Button block loading={busy} onClick={submit}>
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
