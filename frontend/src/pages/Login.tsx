import { useState } from "react";
import { Delete } from "lucide-react";
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

  const key = "flex h-20 items-center justify-center rounded-2xl bg-white text-3xl font-extrabold active:scale-95";
  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6 py-10">
      <div className="mb-8 text-center">
        <div className="text-5xl">🏭</div>
        <h1 className="mt-3 text-2xl font-extrabold">공장 도우미</h1>
        <p className="mt-1 text-stone-600">비밀번호를 눌러 주세요</p>
      </div>
      <div className="mb-6 flex justify-center gap-3" aria-label="입력한 자리 수">
        {Array.from({ length: Math.max(4, pin.length) }).map((_, i) => (
          <span key={i} className={`h-5 w-5 rounded-full ${i < pin.length ? "bg-brand" : "bg-stone-300"}`} />
        ))}
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="grid grid-cols-3 gap-3">
        {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
          <button key={d} className={key} onClick={() => press(d)}>
            {d}
          </button>
        ))}
        <button className={`${key} text-lg`} onClick={() => setPin("")}>
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
  );
}
