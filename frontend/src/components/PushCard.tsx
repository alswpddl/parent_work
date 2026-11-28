// 이 휴대폰으로 알림 받기 — 설정 화면 카드 + 홈 화면 안내 띠
import { useEffect, useState } from "react";
import { BellOff, BellRing, Smartphone, X } from "lucide-react";
import { errorMessage } from "../api/client";
import { pushDevTest, pushTest } from "../api/endpoints";
import { devAlerts, disablePush, enablePush, pushState, setDevAlerts, type PushState } from "../lib/push";
import { useToast } from "./Toast";
import { Alert, Button, Card, Toggle } from "./ui";

const HIDE_KEY = "push.banner.hidden";

function usePush() {
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState("");
  useEffect(() => {
    void pushState().then(setState);
  }, []);
  return { state, setState, busy, setBusy };
}

const STEPS_IOS = ["아래쪽 가운데 공유 버튼(네모에 화살표)을 눌러요", "'홈 화면에 추가'를 눌러요", "홈 화면에 생긴 '공장 관리'로 들어와서 다시 이 버튼을 눌러요"];

export function PushCard() {
  const toast = useToast();
  const { state, setState, busy, setBusy } = usePush();
  const act = async (name: string, fn: () => Promise<void>) => {
    setBusy(name);
    try {
      await fn();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy("");
    }
  };

  return (
    <Card title="이 휴대폰으로 알림 받기">
      <p className="mb-3 break-keep text-stone-600">
        카톡 '나와의 채팅'은 메모라서 휴대폰이 울리지 않아요. 여기서 켜 두면 <b className="text-ink">아침 브리핑·새 주문·재고 경고</b>가 이 휴대폰에 알림으로 와요.
      </p>
      {state === null && <p className="text-stone-500">확인하는 중…</p>}
      {state === "on" && (
        <>
          <Alert tone="ok">이 휴대폰으로 알림이 와요.</Alert>
          <div className="flex flex-wrap gap-2">
            <Button
              size="md"
              icon={<BellRing className="h-5 w-5" />}
              loading={busy === "test"}
              onClick={() =>
                act("test", async () => {
                  const r = await pushTest();
                  toast(r.sent ? `테스트 알림을 ${r.sent}대에 보냈어요. 휴대폰 위쪽을 보세요.` : "보내지 못했어요. 끄고 다시 켜 주세요.", r.sent ? "ok" : "error");
                })
              }
            >
              테스트 알림 보내기
            </Button>
            <Button size="md" variant="ghost" icon={<BellOff className="h-5 w-5" />} loading={busy === "off"} onClick={() => act("off", async () => setState(await disablePush()))}>
              이 휴대폰 알림 끄기
            </Button>
          </div>
          <DevAlerts />
        </>
      )}
      {state === "off" && (
        <Button
          size="lg"
          icon={<BellRing className="h-5 w-5" />}
          loading={busy === "on"}
          onClick={() =>
            act("on", async () => {
              const s = await enablePush();
              setState(s);
              if (s === "on") toast("알림을 켰어요. '테스트 알림 보내기'로 확인해 보세요.");
            })
          }
        >
          이 휴대폰으로 알림 받기
        </Button>
      )}
      {state === "denied" && (
        <Alert tone="warn">
          알림이 <b>차단</b>돼 있어요. 휴대폰 <b>설정 → 앱 → 크롬(또는 공장 관리) → 알림</b>에서 허용으로 바꾼 뒤 이 화면을 다시 열어 주세요.
        </Alert>
      )}
      {state === "ios-install" && (
        <div className="rounded-xl border border-line bg-stone-50 p-4">
          <p className="mb-2 flex items-center gap-2 font-semibold">
            <Smartphone className="h-5 w-5 text-brand" /> 아이폰은 홈 화면에 추가한 앱에서만 알림이 와요
          </p>
          <ol className="list-decimal space-y-1 pl-5 text-[15px] text-stone-700">
            {STEPS_IOS.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
      )}
      {state === "unsupported" && <Alert tone="warn">이 브라우저는 알림을 받을 수 없어요. 휴대폰의 <b>크롬</b>이나 <b>삼성 인터넷</b>으로 열어 주세요.</Alert>}
    </Card>
  );
}

/** 개발자용: 서버 오류가 나면 이 휴대폰에만 알림 (부모님 폰에는 안 감) */
function DevAlerts() {
  const toast = useToast();
  const [on, setOn] = useState<boolean | null>(null);
  useEffect(() => {
    void devAlerts().then(setOn).catch(() => setOn(false));
  }, []);
  if (on === null) return null;
  return (
    <div className="mt-4 border-t border-line pt-4">
      <Toggle
        checked={on}
        label={<span>서버 오류 알림도 받기 <span className="text-sm font-normal text-stone-500">(개발자용 · 이 휴대폰에만)</span></span>}
        onChange={async (x) => {
          try {
            setOn(await setDevAlerts(x));
            if (x) {
              const r = await pushDevTest();
              toast(r.sent ? "켰어요. 시험 알림을 보냈어요." : "켰어요.");
            }
          } catch (e) {
            toast(errorMessage(e), "error");
          }
        }}
      />
    </div>
  );
}

/** 홈 위쪽 띠: 아직 알림을 안 켠 휴대폰에만, 닫으면 다시 안 보여요 */
export function PushBanner() {
  const toast = useToast();
  const { state, setState, busy, setBusy } = usePush();
  const [hidden, setHidden] = useState(() => {
    try {
      return window.localStorage.getItem(HIDE_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (hidden || (state !== "off" && state !== "ios-install")) return null;
  const hide = () => {
    try {
      window.localStorage.setItem(HIDE_KEY, "1");
    } catch {
      /* 저장 못 해도 지금은 닫힘 */
    }
    setHidden(true);
  };
  return (
    <div className="mb-4 flex items-start gap-3 rounded-2xl border border-brand/15 bg-brand-soft p-4">
      <BellRing className="mt-0.5 h-6 w-6 shrink-0 text-brand" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-brand-dark">새 주문·아침 브리핑을 휴대폰 알림으로 받아 보세요</div>
        {state === "ios-install" ? (
          <p className="mt-1 text-[15px] text-stone-600">아이폰은 공유 버튼 → '홈 화면에 추가' 후 그 앱에서 켤 수 있어요.</p>
        ) : (
          <Button
            size="md"
            className="mt-2"
            loading={busy === "on"}
            onClick={async () => {
              setBusy("on");
              try {
                const s = await enablePush();
                setState(s);
                if (s === "on") toast("알림을 켰어요. 이제 이 휴대폰이 울려요.");
                else if (s === "denied") toast("알림이 차단됐어요. 기본 정보·카톡 → 카톡·알림에서 푸는 방법을 볼 수 있어요.", "error");
              } catch (e) {
                toast(errorMessage(e), "error");
              } finally {
                setBusy("");
              }
            }}
          >
            알림 켜기
          </Button>
        )}
      </div>
      <button type="button" aria-label="닫기" onClick={hide} className="rounded-full p-1 text-stone-500 hover:bg-white/60">
        <X className="h-5 w-5" />
      </button>
    </div>
  );
}
