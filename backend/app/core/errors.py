"""앱 공통 예외. 메시지는 화면에 그대로 보여줄 수 있는 한국어로 쓴다."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str, *, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(AppError):
    status_code = 404

    def __init__(self, message: str = "찾을 수 없어요."):
        super().__init__(message, code="not_found")


class ConflictError(AppError):
    status_code = 409

    def __init__(self, message: str = "다른 곳에서 먼저 바뀌었어요. 새로고침 후 다시 해 주세요."):
        super().__init__(message, code="conflict")


class ValidationFailed(AppError):
    status_code = 422

    def __init__(self, message: str):
        super().__init__(message, code="validation")


class UnauthorizedError(AppError):
    status_code = 401

    def __init__(self, message: str = "다시 로그인해 주세요."):
        super().__init__(message, code="unauthorized")


class TooManyRequests(AppError):
    status_code = 429

    def __init__(self, message: str = "잠시 뒤에 다시 해 주세요."):
        super().__init__(message, code="rate_limited")


class SchemaError(AppError):
    status_code = 500

    def __init__(self, message: str):
        super().__init__(message, code="schema")


class UpstreamError(AppError):
    """Google Sheets, Claude 등 외부 서비스 오류."""

    status_code = 502

    def __init__(self, message: str = "외부 서비스 연결이 잠시 불안정해요. 다시 눌러 주세요."):
        super().__init__(message, code="upstream")
