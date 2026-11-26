import { useMemo, useState } from "react";
import { BellRing, ClipboardList, History, PackagePlus, Pencil, Phone, Plus } from "lucide-react";
import { errorMessage } from "../api/client";
import { adjustStock, createInventoryItem, listInventory, receiveStock, stockCheck, stockMoves, stocktake, updateInventoryItem } from "../api/endpoints";
import type { InventoryItem } from "../api/types";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Empty, Field, Input, LoadState, Modal, PageHeader, Select, Spinner } from "../components/ui";
import { num, telHref } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

const STATUS_TONE = { 없음: "red", 부족: "red", 곧부족: "amber", 정상: "green" } as const;

// 분류 순서와 기본 단위 — 처음 추가할 때 고르기 쉽게
export const CATEGORIES = [
  { name: "저장고", unit: "kg", hint: "담아 둔 젓갈 (kg)" },
  { name: "용기", unit: "개", hint: "통·말통 (크기별로 따로)" },
  { name: "뚜껑", unit: "개", hint: "통·말통 뚜껑" },
  { name: "라벨", unit: "장", hint: "라벨지·스티커" },
  { name: "박스", unit: "개", hint: "택배 박스" },
  { name: "기타", unit: "개", hint: "아이스팩·테이프 등" },
] as const;
const CAT_ORDER: string[] = CATEGORIES.map((c) => c.name);
const catRank = (c: string) => (CAT_ORDER.includes(c) ? CAT_ORDER.indexOf(c) : CAT_ORDER.length);
/** 저장고(kg)는 소수점, 나머지는 정수 */
const isDecimal = (unit: string) => /kg|g|리터|L/i.test(unit);
const clean = (v: number, unit: string) => (isDecimal(unit) ? Math.round(v * 1000) / 1000 : Math.round(v));

