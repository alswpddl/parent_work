"""거래명세표 PDF (ReportLab).

한글 폰트
- 기본: backend/fonts/NotoSansKR-Regular.ttf (저장소에 포함) 를 PDF 에 넣는다 → 어디서 열어도 같게 보임
- PDF_FONT_PATH 에 다른 TTF 경로를 주면 그 폰트를 쓴다 (예: 나눔고딕)
- 폰트 파일이 하나도 없으면 ReportLab 내장 CID 폰트(HYGothic-Medium) — 보는 프로그램에 따라 한글이 안 보일 수 있음
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

log = logging.getLogger(__name__)

_FONT_NAME: str | None = None
_FONT_DIR = Path(__file__).resolve().parents[3] / "fonts"
_CANDIDATES = [
    _FONT_DIR / "NotoSansKR-Regular.ttf",  # 저장소에 포함 (Noto Sans CJK KR 한글 부분, SIL OFL)
    _FONT_DIR / "NanumGothic.ttf",
    _FONT_DIR / "NanumGothic-Regular.ttf",
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/nanum/NanumGothic.ttf"),
]


def register_font(custom_path: str = "") -> str:
    global _FONT_NAME
    if _FONT_NAME:
        return _FONT_NAME
    paths = ([Path(custom_path)] if custom_path else []) + _CANDIDATES
    for p in paths:
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont("KR", str(p)))
                _FONT_NAME = "KR"
                return _FONT_NAME
            except Exception:  # noqa: BLE001
                log.warning("폰트 등록 실패: %s", p)
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    _FONT_NAME = "HYGothic-Medium"
    return _FONT_NAME


@dataclass
class Party:
    name: str
    biz_no: str = ""
    owner: str = ""
    address: str = ""
    phone: str = ""
    biz_type: str = ""
    biz_item: str = ""


@dataclass
class StatementLine:
    day: date | None
    product: str
    qty: int
    unit_price: int | None
    amount: int
    vat: int
    order_id: str


@dataclass
class StatementData:
    settlement_id: str
    period: str
    issued: date
    supplier: Party
    buyer: Party
    lines: list[StatementLine]
    supply_total: int
    vat_total: int
    bank_account: str = ""
    note: str = ""

    @property
    def total(self) -> int:
        return self.supply_total + self.vat_total


def _won(v: int | None) -> str:
    return "" if v is None else f"{v:,}"


def build_statement_pdf(data: StatementData, font_path: str = "") -> bytes:
    font = register_font(font_path)
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"거래명세표 {data.period} {data.buyer.name}", author=data.supplier.name,
    )
    base = ParagraphStyle("base", fontName=font, fontSize=9, leading=12)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10)
    title = ParagraphStyle("title", parent=base, fontSize=20, leading=26, alignment=TA_CENTER, spaceAfter=4)
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)

    story: list = [
        Paragraph("거 래 명 세 표", title),
        Paragraph(f"{data.period[:4]}년 {int(data.period[5:7])}월분 · 발행일 {data.issued:%Y-%m-%d} · No. {data.settlement_id}", right),
        Spacer(1, 4 * mm),
    ]

    def party_rows(label: str, p: Party) -> list[list]:
        P = lambda t: Paragraph(t, small)  # noqa: E731
        return [
            [P(label), P("등록번호"), P(p.biz_no or "-"), "", ""],
            ["", P("상호"), P(p.name), P("성명"), P(p.owner or "-")],
            ["", P("주소"), P(p.address or "-"), "", ""],
            ["", P("업태"), P(p.biz_type or "-"), P("종목"), P(p.biz_item or "-")],
        ]

    col = [8 * mm, 17 * mm, 35 * mm, 10 * mm, 21 * mm]
    sup = Table(party_rows("공급자", data.supplier), colWidths=col)
    buy = Table(party_rows("공급받는자", data.buyer), colWidths=col)
    party_style = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("SPAN", (0, 0), (0, -1)),
            ("SPAN", (2, 0), (4, 0)),
            ("SPAN", (2, 2), (4, 2)),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E3F0E8")),
            ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F4F7F5")),
            ("BACKGROUND", (3, 1), (3, 1), colors.HexColor("#F4F7F5")),
            ("BACKGROUND", (3, 3), (3, 3), colors.HexColor("#F4F7F5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
    )
    sup.setStyle(party_style)
    buy.setStyle(party_style)
    story += [Table([[sup, buy]], colWidths=[92 * mm, 92 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]), Spacer(1, 4 * mm)]

    total_style = ParagraphStyle("total", parent=base, fontSize=11, leading=14)
    story.append(
        Table(
            [[Paragraph(f"합계금액 (공급가액 + 세액)   <b>₩ {data.total:,}</b>", total_style)]],
            colWidths=[182 * mm],
            style=[("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8E6")),
                   ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)],
        )
    )
    story.append(Spacer(1, 3 * mm))

    head = ["일자", "품목", "수량", "단가", "공급가액", "세액", "주문번호"]
    rows: list[list] = [head]
    for l in data.lines:
        rows.append([
            l.day.strftime("%m/%d") if l.day else "", Paragraph(l.product, small), f"{l.qty:,}",
            _won(l.unit_price), _won(l.amount), _won(l.vat), Paragraph(l.order_id, small),
        ])
    rows.append(["", "합계", f"{sum(l.qty for l in data.lines):,}", "", _won(data.supply_total), _won(data.vat_total), ""])
    t = Table(rows, colWidths=[14 * mm, 58 * mm, 16 * mm, 20 * mm, 26 * mm, 20 * mm, 28 * mm], repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3F0E8")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F4F7F5")),
                ("ALIGN", (2, 1), (5, -1), "RIGHT"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 5 * mm))
    if data.bank_account:
        story.append(Paragraph(f"입금 계좌: {data.bank_account}", base))
    if data.note:
        story.append(Paragraph(data.note, small))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"{data.supplier.name} · {data.supplier.phone}", small))
    doc.build(story)
    return buf.getvalue()
