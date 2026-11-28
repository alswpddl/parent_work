// 숙성 저장소 지도 — 건물(사각형) 안에 저장소(동그라미)를 줄·칸으로 놓고 숙성 단계를 색으로 보여 준다.
// 색과 숫자는 누르지 않아도 항상 보이고, 저장소를 누르면 양·담근 날을 고칠 수 있다.
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { addTankBuilding, deleteTankBuilding, tankMap, updateTank } from "../api/endpoints";
import type { Tank, TankBuilding, TankMap, TankStatus } from "../api/types";
import { useToast } from "../components/Toast";
import { Alert, Button, Empty, Field, Input, LoadState, Modal, PageHeader, cx } from "../components/ui";
import { useAction, useAsync } from "../lib/hooks";

/** 상태별 색 — 숙성 끝(초록) · 숙성 중(호박) · 비어 있음(회색) */
const LOOK: Record<TankStatus, { label: string; tank: string; dot: string; text: string }> = {
  ready: { label: "숙성 끝", tank: "border-green-700 bg-green-100 text-green-900", dot: "bg-green-600", text: "text-green-800" },
  aging: { label: "숙성 중", tank: "border-amber-700 bg-amber-100 text-amber-900", dot: "bg-amber-600", text: "text-amber-800" },
  empty: { label: "비어 있음", tank: "border-stone-300 bg-stone-100 text-stone-400", dot: "bg-stone-400", text: "text-stone-500" },
};

const kg = (v: number) => `${Math.round(v).toLocaleString("ko-KR")}kg`;
const ym = (iso: string | null) => (iso ? `${iso.slice(0, 4)}년 ${Number(iso.slice(5, 7))}월` : "");

export default function Tanks() {
  const data = useAsync(tankMap, []);
  const [editing, setEditing] = useState<Tank | null>(null);
  const [adding, setAdding] = useState(false);
  const m = data.data;

  return (
    <div>
      <PageHeader
        title="숙성 저장소"
        subtitle={m ? `담근 날부터 ${m.aging_months}개월이 지나면 '숙성 끝'이에요` : undefined}
        actions={
          <Button size="md" icon={<Plus className="h-5 w-5" />} onClick={() => setAdding(true)}>
            건물 추가
          </Button>
        }
      />
      <LoadState loading={data.loading} error={data.error} onRetry={data.reload} />
      {m && (
        <>
          <StatusPanel m={m} />
          {m.buildings.length === 0 ? (
            <Empty>
              <p className="mb-3 break-keep">건물을 추가하면 저장소가 줄·칸으로 그려져요. 건물 이름, 저장소 개수, 한 줄에 몇 개인지만 넣으면 돼요.</p>
              <Button size="md" icon={<Plus className="h-5 w-5" />} onClick={() => setAdding(true)}>
                첫 건물 추가
              </Button>
            </Empty>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {m.buildings.map((b) => (
                <BuildingCard key={b.name} b={b} onPick={setEditing} onChanged={data.setData} />
              ))}
            </div>
          )}
        </>
      )}
      {adding && <AddBuilding onClose={() => setAdding(false)} onDone={(next) => { data.setData(next); setAdding(false); }} />}
      {editing && <EditTank t={editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); void data.reload(); }} />}
    </div>
  );
}

/** 상태 창 — 항상 위에 보이는 숙성 끝/중/비어 있음 개수와 앞으로 출하 가능한 양 */
function StatusPanel({ m }: { m: TankMap }) {
  const s = m.summary;
  const box = (st: TankStatus, count: number, amount?: number) => (
    <div className="min-w-0 px-3 py-2.5 md:px-4 md:py-3">
      <div className={cx("flex items-center gap-1.5 whitespace-nowrap text-sm font-bold", LOOK[st].text)}>
        <span className={cx("h-3 w-3 shrink-0 rounded-full", LOOK[st].dot)} aria-hidden />
        {LOOK[st].label}
      </div>
      <div className="mt-0.5 flex flex-wrap items-baseline gap-x-1.5">
        <span className="text-xl font-extrabold">{count}개</span>
        {amount !== undefined && <span className="whitespace-nowrap text-sm font-semibold text-stone-500">{kg(amount)}</span>}
      </div>
    </div>
  );
  return (
    <section className="sticky top-12 z-20 mb-4 rounded-lg border border-line bg-white md:top-0" aria-label="저장소 상태">
      <div className="grid grid-cols-3 divide-x divide-line">
        {box("ready", s.ready_count, s.ready_kg)}
        {box("aging", s.aging_count, s.aging_kg)}
        {box("empty", s.empty_count)}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-2 text-sm text-stone-600">
        <span className="font-semibold text-stone-700">출하 가능해지는 양</span>
        <span>3개월 안 <b className="text-ink">{kg(s.in_3m_kg)}</b></span>
        <span>6개월 안 <b className="text-ink">{kg(s.in_6m_kg)}</b></span>
        <span>1년 안 <b className="text-ink">{kg(s.in_12m_kg)}</b></span>
      </div>
    </section>
  );
}

