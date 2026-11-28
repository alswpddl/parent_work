import { useState } from "react";
import { Delete, Factory, Lock } from "lucide-react";
import { errorMessage, setToken } from "../api/client";
import { loginPin } from "../api/endpoints";
import { Alert, Button } from "../components/ui";

/** 부모님용: 큰 숫자 키패드로 비밀번호 입력 */
export default function Login({ onDone }: { onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (value = pin) => {
    if (value.length < 4) return;
    setBusy(true);
    setError("");
    try {
      const r = await loginPin(value);
      setToken(r.token);
      onDone();
    } catch (e) {
      setError(errorMessage(e));
      setPin("");
    } finally {
      setBusy(false);
    }
  };

  const press = (d: string) => {
    if (busy) return;
    const next = (pin + d).slice(0, 8);
    setPin(next);
  };

  const key = "flex h-[72px] items-center justify-center rounded-xl border border-line bg-white text-[28px] font-semibold text-ink shadow-card transition-colors hover:bg-stone-50 active:scale-95 active:bg-stone-100";
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-10">
        <div className="mb-8 text-center">
          <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white">
            <Factory className="h-7 w-7" />
          </span>
          <h1 className="mt-4 text-[1.6rem] font-bold tracking-[-0.02em]">공장 관리</h1>
          <p className="mt-1 flex items-center justify-center gap-1.5 text-stone-500">
            <Lock className="h-4 w-4" /> 비밀번호를 눌러 주세요
          </p>
        </div>
        <div className="mb-6 flex justify-center gap-3" aria-label={`${pin.length}자리 입력함`}>
          {Array.from({ length: Math.max(4, pin.length) }).map((_, i) => (
            <span key={i} className={`h-4 w-4 rounded-full transition-colors ${i < pin.length ? "bg-brand" : "border-2 border-stone-300 bg-white"}`} />
          ))}
        </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="grid grid-cols-3 gap-3">
        {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
          <button key={d} className={key} onClick={() => press(d)}>
            {d}
          </button>
        ))}
        <button className={`${key} !text-lg text-stone-600`} onClick={() => setPin("")}>
          지우기
        </button>
        <button className={key} onClick={() => press("0")}>
          0
        </button>
        <button className={key} aria-label="한 자리 지우기" onClick={() => setPin(pin.slice(0, -1))}>
          <Delete className="h-8 w-8" />
        </button>
      </div>
      <Button size="xl" block className="mt-6" loading={busy} disabled={pin.length < 4} onClick={() => submit()}>
        들어가기
      </Button>
      </div>
      <p className="pb-6 text-center text-[13px] text-stone-400">가염식품 · 주문 · 출고 · 재고</p>
    </div>
  );
}
