// 웹 주문서 화면 조각들
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUp, Search, Share2 } from "lucide-react";
import { shopReviews } from "../../api/endpoints";
import type { ShopInfo, ShopReview, ShopReviewList } from "../../api/types";
import { dateKo } from "../../lib/format";
import { Button, CopyButton, Field, Input, Modal, cx } from "../../components/ui";
import { formatAddress, loadPostcode } from "../../lib/postcode";

// ---------------------------------------------------------------- 상품 그림
// 사진이 없으면 그림 대신 '라벨' 모양: 남색 바탕에 명조 품목명 (품목에 '사진주소'를 넣으면 사진으로 바뀜)
export function ProductArt({ name, image, spec, className, big }: { name: string; image?: string; spec?: string; className?: string; big?: boolean }) {
  const [broken, setBroken] = useState(false);
  if (image && !broken) {
    return <img src={image} alt={name} loading="lazy" onError={() => setBroken(true)} className={cx("h-full w-full object-cover", className)} />;
  }
  return (
    <div className={cx("flex h-full w-full flex-col items-center justify-center bg-brand px-2 text-center text-white", className)} aria-hidden>
      <span className={cx("font-serif font-bold leading-tight", big ? "text-4xl" : name.length > 3 ? "text-base" : "text-xl")}>{big ? name : name.slice(0, 4)}</span>
      {big && spec && <span className="mt-2 text-sm text-white/75">{spec}</span>}
    </div>
  );
}