function BuildingCard({ b, onPick, onChanged }: { b: TankBuilding; onPick: (t: Tank) => void; onChanged: (m: TankMap) => void }) {
  const toast = useToast();
  const { busy, run } = useAction();
  const filled = b.tanks.filter((t) => t.status !== "empty").length;
  const cells: (Tank | null)[][] = Array.from({ length: b.rows }, () => Array.from({ length: b.cols }, () => null));
  b.tanks.forEach((t) => {
    if (t.row >= 1 && t.col >= 1 && t.row <= b.rows && t.col <= b.cols) cells[t.row - 1][t.col - 1] = t;
  });
  const remove = () =>
    run(
      "del",
      async () => {
        if (!window.confirm(`${b.name}을(를) 지울까요? 빈 저장소만 지울 수 있어요.`)) return;
        onChanged(await deleteTankBuilding(b.name));
        toast(`${b.name}을(를) 지웠어요.`, "ok");
      },
      (msg) => toast(msg, "error"),
    );

  return (
    <section className="min-w-0 rounded-lg border-2 border-brand/70 bg-white">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-2.5">
        <h2 className="text-xl font-bold text-ink">{b.name}</h2>
        <span className="text-sm text-stone-500">
          {kg(b.total_kg)} · 차 있음 {filled}/{b.tanks.length}
        </span>
      </header>
      <div className="overflow-x-auto p-3">
        <div className="grid gap-1.5 md:gap-2" style={{ gridTemplateColumns: `repeat(${b.cols}, minmax(3.4rem, 5.5rem))` }}>
          {cells.flat().map((t, i) =>
            t ? <TankCell key={t.tank_id} t={t} onClick={() => onPick(t)} /> : <div key={`gap-${i}`} aria-hidden />,
          )}
        </div>
      </div>
      {filled === 0 && (
        <div className="border-t border-dashed border-line px-4 py-2 text-right">
          <Button size="sm" variant="ghost" icon={<Trash2 className="h-4 w-4" />} disabled={busy === "del"} onClick={remove}>
            건물 지우기
          </Button>
        </div>
      )}
    </section>
  );
}

/** 저장소 한 칸 — 번호, 양, 남은 기간이 항상 보인다 */
function TankCell({ t, onClick }: { t: Tank; onClick: () => void }) {
  const look = LOOK[t.status];
  const sub =
    t.status === "empty" ? (
      "비어 있음"
    ) : t.status === "ready" ? (
      "숙성 끝"
    ) : t.months_left === null ? (
      "날짜 없음"
    ) : (
      <>
        {t.months_left}개월<span className="hidden md:inline"> 남음</span>
      </>
    );
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx("flex aspect-square min-w-0 flex-col items-center justify-center overflow-hidden rounded-full border-2 p-0.5 text-center leading-tight", look.tank)}
      aria-label={`${t.building} ${t.no}번 저장소, ${look.label}${t.current_kg ? `, ${kg(t.current_kg)}` : ""}`}
    >
      <span className="text-[15px] font-extrabold">{t.no}</span>
      {t.status !== "empty" && <span className="text-[10px] font-semibold md:text-[11px]">{kg(t.current_kg)}</span>}
      <span className="whitespace-nowrap text-[10px] md:text-[11px]">{sub}</span>
    </button>
  );
}

