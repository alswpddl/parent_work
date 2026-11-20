import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PencilLine, Sparkles } from "lucide-react";
import { errorMessage } from "../api/client";
import { createOrder, getSettings, listCustomers, listProducts, parseOrder } from "../api/endpoints";
import type { OrderDraft } from "../api/types";
import OrderForm, { draftToForm, emptyForm, formToInput, type OrderFormValue } from "../components/OrderForm";
import { useToast } from "../components/Toast";
import { Alert, Button, Card, LoadState, PageHeader, Textarea } from "../components/ui";
import { useFeatures } from "../lib/features";
import { useAsync } from "../lib/hooks";

const SAMPLE = `안녕하세요 사장님~ 한솥식당입니다
참기름 1.8L 10개, 들기름 1.8리터 5통
고춧가루 5키로 2개 부탁드려요
금요일까지 받을 수 있을까요? 오전에 와주세요`;

export default function NewOrder() {
  const toast = useToast();
  const { features } = useFeatures();
  const [params] = useSearchParams();
  const masters = useAsync(() => Promise.all([listCustomers(), listProducts(), getSettings()]), []);
  const [text, setText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [draft, setDraft] = useState<OrderDraft | null>(null);
  const [form, setForm] = useState<OrderFormValue | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [saved, setSaved] = useState<{ id: string; method: string } | null>(null);

  const [customers, products, settings] = masters.data ?? [[], [], null];

  // 리마인드 화면에서 ?customer=C0001 로 들어오면 그 거래처로 바로 직접 입력
  const presetCustomer = params.get("customer");
  useEffect(() => {
    if (!masters.data || !presetCustomer) return;
    const c = masters.data[0].find((x) => x.customer_id === presetCustomer);
    if (c) {
      setForm(emptyForm(c));
      setFormKey((k) => k + 1);
    }
  }, [masters.data, presetCustomer]);

  const parse = async () => {
    if (!text.trim()) return toast("먼저 카톡 주문 내용을 붙여넣어 주세요.", "error");
    setParsing(true);
    setSaved(null);
    try {
      const d = await parseOrder(text);
      setDraft(d);
      setForm(draftToForm(d));
      setFormKey((k) => k + 1);
      window.setTimeout(() => document.getElementById("review")?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setParsing(false);
    }
  };

  const save = async (v: OrderFormValue) => {
    const o = await createOrder({ ...formToInput(v), source: "카톡" });
    toast(`저장했어요 · ${o.ship_method}로 분류됐어요`);
    setSaved({ id: o.order_id, method: o.ship_method });
    setDraft(null);
    setForm(null);
    setText("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div>
      <PageHeader title="주문 넣기" subtitle="거래처가 보낸 카톡을 길게 눌러 복사한 뒤 아래에 붙여넣으세요." />
      <LoadState loading={masters.loading} error={masters.error} onRetry={masters.reload} />

      {saved && (
        <Alert tone="ok" action={<Link to="/shipping" className="font-bold underline">출고 화면으로</Link>}>
          주문 {saved.id} 저장 완료 ({saved.method})
        </Alert>
      )}

      <Card>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="여기에 붙여넣기" className="min-h-[180px]" />
        <div className="mt-3 flex flex-col gap-2 md:flex-row">
          <Button size="xl" block loading={parsing} icon={<Sparkles className="h-6 w-6" />} onClick={parse}>
            {features?.ai_parser ? "AI로 주문 정리하기" : "주문 정리하기"}
          </Button>
          <Button
            size="xl"
            variant="ghost"
            icon={<PencilLine className="h-6 w-6" />}
            onClick={() => {
              setDraft(null);
              setForm(emptyForm());
              setFormKey((k) => k + 1);
            }}
          >
            직접 입력
          </Button>
        </div>
        <div className="mt-3 flex items-center justify-between gap-2 text-sm text-stone-500">
          <span>{features?.ai_parser ? "AI가 거래처·품목·수량·날짜를 찾아요." : "AI 키가 없어 간단 규칙으로 정리해요."}</span>
          <Button size="sm" variant="plain" onClick={() => setText(SAMPLE)}>
            예시 넣어보기
          </Button>
        </div>
      </Card>

      {form && settings && (
        <Card title="주문 확인하기" className="scroll-mt-4" >
          <div id="review" />
          <OrderForm
            key={formKey}
            initial={form}
            customers={customers}
            products={products}
            thresholdKg={settings.threshold_kg}
            warnings={draft?.warnings ?? []}
            parser={draft?.parser}
            onSubmit={save}
            onCancel={() => {
              setForm(null);
              setDraft(null);
            }}
          />
        </Card>
      )}
    </div>
  );
}