/** 제품 표시사항 — 식품 포장 뒷면의 그 표. 상품 소개를 이 형식으로 보여 줘요 */
export function LabelTable({ rows }: { rows: [string, ReactNode][] }) {
  const shown = rows.filter(([, v]) => v !== "" && v !== null && v !== undefined);
  return (
    <table className="w-full border-collapse text-[15px]">
      <tbody>
        {shown.map(([k, v]) => (
          <tr key={k} className="border-t border-line first:border-t-0">
            <th scope="row" className="w-[5.5rem] whitespace-nowrap bg-paper px-3 py-2 text-left align-top font-semibold text-stone-600">{k}</th>
            <td className="break-keep px-3 py-2">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------- 주소 입력 (카카오 우편번호 검색)
export interface Address {
  base: string;
  detail: string;
  zipcode: string;
}

export function AddressField({ value, onChange, error }: { value: Address; onChange: (a: Address) => void; error?: string }) {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState("");
  const detailRef = useRef<HTMLInputElement>(null);
  const openSearch = async () => {
    try {
      await loadPostcode();
      setOpen(true);
    } catch {
      setFailed("주소 찾기를 열지 못했어요. 주소를 직접 적어 주세요.");
    }
  };
  return (
    <div>
      <Field label="받는 주소 *" hint={(error || failed) && <span className="text-red-700">{error || failed}</span>}>
        <div className="flex gap-2">
          <Input value={value.base} placeholder="주소 찾기를 눌러 주세요" autoComplete="street-address" onChange={(e) => onChange({ ...value, base: e.target.value })} />
          <Button size="md" variant="soft" className="shrink-0" icon={<Search className="h-5 w-5" />} onClick={openSearch}>
            주소 찾기
          </Button>
        </div>
      </Field>
      <div className="grid grid-cols-[1fr_7rem] gap-2">
        <Field label="상세 주소">
          <Input ref={detailRef} value={value.detail} placeholder="동·호수" onChange={(e) => onChange({ ...value, detail: e.target.value })} />
        </Field>
        <Field label="우편번호">
          <Input value={value.zipcode} inputMode="numeric" maxLength={6} onChange={(e) => onChange({ ...value, zipcode: e.target.value.replace(/\D/g, "") })} />
        </Field>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="주소 찾기">
        {open && (
          <PostcodeEmbed
            onPick={(addr, zip) => {
              onChange({ ...value, base: addr, zipcode: zip });
              setOpen(false);
              window.setTimeout(() => detailRef.current?.focus(), 100);
            }}
          />
        )}
      </Modal>
    </div>
  );
}

function PostcodeEmbed({ onPick }: { onPick: (address: string, zipcode: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !window.daum?.Postcode) return;
    ref.current.innerHTML = "";
    new window.daum.Postcode({ width: "100%", height: "100%", oncomplete: (d) => onPick(formatAddress(d), d.zonecode) }).embed(ref.current, { autoClose: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div ref={ref} className="h-[460px] w-full overflow-hidden rounded-xl border border-line" />;
}

/** 주소 + 상세주소. 저장된 주소에 이미 상세주소가 들어 있으면 두 번 붙이지 않는다 ('403호 403호' 방지) */
export const joinAddress = (a: Address) => {
  const base = a.base.trim();
  const detail = a.detail.trim();
  if (!detail || base.endsWith(detail)) return base;
  return `${base} ${detail}`;
};

// ---------------------------------------------------------------- 주문 상태
export const STATUS: Record<string, { label: string; tone: "violet" | "amber" | "green" | "red"; step: number }> = {
  접수: { label: "주문 접수", tone: "violet", step: 1 },
  출고대기: { label: "포장 끝, 곧 보내요", tone: "amber", step: 2 },
  출고완료: { label: "보냈어요", tone: "green", step: 3 },
  취소: { label: "취소된 주문", tone: "red", step: 0 },
};

/** 진행 단계: 주문 접수 → 입금 확인 → 포장 → 출발 → 도착 (지난 단계는 색칠) */
export const STEPS = ["주문 접수", "입금 확인", "포장", "출발", "도착"] as const;

export function stepOf(status: string, paid?: boolean, delivered?: boolean): number {
  if (status === "취소") return 0;
  if (status === "출고완료") return delivered ? 5 : 4;
  if (status === "출고대기") return 3; // 포장 끝 = 입금도 지난 것
  return paid ? 2 : 1;
}

/** 단계 이름 (화면 맨 위 굵은 글씨) */
export function stepLabel(status: string, paid?: boolean, delivered?: boolean): string {
  if (status === "취소") return "취소된 주문";
  return ["", "주문 접수", "입금 확인, 곧 포장해요", "포장 끝, 곧 보내요", "보냈어요", "도착했어요"][stepOf(status, paid, delivered)];
}

export function StatusSteps({ status, paid, delivered }: { status: string; paid?: boolean; delivered?: boolean }) {
  const done = stepOf(status, paid, delivered);
  if (!done) return null;
  return (
    <ol className="grid grid-cols-5 gap-1 text-center text-[13px] font-semibold" aria-label={`진행 단계: ${STEPS[done - 1]}`}>
      {STEPS.map((label, i) => (
        <li key={label} aria-current={i === done - 1 ? "step" : undefined} className={cx("border-b-4 py-1.5", i < done ? "border-brand text-brand" : "border-line text-stone-400")}>
          {label}
        </li>
      ))}
    </ol>
  );
}

/** 입금 상태 — 확인 전은 빨강, 확인되면 초록 (취소된 주문은 표시 안 함) */
export function PayStatus({ paid, status, className }: { paid: boolean; status: string; className?: string }) {
  if (status === "취소") return null;
  return paid ? (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap font-bold text-green-700", className)}>
      <span className="h-2 w-2 rounded-full bg-green-600" aria-hidden />입금 완료
    </span>
  ) : (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap font-bold text-red-600", className)}>
      <span className="h-2 w-2 rounded-full bg-red-600" aria-hidden />입금 확인 전
    </span>
  );
}

/** 입금 안 된 주문에 보여 주는 '이렇게 입금해 주세요' 상자 */
export function PayGuide({ amount, account, note }: { amount: number | null; account: string; note?: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-3">
      <div className="font-bold text-red-700">입금해 주시면 바로 준비해요</div>
      <dl className="mt-2 space-y-1 text-[15px]">
        <div className="flex gap-3">
          <dt className="w-16 shrink-0 text-stone-500">금액</dt>
          <dd className="font-bold">{amount !== null ? `${amount.toLocaleString("ko-KR")}원` : note || "확인 후 안내해 드려요"}</dd>
        </div>
        <div className="flex gap-3">
          <dt className="w-16 shrink-0 text-stone-500">계좌</dt>
          <dd className="min-w-0 break-keep font-bold">{account || "공장에서 문자로 알려 드려요"}</dd>
        </div>
      </dl>
      {account && (
        <div className="mt-2">
          <CopyButton size="sm" label="계좌 복사" text={account} />
        </div>
      )}
      <p className="mt-2 break-keep text-sm text-stone-600">입금자명은 주문하신 분 성함으로 해 주세요.</p>
    </div>
  );
}

export function trackUrl(carrier: string, no: string) {
  return `https://search.naver.com/search.naver?query=${encodeURIComponent(`${carrier} ${no}`)}`;
}

export function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-[5.5rem] shrink-0 whitespace-nowrap text-stone-500">{k}</dt>
      <dd className="min-w-0 break-keep font-semibold">{v}</dd>
    </div>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 mt-7 flex items-end justify-between gap-2">
      <h2 className="text-xl font-extrabold text-brand-dark">{children}</h2>
      {right}
    </div>
  );
}

// ---------------------------------------------------------------- 별점·후기·공유
/** 별 다섯 개 (꽉 찬 별 = 점수). 읽는 사람에겐 "별점 4.5점" */
export function Stars({ value, size = "text-base" }: { value: number; size?: string }) {
  const full = Math.round(value);
  return (
    <span className={cx("whitespace-nowrap tracking-tight text-amber-500", size)} aria-label={`별점 ${value}점`}>
      {"★★★★★".slice(0, full)}
      <span className="text-stone-300">{"★★★★★".slice(full)}</span>
    </span>
  );
}

export function StarPicker({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1" role="radiogroup" aria-label="별점">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n}점`}
          onClick={() => onChange(n)}
          className={cx("text-4xl leading-none", n <= value ? "text-amber-500" : "text-stone-300")}
        >
          ★
        </button>
      ))}
    </div>
  );
}

type ReviewSort = "new" | "high" | "low";
const SORTS: { value: ReviewSort; label: string }[] = [
  { value: "new", label: "최신순" },
  { value: "high", label: "별점 높은순" },
  { value: "low", label: "별점 낮은순" },
];

/** 구매 후기: 평균 · 별점 막대 · 정렬 · 5개씩 더보기 (큰 쇼핑몰 후기 칸과 같은 짜임) */
export function ReviewsSection({ name, data }: { name: string; data?: ShopReviewList | null }) {
  const [own, setOwn] = useState<ShopReviewList | null>(null);
  const [failed, setFailed] = useState(false);
  const [sort, setSort] = useState<ReviewSort>("new");
  const [shown, setShown] = useState(5);
  useEffect(() => {
    if (data !== undefined) return;
    shopReviews(name).then(setOwn).catch(() => setFailed(true));
  }, [name, data]);
  const d = data ?? own;
  if (failed || !d) return null;

  const dist = [5, 4, 3, 2, 1].map((star) => ({ star, n: d.items.filter((r) => r.rating === star).length }));
  const most = Math.max(1, ...dist.map((x) => x.n));
  const sorted = [...d.items].sort((a, b) => (sort === "high" ? b.rating - a.rating : sort === "low" ? a.rating - b.rating : 0) || b.created_at.localeCompare(a.created_at));

  return (
    <section>
      {d.items.length === 0 ? (
        <p className="break-keep py-4 text-stone-500">아직 후기가 없어요. 받아 보신 분은 마이페이지 주문 내역에서 후기를 남길 수 있어요.</p>
      ) : (
        <>
          <div className="flex items-center gap-5 border-b border-line pb-4">
            <div className="shrink-0 text-center">
              <div className="text-4xl font-extrabold leading-none tabular-nums">{d.average?.toFixed(1)}</div>
              <Stars value={d.average ?? 0} size="text-sm" />
              <div className="text-xs text-stone-500">후기 {d.count}개</div>
            </div>
            <ul className="min-w-0 flex-1 space-y-1" aria-label="별점별 후기 수">
              {dist.map(({ star, n }) => (
                <li key={star} className="flex items-center gap-2 text-xs text-stone-500">
                  <span className="w-6 shrink-0 tabular-nums">{star}점</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#e3e8ed]">
                    <span className="block h-full rounded-full bg-amber-500" style={{ width: `${(n / most) * 100}%` }} />
                  </span>
                  <span className="w-5 shrink-0 text-right tabular-nums">{n}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex gap-3 py-2 text-sm" role="group" aria-label="후기 정렬">
            {SORTS.map((o) => (
              <button
                key={o.value}
                type="button"
                aria-pressed={sort === o.value}
                onClick={() => setSort(o.value)}
                className={cx("py-1", sort === o.value ? "font-bold text-ink" : "text-stone-500")}
              >
                {o.label}
              </button>
            ))}
          </div>
          <ul className="divide-y divide-line border-t border-line">
            {sorted.slice(0, shown).map((r) => (
              <ReviewItem key={r.review_id} r={r} />
            ))}
          </ul>
          {sorted.length > shown && (
            <Button block variant="ghost" size="md" className="mt-2" onClick={() => setShown((n) => n + 5)}>
              후기 더보기 ({sorted.length - shown})
            </Button>
          )}
        </>
      )}
    </section>
  );
}

function ReviewItem({ r }: { r: ShopReview }) {
  const [open, setOpen] = useState(false);
  const long = r.text.length > 90;
  return (
    <li className="py-3">
      <div className="flex items-center gap-2 text-sm">
        <Stars value={r.rating} size="text-sm" />
        <span className="font-semibold text-stone-700">{r.author}</span>
        <span className="text-stone-400">{r.created_at.slice(0, 10).replace(/-/g, ".")}</span>
      </div>
      {r.spec && <div className="mt-0.5 text-xs text-stone-500">구매 규격: {r.spec}</div>}
      {r.text && (
        <p className={cx("mt-1.5 whitespace-pre-line break-keep", long && !open && "line-clamp-3")}>{r.text}</p>
      )}
      {long && (
        <button type="button" className="mt-1 text-sm font-semibold text-stone-500" onClick={() => setOpen(!open)}>
          {open ? "접기" : "더보기"}
        </button>
      )}
    </li>
  );
}

/** 휴대폰이면 공유 창(카카오톡 등), 컴퓨터면 주소 복사 */
export function ShareButton({ title, text }: { title: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title, text, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* 공유 창을 닫은 경우 */
    }
  };
  return (
    <Button size="sm" variant="ghost" icon={<Share2 className="h-4 w-4" />} onClick={share}>
      {copied ? "주소 복사됨" : "공유하기"}
    </Button>
  );
}


// ---------------------------------------------------------------- 가격 · 단위가격 · 도착 예정
/** 쇼핑몰식 가격: 숫자는 크고 굵게, '원'은 작게 */
export function Price({ value, className, unitClass }: { value: number; className?: string; unitClass?: string }) {
  return (
    <span className={cx("whitespace-nowrap font-extrabold tabular-nums", className)}>
      {value.toLocaleString("ko-KR")}
      <span className={cx("ml-0.5 font-bold", unitClass ?? "text-[0.7em]")}>원</span>
    </span>
  );
}

/** 규격 글자('1.8kg', '20kg 말통')에서 내용량 kg을 읽어요. 못 읽으면 null */
export function specKg(spec: string): number | null {
  const m = /([\d.]+)\s*(kg|㎏|l|ℓ)/i.exec(spec);
  const v = m ? Number(m[1]) : NaN;
  return Number.isFinite(v) && v > 0 ? v : null;
}

/** 1kg당 가격 (쿠팡의 '100g당 ○원' 자리). 계산이 안 되면 null */
export function perKg(price: number | null, spec: string): number | null {
  const kg = specKg(spec);
  if (price === null || !kg) return null;
  return Math.round(price / kg / 10) * 10;
}

/** 오늘 주문하면 가장 빨리 받는 날 — 준비일과 쉬는 요일을 건너뛰어요 */
export function arriveDate(info: ShopInfo, leadDays: number): Date {
  const d = new Date();
  d.setDate(d.getDate() + (Number.isFinite(leadDays) ? leadDays : 1));
  for (let i = 0; i < 7 && info.closed_weekdays.includes((d.getDay() + 6) % 7); i++) d.setDate(d.getDate() + 1);
  return d;
}

export function arriveText(info: ShopInfo, leadDays: number): string {
  const d = arriveDate(info, leadDays);
  const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const diff = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() - new Date(new Date().toDateString()).getTime()) / 86_400_000);
  return `${diff === 1 ? "내일 " : diff === 2 ? "모레 " : ""}${dateKo(iso)}`;
}

// ---------------------------------------------------------------- 맨 위로 · 처음 열 때 자리
export function BackToTop({ raised }: { raised?: boolean }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const on = () => setShow(window.scrollY > 700);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  if (!show) return null;
  return (
    <button
      type="button"
      aria-label="맨 위로"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      className={cx(
        "fixed right-4 z-20 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-white/95 text-stone-600 shadow-md",
        raised ? "bottom-36" : "bottom-24",
      )}
    >
      <ArrowUp className="h-5 w-5" />
    </button>
  );
}

/** 서버가 깨어나는 동안 보여 주는 빈 화면 틀 (빙글빙글 대신) */
export function ShopSkeleton() {
  return (
    <div className="min-h-dvh bg-paper" aria-busy="true" aria-label="주문서를 여는 중">
      <div className="safe-top h-14 bg-brand" />
      <div className="mx-auto max-w-lg space-y-3 px-4 pt-6 md:max-w-3xl">
        <div className="skeleton h-7 w-3/4" />
        <div className="skeleton h-7 w-1/2" />
        <div className="skeleton mt-6 h-24 w-full" />
        <div className="mt-6 rounded-lg border border-line bg-white p-4">
          <div className="skeleton h-6 w-1/3" />
          <div className="skeleton mt-4 h-4 w-full" />
          <div className="skeleton mt-2 h-4 w-5/6" />
          <div className="skeleton mt-2 h-4 w-2/3" />
        </div>
        <p className="pt-4 text-center text-sm text-stone-500">주문서를 여는 중이에요. 처음엔 1분쯤 걸릴 수 있어요.</p>
      </div>
    </div>
  );
}
