import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Link2, MessageCircle, Plus, RefreshCw, Send, Unlink } from "lucide-react";
import { errorMessage } from "../api/client";
import {
  adminHideReview,
  adminReviews,
  briefingPreview,
  briefingSend,
  createCustomer,
  createProduct,
  getSettings,
  getSystemStatus,
  listInventory,
  googleCheck,
  resetWebPassword,
  issueOrderLink,
  kakaoDisconnect,
  kakaoLoginUrl,
  kakaoStatus,
  kakaoTest,
  listCustomers,
  listMessages,
  listProducts,
  notifyStatus,
  notifyTemplates,
  revokeOrderLink,
  saveSettings,
  updateCustomer,
  updateProduct,
  backupNow,
  backupStatus,
  listOrders,
  purgeOrders,
} from "../api/endpoints";
import type { AppSettings, Customer, Order, Product, SystemStatus } from "../api/types";
import { PushCard } from "../components/PushCard";
import { DEFAULT_REFUND } from "./shop/Policy";
import { useToast } from "../components/Toast";
import { Alert, Badge, Button, Card, ConfirmButton, CopyButton, Empty, Field, Input, LoadState, Modal, PageHeader, Segmented, Select, StatusBadge, Textarea, Toggle } from "../components/ui";
import { useFeatures } from "../lib/features";
import { dateKo, num, won } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

type Tab = "basic" | "customers" | "products" | "kakao" | "system";

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const tab = (params.get("tab") as Tab) || "basic";

  // 카카오 연결 후 돌아왔을 때 결과 알림
  useEffect(() => {
    const k = params.get("kakao");
    if (!k) return;
    if (k === "ok") toast("카카오톡이 연결됐어요! 카톡방을 확인해 보세요.");
    else toast(`카카오 연결 실패: ${params.get("msg") ?? ""}`, "error");
    setParams({ tab: "kakao" }, { replace: true });
  }, [params, setParams, toast]);

  return (
    <div>
      <PageHeader title="기본 정보·카톡" />
      <div className="mb-4 overflow-x-auto">
        <Segmented
          className="min-w-[560px]"
          value={tab}
          onChange={(t) => setParams({ tab: t })}
          options={[
            { value: "basic", label: "공장·설정" },
            { value: "customers", label: "거래처" },
            { value: "products", label: "품목" },
            { value: "kakao", label: "카톡·알림" },
            { value: "system", label: "연결 상태" },
          ]}
        />
      </div>
      {tab === "basic" && <BasicTab />}
      {tab === "customers" && <CustomersTab />}
      {tab === "products" && <ProductsTab />}
      {tab === "kakao" && <KakaoTab />}
      {tab === "system" && <SystemTab />}
    </div>
  );
}

