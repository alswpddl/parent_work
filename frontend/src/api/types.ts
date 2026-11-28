// 백엔드 schemas 와 1:1 로 맞춘 타입 (app/schemas/*.py, app/modules/*/service.py)

export type ShipMethod = "택배" | "화물";
export type OrderStatus = "접수" | "출고대기" | "출고완료" | "취소";
export type DefaultMethod = "자동" | "택배" | "화물";

export interface Candidate {
  id: string;
  label: string;
  score: number;
}

// ---------------------------------------------------------------- 시스템
export interface Features {
  modules: { name: string; title: string; quarter: number }[];
  ai_parser: boolean;
  auth_required: boolean;
  env: string;
  integrations: { ai: boolean; kakao: boolean; solapi: boolean; email: boolean; toss?: boolean; toss_test?: boolean };
  public_web_url: string;
  public_shop_url?: string; // 손님 주문서 주소 (따로 있으면 /shop 없이)
}

export interface SystemStatus {
  startup: Record<string, unknown>;
  jobs: { name: string; cron: string | null; module: string; description: string; last_run_at: string | null; last_result: Record<string, unknown> | null }[];
  config_problems: string[];
  integration_warnings: string[];
  modules: string[];
  sheets_backend: string;
  google: { connected: boolean; service_account_email: string; spreadsheet_url: string; system_spreadsheet_url: string };
  kakao_bot: { enabled: boolean; skill_url: string };
}

// ---------------------------------------------------------------- 기준정보
export interface AppSettings {
  threshold_kg: number;
  pallet_kg: number;
  factory_name: string;
  factory_address: string;
  factory_zipcode: string;
  factory_phone: string;
  default_carrier: string;
  briefing_time: string;
  briefing_enabled: boolean;
  self_order_lead_days: number;
  self_order_notice: string;
  notify_new_self_order: boolean;
  notify_customers: boolean;
  stock_alert_enabled: boolean;
  stock_lead_days: number;
  company_biz_no: string;
  company_owner: string;
  company_biz_type: string;
  company_biz_item: string;
  mail_order_no: string;
  auto_delivered_days: number;
  privacy_officer: string;
  refund_policy: string;
  bank_account: string;
  statement_note: string;
  reorder_factor: number;
  reorder_min_orders: number;
  shop_enabled: boolean;
  shop_show_prices: boolean;
  shop_notice: string;
  shop_intro: string;
  privacy_retention: string;
  shop_shipping_fee: number;
  shop_free_shipping_over: number;
  closed_days: string;
  contact_hours: string;
  quiet_hours: string;
  daily_capacity_kg: number;
}

export interface Customer {
  customer_id: string;
  name: string;
  aliases: string;
  type: "B2B" | "B2C";
  contact_name: string;
  phone: string;
  address: string;
  zipcode: string;
  default_method: DefaultMethod;
  memo: string;
  notify_opt_in: boolean;
  biz_no: string;
  owner_name: string;
  email: string;
  active: boolean;
  has_order_link: boolean;
  last_order_date: string | null;
  avg_interval_days: number | null;
  reorder_snooze_until: string | null;
  has_web_account?: boolean;
}
export type CustomerInput = Omit<Customer, "customer_id" | "active" | "has_order_link" | "last_order_date" | "avg_interval_days" | "reorder_snooze_until">;

export interface Product {
  sku: string;
  name: string;
  spec: string;
  aliases: string;
  unit: string;
  unit_kg: number;
  units_per_box: number | null;
  unit_price: number | null;
  retail_price: number | null;
  description: string;
  shop_visible: boolean;
  sold_out: boolean;
  lead_days: number | null;
  image_url: string;
  detail: string;
  tax_type: "과세" | "면세" | "";
  container_item: string;
  box_item: string;
  label_item: string;
  lid_item: string;
  bulk_item: string;
  net_kg: number | null;
  active: boolean;
}
export type ProductInput = Omit<Product, "sku" | "active"> & { sku?: string | null };

