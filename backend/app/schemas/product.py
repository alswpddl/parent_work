from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TaxType = Literal["과세", "면세", ""]


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    spec: str = Field(default="", max_length=30)
    aliases: str = ""
    unit: str = "개"
    unit_kg: float = Field(default=0, ge=0, le=2000)
    units_per_box: int | None = Field(default=None, ge=1, le=1000)
    unit_price: int | None = Field(default=None, ge=0)
    # 웹 주문서: 개인 판매가(부가세 포함, 비우면 공급단가)·설명·노출·품절
    retail_price: int | None = Field(default=None, ge=0)
    description: str = Field(default="", max_length=200)
    shop_visible: bool = True
    sold_out: bool = False
    lead_days: int | None = Field(default=None, ge=0, le=60)
    image_url: str = Field(default="", max_length=500)
    detail: str = Field(default="", max_length=3000)
    # 4분기: 세금·자재 매핑
    tax_type: TaxType = ""
    container_item: str = ""
    box_item: str = ""
    label_item: str = ""
    lid_item: str = ""
    bulk_item: str = ""
    net_kg: float | None = Field(default=None, gt=0, le=2000)

    @field_validator("name", "spec", "aliases", "unit", "description", "container_item", "box_item", "label_item", "lid_item", "bulk_item", "image_url", "detail", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()


class ProductCreate(ProductBase):
    sku: str | None = Field(default=None, max_length=30, description="비우면 P0001 형식으로 자동 발급")


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    spec: str | None = None
    aliases: str | None = None
    unit: str | None = None
    unit_kg: float | None = Field(default=None, ge=0, le=2000)
    units_per_box: int | None = Field(default=None, ge=1, le=1000)
    unit_price: int | None = Field(default=None, ge=0)
    active: bool | None = None
    retail_price: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=200)
    shop_visible: bool | None = None
    sold_out: bool | None = None
    lead_days: int | None = Field(default=None, ge=0, le=60)
    image_url: str | None = Field(default=None, max_length=500)
    detail: str | None = Field(default=None, max_length=3000)
    tax_type: TaxType | None = None
    container_item: str | None = None
    box_item: str | None = None
    label_item: str | None = None
    lid_item: str | None = None
    bulk_item: str | None = None
    net_kg: float | None = Field(default=None, gt=0, le=2000)


class ProductOut(ProductBase):
    sku: str
    active: bool = True

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.spec}".strip()

    @property
    def content_kg(self) -> float:
        """젓갈 내용량(kg). 내용량kg 칸 → 없으면 규격('1kg', '500g', '1.5키로')에서 읽음 → 그래도 없으면 0."""
        if self.net_kg:
            return self.net_kg
        m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|키로|킬로|g|그램)", self.spec.lower())
        if not m:
            return 0.0
        v = float(m.group(1))
        return v / 1000 if m.group(2) in ("g", "그램") else v

    @property
    def shop_price(self) -> int | None:
        """웹 주문서 가격: 개인판매가가 있으면 그것, 없으면 공급단가."""
        return self.retail_price if self.retail_price is not None else self.unit_price

    @property
    def is_taxable(self) -> bool:
        """비어 있으면 과세로 본다 (가공식품 대부분이 과세)."""
        return self.tax_type != "면세"

    @classmethod
    def from_row(cls, d: dict) -> "ProductOut":
        tax = d.get("tax_type") or ""
        return cls(
            sku=d["sku"],
            name=d.get("name") or "(이름 없음)",
            spec=d.get("spec") or "",
            aliases=d.get("aliases") or "",
            unit=d.get("unit") or "개",
            unit_kg=max(0.0, float(d.get("unit_kg") or 0)),
            units_per_box=d.get("units_per_box") if (d.get("units_per_box") or 0) >= 1 else None,
            unit_price=d.get("unit_price") if (d.get("unit_price") or 0) >= 0 else None,
            active=d.get("active") is not False,
            description=d.get("description") or "",
            shop_visible=d.get("shop_visible") is not False,  # 빈칸이면 보이게
            retail_price=d.get("retail_price") if (d.get("retail_price") or 0) > 0 else None,
            sold_out=d.get("sold_out") is True,
            image_url=d.get("image_url") or "",
            detail=d.get("detail") or "",
            lead_days=_lead(d.get("lead_days")),
            tax_type=tax if tax in ("과세", "면세") else "",  # type: ignore[arg-type]
            container_item=d.get("container_item") or "",
            box_item=d.get("box_item") or "",
            label_item=d.get("label_item") or "",
            lid_item=d.get("lid_item") or "",
            bulk_item=d.get("bulk_item") or "",
            net_kg=d.get("net_kg") if (d.get("net_kg") or 0) > 0 else None,
        )

    def alias_list(self) -> list[str]:
        return [a.strip() for a in self.aliases.replace("，", ",").split(",") if a.strip()]


def _lead(v: object) -> int | None:
    """시트 '준비일' 칸 → 0 이상 정수, 비었거나 이상하면 None (_설정 기본값 사용)"""
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if 0 <= v <= 60 else None

