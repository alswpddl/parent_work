import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { getToken } from "./api/client";
import { getFeatures } from "./api/endpoints";
import type { Features } from "./api/types";
import { Alert, Button, Spinner } from "./components/ui";
import AdminLayout from "./layouts/AdminLayout";
import { FeaturesProvider } from "./lib/features";
import { isShopHost } from "./lib/host";
import Home from "./pages/Home";
import Inventory from "./pages/Inventory";
import Tanks from "./pages/Tanks";
import Login from "./pages/Login";
import Marketplace from "./pages/Marketplace";
import More from "./pages/More";
import NewOrder from "./pages/NewOrder";
import Orders from "./pages/Orders";
import Reorder from "./pages/Reorder";
import Settings from "./pages/Settings";
import Settlements from "./pages/Settlements";
import Shipping from "./pages/Shipping";
import SelfOrder from "./pages/public/SelfOrder";
import ShopApp from "./pages/shop/ShopApp";
import Today from "./pages/Today";

export default function App() {
  const location = useLocation();
  // 손님 주문서 전용 주소: 관리자 화면 없이 주문서(+ 거래처 셀프주문)만
  if (isShopHost()) {
    return (
      <Routes>
        <Route path="/order/:token" element={<SelfOrder />} />
        <Route path="*" element={<ShopApp />} />
      </Routes>
    );
  }
  // 고객용 화면(거래처 셀프주문, 웹 주문서)은 로그인·기능목록 없이 바로 띄운다
  if (location.pathname.startsWith("/order/") || location.pathname === "/shop" || location.pathname.startsWith("/shop/")) {
    return (
      <Routes>
        <Route path="/order/:token" element={<SelfOrder />} />
        <Route path="/shop/*" element={<ShopApp />} />
      </Routes>
    );
  }
  return <AdminApp />;
}

function AdminApp() {
  const [features, setFeatures] = useState<Features | null>(null);
  const [error, setError] = useState("");
  const [authed, setAuthed] = useState<boolean>(!!getToken());

  const load = () => {
    setError("");
    getFeatures()
      .then(setFeatures)
      .catch(() => setError("서버에 연결하지 못했어요. 잠시 뒤 다시 눌러 주세요. (처음 접속이면 서버가 깨어나는 데 1분 정도 걸릴 수 있어요)"));
  };
  useEffect(load, []);
  useEffect(() => {
    const onUnauthorized = () => setAuthed(false);
    window.addEventListener("api:unauthorized", onUnauthorized);
    return () => window.removeEventListener("api:unauthorized", onUnauthorized);
  }, []);

  if (error)
    return (
      <div className="mx-auto max-w-md p-6">
        <Alert tone="error">{error}</Alert>
        <Button block onClick={load}>
          다시 연결하기
        </Button>
      </div>
    );
  if (!features) return <Spinner label="공장 도우미를 여는 중…" />;
  if (features.auth_required && !authed) return <Login onDone={() => setAuthed(true)} />;

  const has = (n: string) => features.modules.some((m) => m.name === n);
  return (
    <FeaturesProvider value={features}>
      <Routes>
        <Route element={<AdminLayout onLogout={() => setAuthed(false)} />}>
          <Route index element={<Home />} />
          <Route path="today" element={<Today />} />
          <Route path="orders/new" element={<NewOrder />} />
          <Route path="orders" element={<Orders />} />
          <Route path="shipping" element={<Shipping />} />
          {has("q4_inventory") && <Route path="inventory" element={<Inventory />} />}
          {has("q4_inventory") && <Route path="tanks" element={<Tanks />} />}
          {has("q4_settlement") && <Route path="settlements" element={<Settlements />} />}
          {has("q4_reorder") && <Route path="reorder" element={<Reorder />} />}
          {has("q3_marketplace") && <Route path="marketplace" element={<Marketplace />} />}
          <Route path="settings" element={<Settings />} />
          <Route path="more" element={<More onLogout={() => setAuthed(false)} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </FeaturesProvider>
  );
}
