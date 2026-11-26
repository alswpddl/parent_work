// 큰 글씨·큰 버튼 위주의 공통 UI 조각
import { forwardRef, useEffect, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Check, Copy, Loader2, Minus, Plus, Upload, X } from "lucide-react";
import { copyText } from "../lib/clipboard";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- 버튼
type Variant = "primary" | "ghost" | "danger" | "parcel" | "truck" | "soft" | "plain";
type Size = "xl" | "lg" | "md" | "sm";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-dark",
  ghost: "bg-white text-ink border-2 border-line hover:border-brand",
  danger: "bg-white text-red-700 border-2 border-red-200 hover:bg-red-50",
  parcel: "bg-parcel text-white hover:brightness-110",
  truck: "bg-truck text-white hover:brightness-110",
  soft: "bg-brand-soft text-brand-dark hover:brightness-95",
  plain: "bg-transparent text-ink hover:bg-black/5",
};
const SIZES: Record<Size, string> = {
  xl: "min-h-[64px] px-6 text-xl",
  lg: "min-h-[56px] px-5 text-lg",
  md: "min-h-[46px] px-4 text-base",
  sm: "min-h-[38px] px-3 text-sm",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  block?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "primary", size = "lg", loading, block, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button" // 폼 안에서도 누른다고 제출되지 않게 (제출 버튼은 type="submit" 을 직접 준다)
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl2 font-bold transition active:scale-[.98] disabled:opacity-50 disabled:active:scale-100",
        VARIANTS[variant],
        SIZES[size],
        block && "w-full",
        className,
      )}
    >
      {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

/** 두 번 눌러야 실행 (삭제·취소처럼 되돌리기 어려운 동작) */
export function ConfirmButton({ onConfirm, confirmText = "한 번 더 누르면 실행", children, ...rest }: ButtonProps & { onConfirm: () => void; confirmText?: string }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = window.setTimeout(() => setArmed(false), 3000);
    return () => window.clearTimeout(t);
  }, [armed]);
  return (
    <Button
      {...rest}
      onClick={() => {
        if (armed) {
          setArmed(false);
          onConfirm();
        } else setArmed(true);
      }}
    >
      {armed ? confirmText : children}
    </Button>
  );
}

export function CopyButton({ text, label = "복사", size = "md", variant = "ghost", onCopied }: { text: string | (() => Promise<string>); label?: string; size?: Size; variant?: Variant; onCopied?: (ok: boolean) => void }) {
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  return (
    <Button
      size={size}
      variant={variant}
      loading={loading}
      icon={done ? <Check className="h-5 w-5" /> : <Copy className="h-5 w-5" />}
      onClick={async () => {
        setLoading(true);
        try {
          const value = typeof text === "string" ? text : await text();
          const ok = await copyText(value);
          setDone(ok);
          onCopied?.(ok);
          window.setTimeout(() => setDone(false), 2000);
        } finally {
          setLoading(false);
        }
      }}
    >
      {done ? "복사했어요" : label}
    </Button>
  );
}

// ---------------------------------------------------------------- 상자
/** 제목 앞에 붙은 그림 문자(🔨 📋 …)를 떼어 낸다 — 글자만으로 차분하게 */
const LEADING_EMOJI = /^(?:[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}][\u{FE0F}\u{200D}\p{Extended_Pictographic}]*\s*)+/u;
function plain(t: ReactNode): ReactNode {
  return typeof t === "string" ? t.replace(LEADING_EMOJI, "") : t;
}

