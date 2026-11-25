from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator

from .common import CustomerType, DefaultMethod


def _clean(v: str | None) -> str:
    return (v or "").strip()


class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    aliases: str = ""
    type: CustomerType = "B2B"
    contact_name: str = ""
    phone: str = ""
    address: str = ""
    zipcode: str = ""
    default_method: DefaultMethod = "자동"
    memo: str = ""
    # 3·4분기 항목 (비워 둬도 됨)
    notify_opt_in: bool = True
    biz_no: str = ""
    owner_name: str = ""
    email: str = ""

    @field_validator(
        "name", "aliases", "contact_name", "phone", "address", "zipcode", "memo", "biz_no", "owner_name", "email",
        mode="before",
    )
    @classmethod
    def _strip(cls, v):
        return _clean(v)


class CustomerCreate(CustomerBase):
    pass


class CustomerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    aliases: str | None = None
    type: CustomerType | None = None
    contact_name: str | None = None
    phone: str | None = None
    address: str | None = None
    zipcode: str | None = None
    default_method: DefaultMethod | None = None
    memo: str | None = None
    active: bool | None = None
    notify_opt_in: bool | None = None
    biz_no: str | None = None
    owner_name: str | None = None
    email: str | None = None
    reorder_snooze_until: date | None = None


class CustomerOut(CustomerBase):
    customer_id: str
    active: bool = True
    has_order_link: bool = False
    has_web_account: bool = False  # 웹 주문서 로그인 비밀번호를 만들었는지
    last_order_date: date | None = None
    avg_interval_days: float | None = None
    reorder_snooze_until: date | None = None

    @classmethod
    def from_row(cls, d: dict) -> "CustomerOut":
        return cls(
            customer_id=d["customer_id"],
            name=d.get("name") or "(이름 없음)",
            aliases=d.get("aliases") or "",
            type=d.get("type") if d.get("type") in ("B2B", "B2C") else "B2B",  # type: ignore[arg-type]
            contact_name=d.get("contact_name") or "",
            phone=d.get("phone") or "",
            address=d.get("address") or "",
            zipcode=d.get("zipcode") or "",
            default_method=d.get("default_method") if d.get("default_method") in ("자동", "택배", "화물") else "자동",  # type: ignore[arg-type]
            memo=d.get("memo") or "",
            active=d.get("active") is not False,  # 빈칸이면 사용 중으로 본다
            notify_opt_in=d.get("notify_opt_in") is not False,  # 빈칸이면 받는 것으로 본다
            biz_no=d.get("biz_no") or "",
            owner_name=d.get("owner_name") or "",
            email=d.get("email") or "",
            has_order_link=bool(d.get("order_token")),
            has_web_account=bool(d.get("web_password")),
            last_order_date=d.get("last_order_date"),
            avg_interval_days=d.get("avg_interval_days"),
            reorder_snooze_until=d.get("reorder_snooze_until"),
        )

    def alias_list(self) -> list[str]:
        return [a.strip() for a in self.aliases.replace("，", ",").split(",") if a.strip()]