export default function Inventory() {
  const toast = useToast();
  const { busy, run } = useAction();
  const items = useAsync(listInventory, []);
  const [receiveFor, setReceiveFor] = useState<InventoryItem | null>(null);
  const [adjustFor, setAdjustFor] = useState<InventoryItem | null>(null);
  const [editFor, setEditFor] = useState<InventoryItem | "new" | null>(null);
  const [movesFor, setMovesFor] = useState<InventoryItem | null>(null);
  const [countAll, setCountAll] = useState(false);

  const replace = (it: InventoryItem) => items.setData((xs) => (xs?.some((x) => x.item_id === it.item_id) ? xs.map((x) => (x.item_id === it.item_id ? it : x)) : [...(xs ?? []), it]));
  const lowCount = items.data?.filter((i) => i.status !== "정상").length ?? 0;
  const groups = useMemo(() => {
    const m = new Map<string, InventoryItem[]>();
    for (const i of items.data ?? []) m.set(i.category, [...(m.get(i.category) ?? []), i]);
    return [...m.entries()].sort((a, b) => catRank(a[0]) - catRank(b[0]) || a[0].localeCompare(b[0]));
  }, [items.data]);
  const bulk = (items.data ?? []).filter((i) => i.category === "저장고");

  return (
    <div>
      <PageHeader
        title="재고"
        subtitle="출고 완료하면 통·뚜껑·라벨·박스와 저장고 젓갈(kg)이 자동으로 빠져요. 들어오면 [입고], 세어 보면 [실사]."
        actions={
          <>
            <Button size="md" variant="soft" icon={<ClipboardList className="h-5 w-5" />} disabled={!items.data?.length} onClick={() => setCountAll(true)}>
              재고 한꺼번에 입력
            </Button>
            <Button
              size="md"
              variant="ghost"
              icon={<BellRing className="h-5 w-5" />}
              loading={busy === "check"}
              onClick={() =>
                run("check", async () => {
                  const r = await stockCheck();
                  toast(r.alerted ? `부족 자재 ${r.alerted}개를 카톡으로 알렸어요.` : r.low ? `부족 ${r.low}개 (${r.reason ?? "알림 안 보냄"})` : "부족한 자재가 없어요.");
                }, (m) => toast(m, "error"))
              }
            >
              점검·카톡 경고
            </Button>
            <Button size="md" icon={<Plus className="h-5 w-5" />} onClick={() => setEditFor("new")}>
              추가
            </Button>
          </>
        }
      />
      <LoadState loading={items.loading} error={items.error} onRetry={items.reload} />
      {lowCount > 0 && <Alert tone="warn">보충·발주가 필요한 게 {lowCount}개 있어요.</Alert>}
      {items.data?.length === 0 && <Empty>등록된 재고가 없어요. [추가]를 눌러 저장고 젓갈·통·뚜껑·라벨을 넣어 주세요.</Empty>}

      {bulk.length > 0 && (
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3">
          {bulk.map((i) => (
            <button key={i.item_id} onClick={() => setAdjustFor(i)} className={`rounded-2xl p-4 text-left text-white ${i.status === "정상" ? "bg-brand" : i.status === "곧부족" ? "bg-amber-600" : "bg-red-600"}`}>
              <div className="truncate text-sm opacity-90">🫙 {i.name.replace(/\s*저장고$/, "")}</div>
              <div className="text-3xl font-extrabold">{num(i.stock)}<span className="ml-1 text-lg">{i.unit}</span></div>
              <div className="text-xs opacity-90">{i.days_left !== null ? `약 ${i.days_left}일분` : "저장고"}{i.status !== "정상" ? ` · ${i.status}` : ""}</div>
            </button>
          ))}
        </div>
      )}

      {groups.map(([cat, list]) => (
        <section key={cat} className="mb-6">
          <h2 className="mb-2 text-xl font-extrabold">
            {cat} <span className="text-base font-semibold text-stone-500">{list.length}</span>
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {list.map((i) => (
              <div key={i.item_id} className={`rounded-2xl border bg-white p-4 ${i.status === "정상" ? "border-line" : i.status === "곧부족" ? "border-amber-300" : "border-red-300"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm text-stone-500">{i.item_id}</div>
                    <div className="text-lg font-extrabold">{i.name}</div>
                  </div>
                  <Badge tone={STATUS_TONE[i.status]}>{i.status}</Badge>
                </div>
                <div className="mt-2 flex items-end gap-2">
                  <span className="text-4xl font-extrabold">{num(i.stock)}</span>
                  <span className="pb-1 text-stone-500">{i.unit} / 안전 {num(i.safety_stock)}</span>
                </div>
                <div className="mt-1 text-sm text-stone-600">
                  {i.days_left !== null ? `하루 약 ${num(i.avg_daily_use)}${i.unit} 사용 · ${i.days_left}일분 남음 · ${i.order_by}까지 ${cat === "저장고" ? "보충" : "발주"}` : "최근 30일 사용 기록 없음"}
                </div>
                {i.used_by.length > 0 ? (
                  <div className="mt-1 text-sm text-stone-500">쓰는 품목: {i.used_by.join(", ")}</div>
                ) : (
                  <div className="mt-1 text-sm text-amber-700">아직 연결된 품목이 없어 출고해도 자동으로 안 빠져요 (설정 → 품목에서 연결)</div>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="md" icon={<PackagePlus className="h-5 w-5" />} onClick={() => setReceiveFor(i)}>
                    {cat === "저장고" ? "담그기·입고" : "입고"}
                  </Button>
                  <Button size="md" variant="ghost" onClick={() => setAdjustFor(i)}>
                    실사
                  </Button>
                  <Button size="md" variant="plain" icon={<Pencil className="h-4 w-4" />} onClick={() => setEditFor(i)}>
                    수정
                  </Button>
                  <Button size="md" variant="plain" icon={<History className="h-4 w-4" />} onClick={() => setMovesFor(i)}>
                    기록
                  </Button>
                  {i.supplier_phone && (
                    <a href={telHref(i.supplier_phone)}>
                      <Button size="md" variant="soft" icon={<Phone className="h-4 w-4" />}>{i.supplier || "매입처"}</Button>
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      {receiveFor && <ReceiveModal item={receiveFor} onClose={() => setReceiveFor(null)} onDone={(it) => { replace(it); setReceiveFor(null); toast("입고했어요."); }} />}
      {adjustFor && <AdjustModal item={adjustFor} onClose={() => setAdjustFor(null)} onDone={(it) => { replace(it); setAdjustFor(null); toast("재고를 고쳤어요."); }} />}
      {editFor && <EditModal item={editFor === "new" ? null : editFor} onClose={() => setEditFor(null)} onDone={(it) => { replace(it); setEditFor(null); toast("저장했어요."); }} />}
      {movesFor && <MovesModal item={movesFor} onClose={() => setMovesFor(null)} />}
      {countAll && items.data && (
        <CountAllModal
          items={items.data}
          onClose={() => setCountAll(false)}
          onDone={(xs, changed) => {
            items.setData(xs);
            setCountAll(false);
            toast(changed ? `${changed}개 재고를 고쳤어요.` : "바뀐 게 없어요.");
          }}
        />
      )}
    </div>
  );
}

/** 재고 조사: 전부 한 화면에서 센 숫자를 넣고 한 번에 저장 */
function CountAllModal({ items, onClose, onDone }: { items: InventoryItem[]; onClose: () => void; onDone: (xs: InventoryItem[], changed: number) => void }) {
  const sorted = [...items].sort((a, b) => catRank(a.category) - catRank(b.category) || a.name.localeCompare(b.name));
  const [vals, setVals] = useState<Record<string, string>>(() => Object.fromEntries(items.map((i) => [i.item_id, String(i.stock)])));
  const [reason, setReason] = useState("재고 조사");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const changed = sorted.filter((i) => vals[i.item_id] !== "" && Number(vals[i.item_id]) !== i.stock);
  let lastCat = "";
  return (
    <Modal
      open
      wide
      onClose={onClose}
      title="재고 한꺼번에 입력"
      footer={
        <Button
          block
          loading={busy}
          disabled={!changed.length || !reason.trim()}
          onClick={async () => {
            setBusy(true);
            setErr("");
            try {
              const counts = Object.fromEntries(changed.map((i) => [i.item_id, clean(Number(vals[i.item_id]), i.unit)]));
              const r = await stocktake(counts, reason.trim());
              onDone(r.items, r.changed);
            } catch (e) {
              setErr(errorMessage(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {changed.length ? `${changed.length}개 저장` : "바뀐 숫자가 없어요"}
        </Button>
      }
    >
      <p className="mb-3 text-stone-600">창고에서 실제로 센 숫자로 고쳐 주세요. 그대로인 건 건드리지 않아도 돼요.</p>
      {err && <Alert tone="error">{err}</Alert>}
      <div className="divide-y divide-dashed divide-line">
        {sorted.map((i) => {
          const head = i.category !== lastCat;
          lastCat = i.category;
          const v = vals[i.item_id];
          const diff = v === "" ? 0 : clean(Number(v) - i.stock, i.unit);
          return (
            <div key={i.item_id}>
              {head && <h3 className="pb-1 pt-4 text-lg font-extrabold first:pt-0">{i.category}</h3>}
              <label className="flex items-center gap-3 py-2">
                <span className="min-w-0 flex-1 break-keep">
                  <span className="block font-semibold">{i.name}</span>
                  <span className="text-sm text-stone-500">
                    화면상 {num(i.stock)}{i.unit}
                    {diff !== 0 && <b className={diff < 0 ? "text-red-700" : "text-brand"}> → {diff > 0 ? "+" : ""}{num(diff)}</b>}
                  </span>
                </span>
                <div className="w-28 shrink-0">
                <Input
                  className="text-right"
                  type="number"
                  inputMode={isDecimal(i.unit) ? "decimal" : "numeric"}
                  step={isDecimal(i.unit) ? "0.1" : "1"}
                  min={0}
                  value={v}
                  onChange={(e) => setVals({ ...vals, [i.item_id]: e.target.value })}
                />
                </div>
                <span className="w-8 shrink-0 text-stone-500">{i.unit}</span>
              </label>
            </div>
          );
        })}
      </div>
      <Field label="메모">
        <Input value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </Modal>
  );
}

function ReceiveModal({ item, onClose, onDone }: { item: InventoryItem; onClose: () => void; onDone: (i: InventoryItem) => void }) {
  const [qty, setQty] = useState(item.category === "저장고" ? 0 : item.reorder_qty || 0);
  const [memo, setMemo] = useState(item.supplier);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  return (
    <Modal
      open
      onClose={onClose}
      title={`입고 · ${item.name}`}
      footer={
        <Button block loading={busy} disabled={qty < 1} onClick={async () => {
          setBusy(true);
          try { onDone(await receiveStock(item.item_id, qty, memo)); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
        }}>
          {num(qty)}{item.unit} 입고
        </Button>
      }
    >
      {err && <Alert tone="error">{err}</Alert>}
      <Field label={item.category === "저장고" ? `새로 담근 양 (${item.unit})` : `들어온 수량 (${item.unit})`}>
        <Input type="number" inputMode={isDecimal(item.unit) ? "decimal" : "numeric"} step={isDecimal(item.unit) ? "0.1" : "1"} value={qty} onChange={(e) => setQty(Math.max(0, clean(Number(e.target.value) || 0, item.unit)))} autoFocus />
      </Field>
      <Field label="메모 (매입처 등)">
        <Input value={memo} onChange={(e) => setMemo(e.target.value)} />
      </Field>
      <p className="text-stone-500">입고 후 재고: {num(clean(item.stock + qty, item.unit))}{item.unit}</p>
    </Modal>
  );
}

function AdjustModal({ item, onClose, onDone }: { item: InventoryItem; onClose: () => void; onDone: (i: InventoryItem) => void }) {
  const [stock, setStock] = useState(item.stock);
  const [reason, setReason] = useState("실제로 세어 봄");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  return (
    <Modal
      open
      onClose={onClose}
      title={`실사 · ${item.name}`}
      footer={
        <Button block loading={busy} disabled={!reason.trim()} onClick={async () => {
          setBusy(true);
          try { onDone(await adjustStock(item.item_id, stock, reason)); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
        }}>
          재고를 {num(stock)}{item.unit}로 고치기
        </Button>
      }
    >
      {err && <Alert tone="error">{err}</Alert>}
      <p className="mb-3 text-stone-600">지금 화면상 재고는 {num(item.stock)}{item.unit}이에요. {item.category === "저장고" ? "저장고에 실제로 남은 양(kg)" : "실제로 센 수량"}을 넣어 주세요.</p>
      <Field label={`실제 수량 (${item.unit})`}>
        <Input type="number" inputMode={isDecimal(item.unit) ? "decimal" : "numeric"} step={isDecimal(item.unit) ? "0.1" : "1"} value={stock} onChange={(e) => setStock(Math.max(0, clean(Number(e.target.value) || 0, item.unit)))} autoFocus />
      </Field>
      <Field label="이유">
        <Input value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </Modal>
  );
}

function EditModal({ item, onClose, onDone }: { item: InventoryItem | null; onClose: () => void; onDone: (i: InventoryItem) => void }) {
  const [v, setV] = useState({
    item_id: item?.item_id ?? "",
    category: item?.category ?? "저장고",
    name: item?.name ?? "",
    unit: item?.unit ?? "kg",
    stock: item?.stock ?? 0,
    safety_stock: item?.safety_stock ?? 0,
    reorder_qty: item?.reorder_qty ?? 0,
    supplier: item?.supplier ?? "",
    supplier_phone: item?.supplier_phone ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  const save = async () => {
    setBusy(true);
    try {
      if (item) {
        const { item_id: _id, stock: _s, ...patch } = v;
        void _id;
        void _s;
        onDone(await updateInventoryItem(item.item_id, patch));
      } else onDone(await createInventoryItem({ ...v, item_id: v.item_id || undefined }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open onClose={onClose} title={item ? `자재 수정 · ${item.name}` : "자재 추가"} footer={<Button block loading={busy} disabled={!v.name.trim()} onClick={save}>저장</Button>}>
      {err && <Alert tone="error">{err}</Alert>}
      <Field label="분류">
        <Select
          value={CAT_ORDER.includes(v.category) ? v.category : "기타"}
          onChange={(e) => {
            const c = CATEGORIES.find((x) => x.name === e.target.value)!;
            set({ category: c.name, unit: item ? v.unit : c.unit });
          }}
        >
          {CATEGORIES.map((c) => (
            <option key={c.name} value={c.name}>{c.name} — {c.hint}</option>
          ))}
        </Select>
      </Field>
      <div className="grid gap-x-3 md:grid-cols-2">
        <Field label="이름" hint={v.category === "저장고" ? "예) 새우젓(추젓) 저장고" : v.category === "용기" ? "예) 9kg 말통 / 1kg 통" : v.category === "뚜껑" ? "예) 말통 뚜껑" : undefined}>
          <Input value={v.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label="단위"><Input value={v.unit} onChange={(e) => set({ unit: e.target.value })} /></Field>
        {!item && (
          <Field label={`지금 재고 (${v.unit})`}>
            <Input type="number" inputMode={isDecimal(v.unit) ? "decimal" : "numeric"} step={isDecimal(v.unit) ? "0.1" : "1"} value={v.stock} onChange={(e) => set({ stock: Number(e.target.value) || 0 })} />
          </Field>
        )}
        {!item && <Field label="코드" hint="비우면 M0001 처럼 자동"><Input value={v.item_id} onChange={(e) => set({ item_id: e.target.value })} /></Field>}
        <Field label="안전재고" hint="이 아래로 내려가면 경고"><Input type="number" value={v.safety_stock} onChange={(e) => set({ safety_stock: Number(e.target.value) || 0 })} /></Field>
        <Field label={v.category === "저장고" ? "한 번에 담그는 양" : "한 번에 발주하는 양"}><Input type="number" value={v.reorder_qty} onChange={(e) => set({ reorder_qty: Number(e.target.value) || 0 })} /></Field>
        <Field label={v.category === "저장고" ? "원료 매입처" : "매입처"}><Input value={v.supplier} onChange={(e) => set({ supplier: e.target.value })} /></Field>
        <Field label="매입처 전화"><Input inputMode="tel" value={v.supplier_phone} onChange={(e) => set({ supplier_phone: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}

function MovesModal({ item, onClose }: { item: InventoryItem; onClose: () => void }) {
  const moves = useAsync(() => stockMoves(item.item_id, 100), [item.item_id]);
  return (
    <Modal open onClose={onClose} title={`입출고 기록 · ${item.name}`}>
      {moves.loading && <Spinner />}
      {moves.data?.length === 0 && <Empty>기록이 없어요.</Empty>}
      {moves.data?.map((m, i) => (
        <div key={i} className="flex items-center justify-between gap-3 border-b border-dashed border-line py-2">
          <div>
            <div className="text-sm text-stone-500">{m.ts}</div>
            <div>{m.reason}{m.order_id && <span className="text-sm text-stone-500"> · {m.order_id}</span>}</div>
          </div>
          <div className="text-right">
            <div className={`font-extrabold ${m.change < 0 ? "text-red-700" : "text-brand"}`}>{m.change > 0 ? "+" : ""}{num(m.change)}</div>
            <div className="text-sm text-stone-500">→ {num(m.stock_after)}</div>
          </div>
        </div>
      ))}
    </Modal>
  );
}