// ================================================================ 공장·설정
function BasicTab() {
  const toast = useToast();
  const { has, features } = useFeatures();
  const shopUrl = features?.public_shop_url || `${(features?.public_web_url || window.location.origin).replace(/\/$/, "")}/shop`;
  const s = useAsync(getSettings, []);
  const [v, setV] = useState<AppSettings | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (s.data) setV(s.data);
  }, [s.data]);
  if (!v) return <LoadState loading={s.loading} error={s.error} onRetry={s.reload} />;
  const set = (p: Partial<AppSettings>) => setV({ ...v, ...p });
  const text = (k: keyof AppSettings, label: string, hint?: string) => (
    <Field label={label} hint={hint}>
      <Input value={String(v[k] ?? "")} onChange={(e) => set({ [k]: e.target.value } as Partial<AppSettings>)} />
    </Field>
  );
  const number = (k: keyof AppSettings, label: string, hint?: string) => (
    <Field label={label} hint={hint}>
      <Input type="number" inputMode="decimal" value={String(v[k] ?? "")} onChange={(e) => set({ [k]: Number(e.target.value) } as Partial<AppSettings>)} />
    </Field>
  );

  return (
    <div>
      <Card title="출고 기준">
        <div className="grid gap-x-3 md:grid-cols-2">
          {number("threshold_kg", "화물로 보낼 기준 무게 (kg 이상)")}
          {number("pallet_kg", "파레트 1개당 무게 (kg)")}
          {number("daily_capacity_kg", "하루 최대 작업량 (kg)", "오늘의 할당량이 이보다 많으면 알려줘요. 0 이면 끔")}
        </div>
      </Card>
      <Card title="우리 공장 (상차지·보내는 분·명세서 공급자)">
        <div className="grid gap-x-3 md:grid-cols-2">
          {text("factory_name", "공장 이름 (상호)")}
          {text("factory_phone", "전화번호")}
        </div>
        {text("factory_address", "주소 (상차지)")}
        <div className="grid gap-x-3 md:grid-cols-2">
          {text("factory_zipcode", "우편번호")}
          {text("company_biz_no", "사업자등록번호")}
          {text("company_owner", "대표자")}
          {text("company_biz_type", "업태")}
          {text("company_biz_item", "종목")}
          {text("bank_account", "입금 계좌", "명세서 하단에 보여요")}
        </div>
        {text("statement_note", "명세서 안내 문구")}
      </Card>
      {has("q2_self_order") && (
        <Card title="거래처 셀프 주문">
          {number("self_order_lead_days", "최소 준비일", "오늘로부터 며칠 뒤부터 받는 날로 고를 수 있어요")}
          {text("self_order_notice", "주문 화면 안내 문구")}
          <Toggle checked={v.notify_new_self_order} onChange={(x) => set({ notify_new_self_order: x })} label="셀프주문 들어오면 카톡으로 알려주기" />
          {text("quiet_hours", "밤 알림 쉬는 시간", "예) 20:00-07:00 — 이 시간 주문은 바로 안 알리고 아침 브리핑에 모아서 알려요. 비우면 늘 바로")}
        </Card>
      )}
      {has("q2_web_order") && (
        <Card title="웹 주문서 (누구나 주문하는 사이트)">
          <div className="mb-3 rounded-xl bg-brand-soft px-4 py-3 text-brand-dark">
            <div className="text-sm">주문서 주소 — 카톡 프로필·문자·명함에 넣어 주세요</div>
            <div className="break-all font-bold">{shopUrl}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <CopyButton size="sm" variant="primary" label="주소 복사" text={`${v.factory_name || "저희 공장"} 주문서예요. 눌러서 주문해 주세요!\n${shopUrl}`} onCopied={(ok) => toast(ok ? "복사했어요. 카톡에 붙여넣으세요." : "복사가 막혔어요.", ok ? "ok" : "error")} />
              <a href={shopUrl} target="_blank" rel="noreferrer" className="inline-flex min-h-[38px] items-center rounded-xl2 border border-line bg-white px-3 text-sm font-bold">미리 보기</a>
            </div>
          </div>
          <Toggle checked={v.shop_enabled} onChange={(x) => set({ shop_enabled: x })} label="웹 주문 받기 (끄면 주문서가 닫혀요)" />
          <Toggle checked={v.shop_show_prices} onChange={(x) => set({ shop_show_prices: x })} label="주문서에 가격 보이기" />
          <Field label="공장 소개 (주문서 첫 화면)" hint="두세 줄이면 충분해요. 줄바꿈 그대로 보여요.">
            <Textarea rows={3} value={v.shop_intro} placeholder={"예) 통영에서 30년,\n국산 새우로 직접 담급니다."} onChange={(e) => set({ shop_intro: e.target.value })} />
          </Field>
          {text("shop_notice", "주문서 공지 (노란 칸)", "예) 오후 2시 전 주문은 다음 날 출고 · 입금 확인 후 발송")}
          {text("privacy_retention", "개인정보 보관 기간", "주문서 동의 문구에 그대로 나와요")}
          <div className="grid gap-x-3 md:grid-cols-2">
            {number("shop_shipping_fee", "택배비 (원)", "0 이면 '택배비는 확인 후 안내'로 보여요")}
            {number("shop_free_shipping_over", "이 금액 이상이면 택배비 무료 (원)", "0 이면 무료 없음")}
          </div>
          {text("contact_hours", "문의 받는 시간", "예) 오전 8시 ~ 오후 4시 — 주문서·챗봇에 보여요")}
          {text("closed_days", "받는 날로 못 고르는 요일", "예) 일 / 토,일 / 없음 — 거래처 주문 링크에도 똑같이 적용돼요")}
          <div className="mb-3 mt-2 border-t border-line pt-4">
            <div className="mb-2 font-bold">사업자 정보·약관 (주문서 맨 아래)</div>
            <p className="mb-3 text-sm text-stone-500">상호·대표자·사업자등록번호·주소·전화는 위 '우리 공장'에 적은 값이 그대로 나와요. 빈 칸은 주문서에서 숨겨요.</p>
            <div className="grid gap-x-3 md:grid-cols-2">
              {text("mail_order_no", "통신판매업 신고번호", "예) 제2026-경남통영-0000호 · 신고 면제면 비워 두기")}
              {text("privacy_officer", "개인정보 보호책임자", "예) 최갑열 055-641-6882 · 비우면 대표자·전화")}
            </div>
            <Field label="교환·반품 안내" hint="한 줄에 한 가지씩. 비워 두면 아래 기본 문구가 나와요.">
              <Textarea rows={5} value={v.refund_policy ?? ""} placeholder={DEFAULT_REFUND} onChange={(e) => set({ refund_policy: e.target.value })} />
            </Field>
          </div>
          <p className="text-sm text-stone-500">받는 날은 품목마다 적은 '준비일'을 따르고, 비어 있으면 위 '거래처 셀프 주문'의 최소 준비일을 써요. 입금 계좌는 주문 완료 화면에 보여요.</p>
        </Card>
      )}
      <Card title="자동 알림">
        {has("q2_briefing") && <Toggle checked={v.briefing_enabled} onChange={(x) => set({ briefing_enabled: x })} label="매일 아침 브리핑 카톡" />}
        {has("q3_notify") && <Toggle checked={v.notify_customers} onChange={(x) => set({ notify_customers: x })} label="거래처에 출고 알림톡 보내기" />}
        {has("q4_inventory") && <Toggle checked={v.stock_alert_enabled} onChange={(x) => set({ stock_alert_enabled: x })} label="자재 부족 카톡 경고" />}
        {has("q4_inventory") && number("stock_lead_days", "자재 발주 후 받기까지 걸리는 날", "소진 예측에 써요")}
        {has("q4_reorder") && (
          <div className="grid gap-x-3 md:grid-cols-2">
            {number("reorder_factor", "리마인드 기준 배수", "평소 간격 × 이 값보다 늦으면 알려줘요 (예: 1.3)")}
            {number("reorder_min_orders", "최소 주문 횟수", "이만큼 주문한 거래처부터 계산해요")}
          </div>
        )}
      </Card>
      <Button
        size="xl"
        block
        loading={busy}
        onClick={async () => {
          setBusy(true);
          try {
            setV(await saveSettings(v));
            toast("저장했어요.");
          } catch (e) {
            toast(errorMessage(e), "error");
          } finally {
            setBusy(false);
          }
        }}
      >
        저장
      </Button>
    </div>
  );
}

// ================================================================ 거래처
const EMPTY_CUSTOMER: Partial<Customer> = { name: "", aliases: "", type: "B2B", contact_name: "", phone: "", address: "", zipcode: "", default_method: "자동", memo: "", notify_opt_in: true, biz_no: "", owner_name: "", email: "" };