// ---------------------------------------------------------------- 주문
export interface DraftItem {
  sku: string | null;
  raw_name: string;
  product_name: string;
  qty: number;
  unit_kg: number;
  line_kg: number;
  matched: boolean;
  candidates: Candidate[];
}

export interface OrderDraft {
  parser: "ai" | "rule";
  customer: { customer_id: string | null; name: string; matched: boolean; candidates: Candidate[] };
  recipient: string;
  phone: string;
  address: string;
  zipcode: string;
  due_date: string | null;
  note: string;
  items: DraftItem[];
  order_kg: number;
  ship_method: ShipMethod;
  method_by: string;
  pallets: number;
  threshold_kg: number;
  warnings: string[];
  raw_text: string;
}

export interface OrderLine {
  line_no: number;
  sku: string;
  product_name: string;
  qty: number;
  line_kg: number;
  unit_price: number | null;
  amount: number | null;
}

export interface Order {
  order_id: string;
  created_at: string | null;
  updated_at: string | null;
  source: string;
  customer_id: string;
  customer_name: string;
  recipient: string;
  phone: string;
  address: string;
  zipcode: string;
  due_date: string | null;
  note: string;
  status: OrderStatus;
  ship_method: ShipMethod;
  method_by: string;
  order_kg: number;
  pallets: number;
  boxes: number;
  total_amount: number | null;
  shipping_fee: number;
  shipped_at: string | null;
  delivered_at?: string | null; // 도착일시
  paid_at: string | null;
  carrier: string;
  tracking_no: string;
  truck_no: string;
  driver_phone: string;
  notified_at: string | null;
  ext_order_no: string;
  stock_deducted: boolean;
  settlement_id: string;
  raw_text: string;
  lines: OrderLine[];
}

export interface OrderInput {
  customer_id?: string | null;
  customer_name?: string;
  recipient?: string;
  phone?: string;
  address?: string;
  zipcode?: string;
  due_date?: string | null;
  note?: string;
  items: { sku: string; qty: number }[];
  ship_method?: ShipMethod | null;
  source?: string;
  raw_text?: string;
}

export interface OrderPatch extends Partial<Omit<OrderInput, "items">> {
  items?: { sku: string; qty: number }[];
  auto_method?: boolean;
  status?: "접수" | "출고대기";
}

export interface ProductionSummary {
  until: string | null;
  lines: { sku: string; product_name: string; qty: number; kg: number; order_count: number }[];
  parcel_count: number;
  truck_count: number;
  order_count: number;
}

export interface Board {
  threshold_kg: number;
  parcel: Order[];
  truck: Order[];
  parcel_kg: number;
  truck_kg: number;
}

export interface CarrierFormat {
  code: string;
  name: string;
  verified: boolean;
}

// ---------------------------------------------------------------- 2분기
export interface OrderLink {
  customer_id: string;
  url: string;
  token: string;
}

export interface PublicForm {
  customer_name: string;
  address: string;
  notice: string;
  min_due_date: string;
  products: { sku: string; name: string; spec: string; unit: string; display_name: string }[];
  last_items: { sku: string; qty: number }[];
}

export interface PublicOrder {
  order_id: string;
  created_at: string;
  status: string;
  due_date: string;
  items: string;
  ship_method: string;
  carrier: string;
  tracking_no: string;
  truck_no: string;
  paid: boolean;
  delivered?: boolean; // 도착
}

export interface Briefing {
  day: string;
  text: string;
  sections: { title: string; lines: string[] }[];
  kakao_connected: boolean;
  enabled: boolean;
}

export interface KakaoStatus {
  configured: boolean;
  connected: boolean;
  nickname: string;
  connected_at: string | null;
  refresh_expires_at: string | null;
  redirect_uri: string;
}

export interface MessageLog {
  ts: string;
  channel: string;
  kind: string;
  to: string;
  order_id: string;
  result: string;
  content: string;
  error: string;
}

