import { useState } from "react";
import { Trash2 } from "lucide-react";
import { errorMessage } from "../api/client";
import { deleteMarketMapping, listProducts, marketConfirm, marketMappings, marketPreview } from "../api/endpoints";
import type { MarketPreview, MarketResult } from "../api/types";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Card, Empty, Field, FileDrop, Input, LoadState, PageHeader, Select } from "../components/ui";
import { useAsync } from "../lib/hooks";

interface Pick {
  sku: string;
  multiplier: number;
  remember: boolean;
}

export default function Marketplace() {
  const toast = useToast();
  const products = useAsync(() => listProducts(), []);
  const mappings = useAsync(marketMappings, []);
  const [source, setSource] = useState("auto");
  const [preview, setPreview] = useState<MarketPreview | null>(null);
  const [picks, setPicks] = useState<Record<string, Pick>>({});
  const [skip, setSkip] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<MarketResult | null>(null);

  const upload = async (f: File) => {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const p = await marketPreview(f, source);
      setPreview(p);
      // 추천 품목을 미리 골라 둔다
      const init: Record<string, Pick> = {};
      for (const o of p.orders) for (const l of o.lines) if (!l.mapped && !init[l.external_name]) init[l.external_name] = { sku: l.sku ?? "", multiplier: l.multiplier || 1, remember: true };
      setPicks(init);
      setSkip([]);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!preview) return;
    const missing = preview.unmapped_names.filter((n) => !picks[n]?.sku);
    if (missing.length) return setError(`품목을 골라 주세요: ${missing.join(", ")}`);
    setBusy(true);
    try {
      const mapped = Object.fromEntries(Object.entries(picks).filter(([, p]) => p.sku));
      const r = await marketConfirm(preview.preview_id, mapped, skip);
      setResult(r);
      setPreview(null);
      toast(`${r.created}건 주문을 넣었어요.`);
      void mappings.reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="오픈마켓 주문 가져오기" subtitle="스마트스토어·쿠팡에서 내려받은 주문 엑셀을 올리면 주문장에 똑같이 들어가요." />
      {error && <Alert tone="error">{error}</Alert>}
      {result && (
        <Alert tone="ok">
          {result.created}건 등록 · {result.skipped}건 건너뜀
          {result.errors.map((e) => (
            <div key={e} className="text-sm text-red-700">{e}</div>
          ))}
        </Alert>
      )}

      {!preview && (
        <Card>
          <Field label="어디 주문인가요?">
            <Select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="auto">자동으로 알아보기</option>
              <option value="smartstore">네이버 스마트스토어</option>
              <option value="coupang">쿠팡</option>
            </Select>
          </Field>
          {busy ? <p className="py-8 text-center text-stone-500">파일을 읽는 중…</p> : <FileDrop onFile={upload} />}
          <p className="mt-3 text-sm text-stone-500">스마트스토어 엑셀에 비밀번호가 걸려 있으면, 엑셀에서 열어 비밀번호를 풀고 .xlsx 로 다시 저장해서 올려 주세요.</p>
        </Card>
      )}

      {preview && (
        <>
          <Alert tone="info">
            {preview.source} 주문 {preview.orders.length}건 · 새로 넣을 주문 {preview.ready}건 · 이미 들어간 주문 {preview.duplicates}건
          </Alert>
          {preview.unmapped_names.length > 0 && (
            <Card title="우리 품목과 연결해 주세요" tone="warn">
              <p className="mb-3 text-sm text-stone-600">‘기억하기’를 켜 두면 다음부터는 자동으로 연결돼요. 2병 세트처럼 묶음 상품이면 수량배수를 2로 넣어 주세요.</p>
              {preview.unmapped_names.map((name) => {
                const p = picks[name] ?? { sku: "", multiplier: 1, remember: true };
                const set = (patch: Partial<Pick>) => setPicks({ ...picks, [name]: { ...p, ...patch } });
                return (
                  <div key={name} className="mb-3 rounded-xl bg-white p-3">
                    <div className="mb-2 font-semibold">{name}</div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Select className="min-w-0 flex-1" value={p.sku} onChange={(e) => set({ sku: e.target.value })}>
                        <option value="">— 품목 고르기 —</option>
                        {products.data?.map((x) => (
                          <option key={x.sku} value={x.sku}>{x.name} {x.spec}</option>
                        ))}
                      </Select>
                      <span className="text-sm">× 배수</span>
                      <Input className="w-20 text-center" type="number" min={1} value={p.multiplier} onChange={(e) => set({ multiplier: Math.max(1, Number(e.target.value) || 1) })} />
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" className="h-5 w-5" checked={p.remember} onChange={(e) => set({ remember: e.target.checked })} /> 기억하기
                      </label>
                    </div>
                  </div>
                );
              })}
            </Card>
          )}
          {preview.orders.map((o) => (
            <div key={o.ext_order_no} className={`mb-2 rounded-2xl border bg-white p-3 ${o.status === "이미등록" ? "opacity-60" : ""} border-line`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <b>{o.recipient}</b> <span className="text-sm text-stone-500">{o.phone}</span>
                  <div className="text-sm text-stone-500">{o.address}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={o.status === "이미등록" ? "gray" : o.status === "확인필요" ? "amber" : "green"}>{o.status}</Badge>
                  {o.status !== "이미등록" && (
                    <label className="flex items-center gap-1 text-sm">
                      <input type="checkbox" className="h-5 w-5" checked={skip.includes(o.ext_order_no)} onChange={(e) => setSkip(e.target.checked ? [...skip, o.ext_order_no] : skip.filter((x) => x !== o.ext_order_no))} /> 빼기
                    </label>
                  )}
                </div>
              </div>
              <ul className="mt-1 text-sm">
                {o.lines.map((l, i) => (
                  <li key={i}>{l.external_name} × {l.qty}</li>
                ))}
              </ul>
            </div>
          ))}
          <div className="sticky bottom-24 mt-4 flex gap-2 md:bottom-4">
            <Button variant="ghost" onClick={() => setPreview(null)}>다시 올리기</Button>
            <Button block loading={busy} disabled={!preview.ready} onClick={confirm}>
              {preview.ready - skip.length}건 주문 넣기
            </Button>
          </div>
        </>
      )}

      <Card title="기억해 둔 상품 연결">
        <LoadState loading={mappings.loading} error={mappings.error} />
        {mappings.data?.length === 0 && <Empty>아직 없어요.</Empty>}
        {mappings.data?.map((m) => (
          <div key={`${m.source}${m.external_name}`} className="flex items-center justify-between gap-2 border-b border-dashed border-line py-2">
            <div className="min-w-0">
              <div className="truncate">{m.external_name}</div>
              <div className="text-sm text-stone-500">{m.source} → {m.sku}{m.multiplier > 1 ? ` × ${m.multiplier}` : ""}</div>
            </div>
            <Button size="sm" variant="plain" aria-label="연결 지우기" onClick={async () => { await deleteMarketMapping(m.source, m.external_name); void mappings.reload(); }}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ))}
      </Card>
    </div>
  );
}