function CustomersTab() {
  const toast = useToast();
  const { has } = useFeatures();
  const { busy, run } = useAction();
  const [showInactive, setShowInactive] = useState(false);
  const list = useAsync(() => listCustomers(showInactive), [showInactive]);
  const [edit, setEdit] = useState<Partial<Customer> | null>(null);
  const fail = (m: string) => toast(m, "error");

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        <Button size="md" icon={<Plus className="h-5 w-5" />} onClick={() => setEdit({ ...EMPTY_CUSTOMER })}>거래처 추가</Button>
        <Button size="md" variant="plain" onClick={() => setShowInactive(!showInactive)}>{showInactive ? "쓰는 곳만 보기" : "숨긴 곳도 보기"}</Button>
      </div>
      <LoadState loading={list.loading} error={list.error} onRetry={list.reload} />
      {list.data?.length === 0 && <Empty>거래처가 없어요.</Empty>}
      {list.data?.map((c) => (
        <div key={c.customer_id} className={`mb-3 rounded-2xl border border-line bg-white p-4 ${c.active ? "" : "opacity-60"}`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <button className="text-left" onClick={() => setEdit(c)}>
              <div className="text-lg font-extrabold">{c.name} <span className="text-sm font-normal text-stone-500">{c.customer_id}</span></div>
              <div className="text-sm text-stone-500">{c.contact_name} {c.phone} · {c.address || "주소 없음"}</div>
              {c.last_order_date && <div className="text-sm text-stone-500">최근 주문 {dateKo(c.last_order_date)}{c.avg_interval_days ? ` · 평균 ${c.avg_interval_days}일` : ""}</div>}
            </button>
            <div className="flex flex-wrap gap-1">
              {c.default_method !== "자동" && <Badge tone={c.default_method === "화물" ? "truck" : "parcel"}>항상 {c.default_method}</Badge>}
              {c.has_web_account && <Badge tone="violet">웹 가입</Badge>}
              {!c.active && <Badge>숨김</Badge>}
            </div>
          </div>
          {has("q2_self_order") && c.active && (
            <div className="mt-3 flex flex-wrap gap-2">
              <CopyButton
                size="sm"
                label={c.has_order_link ? "주문 링크 복사" : "주문 링크 만들기"}
                variant="soft"
                text={async () => {
                  const l = await issueOrderLink(c.customer_id);
                  if (!c.has_order_link) void list.reload();
                  return `${c.name} 전용 주문 링크예요. 눌러서 주문해 주세요!\n${l.url}`;
                }}
                onCopied={(ok) => toast(ok ? "링크를 복사했어요. 거래처 카톡방에 붙여넣으세요." : "복사가 막혔어요.", ok ? "ok" : "error")}
              />
              {c.has_order_link && (
                <ConfirmButton size="sm" variant="plain" confirmText="옛 링크가 막혀요. 계속?" onConfirm={() => run(`re-${c.customer_id}`, async () => { await issueOrderLink(c.customer_id, true); toast("새 링크를 만들었어요. 다시 복사해 주세요."); }, fail)}>
                  <RefreshCw className="h-4 w-4" /> 새 링크
                </ConfirmButton>
              )}
              {c.has_order_link && (
                <ConfirmButton size="sm" variant="plain" confirmText="링크를 막을까요?" onConfirm={() => run(`rv-${c.customer_id}`, async () => { await revokeOrderLink(c.customer_id); toast("링크를 막았어요."); void list.reload(); }, fail)}>
                  <Unlink className="h-4 w-4" /> 링크 막기
                </ConfirmButton>
              )}
            </div>
          )}
        </div>
      ))}
      {edit && (
        <CustomerModal
          value={edit}
          busy={busy === "save"}
          onClose={() => setEdit(null)}
          onSave={(v) =>
            run("save", async () => {
              if (v.customer_id) await updateCustomer(v.customer_id, v);
              else await createCustomer(v);
              toast("저장했어요.");
              setEdit(null);
              void list.reload();
            }, fail)
          }
        />
      )}
    </div>
  );
}

/** 손님이 웹 주문서 비밀번호를 잊었을 때 */
function WebAccountReset({ customerId }: { customerId: string }) {
  const toast = useToast();
  const [done, setDone] = useState(false);
  return (
    <div className="mb-3 rounded-xl border border-line bg-white px-4 py-3">
      <div className="font-bold">웹 주문서 가입 손님</div>
      <p className="mb-2 text-sm text-stone-500">비밀번호를 잊었다고 하면 초기화해 주세요. 손님이 같은 번호로 다시 가입하면 돼요 (주문 내역은 그대로).</p>
      <ConfirmButton
        size="sm"
        variant="ghost"
        disabled={done}
        confirmText="비밀번호를 지울까요?"
        onConfirm={async () => {
          try {
            await resetWebPassword(customerId);
            setDone(true);
            toast("비밀번호를 초기화했어요.");
          } catch (e) {
            toast(errorMessage(e), "error");
          }
        }}
      >
        {done ? "초기화했어요" : "비밀번호 초기화"}
      </ConfirmButton>
    </div>
  );
}

function CustomerModal({ value, busy, onClose, onSave }: { value: Partial<Customer>; busy: boolean; onClose: () => void; onSave: (v: Partial<Customer>) => void }) {
  const { has } = useFeatures();
  const [v, setV] = useState(value);
  const set = (p: Partial<Customer>) => setV({ ...v, ...p });
  const inp = (k: keyof Customer, label: string, hint?: string, type = "text") => (
    <Field label={label} hint={hint}>
      <Input type={type} value={String(v[k] ?? "")} onChange={(e) => set({ [k]: e.target.value } as Partial<Customer>)} />
    </Field>
  );
  return (
    <Modal open wide onClose={onClose} title={v.customer_id ? `거래처 수정 · ${v.name}` : "거래처 추가"} footer={<Button block loading={busy} disabled={!v.name?.trim()} onClick={() => onSave(v)}>저장</Button>}>
      <div className="grid gap-x-3 md:grid-cols-2">
        {inp("name", "거래처 이름")}
        {inp("aliases", "다른 이름 (쉼표로)", "카톡에서 부르는 이름. 예) 바다, 바다식당 사장님")}
        {inp("contact_name", "담당자")}
        {inp("phone", "휴대폰", "출고 알림톡을 받을 번호")}
      </div>
      {inp("address", "배송지 주소")}
      <div className="grid gap-x-3 md:grid-cols-2">
        {inp("zipcode", "우편번호")}
        <Field label="출고 방식">
          <Select value={v.default_method} onChange={(e) => set({ default_method: e.target.value as Customer["default_method"] })}>
            <option value="자동">자동 (무게로)</option>
            <option value="택배">항상 택배</option>
            <option value="화물">항상 화물</option>
          </Select>
        </Field>
        <Field label="구분">
          <Select value={v.type} onChange={(e) => set({ type: e.target.value as Customer["type"] })}>
            <option value="B2B">거래처 (B2B)</option>
            <option value="B2C">개인 (B2C)</option>
          </Select>
        </Field>
        {has("q4_settlement") && inp("email", "이메일", "거래명세표 받을 주소", "email")}
        {has("q4_settlement") && inp("biz_no", "사업자번호")}
        {has("q4_settlement") && inp("owner_name", "대표자")}
      </div>
      {inp("memo", "메모")}
      {v.has_web_account && v.customer_id && <WebAccountReset customerId={v.customer_id} />}
      {has("q3_notify") && <Toggle checked={v.notify_opt_in !== false} onChange={(x) => set({ notify_opt_in: x })} label="출고 알림톡 받기" />}
      {v.customer_id && <Toggle checked={v.active !== false} onChange={(x) => set({ active: x })} label="사용 중 (끄면 목록에서 숨김)" />}
    </Modal>
  );
}