// ---------------------------------------------------------------- 3분기
export interface TrackingRow {
  row_no: number;
  tracking_no: string;
  name: string;
  phone: string;
  order_id: string | null;
  customer_name: string;
  status: "매칭" | "확인필요" | "못찾음" | "이미등록" | "송장없음";
  message: string;
  candidates: string[];
}

export interface TrackingPreview {
  import_id: string;
  carrier: string;
  rows: TrackingRow[];
  matched: number;
  total: number;
}

export interface TrackingResult {
  registered: number;
  shipped: number;
  skipped: number;
  errors: string[];
}

export interface NotifyStatus {
  configured: boolean;
  enabled: boolean;
  templates: Record<string, { name: string; env: string; ready: boolean }>;
  sms_fallback: boolean;
}

export interface NotifyResult {
  sent: boolean;
  kind: string;
  reason: string;
  preview: string;
}

export interface MarketLine {
  external_name: string;
  qty: number;
  sku: string | null;
  multiplier: number;
  mapped: boolean;
  candidates: Candidate[];
}

export interface MarketOrder {
  ext_order_no: string;
  recipient: string;
  phone: string;
  address: string;
  zipcode: string;
  message: string;
  lines: MarketLine[];
  status: "등록가능" | "확인필요" | "이미등록";
}

export interface MarketPreview {
  preview_id: string;
  source: string;
  adapter: string;
  orders: MarketOrder[];
  unmapped_names: string[];
  ready: number;
  duplicates: number;
}

export interface MarketResult {
  created: number;
  skipped: number;
  order_ids: string[];
  errors: string[];
}

export interface MarketMapping {
  source: string;
  external_name: string;
  sku: string;
  multiplier: number;
}

// ---------------------------------------------------------------- 4분기
export interface InventoryItem {
  item_id: string;
  category: string;
  name: string;
  unit: string;
  stock: number;
  safety_stock: number;
  reorder_qty: number;
  supplier: string;
  supplier_phone: string;
  status: "정상" | "곧부족" | "부족" | "없음";
  avg_daily_use: number;
  days_left: number | null;
  order_by: string | null;
  used_by: string[];
}

/** 출고 전 주문들이 쓸 자재·저장고 젓갈 vs 지금 재고 */
export interface StockNeed {
  item_id: string;
  name: string;
  category: string;
  unit: string;
  need: number;
  stock: number;
  short: number;
}

export interface StockMove {
  ts: string;
  item_id: string;
  item_name: string;
  change: number;
  stock_after: number;
  reason: string;
  order_id: string;
}

export interface Settlement {
  settlement_id: string;
  period: string;
  customer_id: string;
  customer_name: string;
  order_count: number;
  supply_amount: number;
  vat: number;
  total: number;
  status: "생성" | "발송완료" | "수금완료";
  sent_at: string | null;
  paid_at: string | null;
  memo: string;
  has_email: boolean;
  has_phone: boolean;
}

export interface GenerateResult {
  period: string;
  created: number;
  updated: number;
  kept: string[];
  warnings: string[];
  settlements: Settlement[];
}

export interface SendResult {
  settlement_id: string;
  results: Record<string, string>;
  status: string;
}

export interface ReorderStat {
  customer_id: string;
  customer_name: string;
  phone: string;
  order_count: number;
  last_order_date: string | null;
  avg_interval_days: number | null;
  days_since: number | null;
  expected_date: string | null;
  overdue_days: number;
  due: boolean;
  snoozed_until: string | null;
  last_items: string;
}

// ---------------------------------------------------------------- 웹 주문서 (/shop)
export interface ShopProduct {
  sku: string;
  name: string;
  spec: string;
  unit: string;
  unit_kg: number;
  price: number | null;
  description: string;
  sold_out: boolean;
  image_url: string;
  lead_days: number;
  detail: string;
  review_avg: number | null;
  review_count: number;
}

