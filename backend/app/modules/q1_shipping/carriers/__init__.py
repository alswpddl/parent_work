from __future__ import annotations

from .base import CarrierFormat
from .cj import FORMAT as CJ
from .generic import FORMAT as GENERIC
from .logen import FORMAT as LOGEN

CARRIERS: dict[str, CarrierFormat] = {f.code: f for f in (GENERIC, LOGEN, CJ)}


def get_format(code: str | None) -> CarrierFormat:
    return CARRIERS.get(code or "", GENERIC)
