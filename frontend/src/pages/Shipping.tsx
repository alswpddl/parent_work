import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { FileDown, FileUp, PackageCheck, Truck as TruckIcon } from "lucide-react";
import { saveBlob } from "../api/client";
import { dispatchText, getBoard, listCarrierFormats, listOrders, parcelExcel, shipOrder, trackingCarriers, unshipOrder } from "../api/endpoints";
import type { Order } from "../api/types";
import OrderCard from "../components/OrderCard";
import OrderDetail from "../components/OrderDetail";
import { TrackingImportModal, TrackingInputModal, TruckModal } from "../components/ShippingModals";
import { useToast } from "../components/Toast";
import { Button, Card, CopyButton, Empty, LoadState, PageHeader, Segmented, Select } from "../components/ui";
import { useFeatures } from "../lib/features";
import { kg, todayIso } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

type Tab = "parcel" | "truck" | "done";

export default function Shipping() {
  const toast = useToast();
  const { has } = useFeatures();
  const { busy, run } = useAction();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "parcel";
  const board = useAsync(getBoard, []);
  const formats = useAsync(listCarrierFormats, []);
  const carriers = useAsync(() => (has("q3_tracking") ? trackingCarriers() : Promise.resolve(["CJ대한통운", "로젠택배", "기타"])), []);
  const shippedToday = useAsync(() => (tab === "done" ? listOrders({ status: "출고완료" }).then((xs) => xs.filter((o) => (o.shipped_at ?? "").startsWith(todayIso()))) : Promise.resolve([])), [tab]);
  const [format, setFormat] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [trackingFor, setTrackingFor] = useState<Order | null>(null);
  const [truckFor, setTruckFor] = useState<Order | null>(null);
  const [detail, setDetail] = useState<Order | null>(null);
  const fail = (m: string) => toast(m, "error");

  const refresh = () => {
    void board.reload();
    if (tab === "done") void shippedToday.reload();
  };

  const ship = (o: Order) =>
    run(`ship-${o.order_id}`, async () => {
      await shipOrder(o.order_id);
      toast(`${o.customer_name} 출고 완료`);
      refresh();
    }, fail);

  const download = () =>
    run("xlsx", async () => {
      const code = format || formats.data?.[0]?.code || "generic";
      const { blob, filename } = await parcelExcel(code);
      saveBlob(blob, filename);
      toast("엑셀 파일을 받았어요. 택배사 프로그램에 올려 주세요.");
    }, fail);

  const list = tab === "parcel" ? board.data?.parcel : tab === "truck" ? board.data?.truck : shippedToday.data;

  return (
    <div>
      <PageHeader title="출고하기" subtitle={board.data ? `${board.data.threshold_kg}kg 이상은 화물, 미만은 택배로 나눴어요.` : undefined} />
      <Segmented
        className="mb-4"
        value={tab}
        onChange={(t) => setParams({ tab: t })}
        options={[
          { value: "parcel", label: `📦 택배 ${board.data?.parcel.length ?? ""}` },
          { value: "truck", label: `🚚 화물 ${board.data?.truck.length ?? ""}` },
          { value: "done", label: "오늘 출고" },
        ]}
      />
      <LoadState loading={board.loading} error={board.error} onRetry={board.reload} />

      {tab === "parcel" && board.data && (
        <Card title={`택배 ${board.data.parcel.length}건 · ${kg(board.data.parcel_kg)}`}>
          <div className="flex flex-col gap-2 md:flex-row md:items-center">
            <Select className="md:max-w-xs" value={format} onChange={(e) => setFormat(e.target.value)}>
              {formats.data?.map((f) => (
                <option key={f.code} value={f.code}>
                  {f.name}{f.verified ? "" : " (양식 확인 필요)"}
                </option>
              ))}
            </Select>
            <Button variant="parcel" icon={<FileDown className="h-5 w-5" />} loading={busy === "xlsx"} disabled={!board.data.parcel.length} onClick={download}>
              택배 엑셀 받기
            </Button>
            {has("q3_tracking") && (
              <Button variant="ghost" icon={<FileUp className="h-5 w-5" />} onClick={() => setImportOpen(true)}>
                송장 엑셀 올리기
              </Button>
            )}
          </div>
          <p className="mt-2 text-sm text-stone-500">① 엑셀 받기 → ② 택배사 프로그램에 올려 송장 출력 → ③ 송장 엑셀 올리기 (출고 완료 + 거래처 알림톡)</p>
        </Card>
      )}

      {list && list.length === 0 && <Empty>{tab === "done" ? "오늘 출고한 주문이 없어요." : "출고할 주문이 없어요."}</Empty>}
      {list?.map((o) => (
        <OrderCard key={o.order_id} order={o} onOpen={() => setDetail(o)} showMethod={tab === "done"}>
          {tab === "truck" && (
            <CopyButton
              label="배차 문자 복사"
              variant="truck"
              text={async () => (await dispatchText(o.order_id)).text}
              onCopied={(ok) => toast(ok ? "복사했어요. 화물 기사님 카톡에 붙여넣으세요." : "복사가 막혔어요. 주문을 눌러 직접 복사해 주세요.", ok ? "ok" : "error")}
            />
          )}
          {tab === "truck" && has("q3_tracking") && (
            <Button size="md" variant="ghost" icon={<TruckIcon className="h-5 w-5" />} onClick={() => setTruckFor(o)}>
              차량 정보 → 출고
            </Button>
          )}
          {tab === "parcel" && has("q3_tracking") && (
            <Button size="md" variant="ghost" onClick={() => setTrackingFor(o)}>
              송장 직접 입력
            </Button>
          )}
          {tab !== "done" && (
            <Button size="md" icon={<PackageCheck className="h-5 w-5" />} loading={busy === `ship-${o.order_id}`} onClick={() => ship(o)}>
              출고 완료
            </Button>
          )}
          {tab === "done" && (
            <Button
              size="md"
              variant="ghost"
              loading={busy === `un-${o.order_id}`}
              onClick={() =>
                run(`un-${o.order_id}`, async () => {
                  await unshipOrder(o.order_id);
                  toast("대기로 되돌렸어요.");
                  refresh();
                }, fail)
              }
            >
              되돌리기
            </Button>
          )}
        </OrderCard>
      ))}

      {importOpen && <TrackingImportModal carriers={carriers.data ?? []} onClose={() => setImportOpen(false)} onDone={refresh} />}
      {trackingFor && (
        <TrackingInputModal
          order={trackingFor}
          carriers={carriers.data ?? []}
          onClose={() => setTrackingFor(null)}
          onDone={() => {
            setTrackingFor(null);
            refresh();
          }}
        />
      )}
      {truckFor && (
        <TruckModal
          order={truckFor}
          onClose={() => setTruckFor(null)}
          onDone={() => {
            setTruckFor(null);
            refresh();
          }}
        />
      )}
      {detail && (
        <OrderDetail
          order={detail}
          onClose={() => {
            setDetail(null);
            refresh();
          }}
          onChanged={(o) => setDetail(o)}
        />
      )}
    </div>
  );
}