export interface ShopInfo {
  factory_name: string;
  factory_phone: string;
  factory_address: string;
  notice: string;
  intro: string;
  contact_hours: string;
  show_prices: boolean;
  bank_account: string;
  min_due_date: string;
  closed_weekdays: number[];
  closed_days_text: string;
  shipping_fee: number;
  free_shipping_over: number;
  threshold_kg: number;
  privacy_text: string;
  products: ShopProduct[];
  pay_client_key: string; // 비면 온라인 결제 꺼짐 (계좌 입금만)
  pay_test_mode: boolean;
  kakao_login: boolean;
  google_login?: boolean;
  sms_verify?: boolean; // 비회원 조회를 이름+휴대폰+문자 인증번호로
  business?: Record<string, string>; // 맨 아래 사업자 정보 (상호·대표자·사업자등록번호…)
  refund_policy?: string;
  privacy_retention?: string;
}

export interface ShopReview {
  review_id: string;
  created_at: string;
  product_name: string;
  spec: string;
  author: string;
  rating: number;
  text: string;
}
export interface ShopReviewList {
  average: number | null;
  count: number;
  items: ShopReview[];
}
export interface AdminReview extends ShopReview {
  order_id: string;
  customer_id: string;
  hidden: boolean;
}

/** 결제창 띄우기 전 서버가 정해 준 값 (금액은 서버 계산) */
export interface PayInfo {
  order_id: string;
  order_name: string;
  amount: number;
  customer_name: string;
  client_key: string;
  test_mode: boolean;
}

export interface GuestOrderInput {
  name: string;
  company: string;
  phone: string;
  address: string;
  zipcode: string;
  due_date: string | null;
  note: string;
  items: { sku: string; qty: number }[];
  agree_privacy: boolean;
  website: string;
  client_token: string;
  password?: string;
  receipt_type?: "" | "현금영수증" | "세금계산서";
  receipt_id?: string;
  receipt_email?: string;
}

export interface GuestOrderResult {
  order_id: string;
  created_at: string;
  items: string;
  due_date: string;
  ship_method: string;
  subtotal: number | null;
  shipping_fee: number | null;
  estimated_total: number | null;
  shipping_note: string;
  bank_account: string;
  factory_phone: string;
  token: string;
  pay_token: string;
}

export interface ShopProfile {
  name: string;
  company: string;
  phone: string;
  address: string;
  zipcode: string;
}

export interface ShopAuth {
  token: string;
  profile: ShopProfile;
}

export interface MyOrder {
  order_id: string;
  created_at: string;
  status: string;
  delivered?: boolean;
  due_date: string;
  ship_method: string;
  lines: { sku: string; name: string; qty: number; amount: number | null }[];
  subtotal: number | null;
  shipping_fee: number;
  total: number | null;
  paid: boolean;
  recipient: string;
  address: string;
  carrier: string;
  tracking_no: string;
  truck_no: string;
  recipient_phone: string;
  zipcode: string;
  can_cancel: boolean;
  cancel_note: string;
  reviewable: string[];
}

// ---------------------------------------------------------------- 숙성 저장소 지도
export type TankStatus = "ready" | "aging" | "empty";
export interface Tank {
  tank_id: string;
  building: string;
  no: number;
  row: number;
  col: number;
  capacity_kg: number;
  current_kg: number;
  product: string;
  filled_on: string;
  memo: string;
  status: TankStatus;
  ready_on: string | null;
  months_left: number | null;
  progress: number;
}
export interface TankBuilding {
  name: string;
  rows: number;
  cols: number;
  total_kg: number;
  tanks: Tank[];
}
export interface TankMap {
  aging_months: number;
  summary: {
    ready_count: number;
    ready_kg: number;
    aging_count: number;
    aging_kg: number;
    empty_count: number;
    in_3m_kg: number;
    in_6m_kg: number;
    in_12m_kg: number;
  };
  buildings: TankBuilding[];
}
