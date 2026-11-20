"""여러 스키마가 같이 쓰는 값 목록. 시트에 한국어 그대로 저장된다."""

from __future__ import annotations

from typing import Literal

ShipMethod = Literal["택배", "화물"]
MethodBy = Literal["자동", "수동", "거래처기본"]
DefaultMethod = Literal["자동", "택배", "화물"]
OrderStatus = Literal["접수", "출고대기", "출고완료", "취소"]
OrderSource = Literal["카톡", "셀프주문", "스마트스토어", "쿠팡", "직접"]
CustomerType = Literal["B2B", "B2C"]

OPEN_STATUSES: tuple[str, ...] = ("접수", "출고대기")
SHIP_METHODS: tuple[str, ...] = ("택배", "화물")
