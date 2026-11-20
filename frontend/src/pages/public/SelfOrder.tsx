// 거래처용 모바일 주문 화면 (/order/:token) — 로그인 없음, 큰 버튼
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, History, RotateCcw } from "lucide-react";
import { errorMessage } from "../../api/client";
import { publicForm, publicPlaceOrder, publicRecent } from "../../api/endpoints";
import type { PublicOrder } from "../../api/types";
import { Alert, Badge, Button, Field, Input, Spinner, Stepper } from "../../components/ui";
import { useAsync } from "../../lib/hooks";

export default function SelfOrder() {
  const { token = "" } = useParams();
  const form = useAsync(() => publicForm(token), [token]);
  const recent = useAsync(() => publicRecent(token).catch(() => [] as PublicOrder[]), [token]);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [address, setAddress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<PublicOrder | null>(null);

  const items = useMemo(() => Object.entries(qty).filter(([, q]) => q > 0).map(([sku, q]) => ({ sku, qty: q })), [qty]);
  const f = form.data;

  if (form.loading) return <Spinner label="주문서를 여는 중…" />;
  if (form.error || !f)
    return (
      <div className="mx-auto max-w-md p-6">
        <Alert tone="error">{form.error || "주문 링크가 올바르지 않아요."}</Alert>
        <p className="text-stone-600">공장에 전화해서 새 링크를 받아 주세요.</p>
      </div>
    );

  const submit = async () => {
    setError("");
    if (!items.length) return setError("주문할 품목의 수량을 넣어 주세요.");
    setBusy(true);
    try {
      const r = await publicPlaceOrder(token, { items, due_date: due || null, note, address: address ?? "" });
      setDone(r);
      setQty({});
      setNote("");
      void recent.reload();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto min-h-screen max-w-lg px-4 pb-32 pt-6">
      <header className="mb-5">
        <div className="text-sm text-stone-500">주문서</div>
        <h1 className="text-3xl font-extrabold">{f.customer_name}</h1>
        {f.notice && <p className="mt-2 rounded-xl bg-brand-soft px-4 py-3 text-brand-dark">{f.notice}</p>}
      </header>

      {done && (
        <Alert tone="ok" action={<Button size="sm" variant="ghost" onClick={() => setDone(null)}>또 주문하기</Button>}>
          <CheckCircle2 className="mr-1 inline h-5 w-5" /> 주문이 들어갔어요! ({done.order_id})
          <div className="text-sm">{done.items} · 받는 날 {done.due_date}</div>
        </Alert>
      )}

      {!done && (
        <>
          {f.last_items.length > 0 && (
            <Button
              block
              variant="soft"
              className="mb-4"
              icon={<RotateCcw className="h-5 w-5" />}
              onClick={() => setQty(Object.fromEntries(f.last_items.map((i) => [i.sku, i.qty])))}
            >
              지난번이랑 똑같이 담기
            </Button>
          )}

          <div className="mb-5 space-y-3">
            {f.products.map((p) => (
              <div key={p.sku} className={`flex items-center justify-between gap-3 rounded-2xl border-2 bg-white p-4 ${qty[p.sku] ? "border-brand" : "border-line"}`}>
                <div>
                  <div className="text-lg font-extrabold">{p.name}</div>
                  <div className="text-stone-500">{p.spec} · {p.unit}</div>
                </div>
                <Stepper value={qty[p.sku] ?? 0} onChange={(v) => setQty({ ...qty, [p.sku]: v })} />
              </div>
            ))}
          </div>

          <Field label="받고 싶은 날" hint={`${f.min_due_date} 부터 고를 수 있어요. 비워 두면 공장에서 정해요.`}>
            <Input type="date" min={f.min_due_date} value={due} onChange={(e) => setDue(e.target.value)} />
          </Field>
          <Field label="받는 곳">
            <Input value={address ?? f.address} onChange={(e) => setAddress(e.target.value)} />
          </Field>
          <Field label="요청사항">
            <Input value={note} placeholder="예) 오전에 와 주세요" onChange={(e) => setNote(e.target.value)} />
          </Field>
          {error && <Alert tone="error">{error}</Alert>}

          <div className="safe-bottom fixed inset-x-0 bottom-0 border-t border-line bg-paper px-4 pt-3">
            <div className="mx-auto max-w-lg">
              <Button size="xl" block loading={busy} disabled={!items.length} onClick={submit}>
                {items.length ? `${items.reduce((a, i) => a + i.qty, 0)}개 주문하기` : "수량을 넣어 주세요"}
              </Button>
            </div>
          </div>
        </>
      )}

      {(recent.data?.length ?? 0) > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 flex items-center gap-2 text-lg font-extrabold">
            <History className="h-5 w-5" /> 최근 주문
          </h2>
          {recent.data!.map((o) => (
            <div key={o.order_id} className="mb-2 rounded-2xl border border-line bg-white p-4">
              <div className="flex justify-between gap-2">
                <span className="text-sm text-stone-500">{o.created_at}</span>
                <Badge tone={o.status === "출고완료" ? "green" : o.status === "취소" ? "red" : "violet"}>{o.status === "출고완료" ? "보냈어요" : o.status === "취소" ? "취소" : "준비 중"}</Badge>
              </div>
              <div className="mt-1 font-semibold">{o.items}</div>
              <div className="text-sm text-stone-500">
                받는 날 {o.due_date}
                {o.tracking_no && ` · ${o.carrier} ${o.tracking_no}`}
                {o.truck_no && ` · 화물차 ${o.truck_no}`}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
