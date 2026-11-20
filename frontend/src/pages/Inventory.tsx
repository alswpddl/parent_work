import { useState } from "react";
import { BellRing, History, PackagePlus, Pencil, Phone, Plus } from "lucide-react";
import { errorMessage } from "../api/client";
import { adjustStock, createInventoryItem, listInventory, receiveStock, stockCheck, stockMoves, updateInventoryItem } from "../api/endpoints";
import type { InventoryItem } from "../api/types";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Empty, Field, Input, LoadState, Modal, PageHeader, Spinner } from "../components/ui";
import { num, telHref } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

const STATUS_TONE = { 없음: "red", 부족: "red", 곧부족: "amber", 정상: "green" } as const;

export default function Inventory() {
  const toast = useToast();
  const { busy, run } = useAction();
  const items = useAsync(listInventory, []);
  const [receiveFor, setReceiveFor] = useState<InventoryItem | null>(null);
  const [adjustFor, setAdjustFor] = useState<InventoryItem | null>(null);
  const [editFor, setEditFor] = useState<InventoryItem | "new" | null>(null);
  const [movesFor, setMovesFor] = useState<InventoryItem | null>(null);

  const replace = (it: InventoryItem) => items.setData((xs) => (xs?.some((x) => x.item_id === it.item_id) ? xs.map((x) => (x.item_id === it.item_id ? it : x)) : [...(xs ?? []), it]));
  const lowCount = items.data?.filter((i) => i.status !== "정상").length ?? 0;

  return (
    <div>
      <PageHeader
        title="자재 재고"
        subtitle="출고 완료하면 용기·박스·라벨이 자동으로 빠져요. 입고되면 [입고]를 눌러 주세요."
        actions={
          <>
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
              자재 추가
            </Button>
          </>
        }
      />
      <LoadState loading={items.loading} error={items.error} onRetry={items.reload} />
      {lowCount > 0 && <Alert tone="warn">발주가 필요한 자재가 {lowCount}개 있어요.</Alert>}
      {items.data?.length === 0 && <Empty>등록된 자재가 없어요. [자재 추가]를 눌러 주세요.</Empty>}

      <div className="grid gap-3 md:grid-cols-2">
        {items.data?.map((i) => (
          <div key={i.item_id} className={`rounded-2xl border bg-white p-4 ${i.status === "정상" ? "border-line" : i.status === "곧부족" ? "border-amber-300" : "border-red-300"}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm text-stone-500">{i.category} · {i.item_id}</div>
                <div className="text-lg font-extrabold">{i.name}</div>
              </div>
              <Badge tone={STATUS_TONE[i.status]}>{i.status}</Badge>
            </div>
            <div className="mt-2 flex items-end gap-2">
              <span className="text-4xl font-extrabold">{num(i.stock)}</span>
              <span className="pb-1 text-stone-500">{i.unit} / 안전 {num(i.safety_stock)}</span>
            </div>
            <div className="mt-1 text-sm text-stone-600">
              {i.days_left !== null ? `하루 약 ${i.avg_daily_use}${i.unit} 사용 · ${i.days_left}일분 남음 · ${i.order_by}까지 발주` : "최근 30일 사용 기록 없음"}
            </div>
            {i.used_by.length > 0 && <div className="mt-1 text-sm text-stone-500">쓰는 품목: {i.used_by.join(", ")}</div>}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="md" icon={<PackagePlus className="h-5 w-5" />} onClick={() => setReceiveFor(i)}>
                입고
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

      {receiveFor && <ReceiveModal item={receiveFor} onClose={() => setReceiveFor(null)} onDone={(it) => { replace(it); setReceiveFor(null); toast("입고했어요."); }} />}
      {adjustFor && <AdjustModal item={adjustFor} onClose={() => setAdjustFor(null)} onDone={(it) => { replace(it); setAdjustFor(null); toast("재고를 고쳤어요."); }} />}
      {editFor && <EditModal item={editFor === "new" ? null : editFor} onClose={() => setEditFor(null)} onDone={(it) => { replace(it); setEditFor(null); toast("저장했어요."); }} />}
      {movesFor && <MovesModal item={movesFor} onClose={() => setMovesFor(null)} />}
    </div>
  );
}

function ReceiveModal({ item, onClose, onDone }: { item: InventoryItem; onClose: () => void; onDone: (i: InventoryItem) => void }) {
  const [qty, setQty] = useState(item.reorder_qty || 0);
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
      <Field label={`들어온 수량 (${item.unit})`}>
        <Input type="number" inputMode="numeric" value={qty} onChange={(e) => setQty(Math.max(0, Math.round(Number(e.target.value) || 0)))} autoFocus />
      </Field>
      <Field label="메모 (매입처 등)">
        <Input value={memo} onChange={(e) => setMemo(e.target.value)} />
      </Field>
      <p className="text-stone-500">입고 후 재고: {num(item.stock + qty)}{item.unit}</p>
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
      <p className="mb-3 text-stone-600">지금 화면상 재고는 {num(item.stock)}{item.unit}이에요. 실제로 센 수량을 넣어 주세요.</p>
      <Field label={`실제 수량 (${item.unit})`}>
        <Input type="number" inputMode="numeric" value={stock} onChange={(e) => setStock(Math.max(0, Math.round(Number(e.target.value) || 0)))} autoFocus />
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
    category: item?.category ?? "용기",
    name: item?.name ?? "",
    unit: item?.unit ?? "개",
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
      {!item && <Field label="자재코드" hint="비우면 M0001 처럼 자동. 품목 탭의 용기/박스/라벨자재 칸에 이 코드를 적어요."><Input value={v.item_id} onChange={(e) => set({ item_id: e.target.value })} /></Field>}
      <div className="grid gap-x-3 md:grid-cols-2">
        <Field label="이름"><Input value={v.name} onChange={(e) => set({ name: e.target.value })} /></Field>
        <Field label="분류"><Input value={v.category} onChange={(e) => set({ category: e.target.value })} placeholder="용기 / 박스 / 라벨" /></Field>
        <Field label="단위"><Input value={v.unit} onChange={(e) => set({ unit: e.target.value })} /></Field>
        {!item && <Field label="지금 재고"><Input type="number" value={v.stock} onChange={(e) => set({ stock: Number(e.target.value) || 0 })} /></Field>}
        <Field label="안전재고" hint="이 아래로 내려가면 경고"><Input type="number" value={v.safety_stock} onChange={(e) => set({ safety_stock: Number(e.target.value) || 0 })} /></Field>
        <Field label="한 번에 발주하는 양"><Input type="number" value={v.reorder_qty} onChange={(e) => set({ reorder_qty: Number(e.target.value) || 0 })} /></Field>
        <Field label="매입처"><Input value={v.supplier} onChange={(e) => set({ supplier: e.target.value })} /></Field>
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

