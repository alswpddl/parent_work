"""환경변수 설정.

pydantic-settings 의존성을 줄이기 위해 os.environ 을 직접 읽어 pydantic 모델로 검증한다.
Render / Codespaces 어디서든 환경변수로 주입하는 것을 기본으로 하고,
로컬 개발 시에는 python-dotenv 가 있으면 backend/.env 를 자동으로 읽는다.
"""

from __future__ import annotations

import json
import re
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def sheet_id(v: str | None) -> str:
    """시트 주소 전체를 붙여넣어도 ID 만 뽑는다.
    https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0 → <ID>"""
    v = (v or "").strip()
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", v)
    return m.group(1) if m else v


def _list(v: str | None, default: list[str]) -> list[str]:
    if v is None or v.strip() == "":
        return list(default)
    return [x.strip() for x in v.split(",") if x.strip()]


ALL_MODULES = [
    "q1_masters",
    "q1_orders",
    "q1_shipping",
    "q2_self_order",
    "q2_web_order",
    "q2_briefing",
    "q3_tracking",
    "q3_notify",
    "q3_marketplace",
    "q4_inventory",
    "q4_settlement",
    "q4_reorder",
]
DEFAULT_MODULES = list(ALL_MODULES)


class AppConfig(BaseModel):
    app_env: Literal["dev", "prod", "test"] = "dev"

    # --- 공개 주소 (카카오 링크·리다이렉트·거래처 주문 링크에 사용) ---
    public_web_url: str = "http://localhost:5173"  # 프론트(Vercel) 주소
    public_api_url: str = "http://localhost:8000"  # 백엔드(Render) 주소

    # --- Google Sheets ---
    sheets_backend: Literal["memory", "gspread"] = "memory"
    spreadsheet_id: str = ""
    system_spreadsheet_id: str = ""  # 토큰·발송기록용 비공개 시트 (비우면 본 시트의 _토큰/_발송기록 탭)
    service_account_info: dict | None = None
    sheets_cache_ttl: float = 30.0
    auto_init_sheets: bool = True
    seed_demo_data: bool = True  # memory 백엔드에서만 사용

    # --- Claude ---
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-5-5"
    claude_timeout: float = 30.0

    # --- 카카오 '나에게 보내기' (부모님 브리핑·경고) ---
    kakao_rest_api_key: str = ""
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = ""  # 비우면 {public_api_url}/api/integrations/kakao/callback

    # --- 솔라피 알림톡 (거래처 안내) ---
    solapi_api_key: str = ""
    solapi_api_secret: str = ""
    solapi_sender: str = ""  # 솔라피에 등록한 발신번호 (문자 대체발송용)
    solapi_pfid: str = ""  # 카카오 비즈니스 채널 연동 ID
    solapi_tpl_parcel: str = ""  # 택배 출고 안내 템플릿 ID
    solapi_tpl_truck: str = ""  # 화물 출고 안내 템플릿 ID
    solapi_tpl_statement: str = ""  # 거래명세표 안내 템플릿 ID
    solapi_tpl_order_received: str = ""  # 주문 접수 확인 템플릿 ID (선택)
    solapi_sms_fallback: bool = True  # 알림톡 실패 시 문자로 대체발송

    # --- 메일 (거래명세표 PDF 발송) ---
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # --- PDF ---
    pdf_font_path: str = ""  # 한글 TTF (예: fonts/NanumGothic.ttf). 비우면 내장 CID 폰트

    # --- 인증 ---
    admin_pin: str = ""
    auth_secret: str = "dev-only-change-me"
    token_ttl_hours: int = 24 * 30
    job_secret: str = ""

    # --- 웹 ---
    frontend_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- 모듈 ---
    enabled_modules: list[str] = Field(default_factory=lambda: list(DEFAULT_MODULES))
    enable_internal_scheduler: bool = False

    @field_validator("sheets_cache_ttl")
    @classmethod
    def _ttl_non_negative(cls, v: float) -> float:
        return max(0.0, v)

    @field_validator("public_web_url", "public_api_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    # ---------------------------------------------------------------- 파생 값
    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def kakao_enabled(self) -> bool:
        return bool(self.kakao_rest_api_key)

    @property
    def kakao_callback_url(self) -> str:
        return self.kakao_redirect_uri or f"{self.public_api_url}/api/integrations/kakao/callback"

    @property
    def solapi_enabled(self) -> bool:
        return bool(self.solapi_api_key and self.solapi_api_secret and self.solapi_pfid)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @classmethod
    def from_env(cls) -> "AppConfig":
        _load_dotenv()
        env = os.environ

        sa_info: dict | None = None
        raw_json = env.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        sa_file = env.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        try:
            if raw_json:
                sa_info = json.loads(raw_json)
            elif sa_file:
                sa_info = json.loads(Path(sa_file).read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON 을 읽지 못했어요. 내려받은 키 파일(.json) 내용을 "
                "{ 부터 } 까지 빠짐없이 그대로 붙여넣었는지 확인해 주세요."
            ) from e

        g = env.get
        return cls(
            app_env=g("APP_ENV", "dev"),  # type: ignore[arg-type]
            public_web_url=g("PUBLIC_WEB_URL", "http://localhost:5173"),
            public_api_url=g("PUBLIC_API_URL", "http://localhost:8000"),
            sheets_backend=g("SHEETS_BACKEND", "memory"),  # type: ignore[arg-type]
            spreadsheet_id=sheet_id(g("GOOGLE_SPREADSHEET_ID", "")),
            system_spreadsheet_id=sheet_id(g("SYSTEM_SPREADSHEET_ID", "")),
            service_account_info=sa_info,
            sheets_cache_ttl=float(g("SHEETS_CACHE_TTL", "30")),
            auto_init_sheets=_bool(g("AUTO_INIT_SHEETS"), True),
            seed_demo_data=_bool(g("SEED_DEMO_DATA"), True),
            anthropic_api_key=g("ANTHROPIC_API_KEY", ""),
            claude_model=g("CLAUDE_MODEL", "claude-haiku-5-5"),
            claude_timeout=float(g("CLAUDE_TIMEOUT", "30")),
            kakao_rest_api_key=g("KAKAO_REST_API_KEY", ""),
            kakao_client_secret=g("KAKAO_CLIENT_SECRET", ""),
            kakao_redirect_uri=g("KAKAO_REDIRECT_URI", ""),
            solapi_api_key=g("SOLAPI_API_KEY", ""),
            solapi_api_secret=g("SOLAPI_API_SECRET", ""),
            solapi_sender=g("SOLAPI_SENDER", ""),
            solapi_pfid=g("SOLAPI_PFID", ""),
            solapi_tpl_parcel=g("SOLAPI_TPL_PARCEL", ""),
            solapi_tpl_truck=g("SOLAPI_TPL_TRUCK", ""),
            solapi_tpl_statement=g("SOLAPI_TPL_STATEMENT", ""),
            solapi_tpl_order_received=g("SOLAPI_TPL_ORDER_RECEIVED", ""),
            solapi_sms_fallback=_bool(g("SOLAPI_SMS_FALLBACK"), True),
            smtp_host=g("SMTP_HOST", ""),
            smtp_port=int(g("SMTP_PORT", "465")),
            smtp_user=g("SMTP_USER", ""),
            smtp_password=g("SMTP_PASSWORD", ""),
            smtp_from=g("SMTP_FROM", ""),
            pdf_font_path=g("PDF_FONT_PATH", ""),
            admin_pin=g("ADMIN_PIN", ""),
            auth_secret=g("AUTH_SECRET", "dev-only-change-me"),
            token_ttl_hours=int(g("TOKEN_TTL_HOURS", str(24 * 30))),
            job_secret=g("JOB_SECRET", ""),
            frontend_origins=_list(g("FRONTEND_ORIGINS"), ["http://localhost:5173"]),
            enabled_modules=_list(g("ENABLED_MODULES"), DEFAULT_MODULES),
            enable_internal_scheduler=_bool(g("ENABLE_INTERNAL_SCHEDULER"), False),
        )

    def check_production(self) -> list[str]:
        """운영 환경에서 빠지면 안 되는 설정을 점검해 문제 목록을 돌려준다."""
        problems: list[str] = []
        if self.app_env != "prod":
            return problems
        if self.sheets_backend != "gspread":
            problems.append("SHEETS_BACKEND=gspread 로 설정해야 합니다.")
        if not self.spreadsheet_id:
            problems.append("GOOGLE_SPREADSHEET_ID 가 비어 있습니다.")
        if not self.service_account_info:
            problems.append("GOOGLE_SERVICE_ACCOUNT_JSON 이 비어 있습니다.")
        if not self.admin_pin or len(self.admin_pin) < 4:
            problems.append("ADMIN_PIN 을 4자리 이상으로 설정해야 합니다.")
        if self.auth_secret == "dev-only-change-me" or len(self.auth_secret) < 32:
            problems.append("AUTH_SECRET 을 32자 이상의 임의 문자열로 바꿔야 합니다.")
        if not self.job_secret:
            problems.append("JOB_SECRET 이 비어 있습니다 (정기작업 호출용).")
        if "localhost" in self.public_web_url or "localhost" in self.public_api_url:
            problems.append("PUBLIC_WEB_URL / PUBLIC_API_URL 을 실제 배포 주소로 바꿔야 합니다.")
        return problems

    def integration_warnings(self) -> list[str]:
        """빠져도 서버는 뜨지만 기능이 꺼지는 설정 (상태 화면에 표시)."""
        w: list[str] = []
        if not self.ai_enabled:
            w.append("ANTHROPIC_API_KEY 없음 → 카톡 주문은 간단 규칙으로만 정리돼요.")
        if not self.kakao_enabled:
            w.append("KAKAO_REST_API_KEY 없음 → 아침 브리핑·재고 경고 카톡이 꺼져 있어요.")
        if not self.solapi_enabled:
            w.append("솔라피 키/채널 없음 → 거래처 출고 알림톡이 꺼져 있어요.")
        else:
            if not self.solapi_tpl_parcel:
                w.append("SOLAPI_TPL_PARCEL 없음 → 택배 출고 알림톡을 보낼 수 없어요.")
            if not self.solapi_tpl_truck:
                w.append("SOLAPI_TPL_TRUCK 없음 → 화물 출고 알림톡을 보낼 수 없어요.")
        if not self.smtp_enabled:
            w.append("SMTP 설정 없음 → 거래명세표 이메일 발송이 꺼져 있어요.")
        if self.sheets_backend == "gspread" and not self.system_spreadsheet_id:
            w.append("SYSTEM_SPREADSHEET_ID 없음 → 카카오 토큰을 본 시트의 _토큰 탭에 저장해요 (부모님이 지우지 않게 주의).")
        return w
