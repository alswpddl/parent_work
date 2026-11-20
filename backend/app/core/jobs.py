"""정기작업 레지스트리.

같은 작업을 두 가지 방식으로 실행할 수 있다.
1) 외부 트리거(기본): GitHub Actions cron 이 POST /api/jobs/{name} 호출 → 잠든 Render 무료 서버도 깨운다.
2) 내부 스케줄러(선택): ENABLE_INTERNAL_SCHEDULER=true 이고 APScheduler 가 설치돼 있으면
   서버 안에서 cron 으로 실행 (잠들지 않는 유료 서버용).

모듈은 register() 에서 ctx.jobs.register(...) 로 작업을 등록한다.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .errors import NotFoundError, TooManyRequests
from .timeutil import KST, now

log = logging.getLogger(__name__)

JobFunc = Callable[[Any], dict]  # (ctx) -> 결과 요약 dict


@dataclass
class Job:
    name: str
    func: JobFunc
    cron: str | None  # "0 8 * * *" (KST 기준) — 내부 스케줄러용. 외부 cron 은 workflow 파일에 따로 적는다.
    description: str = ""
    module: str = ""
    last_run_at: datetime | None = None
    last_result: dict | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._scheduler = None

    def register(self, name: str, func: JobFunc, *, cron: str | None = None, description: str = "", module: str = "") -> None:
        if name in self._jobs:
            raise ValueError(f"작업 이름 중복: {name}")
        self._jobs[name] = Job(name=name, func=func, cron=cron, description=description, module=module)

    def list(self) -> list[Job]:
        return list(self._jobs.values())

    def run(self, name: str, ctx: Any) -> dict:
        job = self._jobs.get(name)
        if job is None:
            raise NotFoundError(f"'{name}' 작업이 없어요.")
        if not job._lock.acquire(blocking=False):  # 같은 작업이 겹쳐 돌지 않게
            raise TooManyRequests(f"'{name}' 작업이 이미 실행 중이에요.")
        try:
            result = job.func(ctx) or {}
            job.last_run_at = now()
            job.last_result = {"ok": True, **result}
            return job.last_result
        except Exception as e:
            job.last_run_at = now()
            job.last_result = {"ok": False, "error": str(e)}
            log.exception("작업 %s 실패", name)
            raise
        finally:
            job._lock.release()

    # --- 내부 스케줄러 (선택) ---
    def start_internal_scheduler(self, ctx: Any) -> bool:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
            from apscheduler.triggers.cron import CronTrigger  # type: ignore
        except ImportError:
            log.warning("APScheduler 가 없어 내부 스케줄러를 켜지 않아요.")
            return False
        sched = BackgroundScheduler(timezone=KST)
        for job in self._jobs.values():
            if job.cron:
                sched.add_job(self._safe_run, CronTrigger.from_crontab(job.cron, timezone=KST), args=[job.name, ctx], id=job.name)
        sched.start()
        self._scheduler = sched
        log.info("내부 스케줄러 시작: %s", [j.name for j in self._jobs.values() if j.cron])
        return True

    def _safe_run(self, name: str, ctx: Any) -> None:
        try:
            self.run(name, ctx)
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
