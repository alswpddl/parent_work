"""상품 사진 저장소 — 따로 파일 서버가 없어서 구글 시트 '_사진' 탭에 base64 조각으로 둔다.

관리자 화면이 사진을 휴대폰에서 1200px 이하 JPEG로 줄여 보내므로 한 장이 보통 100~300KB.
주소: {PUBLIC_API_URL}/api/public/images/{사진ID} — 한 번 올린 사진은 바뀌지 않아 오래 캐시해도 된다.
"""

from __future__ import annotations

import base64
import binascii
import re
import secrets
import threading
from typing import Any

from ..core.errors import NotFoundError, ValidationFailed
from ..core.repository import Repository
from ..core.sheet_schema import IMAGES
from ..core.timeutil import now

CHUNK = 40_000
MAX_BYTES = 900_000
DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)$")


class ImageStore:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.repo: Repository[dict] = Repository(ctx.sheets, IMAGES)
        self._cache: dict[str, tuple[str, bytes]] = {}
        self._lock = threading.Lock()

    def save(self, data_url: str) -> str:
        m = DATA_URL.match((data_url or "").strip())
        if not m:
            raise ValidationFailed("사진은 JPG·PNG·WEBP만 올릴 수 있어요.")
        mime, b64 = m.group(1), re.sub(r"\s", "", m.group(2))
        try:
            raw = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValidationFailed("사진 파일이 깨졌어요. 다시 골라 주세요.") from e
        if len(raw) > MAX_BYTES:
            raise ValidationFailed("사진이 너무 커요. 다른 사진을 골라 주세요.")
        image_id = f"IMG{now():%y%m%d}{secrets.token_hex(3).upper()}"
        parts = [b64[i : i + CHUNK] for i in range(0, len(b64), CHUNK)]
        ts = now()
        self.repo.insert_many([{"image_id": image_id, "part": n, "mime": mime, "data": p, "created_at": ts} for n, p in enumerate(parts)])
        with self._lock:
            self._cache[image_id] = (mime, raw)
        return image_id

    def load(self, image_id: str) -> tuple[str, bytes]:
        with self._lock:
            hit = self._cache.get(image_id)
        if hit:
            return hit
        rows = sorted((d for d in self.repo.rows(fresh=True) if d.get("image_id") == image_id), key=lambda d: int(d.get("part") or 0))
        if not rows:
            raise NotFoundError("사진이 없어요.")
        raw = base64.b64decode("".join(str(d.get("data") or "") for d in rows))
        out = (str(rows[0].get("mime") or "image/jpeg"), raw)
        with self._lock:
            if len(self._cache) > 50:
                self._cache.clear()
            self._cache[image_id] = out
        return out

    def url(self, image_id: str) -> str:
        return f"{self.ctx.config.public_api_url.rstrip('/')}/api/public/images/{image_id}"


def images_of(ctx: Any) -> ImageStore:
    store = ctx.services.get("images")
    if store is None:
        store = ctx.services["images"] = ImageStore(ctx)
    return store
