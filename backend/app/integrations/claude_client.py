"""Anthropic Claude API 래퍼.

구조화된 결과를 받기 위해 도구(tool) 하나를 정의하고 그 도구를 '강제 호출'(tool_choice=tool)한다.
기본 모델 claude-haiku-5-5 는 강제 호출을 지원한다. 강제 호출을 지원하지 않는 모델
(예: claude-sonnet-5-5, claude-opus-5-5)로 바꾸면 400 이 나므로, 그때는 tool_choice=auto 로 한 번 더 시도한다.
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.errors import UpstreamError

log = logging.getLogger(__name__)


class ClaudeUnavailable(Exception):
    """API 키 없음 / 호출 실패 — 호출 측은 규칙 파서로 대체한다."""


class ClaudeClient:
    def __init__(self, api_key: str, model: str, timeout: float = 30.0, client: Any = None):
        self.model = model
        self._client = client
        if self._client is None and api_key:
            try:
                import anthropic  # type: ignore
            except ImportError:  # pragma: no cover
                log.warning("anthropic 패키지가 없어 AI 파서를 끕니다.")
                return
            self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def call_tool(self, *, system: str, user: str, tool: dict, max_tokens: int = 2048) -> dict:
        if not self.enabled:
            raise ClaudeUnavailable("ANTHROPIC_API_KEY 가 설정되지 않았어요.")
        base = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            messages=[{"role": "user", "content": user}],
        )
        try:
            resp = self._client.messages.create(**base, tool_choice={"type": "tool", "name": tool["name"]})
        except Exception as e:  # noqa: BLE001
            if _status(e) == 400:
                log.info("강제 도구 호출 미지원 모델로 보임 → tool_choice=auto 로 재시도")
                retry = dict(base)
                retry["messages"] = [
                    {"role": "user", "content": f"{user}\n\n반드시 {tool['name']} 도구를 호출해서 답하세요."}
                ]
                try:
                    resp = self._client.messages.create(**retry, tool_choice={"type": "auto"})
                except Exception as e2:  # noqa: BLE001
                    raise ClaudeUnavailable(str(e2)) from e2
            else:
                raise ClaudeUnavailable(str(e)) from e

        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool["name"]:
                data = getattr(block, "input", None)
                if isinstance(data, dict):
                    return data
        raise ClaudeUnavailable("AI 응답에 주문 정보가 없어요.")


def _status(e: Exception) -> int | None:
    code = getattr(e, "status_code", None)
    if code is None:
        code = getattr(getattr(e, "response", None), "status_code", None)
    return code


__all__ = ["ClaudeClient", "ClaudeUnavailable", "UpstreamError"]