// ================================================================ 품목
const EMPTY_PRODUCT: Partial<Product> = { name: "", spec: "", aliases: "", description: "", shop_visible: true, sold_out: false, unit: "통", unit_kg: 0, units_per_box: null, unit_price: null, retail_price: null, tax_type: "", container_item: "", box_item: "", label_item: "", lid_item: "", bulk_item: "", net_kg: null };

function ProductsTab() {
  const toast = useToast();
  const { has } = useFeatures();
  const { busy, run } = useAction();
  const list = useAsync(() => listProducts(true), []);
  const [edit, setEdit] = useState<Partial<Product> | null>(null);
  return (
    <div>
      <Button size="md" className="mb-3" icon={<Plus className="h-5 w-5" />} onClick={() => setEdit({ ...EMPTY_PRODUCT })}>품목 추가</Button>
      <LoadState loading={list.loading} error={list.error} onRetry={list.reload} />
      {list.data?.map((p) => (
        <div key={p.sku} className={`mb-2 rounded-2xl border border-line bg-white ${p.active ? "" : "opacity-60"}`}>
        <button onClick={() => setEdit(p)} className="block w-full p-4 pb-2 text-left">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-lg font-extrabold">{p.name} {p.spec} <span className="text-sm font-normal text-stone-500">{p.sku}</span></div>
            <div className="flex gap-1">
              {p.tax_type && <Badge>{p.tax_type}</Badge>}
              {has("q2_web_order") && !p.shop_visible && p.active && <Badge tone="amber">주문서 숨김</Badge>}
              {has("q2_web_order") && p.sold_out && p.active && <Badge tone="red">품절</Badge>}
              {!p.active && <Badge>숨김</Badge>}
            </div>
          </div>
          <div className="text-sm text-stone-500">
            1{p.unit} {p.unit_kg}kg{p.units_per_box ? ` · 박스당 ${p.units_per_box}${p.unit}` : ""}{p.unit_price !== null ? ` · ${won(p.unit_price)}` : " · 단가 없음"}
            {has("q2_web_order") && p.retail_price !== null && ` · 개인 ${won(p.retail_price)}`}
            {has("q4_inventory") && (p.bulk_item || p.container_item || p.lid_item || p.label_item || p.box_item) && ` · 재고 ${[p.bulk_item, p.container_item, p.lid_item, p.label_item, p.box_item].filter(Boolean).join("/")}`}
          </div>
        </button>
        {has("q2_web_order") && p.active && (
          <div className="px-4 pb-3">
            <Button
              size="sm"
              variant={p.sold_out ? "soft" : "ghost"}
              loading={busy === `so-${p.sku}`}
              onClick={() =>
                run(`so-${p.sku}`, async () => {
                  const updated = await updateProduct(p.sku, { sold_out: !p.sold_out });
                  list.setData((xs) => xs?.map((x) => (x.sku === p.sku ? updated : x)));
                  toast(updated.sold_out ? `${p.name} ${p.spec} 품절로 바꿨어요.` : `${p.name} ${p.spec} 다시 팔아요.`);
                }, (m) => toast(m, "error"))
              }
            >
              {p.sold_out ? "다시 팔기" : "품절로 바꾸기"}
            </Button>
          </div>
        )}
        </div>
      ))}
      {has("q2_web_order") && <ReviewsAdmin />}
      {edit && (
        <ProductModal
          value={edit}
          busy={!!busy}
          onClose={() => setEdit(null)}
          onSave={(v) =>
            run("save", async () => {
              const money = (x: unknown) => (x === null || x === undefined || String(x) === "" ? null : Number(x));
              const body = { ...v, lead_days: v.lead_days === null || v.lead_days === undefined || String(v.lead_days) === "" ? null : Math.max(0, Math.round(Number(v.lead_days))), unit_kg: Number(v.unit_kg) || 0, units_per_box: v.units_per_box ? Number(v.units_per_box) : null, unit_price: money(v.unit_price), retail_price: money(v.retail_price) };
              if (v.sku && list.data?.some((p) => p.sku === v.sku)) await updateProduct(v.sku, body);
              else await createProduct(body);
              toast("저장했어요.");
              setEdit(null);
              void list.reload();
            }, (m) => toast(m, "error"))
          }
        />
      )}
    </div>
  );
}

