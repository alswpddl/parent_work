"""_설정 탭에 key/value 로 저장되는 운영 설정. 부모님이 시트에서 직접 고쳐도 된다."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# (key, 항목 라벨, 기본값, 설명) — 탭에 없는 키는 서버 시작 시 기본값으로 채워 넣는다.
SETTING_DEFS: list[tuple[str, str, str, str]] = [
    # --- 1분기: 출고
    ("threshold_kg", "화물 기준 무게(kg)", "50", "주문 총중량이 이 값 이상이면 화물 트럭으로 분류"),
    ("pallet_kg", "파레트 1개당 무게(kg)", "600", "화물 배차 문자에 파레트 수를 계산할 때 사용"),
    ("factory_name", "공장 이름", "", "택배 보내는 분 / 배차 문자 상차지 이름 / 명세서 상호"),
    ("factory_address", "공장 주소(상차지)", "", ""),
    ("factory_zipcode", "공장 우편번호", "", ""),
    ("factory_phone", "공장 전화번호", "", ""),
    ("default_carrier", "기본 택배사", "generic", "generic / logen / cj"),
    # --- 2분기: 셀프주문·브리핑
    ("briefing_time", "아침 브리핑 시각", "08:00", "안내용. 실제 발송 시각은 GitHub Actions 일정에서 바꿉니다"),
    ("briefing_enabled", "아침 브리핑 보내기", "예", "예 / 아니오"),
    ("self_order_lead_days", "셀프주문 최소 준비일", "1", "오늘로부터 며칠 뒤부터 납기일로 고를 수 있는지"),
    ("self_order_notice", "셀프주문 안내 문구", "", "거래처 주문 화면 맨 위에 보이는 문구"),
    ("notify_new_self_order", "셀프주문 들어오면 카톡 알림", "예", "예 / 아니오"),
    # --- 웹 주문서 (/shop)
    ("shop_enabled", "웹 주문서 받기", "예", "예 / 아니오 — 아니오면 주문서 화면에 '지금은 주문을 받지 않아요' 표시"),
    ("shop_show_prices", "웹 주문서에 가격 보이기", "예", "예 / 아니오"),
    ("shop_notice", "웹 주문서 안내 문구", "", "주문서 맨 위에 보이는 문구 (예: 오후 2시 전 주문은 당일 출고)"),
    ("privacy_retention", "개인정보 보관 기간", "주문일로부터 1년", "웹 주문서 개인정보 동의 문구에 표시"),
    ("shop_intro", "웹 주문서 공장 소개", "", "주문서 첫 화면에 보이는 소개 (예: 통영에서 30년, 국산 새우로 직접 담급니다)"),
    ("shop_shipping_fee", "웹 주문 택배비(원)", "0", "0 이면 '택배비는 확인 후 안내'로 표시"),
    ("shop_free_shipping_over", "택배비 무료 기준 금액(원)", "0", "이 금액 이상 주문하면 택배비 무료. 0 이면 무료 없음"),
    ("closed_days", "받는 날로 못 고르는 요일", "일", "쉼표로 (예: 일 또는 토,일). 택배가 쉬는 날. 없으면 '없음'"),
    # --- 3분기: 알림톡
    ("notify_customers", "거래처 출고 알림톡 보내기", "예", "예 / 아니오"),
    # --- 4분기: 재고·정산·리마인드
    ("stock_alert_enabled", "재고 부족 카톡 경고", "예", "예 / 아니오"),
    ("stock_lead_days", "자재 발주 소요일", "5", "발주 후 받을 때까지 걸리는 날 (소진 예측에 사용)"),
    ("company_biz_no", "사업자등록번호", "", "거래명세표 공급자 정보"),
    ("company_owner", "대표자", "", ""),
    ("company_biz_type", "업태", "제조", ""),
    ("company_biz_item", "종목", "식품", ""),
    ("bank_account", "입금 계좌", "", "거래명세표 하단에 표시 (예: 농협 000-0000-0000 홍길동)"),
    ("statement_note", "명세서 안내 문구", "", "거래명세표 하단 메모"),
    ("reorder_factor", "리마인드 기준 배수", "1.3", "평균 주문 간격 × 이 값보다 오래 주문이 없으면 알림"),
    ("reorder_min_orders", "리마인드 최소 주문 횟수", "3", "이 횟수 이상 주문한 거래처만 계산"),
]

_YES = {"예", "네", "y", "yes", "true", "1", "on", "o"}


class AppSettings(BaseModel):
    threshold_kg: float = Field(default=50, ge=0)
    pallet_kg: float = Field(default=600, gt=0)
    factory_name: str = ""
    factory_address: str = ""
    factory_zipcode: str = ""
    factory_phone: str = ""
    default_carrier: str = "generic"
    briefing_time: str = "08:00"
    briefing_enabled: bool = True
    self_order_lead_days: int = Field(default=1, ge=0, le=30)
    self_order_notice: str = ""
    notify_new_self_order: bool = True
    shop_enabled: bool = True
    shop_show_prices: bool = True
    shop_notice: str = ""
    privacy_retention: str = "주문일로부터 1년"
    shop_intro: str = ""
    shop_shipping_fee: int = Field(default=0, ge=0, le=100_000)
    shop_free_shipping_over: int = Field(default=0, ge=0)
    closed_days: str = "일"
    notify_customers: bool = True
    stock_alert_enabled: bool = True
    stock_lead_days: int = Field(default=5, ge=0, le=90)
    company_biz_no: str = ""
    company_owner: str = ""
    company_biz_type: str = "제조"
    company_biz_item: str = "식품"
    bank_account: str = ""
    statement_note: str = ""
    reorder_factor: float = Field(default=1.3, ge=1.0, le=5.0)
    reorder_min_orders: int = Field(default=3, ge=2, le=50)

    @field_validator(
        "briefing_enabled", "notify_new_self_order", "shop_enabled", "shop_show_prices", "notify_customers",
        "stock_alert_enabled", mode="before",
    )
    @classmethod
    def _yes_no(cls, v):
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in _YES


class SettingsPatch(BaseModel):
    threshold_kg: float | None = Field(default=None, ge=0)
    pallet_kg: float | None = Field(default=None, gt=0)
    factory_name: str | None = None
    factory_address: str | None = None
    factory_zipcode: str | None = None
    factory_phone: str | None = None
    default_carrier: str | None = None
    briefing_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    briefing_enabled: bool | None = None
    self_order_lead_days: int | None = Field(default=None, ge=0, le=30)
    self_order_notice: str | None = None
    notify_new_self_order: bool | None = None
    shop_enabled: bool | None = None
    shop_show_prices: bool | None = None
    shop_notice: str | None = None
    privacy_retention: str | None = Field(default=None, max_length=60)
    shop_intro: str | None = Field(default=None, max_length=500)
    shop_shipping_fee: int | None = Field(default=None, ge=0, le=100_000)
    shop_free_shipping_over: int | None = Field(default=None, ge=0)
    closed_days: str | None = Field(default=None, max_length=20)
    notify_customers: bool | None = None
    stock_alert_enabled: bool | None = None
    stock_lead_days: int | None = Field(default=None, ge=0, le=90)
    company_biz_no: str | None = None
    company_owner: str | None = None
    company_biz_type: str | None = None
    company_biz_item: str | None = None
    bank_account: str | None = None
    statement_note: str | None = None
    reorder_factor: float | None = Field(default=None, ge=1.0, le=5.0)
    reorder_min_orders: int | None = Field(default=None, ge=2, le=50)


WEEKDAYS_KO = "월화수목금토일"


def closed_weekdays(text: str) -> set[int]:
    """'토,일' → {5, 6} (월=0). 모르는 글자는 무시."""
    return {WEEKDAYS_KO.index(ch) for ch in (text or "") if ch in WEEKDAYS_KO}
