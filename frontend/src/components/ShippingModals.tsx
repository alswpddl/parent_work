// 출고 화면의 대화상자들: 송장 엑셀 올리기 / 송장 직접 입력 / 화물 차량 정보
import { useState } from "react";
import { errorMessage } from "../api/client";
import { setTracking, setTruck, trackingConfirm, trackingPreview } from "../api/endpoints";
import type { Order, TrackingPreview, TrackingResult } from "../api/types";
import { useToast } from "./Toast";
import { Alert, Badge, Button, Field, FileDrop, Input, Modal, Select } from "./ui";

const STATUS_TONE = { 매칭: "green", 확인필요: "amber", 못찾음: "red", 이미등록: "gray", 송장없음: "gray" } as const;

export function TrackingImportModal({ carriers, onClose, onDone }: { carriers: string[]; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [carrier, setCarrier] = useState(carriers[0] ?? "CJ대한통운");
  const [preview, setPreview] = useState<TrackingPreview | null>(null);
  const [picks, setPicks] = useState<Record<number, string>>({});
  const [skip, setSkip] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TrackingResult | null>(null);
  const [error, setError] = useState("");

  const upload = async (f: File) => {
    setBusy(true);
    setError("");
    try {
      const p = await trackingPreview(f, carrier);
      setPreview(p);
      setPicks({});
      setSkip([]);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const r = await trackingConfirm(preview.import_id, carrier, picks, skip);
      setResult(r);
      toast(`송장 ${r.registered}건 등록했어요.`);
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const willRegister = preview ? preview.rows.filter((r) => !skip.includes(r.row_no) && (picks[r.row_no] || r.status === "매칭")).length : 0;

  return (
    <Modal
      open
      wide
      onClose={onClose}
      title="송장 엑셀 올리기"
      footer={
        preview && !result ? (
          <Button block loading={busy} disabled={!willRegister} onClick={confirm}>
            {willRegister}건 송장 등록하고 출고 완료
          </Button>
        ) : (
          <Button block variant="ghost" onClick={onClose}>
            닫기
          </Button>
        )
      }
    >
      {error && <Alert tone="error">{error}</Alert>}
      {result ? (
        <div>
          <Alert tone="ok">
            {result.registered}건 등록 · {result.shipped}건 출고 완료 · {result.skipped}건 건너뜀
          </Alert>
          {result.errors.map((e) => (
            <Alert key={e} tone="warn">{e}</Alert>
          ))}
          <p className="text-stone-600">알림톡이 켜져 있으면 거래처에 송장 안내가 자동으로 나가요.</p>
        </div>
      ) : !preview ? (
        <>
          <Field label="택배사">
            <Select value={carrier} onChange={(e) => setCarrier(e.target.value)}>
              {carriers.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </Select>
          </Field>
          <p className="mb-3 text-stone-600">택배사 프로그램에서 송장을 뽑은 뒤 받은 엑셀을 올려 주세요. 주문번호 또는 받는분·전화번호로 주문을 찾아요.</p>
          {busy ? <p className="py-8 text-center text-stone-500">파일을 읽는 중…</p> : <FileDrop onFile={upload} />}
        </>
      ) : (
        <div>
          <Alert tone="info">
            {preview.total}줄 중 <b>{preview.matched}건</b>을 찾았어요. 노란 줄은 주문을 골라 주세요.
          </Alert>
          {preview.rows.map((r) => (
            <div key={r.row_no} className="mb-2 rounded-xl border border-line bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <b>{r.name || "(이름 없음)"}</b> <span className="text-sm text-stone-500">{r.phone}</span>
                  <div className="text-sm">송장 {r.tracking_no || "-"}</div>
                </div>
                <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
              </div>
              {r.order_id && <div className="mt-1 text-sm text-stone-600">→ {r.customer_name} ({r.order_id})</div>}
              {r.message && <div className="mt-1 text-sm text-stone-500">{r.message}</div>}
              {r.status === "확인필요" && (
                <Select className="mt-2" value={picks[r.row_no] ?? ""} onChange={(e) => setPicks({ ...picks, [r.row_no]: e.target.value })}>
                  <option value="">— 주문 고르기 —</option>
                  {r.candidates.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </Select>
              )}
              {r.status === "매칭" && (
                <label className="mt-2 flex items-center gap-2 text-sm">
                  <input type="checkbox" className="h-5 w-5" checked={skip.includes(r.row_no)} onChange={(e) => setSkip(e.target.checked ? [...skip, r.row_no] : skip.filter((x) => x !== r.row_no))} />
                  이 줄은 건너뛰기
                </label>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

export function TrackingInputModal({ order, carriers, onClose, onDone }: { order: Order; carriers: string[]; onClose: () => void; onDone: (o: Order) => void }) {
  const toast = useToast();
  const [carrier, setCarrier] = useState(order.carrier || carriers[0] || "CJ대한통운");
  const [no, setNo] = useState(order.tracking_no);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const o = await setTracking(order.order_id, carrier, no, true);
      toast("송장을 넣고 출고 완료했어요.");
      onDone(o);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open onClose={onClose} title={`송장 입력 · ${order.customer_name}`} footer={<Button block loading={busy} disabled={no.replace(/\D/g, "").length < 4} onClick={save}>저장하고 출고 완료</Button>}>
      <Field label="택배사">
        <Select value={carrier} onChange={(e) => setCarrier(e.target.value)}>
          {carriers.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </Select>
      </Field>
      <Field label="송장번호">
        <Input inputMode="numeric" value={no} onChange={(e) => setNo(e.target.value)} autoFocus />
      </Field>
    </Modal>
  );
}

export function TruckModal({ order, onClose, onDone }: { order: Order; onClose: () => void; onDone: (o: Order) => void }) {
  const toast = useToast();
  const [truck, setTruckNo] = useState(order.truck_no);
  const [phone, setPhone] = useState(order.driver_phone);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const o = await setTruck(order.order_id, truck, phone, true);
      toast("차량 정보를 넣고 출고 완료했어요.");
      onDone(o);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open onClose={onClose} title={`차량 정보 · ${order.customer_name}`} footer={<Button block variant="truck" loading={busy} disabled={truck.trim().length < 2} onClick={save}>저장하고 출고 완료</Button>}>
      <Field label="차량번호" hint="예) 경기12가3456">
        <Input value={truck} onChange={(e) => setTruckNo(e.target.value)} autoFocus />
      </Field>
      <Field label="기사님 연락처">
        <Input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
      <p className="text-sm text-stone-500">알림톡이 켜져 있으면 거래처에 차량번호와 기사님 연락처가 안내돼요.</p>
    </Modal>
  );
}
