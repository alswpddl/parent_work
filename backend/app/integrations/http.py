"""표준 라이브러리(urllib)만 쓰는 작은 HTTP 도우미.

외부 API 클라이언트(카카오·솔라피)는 이 함수를 주입받아 쓰므로, 테스트에서는 가짜 함수로 바꿔 끼운다.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class HttpResponse:
    status: int
    body: str

    def json(self) -> Any:
        try:
            return json.loads(self.body) if self.body else {}
        except json.JSONDecodeError:
            return {"raw": self.body}

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


HttpFunc = Callable[..., HttpResponse]


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    form: dict[str, Any] | None = None,
    json_body: Any = None,
    data: bytes | None = None,
    timeout: float = 15.0,
) -> HttpResponse:
    hdrs = dict(headers or {})
    if data is not None:
        pass  # 이미 만들어진 바이트 본문 (웹 푸시 암호문)
    elif form is not None:
        data = urllib.parse.urlencode({k: v for k, v in form.items() if v is not None}).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    elif json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — 고정된 https 주소만 호출
            return HttpResponse(resp.status, resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, e.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("HTTP %s %s 실패: %s", method, url, e)
        return HttpResponse(0, json.dumps({"error": str(e)}))