function ProductModal({ value, busy, onClose, onSave }: { value: Partial<Product>; busy: boolean; onClose: () => void; onSave: (v: Partial<Product>) => void }) {
  const { has } = useFeatures();
  const [v, setV] = useState(value);
  const set = (p: Partial<Product>) => setV({ ...v, ...p });
  const isNew = !value.sku;
  const stock = useAsync(() => (has("q4_inventory") ? listInventory() : Promise.resolve([])), []);
  // 규격 '1kg', '500g' 에서 내용량 읽기 (서버 규칙과 같음)
  const specKg = (() => {
    const m = /(\d+(?:\.\d+)?)\s*(kg|키로|킬로|g|그램)/i.exec(v.spec ?? "");
    if (!m) return 0;
    const n = Number(m[1]);
    return /^(g|그램)$/i.test(m[2]) ? n / 1000 : n;
  })();
  const contentKg = v.net_kg || specKg;
  const pick = (k: "bulk_item" | "container_item" | "lid_item" | "label_item" | "box_item", label: string, category: string, hint: string) => {
    const cur = (v[k] as string) || "";
    const opts = (stock.data ?? []).filter((i) => i.category === category || i.item_id === cur);
    const others = (stock.data ?? []).filter((i) => i.category !== category && i.item_id !== cur);
    return (
      <Field label={label} hint={hint}>
        <Select value={cur} onChange={(e) => set({ [k]: e.target.value } as Partial<Product>)}>
          <option value="">— 안 씀 —</option>
          {opts.map((i) => (
            <option key={i.item_id} value={i.item_id}>{i.name} ({num(i.stock)}{i.unit})</option>
          ))}
          {others.length > 0 && (
            <optgroup label="다른 분류">
              {others.map((i) => (
                <option key={i.item_id} value={i.item_id}>{i.category} · {i.name}</option>
              ))}
            </optgroup>
          )}
          {cur && !(stock.data ?? []).some((i) => i.item_id === cur) && <option value={cur}>{cur} (재고에 없는 코드)</option>}
        </Select>
      </Field>
    );
  };
  const inp = (k: keyof Product, label: string, hint?: string, type = "text") => (
    <Field label={label} hint={hint}>
      <Input type={type} inputMode={type === "number" ? "decimal" : undefined} value={v[k] === null || v[k] === undefined ? "" : String(v[k])} onChange={(e) => set({ [k]: e.target.value } as Partial<Product>)} />
    </Field>
  );
  return (
    <Modal open wide onClose={onClose} title={isNew ? "품목 추가" : `품목 수정 · ${v.name} ${v.spec}`} footer={<Button block loading={busy} disabled={!v.name?.trim()} onClick={() => onSave(v)}>저장</Button>}>
      <div className="grid gap-x-3 md:grid-cols-2">
        {isNew && inp("sku", "품목코드", "비우면 P0001 처럼 자동")}
        {inp("name", "품목 이름", "예) 새우젓(추젓)")}
        {inp("spec", "규격", "카톡에 적히는 그대로. 예) 1kg, 500g")}
        {inp("aliases", "다른 이름 (쉼표로)", "예) 새우젓 큰통, 추젓")}
        {inp("unit", "단위", "통 / 병 / 말통")}
        {inp("unit_kg", "1개 무게 (kg, 포장 포함)", undefined, "number")}
        {inp("units_per_box", "한 박스에 몇 개", "택배 박스 수·박스 자재 계산", "number")}
        {inp("unit_price", "공급 단가 (원, 부가세 별도)", "월말 정산에 써요", "number")}
        {inp("lead_days", "준비일 (주문 후 며칠)", "이 품목을 받을 수 있는 가장 빠른 날. 비우면 기본 준비일", "number")}
        {has("q2_web_order") && inp("retail_price", "개인 판매가 (원, 웹 주문서)", "비우면 공급 단가를 보여 줘요", "number")}
        {has("q4_settlement") && (
          <Field label="과세 구분">
            <Select value={v.tax_type ?? ""} onChange={(e) => set({ tax_type: e.target.value as Product["tax_type"] })}>
              <option value="">과세 (기본)</option>
              <option value="과세">과세</option>
              <option value="면세">면세</option>
            </Select>
          </Field>
        )}
      </div>
      {has("q4_inventory") && (
        <>
          <h3 className="mb-1 mt-2 font-extrabold">출고하면 자동으로 빠지는 재고</h3>
          <p className="mb-2 text-sm text-stone-500">고른 재고가 출고 완료 때 알아서 줄어요. 목록에 없으면 [재고] 화면에서 먼저 추가해 주세요.</p>
          <div className="grid gap-x-3 md:grid-cols-2">
            {pick("bulk_item", "저장고 젓갈", "저장고", `1개당 ${contentKg ? `${contentKg}kg` : "내용량 kg"}`)}
            <Field label="내용량 (kg)" hint={v.net_kg ? "직접 넣은 값" : contentKg ? `규격 '${v.spec}'에서 읽음: ${contentKg}kg — 다르면 넣어 주세요` : "규격에 kg·g가 없으면 꼭 넣어 주세요"}>
              <Input type="number" inputMode="decimal" step="0.1" value={v.net_kg ?? ""} placeholder={contentKg ? String(contentKg) : ""} onChange={(e) => set({ net_kg: e.target.value === "" ? null : Number(e.target.value) })} />
            </Field>
            {pick("container_item", "통·말통", "용기", "1개당 1")}
            {pick("lid_item", "뚜껑", "뚜껑", "1개당 1")}
            {pick("label_item", "라벨", "라벨", "1개당 1")}
            {pick("box_item", "박스", "박스", "박스입수마다 1")}
          </div>
        </>
      )}
      {has("q2_web_order") && (
        <>
          {inp("description", "주문서 설명 (한 줄)", "웹 주문서 품목 아래에 보여요. 예) 김장용 추젓")}
          {inp("image_url", "사진 주소 (선택)", "https:// 로 시작하는 사진 링크. 비우면 그림으로 보여요")}
          <Field label="상세 설명 (선택)" hint="상품 화면 아래에 그대로 보여요. 원재료·숙성 기간·맛·보관법·드시는 법 등">
            <Textarea
              className="min-h-[120px]"
              maxLength={3000}
              value={v.detail ?? ""}
              placeholder={"통영 앞바다 멸치와 천일염만으로 담가 2년 넘게 숙성했어요.\n김치·나물무침·국 간에 좋아요."}
              onChange={(e) => set({ detail: e.target.value })}
            />
          </Field>
          <Toggle checked={v.shop_visible !== false} onChange={(x) => set({ shop_visible: x })} label="웹 주문서에 보이기" />
          <Toggle checked={!!v.sold_out} onChange={(x) => set({ sold_out: x })} label="품절 (주문서에 '품절'로 보이고 주문은 안 받아요)" />
        </>
      )}
      {!isNew && <Toggle checked={v.active !== false} onChange={(x) => set({ active: x })} label="판매 중 (끄면 주문 화면에서 숨김)" />}
    </Modal>
  );
}

