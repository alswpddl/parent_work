"""상품 사진 올리기: 시트 '_사진' 탭에 조각으로 저장 → 다시 읽어도 똑같은 바이트"""
import base64

import pytest

from app.core.errors import ValidationFailed
from app.services.images import CHUNK, images_of


def test_save_split_and_load(full_ctx):
    store = images_of(full_ctx)
    raw = bytes(range(256)) * 400  # 102KB → base64 약 136K자 → 4조각
    iid = store.save("data:image/jpeg;base64," + base64.b64encode(raw).decode())
    rows = [d for d in store.repo.rows(fresh=True) if d["image_id"] == iid]
    assert len(rows) == -(-len(base64.b64encode(raw)) // CHUNK) and len(rows) >= 3
    store._cache.clear()  # 서버 재시작 흉내
    mime, back = store.load(iid)
    assert mime == "image/jpeg" and back == raw
    assert store.url(iid) == f"https://api.example.com/api/public/images/{iid}"


def test_rejects_non_images(full_ctx):
    with pytest.raises(ValidationFailed):
        images_of(full_ctx).save("data:text/html;base64,PGgxPmhpPC9oMT4=")
    with pytest.raises(ValidationFailed):
        images_of(full_ctx).save("https://example.com/a.jpg")
