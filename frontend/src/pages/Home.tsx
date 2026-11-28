import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Clock, ClipboardPaste, Package, PhoneCall, Send, Truck } from "lucide-react";
import { briefingPreview, briefingSend, getBoard, kakaoStatus, listInventory, productionSummary, reorderReminders } from "../api/endpoints";
import { PushBanner } from "../components/PushCard";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Card, Empty, LoadState, PageHeader } from "../components/ui";
import { useFeatures } from "../lib/features";
import { dateKo, isPast, kg, telHref, todayIso } from "../lib/format";
import { useAction, useAsync, useAutoRefresh } from "../lib/hooks";
import { needsPayment } from "../lib/orders";

export default function Home() {
  const toast = useToast();
  const { has, features } = useFeatures();
  const { busy, run } = useAction();

  const board = useAsync(getBoard, []);
  const prod = useAsync(() => productionSummary(todayIso(1)), []);
  const low = useAsync(() => (has("q4_inventory") ? listInventory().then((xs) => xs.filter((i) => i.status !== "정상")) : Promise.resolve([])), []);
  const remind = useAsync(() => (has("q4_reorder") ? reorderReminders() : Promise.resolve([])), []);
  const kakao = useAsync(() => (has("q2_briefing") && features?.integrations.kakao ? kakaoStatus() : Promise.resolve(null)), []);
  const brief = useAsync(() => (has("q2_briefing") ? briefingPreview() : Promise.resolve(null)), []);
  useAutoRefresh(() => Promise.all([board.refresh(), prod.refresh()]));

  const all = [...(board.data?.parcel ?? []), ...(board.data?.truck ?? [])];
  const overdue = all.filter((o) => isPast(o.due_date));
  const unpaid = all.filter(needsPayment);
  const today = new Date();

  return (
    <div>
      <PageHeader title={`${today.getMonth() + 1}월 ${today.getDate()}일 오늘 할 일`} subtitle="출고 대기 주문과 만들 물량을 한눈에 봐요." />

      <PushBanner />

      {has("q2_briefing") && features?.integrations.kakao && kakao.data && !kakao.data.connected && (
        <Alert tone="warn" action={<Link to="/settings?tab=kakao"><Button size="sm">카카오 연결</Button></Link>}>
          카카오톡이 연결되지 않아 아침 브리핑이 가지 않아요.
        </Alert>
      )}

      <LoadState loading={board.loading} error={board.error} onRetry={board.reload} />
      {board.data && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          <Stat to="/shipping?tab=parcel" icon={<Package className="h-[18px] w-[18px]" />} accent="text-parcel" label="택배" value={board.data.parcel.length} sub={kg(board.data.parcel_kg)} />
          <Stat to="/shipping?tab=truck" icon={<Truck className="h-[18px] w-[18px]" />} accent="text-truck" label="화물" value={board.data.truck.length} sub={kg(board.data.truck_kg)} />
          <Stat
            icon={<Clock className="h-[18px] w-[18px]" />}
            accent="text-bad"
            label="늦은 주문"
            value={overdue.length}
            sub={overdue.map((o) => o.customer_name).join(", ") || "없음"}
            alarm={overdue.length > 0}
          />
        </div>
      )}

      {unpaid.length > 0 && (
        <Alert tone="warn" action={<Link to="/today"><Button size="sm">확인하기</Button></Link>}>
          입금 확인을 기다리는 웹 주문 {unpaid.length}건 · {[...new Set(unpaid.map((o) => o.customer_name))].join(", ")}
        </Alert>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3">
        <Link to="/orders/new">
          <Button size="xl" block icon={<ClipboardPaste className="h-6 w-6" />}>
            주문 넣기
          </Button>
        </Link>
        <Link to="/shipping">
          <Button size="xl" block variant="ghost" icon={<Truck className="h-6 w-6" />}>
            출고하기
          </Button>
        </Link>
      </div>

      <Card title="내일까지 만들 물량" actions={<Link to="/today"><Button size="sm" variant="ghost">할당량 체크하기</Button></Link>}>
        <LoadState loading={prod.loading} error={prod.error} />
        {prod.data && prod.data.lines.length === 0 && <Empty>만들 물량이 없어요.</Empty>}
        <div className="flex flex-wrap gap-2">
          {prod.data?.lines.map((l) => (
            <div key={l.sku || l.product_name} className="min-w-[9rem] rounded-xl border border-line bg-stone-50 px-4 py-3">
              <div className="font-semibold text-stone-700">{l.product_name}</div>
              <div className="mt-0.5 text-2xl font-bold text-ink">{l.qty.toLocaleString("ko-KR")}<span className="ml-0.5 text-base font-semibold text-stone-500">개</span></div>
              <div className="text-sm text-stone-500">{l.order_count}건 · {kg(l.kg)}</div>
            </div>
          ))}
        </div>
      </Card>

      {has("q4_inventory") && (low.data?.length ?? 0) > 0 && (
        <Card title={"자재 발주 필요"} tone="warn" actions={<Link to="/inventory"><Button size="sm" variant="ghost">재고 보기</Button></Link>}>
          {low.data!.map((i) => (
            <div key={i.item_id} className="flex flex-wrap items-center justify-between gap-2 border-b border-dashed border-amber-200 py-2 last:border-0">
              <span className="font-semibold">{i.name}</span>
              <span>
                {i.stock.toLocaleString("ko-KR")}{i.unit} <Badge tone={i.status === "곧부족" ? "amber" : "red"}>{i.status}</Badge>
              </span>
            </div>
          ))}
        </Card>
      )}

      {has("q4_reorder") && (remind.data?.length ?? 0) > 0 && (
        <Card title="주문할 때 된 거래처" actions={<Link to="/reorder"><Button size="sm" variant="ghost">전체 보기</Button></Link>}>
          {remind.data!.slice(0, 5).map((s) => (
            <div key={s.customer_id} className="flex flex-wrap items-center justify-between gap-2 border-b border-dashed border-line py-2 last:border-0">
              <div>
                <div className="font-semibold">{s.customer_name}</div>
                <div className="text-sm text-stone-500">마지막 {dateKo(s.last_order_date)} · 보통 {s.avg_interval_days}일마다</div>
              </div>
              {s.phone && (
                <a href={telHref(s.phone)}>
                  <Button size="md" variant="soft" icon={<PhoneCall className="h-5 w-5" />}>전화</Button>
                </a>
              )}
            </div>
          ))}
        </Card>
      )}

      {has("q2_briefing") && brief.data && (
        <Card
          title="아침 브리핑 미리보기"
          actions={
            features?.integrations.kakao && (
              <Button
                size="sm"
                loading={busy === "brief"}
                icon={<Send className="h-4 w-4" />}
                onClick={() =>
                  run("brief", async () => {
                    const r = await briefingSend();
                    toast(r.sent ? "카톡으로 보냈어요." : "보내지 못했어요. 카카오 연결을 확인해 주세요.", r.sent ? "ok" : "error");
                  }, (m) => toast(m, "error"))
                }
              >
                지금 카톡 보내기
              </Button>
            )
          }
        >
          <pre className="whitespace-pre-wrap rounded-xl border border-line bg-stone-50 p-4 font-sans text-base">{brief.data.text}</pre>
          {!brief.data.enabled && <p className="mt-2 text-sm text-stone-500">자동 브리핑은 꺼져 있어요 (기본 정보 → 카톡).</p>}
        </Card>
      )}
      {brief.error && <Alert tone="error">{brief.error}</Alert>}
    </div>
  );
}

/** 홈 위쪽 숫자 칸 — 흰 바탕에 큰 숫자, 색은 표식에만. 늦은 주문이 있으면 칸 전체가 빨갛게 */
function Stat({ to, icon, accent, label, value, sub, alarm }: { to?: string; icon: ReactNode; accent: string; label: string; value: number; sub: string; alarm?: boolean }) {
  const body = (
    <>
      <div className={`flex items-center gap-1.5 whitespace-nowrap text-[15px] font-semibold ${alarm ? "text-bad" : "text-stone-600"}`}>
        <span className={accent}>{icon}</span>
        {label}
      </div>
      <div className={`mt-1 text-[2.25rem] font-bold leading-none ${alarm ? "text-bad" : "text-ink"}`}>
        {value}
        <span className="ml-0.5 text-base font-semibold text-stone-500">건</span>
      </div>
      <div className={`mt-1.5 truncate text-[14px] ${alarm ? "text-bad" : "text-stone-500"}`}>{sub}</div>
    </>
  );
  const cls = `block rounded-2xl border p-4 shadow-card ${alarm ? "border-[#f3c3b8] bg-bad-soft" : "border-line bg-white"}`;
  return to ? (
    <Link to={to} className={`${cls} transition-colors hover:border-stone-300`}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}
