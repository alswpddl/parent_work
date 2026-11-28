// 온라인 결제 (토스페이먼츠 결제위젯)
//   /shop/pay/:주문번호?t=결제표   (주문 완료 화면에서)
//   /shop/pay/:주문번호?p=전화뒤4자리 (비회원 주문 조회에서)
//   /shop/pay/:주문번호            (로그인 손님 — 마이페이지에서)
//   /shop/pay/success · /shop/pay/fail  토스가 돌려보내는 곳
// 금액은 서버가 주문장에서 계산해서 내려 주고, 승인할 때 서버가 한 번 더 맞춰 본다.
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { CheckCircle2, CreditCard } from "lucide-react";
import { errorMessage } from "../../api/client";
import { shopPayConfirm, shopPayInfo } from "../../api/endpoints";
import type { PayInfo, PublicOrder } from "../../api/types";
import { Alert, Button, Spinner } from "../../components/ui";
import { won } from "../../lib/format";
import { makeWidgets, recallPayAccess, rememberPayAccess, type TossWidgets } from "../../lib/toss";
import { PayStatus, Row, StatusSteps } from "./parts";
import { useShop } from "./store";

export function Pay({ orderId }: { orderId: string }) {
  const s = useShop();
  const loc = useLocation();
  const q = new URLSearchParams(loc.search);
  const payToken = q.get("t") || "";
  const phone4 = q.get("p") || "";
  const [info, setInfo] = useState<PayInfo | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [paying, setPaying] = useState(false);
  const widgets = useRef<TossWidgets | null>(null);

  useEffect(() => {
    let alive = true;
    rememberPayAccess(orderId, loc.search);
    shopPayInfo(orderId, { payToken, phone4, token: s.auth?.token })
      .then(async (p) => {
        if (!alive) return;
        setInfo(p);
        const w = await makeWidgets(p.client_key);
        if (!alive) return;
        await w.setAmount({ currency: "KRW", value: p.amount });
        await Promise.all([
          w.renderPaymentMethods({ selector: "#toss-methods", variantKey: "DEFAULT" }),
          w.renderAgreement({ selector: "#toss-agreement", variantKey: "AGREEMENT" }),
        ]);
        widgets.current = w;
        if (alive) setReady(true);
      })
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  const pay = async () => {
    if (!info || !widgets.current) return;
    setPaying(true);
    setError("");
    try {
      const base = `${window.location.origin}/shop/pay`;
      await widgets.current.requestPayment({
        orderId: info.order_id,
        orderName: info.order_name,
        customerName: info.customer_name,
        successUrl: `${base}/success`,
        failUrl: `${base}/fail`,
      });
    } catch (e) {
      // 손님이 결제창을 닫은 경우도 여기로 온다
      const msg = errorMessage(e);
      if (!/취소|cancel/i.test(msg)) setError(msg);
    } finally {
      setPaying(false);
    }
  };

  return (
    <div>
      <h1 className="mb-1 border-b border-line pb-3 text-2xl font-bold text-ink">결제하기</h1>
      {info?.test_mode && (
        <Alert tone="warn">테스트 결제예요. 결제해도 실제 돈은 빠지지 않아요.</Alert>
      )}
      {error && <Alert tone="error">{error}</Alert>}
      {info && (
        <div className="my-4 rounded-lg border border-line bg-white">
          <div className="space-y-1 p-3 text-[15px]">
            <Row k="주문번호" v={info.order_id} />
            <Row k="상품" v={info.order_name} />
            <Row k="결제 금액" v={<b className="text-lg text-brine">{won(info.amount)}</b>} />
          </div>
        </div>
      )}
      {!info && !error && <Spinner label="주문 확인 중…" />}
      {/* 토스 결제위젯이 이 안에 그려진다 (카드·계좌 정보는 토스 화면에서만 입력) */}
      <div id="toss-methods" />
      <div id="toss-agreement" />
      {info && !ready && !error && <Spinner label="결제창 불러오는 중…" />}
      {ready && (
        <div className="sticky bottom-20 z-10 mt-4 bg-paper/95 py-2">
          <Button size="xl" block disabled={paying} icon={<CreditCard className="h-6 w-6" />} onClick={pay}>
            {paying ? "결제창 여는 중…" : `${won(info!.amount)} 결제하기`}
          </Button>
        </div>
      )}
      <p className="mt-4 break-keep text-sm text-stone-500">
        카드 번호·비밀번호 같은 결제 정보는 토스페이먼츠 결제창에서만 입력되고, 공장에는 남지 않아요. 계좌로 입금하셔도 돼요.
      </p>
    </div>
  );
}

export function PaySuccess() {
  const loc = useLocation();
  const q = new URLSearchParams(loc.search);
  const [order, setOrder] = useState<PublicOrder | null>(null);
  const [error, setError] = useState("");
  const sent = useRef(false);
  const orderId = q.get("orderId") || "";

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    const paymentKey = q.get("paymentKey") || "";
    const amount = Number(q.get("amount") || 0);
    if (!paymentKey || !orderId || !amount) {
      setError("결제 정보가 없어요. 주문 조회에서 결제 상태를 확인해 주세요.");
      return;
    }
    shopPayConfirm({ payment_key: paymentKey, order_id: orderId, amount })
      .then(setOrder)
      .catch((e) => setError(errorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error)
    return (
      <div>
        <Alert tone="error">{error}</Alert>
        <p className="mb-4 break-keep text-stone-600">돈이 빠져나갔는데 이 화면이 보이면 공장에 연락해 주세요. 승인이 안 된 결제는 자동으로 취소돼요.</p>
        {orderId && (
          <Link to={`/shop/pay/${encodeURIComponent(orderId)}${recallPayAccess(orderId)}`}>
            <Button block size="lg">다시 결제하기</Button>
          </Link>
        )}
      </div>
    );
  if (!order) return <Spinner label="결제 확인 중… 이 화면을 닫지 마세요" />;
  return (
    <div>
      <div className="mb-5 border-b-2 border-brand pb-4 text-center">
        <CheckCircle2 className="mx-auto mb-2 h-12 w-12 text-green-600" />
        <div className="text-2xl font-bold text-ink">결제가 완료됐어요</div>
        <div className="mt-1 break-keep text-stone-600">바로 준비해서 보내 드릴게요.</div>
      </div>
      <div className="mb-4">
        <StatusSteps status={order.status} paid={order.paid} />
      </div>
      <div className="mb-4 space-y-1 rounded-lg border border-line bg-white p-3 text-[15px]">
        <Row k="주문번호" v={order.order_id} />
        <Row k="결제" v={<PayStatus paid={order.paid} status={order.status} />} />
        <Row k="받는 날" v={order.due_date} />
      </div>
      <Link to="/shop/my">
        <Button block size="lg" variant="ghost">주문 내역 보기</Button>
      </Link>
    </div>
  );
}

export function PayFail() {
  const loc = useLocation();
  const nav = useNavigate();
  const q = new URLSearchParams(loc.search);
  const orderId = q.get("orderId") || "";
  const code = q.get("code") || "";
  const canceled = code === "PAY_PROCESS_CANCELED" || code === "USER_CANCEL";
  return (
    <div>
      <h1 className="mb-3 text-2xl font-bold text-ink">{canceled ? "결제를 그만두셨어요" : "결제가 안 됐어요"}</h1>
      {!canceled && <Alert tone="error">{q.get("message") || "결제 중 문제가 생겼어요."}</Alert>}
      <p className="mb-4 break-keep text-stone-600">돈은 빠져나가지 않았어요. 다시 결제하거나 계좌로 입금하셔도 돼요.</p>
      {orderId && (
        <Button block size="lg" onClick={() => nav(`/shop/pay/${encodeURIComponent(orderId)}${recallPayAccess(orderId)}`)}>
          다시 결제하기
        </Button>
      )}
    </div>
  );
}