// ================================================================ 카톡·알림
/** 구매 후기 — 부모님이 보고, 이상한 글은 숨기기 */
function ReviewsAdmin() {
  const toast = useToast();
  const { busy, run } = useAction();
  const list = useAsync(adminReviews, []);
  const items = list.data ?? [];
  return (
    <Card title={`구매 후기${items.length ? ` (${items.length})` : ""}`}>
      <LoadState loading={list.loading} error={list.error} onRetry={list.reload} />
      {!list.loading && items.length === 0 && <p className="text-stone-500">아직 후기가 없어요. 출고가 끝난 손님이 마이페이지에서 남길 수 있어요.</p>}
      <ul className="divide-y divide-line">
        {items.slice(0, 30).map((r) => (
          <li key={r.review_id} className={`py-2.5 ${r.hidden ? "opacity-50" : ""}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm">
                <span className="text-amber-500">{"★".repeat(r.rating)}</span> <b>{r.product_name}</b> {r.spec} · {r.author} · {r.created_at} · {r.order_id}
              </div>
              <Button
                size="sm"
                variant="ghost"
                loading={busy === r.review_id}
                onClick={() =>
                  run(r.review_id, async () => {
                    const u = await adminHideReview(r.review_id, !r.hidden);
                    list.setData((xs) => xs?.map((x) => (x.review_id === u.review_id ? u : x)));
                    toast(u.hidden ? "후기를 숨겼어요." : "후기를 다시 보여요.");
                  }, (m) => toast(m, "error"))
                }
              >
                {r.hidden ? "다시 보이기" : "숨기기"}
              </Button>
            </div>
            {r.text && <p className="mt-0.5 break-keep">{r.text}</p>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function KakaoTab() {
  const toast = useToast();
  const { has, features } = useFeatures();
  const { busy, run } = useAction();
  const status = useAsync(() => (has("q2_briefing") ? kakaoStatus() : Promise.resolve(null)), []);
  const notify = useAsync(() => (has("q3_notify") ? notifyStatus() : Promise.resolve(null)), []);
  const brief = useAsync(() => (has("q2_briefing") ? briefingPreview() : Promise.resolve(null)), []);
  const logs = useAsync(() => listMessages(undefined, 30), []);
  const [tplOpen, setTplOpen] = useState(false);
  const fail = (m: string) => toast(m, "error");
  const st = status.data;

  return (
    <div>
      <PushCard />
      {has("q2_briefing") && (
        <Card title={<span><MessageCircle className="mr-1 inline h-5 w-5" />부모님 카톡 (나에게 보내기)</span>}>
          <LoadState loading={status.loading} error={status.error} />
          {!features?.integrations.kakao && <Alert tone="warn">서버에 KAKAO_REST_API_KEY 가 없어요. 설정 안내 문서(docs/카카오_연동_가이드.md)를 따라 넣어 주세요.</Alert>}
          {st && (
            <>
              <p className="mb-3 text-lg">
                {st.connected ? <><b>{st.nickname || "카카오 계정"}</b>과 연결돼 있어요.</> : "아직 연결되지 않았어요."}
              </p>
              {st.refresh_expires_at && <p className="mb-3 text-sm text-stone-500">연결 유지 기한 {dateKo(st.refresh_expires_at)} (매주 자동 연장)</p>}
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={!st.configured}
                  loading={busy === "login"}
                  icon={<Link2 className="h-5 w-5" />}
                  onClick={() => run("login", async () => { window.location.href = (await kakaoLoginUrl()).url; }, fail)}
                >
                  {st.connected ? "다시 연결" : "카카오 연결"}
                </Button>
                {st.connected && (
                  <Button variant="ghost" loading={busy === "test"} icon={<Send className="h-5 w-5" />} onClick={() => run("test", async () => { await kakaoTest(); toast("테스트 메시지를 보냈어요. 카톡을 확인해 보세요."); void logs.reload(); }, fail)}>
                    테스트 보내기
                  </Button>
                )}
                {st.connected && (
                  <ConfirmButton variant="danger" confirmText="연결을 끊을까요?" onConfirm={() => run("dc", async () => { await kakaoDisconnect(); toast("연결을 끊었어요."); void status.reload(); }, fail)}>
                    연결 끊기
                  </ConfirmButton>
                )}
              </div>
              <p className="mt-3 text-sm text-stone-500">부모님 휴대폰에서 이 화면을 열고 [카카오 연결]을 누르면, 그 카카오 계정의 ‘나와의 채팅’으로 브리핑·경고가 와요.</p>
            </>
          )}
        </Card>
      )}

      {has("q2_briefing") && brief.data && (
        <Card
          title="아침 브리핑 미리보기"
          actions={st?.connected && <Button size="sm" loading={busy === "brief"} onClick={() => run("brief", async () => { const r = await briefingSend(); toast(r.sent ? "보냈어요." : "못 보냈어요.", r.sent ? "ok" : "error"); void logs.reload(); }, fail)}>지금 보내기</Button>}
        >
          <pre className="whitespace-pre-wrap rounded-xl bg-white p-4 font-sans">{brief.data.text}</pre>
        </Card>
      )}

      {has("q3_notify") && notify.data && (
        <Card title="거래처 알림톡 (솔라피)" actions={<Button size="sm" variant="ghost" onClick={() => setTplOpen(true)}>템플릿 문구 보기</Button>}>
          {!notify.data.configured && <Alert tone="warn">솔라피 API 키·채널 ID 가 없어 알림톡이 꺼져 있어요.</Alert>}
          {Object.entries(notify.data.templates).map(([k, t]) => (
            <div key={k} className="flex items-center justify-between border-b border-dashed border-line py-2">
              <span>{t.name} <span className="text-sm text-stone-500">{t.env}</span></span>
              <Badge tone={t.ready ? "green" : "gray"}>{t.ready ? "준비됨" : "미설정"}</Badge>
            </div>
          ))}
          <p className="mt-2 text-sm text-stone-500">알림톡 실패 시 문자 대체발송: {notify.data.sms_fallback ? "켜짐" : "꺼짐"}</p>
        </Card>
      )}

      <Card title="최근 발송 기록">
        <LoadState loading={logs.loading} error={logs.error} />
        {logs.data?.length === 0 && <Empty>아직 보낸 메시지가 없어요.</Empty>}
        {logs.data?.map((m, i) => (
          <div key={i} className="border-b border-dashed border-line py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm text-stone-500">{m.ts} · {m.channel} · {m.kind} → {m.to}</span>
              <Badge tone={m.result === "성공" ? "green" : m.result === "실패" ? "red" : "gray"}>{m.result}</Badge>
            </div>
            {m.error && <div className="text-sm text-red-700">{m.error}</div>}
          </div>
        ))}
      </Card>
      {tplOpen && <TemplatesModal onClose={() => setTplOpen(false)} />}
    </div>
  );
}

function TemplatesModal({ onClose }: { onClose: () => void }) {
  const tpl = useAsync(notifyTemplates, []);
  return (
    <Modal open wide onClose={onClose} title="알림톡 템플릿 문구 (솔라피에 그대로 등록)">
      <LoadState loading={tpl.loading} error={tpl.error} />
      {tpl.data &&
        Object.entries(tpl.data).map(([k, t]) => (
          <div key={k} className="mb-4">
            <div className="mb-1 flex items-center justify-between">
              <b>{t.name}</b>
              <CopyButton size="sm" text={t.text} />
            </div>
            <pre className="whitespace-pre-wrap rounded-xl bg-white p-3 font-sans text-sm">{t.text}</pre>
            <div className="mt-1 text-sm text-stone-500">승인 후 템플릿 ID 를 서버 환경변수 {t.env} 에 넣어 주세요.</div>
          </div>
        ))}
    </Modal>
  );
}

// ================================================================ 상태
const GUIDE_URL = "https://github.com/alswpddl/parent_work/blob/main/docs/구글시트_연동_가이드.md";

function GoogleCard({ g }: { g: SystemStatus["google"] }) {
  const toast = useToast();
  const { busy, run } = useAction();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  return (
    <Card title="구글 시트 (데이터 저장소)">
      {g.connected ? (
        <Alert tone="ok">구글 시트에 저장하고 있어요. 서버가 꺼졌다 켜져도 주문이 그대로 남아요.</Alert>
      ) : (
        <Alert tone="warn" action={<a href={GUIDE_URL} target="_blank" rel="noreferrer"><Button size="sm">연결 방법</Button></a>}>
          지금은 연습용 메모리 모드라 서버가 잠들면 주문이 사라져요. 실제로 쓰기 전에 구글 시트를 연결해 주세요.
        </Alert>
      )}
      {g.service_account_email && (
        <div className="mb-3 rounded-xl bg-white p-3">
          <div className="text-sm text-stone-500">서버 전용 구글 계정 (서비스 계정) — 시트를 이 주소와 '편집자'로 공유해야 해요</div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="break-all font-semibold">{g.service_account_email}</span>
            <CopyButton size="sm" text={g.service_account_email} onCopied={(ok) => toast(ok ? "복사했어요." : "복사가 막혔어요.", ok ? "ok" : "error")} />
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {g.spreadsheet_url && (
          <a href={g.spreadsheet_url} target="_blank" rel="noreferrer"><Button size="sm" variant="soft">주문장 시트 열기</Button></a>
        )}
        {g.system_spreadsheet_url && (
          <a href={g.system_spreadsheet_url} target="_blank" rel="noreferrer"><Button size="sm" variant="ghost">시스템 시트 열기</Button></a>
        )}
        <Button size="sm" variant="ghost" icon={<RefreshCw className="h-4 w-4" />} loading={busy === "check"} onClick={() => run("check", async () => setResult(await googleCheck()), (m) => toast(m, "error"))}>
          연결 확인
        </Button>
      </div>
      {result && <div className="mt-3"><Alert tone={result.ok ? "ok" : "error"}>{result.message}</Alert></div>}
    </Card>
  );
}

const BOT_GUIDE_URL = "https://github.com/alswpddl/parent_work/blob/main/docs/카카오톡_챗봇_가이드.md";

function KakaoBotCard({ b }: { b: SystemStatus["kakao_bot"] }) {
  const toast = useToast();
  return (
    <Card title="카카오톡 채널 챗봇">
      {b.enabled ? (
        <>
          <Alert tone="ok">
            챗봇 서버가 켜져 있어요. 정해진 질문에만 답하고, 그 밖의 말에는 메뉴 버튼과 전화번호를 보여 줘요.
          </Alert>
          <div className="mb-3 rounded-xl border border-line bg-white p-3">
            <div className="mb-2 font-bold">스킬 주소</div>
            <p className="mb-2 text-sm text-stone-500">카카오 챗봇 관리자센터 [스킬] → URL 칸에 붙여넣어요. 비밀 키가 들어 있으니 남에게 보여 주지 마세요.</p>
            <CopyButton
              label="스킬 주소 복사하기"
              variant="primary"
              text={b.skill_url}
              onCopied={(ok) => toast(ok ? "복사했어요. 챗봇 관리자센터에 붙여넣으세요." : "자동 복사가 막혔어요. 아래 칸을 길게 눌러(또는 눌러서 Ctrl+C) 복사해 주세요.", ok ? "ok" : "error")}
            />
            <input
              readOnly
              aria-label="스킬 주소"
              value={b.skill_url}
              onFocus={(e: { currentTarget: HTMLInputElement }) => e.currentTarget.select()}
              onClick={(e: { currentTarget: HTMLInputElement }) => e.currentTarget.select()}
              className="mt-2 w-full rounded-lg border border-line bg-stone-50 px-2 py-2 font-mono text-xs"
            />
            <p className="mt-1 text-xs text-stone-400">버튼이 안 되면 위 칸을 누르면 전체 선택돼요 → Ctrl+C</p>
          </div>
        </>
      ) : (
        <Alert tone="warn">챗봇이 아직 꺼져 있어서 스킬 주소가 없어요. 서버(Render)에 KAKAO_SKILL_KEY 값이 있어야 켜져요.</Alert>
      )}
      <p className="mb-2 text-sm text-stone-600">
        손님이 공장 카카오톡 채널에 "택배비 얼마예요?", "명란 있어요?", "20261126-K7Q3 5678" 처럼 보내면 바로 답해요. 못 알아들은 질문은 [기록]에 '챗봇 질문'으로 남아요.
      </p>
      <a href={BOT_GUIDE_URL} target="_blank" rel="noreferrer"><Button size="sm" variant="soft">연결 방법</Button></a>
    </Card>
  );
}

/** 온라인 결제(토스페이먼츠) 켜짐 여부 — 키는 서버(Render)에만 둔다 */
function TossCard() {
  const { features } = useFeatures();
  const on = !!features?.integrations.toss;
  const test = !!features?.integrations.toss_test;
  return (
    <Card title="온라인 결제 (토스페이먼츠)">
      {!on && (
        <Alert tone="info">
          꺼져 있어요. 손님은 계좌 입금만 할 수 있어요. 켜려면 Render 에 TOSS_CLIENT_KEY · TOSS_SECRET_KEY 를 넣어 주세요.
        </Alert>
      )}
      {on && test && (
        <Alert tone="warn">테스트 모드예요. 손님이 결제해도 실제 돈은 빠지지 않아요. 계약 후 라이브 키(live_…)로 바꾸면 실제 결제가 돼요.</Alert>
      )}
      {on && !test && <Alert tone="ok">실제 결제를 받고 있어요. 카드 결제 주문을 취소하면 자동으로 환불돼요.</Alert>}
      <p className="mt-2 text-sm text-stone-500">
        카드 번호·CVC 같은 결제 정보는 토스 결제창에서만 입력돼요. 우리 서버와 시트에는 결제수단 이름과 결제키만 남아요.
      </p>
    </Card>
  );
}

/** 구글 시트 매일 백업 (새벽 3시 30분 자동, 14일 보관) + 지금 백업 버튼 */
function BackupCard() {
  const toast = useToast();
  const st = useAsync(backupStatus, []);
  const [busy, setBusy] = useState(false);
  const d = st.data;
  const last = d?.last_result;
  return (
    <Card title="시트 백업">
      <p className="mb-3 break-keep text-stone-600">
        매일 새벽 3시 30분에 주문장·거래처·품목·저장소·후기·설정을 날짜별 탭으로 복사해 두고, 14일 지난 것은 지워요.
      </p>
      {d && !d.where && (
        <Alert tone="warn">
          백업할 시트가 아직 없어요. 구글 시트를 새로 하나 만들어 서비스 계정에 <b>편집자</b>로 공유하고, 그 시트 ID를 Render의 <b>BACKUP_SPREADSHEET_ID</b>에 넣어 주세요.
        </Alert>
      )}
      {d?.where && <p className="mb-2 text-[15px]">백업 위치: <b>{d.where}</b></p>}
      {last && (
        <p className="mb-3 text-[15px] text-stone-600">
          마지막 백업: {d?.last_run_at ? dateKo(d.last_run_at.slice(0, 10)) : "-"} ·{" "}
          {last.skipped ? last.skipped : last.ok === false ? `실패 (${last.error ?? ""})` : `${last.tab} (${(last.rows ?? 0).toLocaleString("ko-KR")}줄)`}
        </p>
      )}
      <Button
        size="md"
        variant="ghost"
        loading={busy}
        disabled={!d?.where}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await backupNow();
            toast(r.skipped ? r.skipped : `백업했어요: ${r.tab}`, r.skipped ? "error" : "ok");
            void st.reload();
          } catch (e) {
            toast(errorMessage(e), "error");
          } finally {
            setBusy(false);
          }
        }}
      >
        지금 백업하기
      </Button>
    </Card>
  );
}

/** 시험으로 넣은 주문 지우기 — 골라서 '삭제'라고 적고 누르면 취소(재고 되돌림) 뒤 장부에서 지워요 */
function PurgeCard() {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const list = useAsync(() => (open ? listOrders({ include_cancelled: true }) : Promise.resolve([] as Order[])), [open]);
  const [pick, setPick] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const orders = [...(list.data ?? [])].sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
  const toggle = (id: string) => setPick((p) => {
    const n = new Set(p);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    return n;
  });
  return (
    <Card title="테스트 주문 정리">
      <p className="mb-3 break-keep text-stone-600">
        연습으로 넣은 주문을 장부에서 완전히 지워요. 먼저 취소 처리돼서 재고가 원래대로 돌아오고, 카드 결제였으면 환불돼요. 월말 정산에 들어간 주문은 지울 수 없어요.
      </p>
      {!open ? (
        <Button size="md" variant="ghost" onClick={() => setOpen(true)}>주문 목록 열기</Button>
      ) : (
        <>
          <LoadState loading={list.loading} error={list.error} onRetry={list.reload} />
          {list.data && (
            <>
              <div className="mb-2 flex items-center justify-between gap-2 text-[15px]">
                <span>{orders.length}건 중 <b>{pick.size}건</b> 골랐어요</span>
                <span className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setPick(new Set(orders.map((o) => o.order_id)))}>전부 고르기</Button>
                  <Button size="sm" variant="ghost" onClick={() => setPick(new Set())}>모두 풀기</Button>
                </span>
              </div>
              <div className="max-h-[360px] overflow-y-auto rounded-xl border border-line">
                {orders.length === 0 && <p className="p-4 text-stone-500">주문이 없어요.</p>}
                {orders.map((o) => (
                  <label key={o.order_id} className="flex cursor-pointer items-start gap-3 border-b border-line px-3 py-2.5 last:border-0 hover:bg-stone-50">
                    <input type="checkbox" className="mt-1 h-5 w-5 accent-brand" checked={pick.has(o.order_id)} onChange={() => toggle(o.order_id)} />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-x-2">
                        <b>{o.customer_name}</b>
                        <StatusBadge status={o.status} />
                        <span className="text-sm text-stone-500">{o.order_id}</span>
                      </span>
                      <span className="block truncate text-sm text-stone-500">
                        {o.created_at ? dateKo(String(o.created_at).slice(0, 10)) : ""} · {o.lines.map((l) => `${l.product_name} ${l.qty}`).join(", ")}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
              <Field label="확인" hint="실수 방지: 아래 칸에 '삭제'라고 적어야 버튼이 눌려요">
                <Input value={confirm} placeholder="삭제" onChange={(e) => setConfirm(e.target.value)} />
              </Field>
              <Button
                variant="danger"
                block
                loading={busy}
                disabled={!pick.size || confirm.trim() !== "삭제"}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const r = await purgeOrders([...pick], confirm);
                    toast(`${r.deleted.length}건을 지웠어요.${r.skipped.length ? ` ${r.skipped.length}건은 못 지웠어요: ${r.skipped.map((x) => x.reason).join(" / ")}` : ""}`, r.skipped.length ? "error" : "ok");
                    setPick(new Set());
                    setConfirm("");
                    void list.reload();
                  } catch (e) {
                    toast(errorMessage(e), "error");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                고른 {pick.size}건 완전히 지우기
              </Button>
            </>
          )}
        </>
      )}
    </Card>
  );
}

function SystemTab() {
  const s = useAsync(getSystemStatus, []);
  return (
    <div>
      <LoadState loading={s.loading} error={s.error} onRetry={s.reload} />
      {s.data && (
        <>
          <GoogleCard g={s.data.google} />
          <BackupCard />
          <PurgeCard />
          {s.data.kakao_bot && <KakaoBotCard b={s.data.kakao_bot} />}
          <TossCard />
          <Card title="연결 상태">
            <p className="mb-2">데이터 저장소: <b>{s.data.sheets_backend === "gspread" ? "구글 시트" : "메모리 (연습용 · 서버 끄면 사라짐)"}</b></p>
            {s.data.config_problems.map((p) => (
              <Alert key={p} tone="error">{p}</Alert>
            ))}
            {s.data.integration_warnings.length === 0 ? <Alert tone="ok">모든 외부 연동이 설정돼 있어요.</Alert> : s.data.integration_warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
          </Card>
          <Card title="정기 작업">
            {s.data.jobs.map((j) => (
              <div key={j.name} className="border-b border-dashed border-line py-2">
                <div className="flex justify-between gap-2">
                  <b>{j.description}</b>
                  <span className="text-sm text-stone-500">{j.cron}</span>
                </div>
                <div className="text-sm text-stone-500">{j.name} · 마지막 실행 {j.last_run_at ? new Date(j.last_run_at).toLocaleString("ko-KR") : "없음 (서버 재시작 후)"}</div>
              </div>
            ))}
            <p className="mt-2 text-sm text-stone-500">실제 실행 시각은 GitHub Actions(.github/workflows/jobs-cron.yml)에서 정해요.</p>
          </Card>
          <Card title="켜진 기능">
            <div className="flex flex-wrap gap-2">
              {s.data.modules.map((m) => (
                <Badge key={m}>{m}</Badge>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
