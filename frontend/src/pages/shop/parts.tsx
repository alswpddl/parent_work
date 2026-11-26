// 웹 주문서 화면 조각들
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { Button, Field, Input, Modal, cx } from "../../components/ui";
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

export const joinAddress = (a: Address) => `${a.base} ${a.detail}`.trim();

// ---------------------------------------------------------------- 주문 상태
export const STATUS: Record<string, { label: string; tone: "violet" | "amber" | "green" | "red"; step: number }> = {
  접수: { label: "주문 확인·준비 중", tone: "violet", step: 1 },
  출고대기: { label: "포장 끝, 곧 보내요", tone: "amber", step: 2 },
  출고완료: { label: "보냈어요", tone: "green", step: 3 },
  취소: { label: "취소된 주문", tone: "red", step: 0 },
};

export function StatusSteps({ status }: { status: string }) {
  const step = STATUS[status]?.step ?? 1;
  if (!step) return null;
  return (
    <ol className="grid grid-cols-3 gap-1 text-center text-sm font-semibold">
      {["접수", "포장", "출발"].map((label, i) => (
        <li key={label} className={cx("border-b-4 py-1.5", i < step ? "border-brand text-brand" : "border-line text-stone-400")}>
          {label}
        </li>
      ))}
    </ol>
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
