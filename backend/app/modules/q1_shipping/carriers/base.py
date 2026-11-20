"""택배사별 대량 업로드 엑셀 양식 정의.

양식은 '열 이름 + 값 꺼내는 함수' 목록일 뿐이라, 택배사 프로그램에서 받은 업로드 양식을 보고
열 이름과 순서만 맞춰 주면 된다. verified=False 인 양식은 실제 양식과 대조가 끝나지 않았다는 뜻이고,
화면에 '(양식 확인 필요)' 로 표시된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ....schemas.order import OrderOut
from ....schemas.settings import AppSettings

Getter = Callable[[OrderOut, AppSettings], Any]


@dataclass(frozen=True)
class CarrierFormat:
    code: str
    name: str
    columns: tuple[tuple[str, Getter, int], ...]  # (열 이름, 값 함수, 열 너비)
    verified: bool = False
    sheet_name: str = "Sheet1"
    text_columns: tuple[str, ...] = ()  # 엑셀에서 텍스트로 강제할 열 (전화·우편번호)


# ---- 공통 값 함수 -----------------------------------------------------------
def item_summary(o: OrderOut) -> str:
    return ", ".join(f"{l.product_name} x{l.qty}" for l in o.lines)


def recipient(o: OrderOut, s: AppSettings) -> str:
    return o.recipient or o.customer_name


def boxes(o: OrderOut, s: AppSettings) -> int:
    return max(1, o.boxes)


def message(o: OrderOut, s: AppSettings) -> str:
    return o.note
