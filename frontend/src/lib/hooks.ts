import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "../api/client";

/** 화면 진입 시 데이터를 불러오고, reload 로 다시 불러온다. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const seq = useRef(0);

  const reload = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    setError("");
    try {
      const v = await fnRef.current();
      if (my === seq.current) setData(v);
    } catch (e) {
      if (my === seq.current) setError(errorMessage(e));
    } finally {
      if (my === seq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

/** 버튼 클릭 작업: 진행 중 표시 + 오류 메시지 */
export function useAction() {
  const [busy, setBusy] = useState<string>("");
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, onError?: (msg: string) => void): Promise<T | undefined> => {
    setBusy(key);
    try {
      return await fn();
    } catch (e) {
      onError?.(errorMessage(e));
      return undefined;
    } finally {
      setBusy("");
    }
  }, []);
  return { busy, run };
}
