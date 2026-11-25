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

  /** 화면 깜빡임 없이 뒤에서 새로 받기 (실패해도 지금 보이는 데이터는 그대로) */
  const refresh = useCallback(async () => {
    const my = ++seq.current;
    try {
      const v = await fnRef.current();
      if (my === seq.current) {
        setData(v);
        setError("");
        setLoading(false);
      }
    } catch {
      /* 다음 번에 다시 시도 */
    }
  }, []);

  return { data, error, loading, reload, refresh, setData };
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

/**
 * 화면을 켜 둔 채로도 새 주문이 보이게: 다른 앱 보다가 돌아오면(탭이 다시 보이면) 바로,
 * 보고 있는 동안은 everyMs 마다 다시 불러온다. 화면이 안 보일 때는 쉰다(데이터·배터리 절약).
 */
export function useAutoRefresh(reload: () => unknown, everyMs = 60_000) {
  const ref = useRef(reload);
  ref.current = reload;
  useEffect(() => {
    let last = Date.now();
    const go = () => {
      if (document.visibilityState !== "visible") return;
      last = Date.now();
      void ref.current();
    };
    const onVisible = () => {
      // 잠깐 다른 탭에 다녀온 정도(10초 안)는 그냥 둔다
      if (document.visibilityState === "visible" && Date.now() - last > 10_000) go();
    };
    const timer = window.setInterval(go, everyMs);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [everyMs]);
}
