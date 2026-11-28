"""앱 전체가 공유하는 객체 묶음(의존성 컨테이너)과 시작 시 준비 작업."""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any

from .config import AppConfig
from .core.auth import LoginLimiter
from .core.briefing import BriefingRegistry
from .core.events import EventBus
from .core.jobs import JobRegistry
from .core.sheet_schema import ALL_TABS, SYS_MESSAGES, SYS_TOKENS, TabSpec
from .core.sheets import GspreadBackend, MemoryBackend, SheetBackend, SheetsClient, build_backend
from .integrations.claude_client import ClaudeClient
from .integrations.http import HttpFunc, http_request
from .integrations.kakao import KakaoClient
from .integrations.mailer import Mailer
from .integrations.notifier import OwnerNotifier
from .integrations.webpush import WebPushClient
from .integrations.solapi import SolapiClient
from .repositories.customers import CustomerRepo
from .repositories.logs import LogRepo
from .repositories.orders import OrderRepo
from .repositories.products import ProductRepo
from .repositories.settings import SettingsRepo
from .repositories.system import MessageLogRepo, TokenRepo
from .services.order_service import OrderService

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    config: AppConfig
    sheets: SheetsClient
    system_sheets: SheetsClient
    customers: CustomerRepo
    products: ProductRepo
    orders_repo: OrderRepo
    settings: SettingsRepo
    logs: LogRepo
    tokens: TokenRepo
    messages: MessageLogRepo
    bus: EventBus
    jobs: JobRegistry
    briefing: BriefingRegistry
    claude: ClaudeClient
    kakao: KakaoClient
    solapi: SolapiClient
    mailer: Mailer
    notifier: OwnerNotifier
    orders: OrderService
    push: WebPushClient | None = None
    login_limiter: LoginLimiter = field(default_factory=LoginLimiter)
    enabled_modules: list[str] = field(default_factory=list)
    startup_report: dict = field(default_factory=dict)
    services: dict[str, Any] = field(default_factory=dict)  # 모듈이 만든 서비스 (예: "inventory")
    system_tab_specs: tuple[TabSpec, ...] = ()
    http: HttpFunc = http_request  # 외부 API 호출 (토스페이먼츠 등). 테스트에서 가짜로 바꿔 끼움


def _system_specs(separate: bool) -> tuple[TabSpec, TabSpec]:
    """별도 시스템 시트면 '토큰'/'발송기록', 본 시트를 같이 쓰면 '_토큰'/'_발송기록'."""
    if separate:
        return SYS_TOKENS, SYS_MESSAGES
    return (
        dataclasses.replace(SYS_TOKENS, title="_토큰"),
        dataclasses.replace(SYS_MESSAGES, title="_발송기록"),
    )


def build_context(
    config: AppConfig,
    backend: SheetBackend | None = None,
    claude: ClaudeClient | None = None,
    *,
    system_backend: SheetBackend | None = None,
    http: HttpFunc = http_request,
    mailer: Mailer | None = None,
) -> AppContext:
    backend = backend or build_backend(config)
    sheets = SheetsClient(backend, ttl=config.sheets_cache_ttl)

    separate = bool(system_backend) or bool(config.system_spreadsheet_id and config.sheets_backend == "gspread")
    if system_backend is None and separate:
        assert config.service_account_info is not None
        system_backend = GspreadBackend(config.system_spreadsheet_id, config.service_account_info)
    sys_ttl = min(5.0, config.sheets_cache_ttl)
    system_sheets = SheetsClient(system_backend, ttl=sys_ttl) if system_backend else SheetsClient(backend, ttl=sys_ttl)
    tok_spec, msg_spec = _system_specs(separate)

    customers = CustomerRepo(sheets)
    products = ProductRepo(sheets)
    orders_repo = OrderRepo(sheets)
    settings = SettingsRepo(sheets)
    logs = LogRepo(sheets)
    tokens = TokenRepo(system_sheets, tok_spec)
    messages = MessageLogRepo(system_sheets, msg_spec)
    bus = EventBus()

    push = WebPushClient(tokens, subject=config.public_web_url, http=http)
    kakao = KakaoClient(
        rest_api_key=config.kakao_rest_api_key,
        client_secret=config.kakao_client_secret,
        redirect_uri=config.kakao_callback_url,
        tokens=tokens,
        http=http,
    )
    solapi = SolapiClient(
        api_key=config.solapi_api_key,
        api_secret=config.solapi_api_secret,
        sender=config.solapi_sender,
        pfid=config.solapi_pfid,
        sms_fallback=config.solapi_sms_fallback,
        http=http,
    )
    mailer = mailer or Mailer(
        host=config.smtp_host,
        port=config.smtp_port,
        user=config.smtp_user,
        password=config.smtp_password,
        sender=config.smtp_from,
    )
    service = OrderService(
        orders=orders_repo, customers=customers, products=products, settings=settings, logs=logs, bus=bus
    )
    ctx = AppContext(
        config=config,
        sheets=sheets,
        system_sheets=system_sheets,
        customers=customers,
        products=products,
        orders_repo=orders_repo,
        settings=settings,
        logs=logs,
        tokens=tokens,
        messages=messages,
        bus=bus,
        http=http,
        jobs=JobRegistry(),
        briefing=BriefingRegistry(),
        claude=claude or ClaudeClient(config.anthropic_api_key, config.claude_model, config.claude_timeout),
        kakao=kakao,
        solapi=solapi,
        mailer=mailer,
        notifier=OwnerNotifier(kakao, messages, config.public_web_url, push=push),
        push=push,
        orders=service,
        system_tab_specs=(tok_spec, msg_spec),
    )
    from .services.backup import run_backup

    ctx.jobs.register("sheet_backup", run_backup, cron="30 3 * * *", description="구글 시트 매일 백업 (14일 보관)", module="core")
    ctx.jobs.register(
        "auto_delivered", lambda c: c.orders.auto_deliver(c.settings.load().auto_delivered_days),
        cron="50 6 * * *", description="출고 며칠 지난 주문을 도착으로", module="core",
    )
    return ctx


def bootstrap(ctx: AppContext) -> dict:
    """시트 탭·헤더 준비 → 기본 설정 채우기 → (메모리 모드) 예시 데이터."""
    report: dict = {"tabs_added_headers": {}, "settings_added": [], "demo_seeded": False}
    is_memory = isinstance(ctx.sheets.backend, MemoryBackend)
    if ctx.config.auto_init_sheets or is_memory:
        for spec in ALL_TABS:
            added = ctx.sheets.ensure_tab(spec)
            if added:
                report["tabs_added_headers"][spec.title] = added
        for spec in ctx.system_tab_specs:
            added = ctx.system_sheets.ensure_tab(spec)
            if added:
                report["tabs_added_headers"][spec.title] = added
        report["settings_added"] = ctx.settings.ensure_defaults()
    if is_memory and ctx.config.seed_demo_data and not ctx.products.rows():
        from .demo_data import seed_demo

        seed_demo(ctx)
        report["demo_seeded"] = True
    ctx.startup_report = report
    log.info("bootstrap: %s", report)
    return report
