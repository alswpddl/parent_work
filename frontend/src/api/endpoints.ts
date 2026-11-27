// 백엔드 API 를 부르는 함수 모음 (화면은 이 함수만 쓴다)
import { api, apiBlob } from "./client";
import type {
  AppSettings,
  Board,
  Briefing,
  CarrierFormat,
  Customer,
  PayInfo,
  CustomerInput,
  Features,
  GenerateResult,
  GuestOrderInput,
  GuestOrderResult,
  InventoryItem,
  StockNeed,
  KakaoStatus,
  MarketMapping,
  MarketPreview,
  MarketResult,
  MessageLog,
  NotifyResult,
  NotifyStatus,
  Order,
  OrderDraft,
  OrderInput,
  OrderLink,
  OrderPatch,
  Product,
  ProductInput,
  ProductionSummary,
  PublicForm,
  PublicOrder,
  ReorderStat,
  SendResult,
  ShopAuth,
  ShopInfo,
  ShopProfile,
  MyOrder,
  Settlement,
  StockMove,
  SystemStatus,
  TrackingPreview,
  TrackingResult,
} from "./types";

// ---------------------------------------------------------------- 시스템
export const getFeatures = () => api<Features>("/api/system/features", { auth: false });
export const getSystemStatus = () => api<SystemStatus>("/api/system/status");
export const googleCheck = () => api<{ ok: boolean; message: string }>("/api/system/google/check", { method: "POST" });
export const loginPin = (pin: string) => api<{ token: string; expires_at: string }>("/api/auth/pin", { body: { pin }, auth: false });

// ---------------------------------------------------------------- 기준정보
export const getSettings = () => api<AppSettings>("/api/settings");
export const saveSettings = (patch: Partial<AppSettings>) => api<AppSettings>("/api/settings", { method: "PUT", body: patch });

export const listCustomers = (includeInactive = false) => api<Customer[]>("/api/customers", { query: { include_inactive: includeInactive } });
export const createCustomer = (c: Partial<CustomerInput>) => api<Customer>("/api/customers", { body: c });
export const updateCustomer = (id: string, patch: Partial<Customer>) => api<Customer>(`/api/customers/${id}`, { method: "PATCH", body: patch });

export const listProducts = (includeInactive = false) => api<Product[]>("/api/products", { query: { include_inactive: includeInactive } });
export const createProduct = (p: Partial<ProductInput>) => api<Product>("/api/products", { body: p });
export const updateProduct = (sku: string, patch: Partial<Product>) => api<Product>(`/api/products/${sku}`, { method: "PATCH", body: patch });

// ---------------------------------------------------------------- 주문
export const parseOrder = (text: string, useAi = true) => api<OrderDraft>("/api/orders/parse", { body: { text, use_ai: useAi } });
export const createOrder = (o: OrderInput) => api<Order>("/api/orders", { body: o });
export const listOrders = (q: { status?: string; method?: string; customer_id?: string; include_cancelled?: boolean; due_from?: string; due_to?: string } = {}) =>
  api<{ orders: Order[]; count: number }>("/api/orders", { query: q }).then((r) => r.orders);
export const getOrder = (id: string) => api<Order>(`/api/orders/${id}`);
export const updateOrder = (id: string, patch: OrderPatch) => api<Order>(`/api/orders/${id}`, { method: "PATCH", body: patch });
export const setOrderPaid = (id: string, paid: boolean) => api<Order>(`/api/orders/${encodeURIComponent(id)}/paid`, { body: { paid } });
export const cancelOrder = (id: string) => api<Order>(`/api/orders/${id}/cancel`, { method: "POST" });
export const productionSummary = (until?: string) => api<ProductionSummary>("/api/production/summary", { query: { until } });

// ---------------------------------------------------------------- 출고
export const getBoard = () => api<Board>("/api/shipping/board");
export const listCarrierFormats = () => api<CarrierFormat[]>("/api/shipping/carriers");
export const parcelExcel = (carrier: string, orderIds?: string[]) =>
  apiBlob("/api/shipping/parcel-export", { body: { carrier, order_ids: orderIds ?? null } }, "택배발송.xlsx");
export const dispatchText = (id: string) => api<{ order_id: string; text: string }>(`/api/shipping/${id}/dispatch-text`);
export const shipOrder = (id: string) => api<Order>(`/api/shipping/${id}/ship`, { method: "POST" });
export const unshipOrder = (id: string) => api<Order>(`/api/shipping/${id}/unship`, { method: "POST" });

