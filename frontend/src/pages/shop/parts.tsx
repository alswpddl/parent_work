// 웹 주문서 화면 조각들
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { Button, Field, Input, Modal, cx } from "../../components/ui";
import { formatAddress, loadPostcode } from "../../lib/postcode";

// ---------------------------------------------------------------- 상품 그림
// 사진이 없으면 이름으로 고른 그림 + 색 타일 (부모님이 품목에 '사진주소'를 넣으면 사진으로 바뀜)
const ART: [RegExp, string, string][] = [
  [/새우|추젓|육젓|오젓/, "🦐", "from-rose-100 to-orange-100"],
  [/명란|창란|알/, "🍣", "from-pink-100 to-rose-200"],
  [/오징어/, "🦑", "from-amber-100 to-orange-200"],
  [/낙지|쭈꾸미|주꾸미/, "🐙", "from-red-100 to-rose-200"],
  [/멸치|액젓|까나리/, "🐟", "from-sky-100 to-cyan-100"],
  [/굴|어리굴/, "🦪", "from-stone-100 to-slate-200"],
  [/조개|바지락/, "🐚", "from-amber-50 to-yellow-100"],
  [/게|꽃게/, "🦀", "from-orange-100 to-red-200"],
];

export function ProductArt({ name, image, className, big }: { name: string; image?: string; className?: string; big?: boolean }) {
  const [broken, setBroken] = useState(false);
  if (image && !broken) {
    return <img src={image} alt={name} loading="lazy" onError={() => setBroken(true)} className={cx("h-full w-full object-cover", className)} />;
  }
  const [, emoji, grad] = ART.find(([re]) => re.test(name)) ?? [null, "🫙", "from-emerald-50 to-teal-100"];
  return (
    <div className={cx("flex h-full w-full items-center justify-center bg-gradient-to-br", grad, className)} aria-hidden>
      <span className={big ? "text-8xl" : "text-5xl"}>{emoji}</span>
    </div>
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
        <li key={label} className={cx("rounded-lg py-1.5", i < step ? "bg-brand text-white" : "bg-stone-100 text-stone-400")}>
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
      <h2 className="text-xl font-extrabold">{children}</h2>
      {right}
    </div>
  );
}