export function Card({ title, actions, children, className, tone }: { title?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string; tone?: "warn" | "info" }) {
  return (
    <section
      className={cx(
        "mb-4 rounded-2xl border p-4 md:p-5",
        tone === "warn" ? "border-amber-200 bg-amber-50" : tone === "info" ? "border-parcel/20 bg-parcel-soft" : "border-line bg-white",
        className,
      )}
    >
      {(title || actions) && (
        <div className="-mx-4 mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 pb-3 md:-mx-5 md:px-5">
          {title && <h2 className="text-lg font-extrabold">{plain(title)}</h2>}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-extrabold">{plain(title)}</h1>
        {subtitle && <p className="mt-1 text-sm text-stone-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

type Tone = "green" | "parcel" | "truck" | "gray" | "red" | "violet" | "amber";
const TONES: Record<Tone, string> = {
  green: "bg-brand-soft text-brand-dark",
  parcel: "bg-parcel-soft text-parcel",
  truck: "bg-truck-soft text-truck",
  gray: "bg-stone-200 text-stone-700",
  red: "bg-red-100 text-red-700",
  violet: "bg-violet-100 text-violet-700",
  amber: "bg-amber-100 text-amber-800",
};

export function Badge({ tone = "gray", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded px-2.5 py-0.5 text-sm font-bold", TONES[tone], className)}>{children}</span>;
}

export function MethodBadge({ method }: { method: string }) {
  return <Badge tone={method === "화물" ? "truck" : "parcel"}>{method === "화물" ? "🚚 화물" : "📦 택배"}</Badge>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone: Tone = status === "출고완료" ? "gray" : status === "취소" ? "red" : status === "출고대기" ? "violet" : "green";
  return <Badge tone={tone}>{status}</Badge>;
}

export function Alert({ tone = "warn", children, action }: { tone?: "warn" | "info" | "error" | "ok"; children: ReactNode; action?: ReactNode }) {
  const cls = {
    warn: "border-amber-200 bg-amber-50 text-amber-900",
    info: "border-parcel/20 bg-parcel-soft text-parcel",
    error: "border-red-200 bg-red-50 text-red-800",
    ok: "border-brand/20 bg-brand-soft text-brand-dark",
  }[tone];
  return (
    <div className={cx("mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl2 border px-4 py-3 text-base", cls)}>
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-line px-4 py-10 text-center text-stone-500">{children}</div>;
}

export function Spinner({ label = "불러오는 중…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-stone-500">
      <Loader2 className="h-6 w-6 animate-spin" /> {label}
    </div>
  );
}

export function LoadState({ loading, error, onRetry }: { loading: boolean; error: string; onRetry?: () => void }) {
  if (error) return <Alert tone="error" action={onRetry && <Button size="sm" variant="ghost" onClick={onRetry}>다시 시도</Button>}>{error}</Alert>;
  if (loading) return <Spinner />;
  return null;
}

// ---------------------------------------------------------------- 입력
const inputCls = "w-full rounded-xl border-2 border-line bg-white px-4 py-3 text-lg outline-none focus:border-brand";

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx("mb-3 block", className)}>
      <span className="mb-1.5 block text-sm font-bold text-stone-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-sm text-stone-500">{hint}</span>}
    </label>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(props, ref) {
  return <input ref={ref} {...props} className={cx(inputCls, props.className)} />;
});

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(inputCls, "pr-8", props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(inputCls, "min-h-[140px] resize-y", props.className)} />;
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="mb-3 flex w-full items-center justify-between gap-3 rounded-xl border-2 border-line bg-white px-4 py-3 text-left">
      <span className="font-semibold">{label}</span>
      <span className={cx("relative h-8 w-14 rounded-full transition", checked ? "bg-brand" : "bg-stone-300")}>
        <span className={cx("absolute top-1 h-6 w-6 rounded-full bg-white shadow transition", checked ? "left-7" : "left-1")} />
      </span>
    </button>
  );
}

export function Stepper({ value, onChange, min = 0, max = 99999 }: { value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  const btn = "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border-2 border-line bg-white text-2xl font-extrabold active:scale-95";
  return (
    <div className="flex items-center gap-1.5">
      <button type="button" aria-label="하나 빼기" className={btn} onClick={() => onChange(Math.max(min, value - 1))}>
        <Minus className="h-5 w-5" />
      </button>
      <input
        type="number"
        inputMode="numeric"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(Math.min(max, Math.max(min, Math.round(Number(e.target.value) || 0))))}
        className="h-12 w-20 rounded-xl border-2 border-line bg-white text-center text-xl font-extrabold outline-none focus:border-brand"
        aria-label="수량"
      />
      <button type="button" aria-label="하나 더하기" className={btn} onClick={() => onChange(Math.min(max, value + 1))}>
        <Plus className="h-5 w-5" />
      </button>
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, className }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cx("flex gap-1 rounded-2xl bg-[#e3e8ed] p-1", className)} role="group">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx("flex-1 rounded-xl px-3 py-3 text-base font-bold transition", o.value === value ? "bg-white text-ink shadow-sm" : "text-stone-500")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function FileDrop({ onFile, accept = ".xlsx,.csv", label = "엑셀 파일을 여기에 끌어다 놓거나 눌러서 고르세요" }: { onFile: (f: File) => void; accept?: string; label?: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      onClick={() => ref.current?.click()}
      className={cx("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center", over ? "border-brand bg-brand-soft" : "border-line bg-white")}
    >
      <Upload className="h-8 w-8 text-brand" />
      <span className="font-semibold">{label}</span>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------- 대화상자
export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 md:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        className={cx("flex max-h-[92vh] w-full flex-col rounded-t-3xl bg-paper md:rounded-3xl", wide ? "md:max-w-4xl" : "md:max-w-xl")}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="text-xl font-extrabold">{title}</h2>
          <button aria-label="닫기" onClick={onClose} className="rounded-full p-2 hover:bg-black/5">
            <X className="h-6 w-6" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="safe-bottom flex flex-wrap gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function KV({ k, v }: { k: ReactNode; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-dashed border-line py-2 last:border-0">
      <span className="shrink-0 text-stone-500">{k}</span>
      <span className="text-right font-semibold">{v}</span>
    </div>
  );
}