// ---------------------------------------------------------------- 2분기
export const issueOrderLink = (customerId: string, regenerate = false) =>
  api<OrderLink>(`/api/customers/${customerId}/order-link`, { method: "POST", query: { regenerate } });
export const revokeOrderLink = (customerId: string) => api<void>(`/api/customers/${customerId}/order-link`, { method: "DELETE" });
export const publicForm = (token: string) => api<PublicForm>(`/api/public/order-form/${token}`, { auth: false });
export const publicPlaceOrder = (token: string, body: { items: { sku: string; qty: number }[]; due_date: string | null; note: string; address: string }) =>
  api<PublicOrder>(`/api/public/orders/${token}`, { body, auth: false });
export const shopInfo = () => api<ShopInfo>("/api/public/shop", { auth: false });
export const shopPlaceOrder = (body: GuestOrderInput) => api<GuestOrderResult>("/api/public/shop/orders", { body, auth: false });
const shopAuth = (token: string): { auth: false; headers: Record<string, string> } => ({ auth: false, headers: token ? { "X-Shop-Token": token } : {} });
export const shopPlaceOrderAs = (body: GuestOrderInput, token: string) => api<GuestOrderResult>("/api/public/shop/orders", { body, ...shopAuth(token) });
export const shopSignup = (body: { name: string; company: string; phone: string; password: string; address: string; zipcode: string; agree_privacy: boolean }) =>
  api<ShopAuth>("/api/public/shop/auth/signup", { body, auth: false });
export const shopLogin = (phone: string, password: string) => api<ShopAuth>("/api/public/shop/auth/login", { body: { phone, password }, auth: false });
export const shopMe = (token: string) => api<ShopProfile>("/api/public/shop/me", shopAuth(token));
export const shopUpdateMe = (token: string, patch: Partial<ShopProfile>) => api<ShopProfile>("/api/public/shop/me", { method: "PATCH", body: patch, ...shopAuth(token) });
export const shopChangePassword = (token: string, old_password: string, new_password: string) =>
  api<ShopAuth>("/api/public/shop/me/password", { body: { old_password, new_password }, ...shopAuth(token) });
export const shopMyOrders = (token: string) => api<MyOrder[]>("/api/public/shop/me/orders", shopAuth(token));
export const resetWebPassword = (customerId: string) => api<Customer>(`/api/customers/${encodeURIComponent(customerId)}/reset-web-password`, { method: "POST" });
export const shopLookup = (orderId: string, phone4: string) =>
  api<PublicOrder>("/api/public/shop/orders/lookup", { query: { order_id: orderId, phone4 }, auth: false });
export const shopPayInfo = (orderId: string, by: { payToken?: string; phone4?: string; token?: string }) =>
  api<PayInfo>(`/api/public/shop/pay/${encodeURIComponent(orderId)}`, {
    query: { pay_token: by.payToken || "", phone: by.phone4 || "" },
    ...shopAuth(by.token || ""),
  });
export const shopPayConfirm = (body: { payment_key: string; order_id: string; amount: number }) =>
  api<PublicOrder>("/api/public/shop/pay/confirm", { body, auth: false });
export const publicRecent = (token: string) => api<PublicOrder[]>(`/api/public/orders/${token}`, { auth: false });

export const briefingPreview = () => api<Briefing>("/api/briefing/preview");
export const briefingSend = () => api<{ sent: boolean }>("/api/briefing/send", { method: "POST" });
export const kakaoStatus = () => api<KakaoStatus>("/api/integrations/kakao/status");
export const kakaoLoginUrl = () => api<{ url: string }>("/api/integrations/kakao/login-url", { method: "POST" });
export const kakaoTest = () => api<{ sent: boolean }>("/api/integrations/kakao/test", { method: "POST" });
export const kakaoDisconnect = () => api<void>("/api/integrations/kakao/disconnect", { method: "POST" });
export const listMessages = (orderId?: string, limit = 100) => api<MessageLog[]>("/api/messages", { query: { order_id: orderId, limit } });

// ---------------------------------------------------------------- 3분기
export const trackingCarriers = () => api<string[]>("/api/tracking/carriers");
export const trackingPreview = (file: File, carrier: string) => {
  const form = new FormData();
  form.append("file", file);
  form.append("carrier", carrier);
  return api<TrackingPreview>("/api/tracking/import", { form, method: "POST" });
};
export const trackingConfirm = (importId: string, carrier: string, picks: Record<number, string>, skipRows: number[]) =>
  api<TrackingResult>(`/api/tracking/import/${importId}/confirm`, { body: { carrier, picks, skip_rows: skipRows } });
