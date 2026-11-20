"""택배 일괄 업로드용 .xlsx 생성 (openpyxl)."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ...schemas.order import OrderOut
from ...schemas.settings import AppSettings
from .carriers.base import CarrierFormat


def build_parcel_workbook(orders: list[OrderOut], fmt: CarrierFormat, settings: AppSettings) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = fmt.sheet_name[:31]

    headers = [c[0] for c in fmt.columns]
    ws.append(headers)
    head_font = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E3F0E8")
    for i, (title, _, width) in enumerate(fmt.columns, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(i)].width = width

    text_idx = {headers.index(h) + 1 for h in fmt.text_columns if h in headers}
    for o in orders:
        row = []
        for _, getter, _ in fmt.columns:
            v = getter(o, settings)
            row.append("" if v is None else v)
        ws.append(row)
        r = ws.max_row
        for c in text_idx:  # 전화번호·우편번호는 텍스트 서식 (앞자리 0 보존)
            cell = ws.cell(row=r, column=c)
            cell.value = "" if cell.value is None else str(cell.value)
            cell.number_format = "@"

    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