function AddBuilding({ onClose, onDone }: { onClose: () => void; onDone: (m: TankMap) => void }) {
  const toast = useToast();
  const { busy, run } = useAction();
  const [v, setV] = useState({ name: "", count: "10", per_row: "5", capacity_kg: "", product: "멸치액젓" });
  const [err, setErr] = useState("");
  const save = () => {
    const count = Number(v.count);
    const per = Number(v.per_row);
    if (!v.name.trim()) return setErr("건물 이름을 넣어 주세요. 예) 1동");
    if (!(count >= 1 && count <= 40)) return setErr("저장소 개수는 1~40개로 넣어 주세요.");
    if (!(per >= 1 && per <= 20)) return setErr("한 줄에 놓인 개수는 1~20개로 넣어 주세요.");
    setErr("");
    return run(
      "add",
      async () => {
        const m = await addTankBuilding({ name: v.name.trim(), count, per_row: per, capacity_kg: Number(v.capacity_kg) || 0, product: v.product.trim() });
        toast(`${v.name.trim()}을(를) 추가했어요.`, "ok");
        onDone(m);
      },
      setErr,
    );
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="건물 추가"
      footer={
        <Button block size="lg" disabled={busy === "add"} onClick={save}>
          건물 추가
        </Button>
      }
    >
      {err && <Alert tone="error">{err}</Alert>}
      <Field label="건물 이름">
        <Input value={v.name} placeholder="1동" onChange={(e) => setV({ ...v, name: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="저장소 개수">
          <Input inputMode="numeric" value={v.count} onChange={(e) => setV({ ...v, count: e.target.value.replace(/\D/g, "") })} />
        </Field>
        <Field label="한 줄에 몇 개" hint="10개를 5개씩 두 줄이면 5">
          <Input inputMode="numeric" value={v.per_row} onChange={(e) => setV({ ...v, per_row: e.target.value.replace(/\D/g, "") })} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="저장소 하나 용량 (kg)" hint="모르면 비워 두세요">
          <Input inputMode="decimal" value={v.capacity_kg} placeholder="1000" onChange={(e) => setV({ ...v, capacity_kg: e.target.value })} />
        </Field>
        <Field label="품목">
          <Input value={v.product} onChange={(e) => setV({ ...v, product: e.target.value })} />
        </Field>
      </div>
      <p className="text-sm text-stone-500">처음엔 모두 '비어 있음'으로 그려져요. 저장소를 눌러 양과 담근 날을 넣어 주세요.</p>
    </Modal>
  );
}

function EditTank({ t, onClose, onDone }: { t: Tank; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const { busy, run } = useAction();
  const [current, setCurrent] = useState(t.current_kg ? String(t.current_kg) : "");
  const [filled, setFilled] = useState(t.filled_on.slice(0, 7));
  const [memo, setMemo] = useState(t.memo);
  const [cap, setCap] = useState(t.capacity_kg ? String(t.capacity_kg) : "");
  const [err, setErr] = useState("");
  const look = LOOK[t.status];

  const save = (patch?: Parameters<typeof updateTank>[1]) =>
    run(
      "save",
      async () => {
        const kgNum = Number(current || 0);
        if (Number.isNaN(kgNum) || kgNum < 0) throw new Error("양은 숫자로 넣어 주세요.");
        await updateTank(
          t.tank_id,
          patch ?? { current_kg: kgNum, filled_on: kgNum > 0 ? filled : "", memo, capacity_kg: Number(cap) || 0 },
        );
        toast(`${t.building} ${t.no}번을 저장했어요.`, "ok");
        onDone();
      },
      setErr,
    );

  return (
    <Modal
      open
      onClose={onClose}
      title={`${t.building} ${t.no}번 저장소`}
      footer={
        <div className="flex gap-2">
          {t.status !== "empty" && (
            <Button size="lg" variant="ghost" disabled={busy === "save"} onClick={() => save({ current_kg: 0, filled_on: "" })}>
              비우기
            </Button>
          )}
          <div className="flex-1">
            <Button size="lg" block disabled={busy === "save"} onClick={() => save()}>
              저장
            </Button>
          </div>
        </div>
      }
    >
      <div className={cx("mb-3 flex items-center gap-2 font-bold", look.text)}>
        <span className={cx("h-3 w-3 rounded-full", look.dot)} aria-hidden />
        {look.label}
        {t.status === "aging" && t.ready_on && <span className="font-normal text-stone-600">· {ym(t.ready_on)}부터 출하 가능</span>}
      </div>
      {t.status === "aging" && t.ready_on && (
        <div className="mb-4 h-2 overflow-hidden rounded-full bg-stone-200" aria-label={`숙성 ${t.progress}%`}>
          <div className="h-full bg-amber-600" style={{ width: `${t.progress}%` }} />
        </div>
      )}
      {err && <Alert tone="error">{err}</Alert>}
      <div className="grid grid-cols-2 gap-3">
        <Field label="지금 양 (kg)" hint="0이면 비어 있음">
          <Input inputMode="decimal" value={current} placeholder="850" onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="담근 날" hint="달까지만 알아도 돼요">
          <Input type="month" value={filled} onChange={(e) => setFilled(e.target.value)} />
        </Field>
      </div>
      <Field label="용량 (kg)">
        <Input inputMode="decimal" value={cap} placeholder="1000" onChange={(e) => setCap(e.target.value)} />
      </Field>
      <Field label="메모">
        <Input value={memo} placeholder="2차 담금, 염도 높음 등" onChange={(e) => setMemo(e.target.value)} />
      </Field>
    </Modal>
  );
}