export const setTracking = (id: string, carrier: string, trackingNo: string, ship = true) =>
  api<Order>(`/api/shipping/${id}/tracking`, { method: "PUT", body: { carrier, tracking_no: trackingNo, ship } });
export const setTruck = (id: string, truckNo: string, driverPhone: string, ship = true) =>
  api<Order>(`/api/shipping/${id}/truck`, { method: "PUT", body: { truck_no: truckNo, driver_phone: driverPhone, ship } });

export const notifyStatus = () => api<NotifyStatus>("/api/notify/status");
export const notifyTemplates = () => api<Record<string, { name: string; env: string; text: string }>>("/api/notify/templates");
export const notifyPreview = (id: string) => api<NotifyResult>(`/api/notify/${id}/preview`);
export const notifyResend = (id: string) => api<NotifyResult>(`/api/notify/${id}/send`, { method: "POST" });

export const marketPreview = (file: File, source: string) => {
  const form = new FormData();
  form.append("file", file);
  form.append("source", source);
  return api<MarketPreview>("/api/marketplace/import", { form, method: "POST" });
};
export const marketConfirm = (
  previewId: string,
  mappings: Record<string, { sku: string; multiplier: number; remember: boolean }>,
  skipOrders: string[],
) => api<MarketResult>(`/api/marketplace/import/${previewId}/confirm`, { body: { mappings, skip_orders: skipOrders } });
export const marketMappings = () => api<MarketMapping[]>("/api/marketplace/mappings");
export const deleteMarketMapping = (source: string, externalName: string) =>
  api<void>("/api/marketplace/mappings", { method: "DELETE", query: { source, external_name: externalName } });

// ---------------------------------------------------------------- 4분기
export const listInventory = () => api<InventoryItem[]>("/api/inventory");
export const createInventoryItem = (body: Partial<InventoryItem> & { name: string }) => api<InventoryItem>("/api/inventory", { body });
export const updateInventoryItem = (id: string, patch: Partial<InventoryItem>) => api<InventoryItem>(`/api/inventory/${id}`, { method: "PATCH", body: patch });
export const receiveStock = (id: string, qty: number, memo: string) => api<InventoryItem>(`/api/inventory/${id}/receive`, { body: { qty, memo } });
export const adjustStock = (id: string, stock: number, reason: string) => api<InventoryItem>(`/api/inventory/${id}/adjust`, { body: { stock, reason } });
export const stockMoves = (itemId?: string, limit = 100) => api<StockMove[]>("/api/inventory/moves", { query: { item_id: itemId, limit } });
export const stockNeeds = (until?: string) => api<StockNeed[]>("/api/inventory/needs", { query: { until } });
export const stocktake = (counts: Record<string, number>, reason: string) =>
  api<{ changed: number; items: InventoryItem[] }>("/api/inventory/stocktake", { body: { counts, reason } });
export const stockCheck = () => api<{ low: number; alerted: number; reason?: string }>("/api/inventory/check", { method: "POST" });

export const listSettlements = (period?: string) => api<Settlement[]>("/api/settlements", { query: { period } });
export const generateSettlements = (period: string, force = false) => api<GenerateResult>("/api/settlements/generate", { body: { period, force } });
export const settlementPdf = (id: string) => apiBlob(`/api/settlements/${id}/pdf`, {}, "거래명세표.pdf");
export const settlementLink = (id: string) => api<{ url: string }>(`/api/settlements/${id}/link`);
export const sendSettlement = (id: string, via: string[]) => api<SendResult>(`/api/settlements/${id}/send`, { body: { via } });
export const sendAllSettlements = (period: string, via: string[]) => api<SendResult[]>("/api/settlements/send-all", { body: { via }, query: { period } });
export const updateSettlement = (id: string, patch: { status?: string; paid_at?: string | null; memo?: string }) =>
  api<Settlement>(`/api/settlements/${id}`, { method: "PATCH", body: patch });

export const reorderReminders = () => api<ReorderStat[]>("/api/reorder/reminders");
export const reorderStats = () => api<ReorderStat[]>("/api/reorder/stats");
export const reorderSnooze = (customerId: string, days: number) => api<ReorderStat>(`/api/reorder/${customerId}/snooze`, { body: { days } });
export const reorderRecompute = () => api<{ updated: number; due: number }>("/api/reorder/recompute", { method: "POST" });
