import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { cx } from "./ui";

type Kind = "ok" | "error" | "info";
/** 알림 옆 버튼 (예: '장바구니 보기') */
export interface ToastAction {
  label: string;
  onClick: () => void;
}
interface ToastItem {
  id: number;
  text: string;
  kind: Kind;
  action?: ToastAction;
}

const Ctx = createContext<(text: string, kind?: Kind, action?: ToastAction) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);
  const show = useCallback((text: string, kind: Kind = "ok", action?: ToastAction) => {
    const id = ++seq.current;
    setItems((xs) => [...xs.slice(-2), { id, text, kind, action }]);
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === "error" ? 5000 : action ? 4000 : 2800);
  }, []);
  return (
    <Ctx.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6" role="status" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className={cx(
              "toast-in flex max-w-md items-center gap-4 rounded-2xl px-5 py-3 text-base font-semibold text-white shadow-lg",
              t.action ? "pointer-events-auto w-full justify-between text-left" : "text-center",
              t.kind === "error" ? "bg-red-700" : t.kind === "info" ? "bg-parcel" : "bg-ink",
            )}
          >
            <span className="min-w-0 break-keep">{t.text}</span>
            {t.action && (
              <button
                type="button"
                className="shrink-0 font-bold text-amber-300 underline-offset-2 hover:underline"
                onClick={() => {
                  t.action?.onClick();
                  setItems((xs) => xs.filter((x) => x.id !== t.id));
                }}
              >
                {t.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  return useContext(Ctx);
}
