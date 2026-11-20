import { Link } from "react-router-dom";
import { AlertTriangle, ClipboardPaste, MessageCircle, PhoneCall, Send, Truck } from "lucide-react";
import { briefingPreview, briefingSend, getBoard, kakaoStatus, listInventory, productionSummary, reorderReminders } from "../api/endpoints";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Card, Empty, LoadState, PageHeader } from "../components/ui";
import { useFeatures } from "../lib/features";
import { dateKo, isPast, kg, telHref, todayIso } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

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

  const all = [...(board.data?.parcel ?? []), ...(board.data?.truck ?? [])];
  const overdue = all.filter((o) => isPast(o.due_date));
  const today = new Date();

  return (
    <div>
      <PageHeader title={`${today.getMonth() + 1}월 ${today.getDate()}일 오늘 할 일`} subtitle="출고 대기 주문과 만들 물량을 한눈에 봐요." />

      {has("q2_briefing") && features?.integrations.kakao && kakao.data && !kakao.data.connected && (
        <Alert tone="warn" action={<Link to="/settings?tab=kakao"><Button size="sm">카카오 연결</Button></Link>}>
          <MessageCircle className="mr-1 inline h-5 w-5" /> 카카오톡이 연결되지 않아 아침 브리핑이 가지 않아요.
        </Alert>
      )}

      <LoadState loading={board.loading} error={board.error} onRetry={board.reload} />
      {board.data && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          <Link to="/shipping?tab=parcel" className="rounded-2xl bg-parcel p-4 text-white shadow-sm">
            <div className="text-sm opacity-90">📦 택배</div>
            <div className="text-4xl font-extrabold">{board.data.parcel.length}</div>
            <div className="text-sm opacity-90">{kg(board.data.parcel_kg)}</div>
          </Link>
          <Link to="/shipping?tab=truck" className="rounded-2xl bg-truck p-4 text-white shadow-sm">
            <div className="text-sm opacity-90">🚚 화물</div>
            <div className="text-4xl font-extrabold">{board.data.truck.length}</div>
            <div className="text-sm opacity-90">{kg(board.data.truck_kg)}</div>
          </Link>
          <div className={`rounded-2xl p-4 shadow-sm ${overdue.length ? "bg-red-600 text-white" : "bg-white"}`}>
            <div className="whitespace-nowrap text-sm opacity-90">⏰ 늦은 주문</div>
            <div className="text-4xl font-extrabold">{overdue.length}</div>
            <div className="truncate text-sm opacity-90">{overdue.map((o) => o.customer_name).join(", ") || "없음"}</div>
          </div>
        </div>
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

      <Card title="🔨 내일까지 만들 물량">
        <LoadState loading={prod.loading} error={prod.error} />
        {prod.data && prod.data.lines.length === 0 && <Empty>만들 물량이 없어요.</Empty>}
        <div className="flex flex-wrap gap-2">
          {prod.data?.lines.map((l) => (
            <div key={l.sku || l.product_name} className="rounded-2xl border border-line bg-white px-4 py-3">
              <div className="font-semibold">{l.product_name}</div>
              <div className="text-2xl font-extrabold text-brand">{l.qty.toLocaleString("ko-KR")}개</div>
              <div className="text-sm text-stone-500">{l.order_count}건 · {kg(l.kg)}</div>
            </div>
          ))}
        </div>
      </Card>

      {has("q4_inventory") && (low.data?.length ?? 0) > 0 && (
        <Card title={<span><AlertTriangle className="mr-1 inline h-5 w-5 text-amber-600" />자재 발주 필요</span>} tone="warn" actions={<Link to="/inventory"><Button size="sm" variant="ghost">재고 보기</Button></Link>}>
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
        <Card title="📞 주문할 때 된 거래처" actions={<Link to="/reorder"><Button size="sm" variant="ghost">전체 보기</Button></Link>}>
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
          title="📨 아침 브리핑 미리보기"
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
          <pre className="whitespace-pre-wrap rounded-xl bg-white p-4 font-sans text-base">{brief.data.text}</pre>
          {!brief.data.enabled && <p className="mt-2 text-sm text-stone-500">자동 브리핑은 꺼져 있어요 (기본 정보 → 카톡).</p>}
        </Card>
      )}
      {brief.error && <Alert tone="error">{brief.error}</Alert>}
    </div>
  );
}
