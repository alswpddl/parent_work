"""구글 시트 매일 백업.

본 시트의 주요 탭(주문장·거래처·품목·재고·저장소·후기·_설정 …)을 '백업 YYYY-MM-DD' 탭 하나에 위아래로 붙여
**따로 만든 백업용 스프레드시트**에 쓴다. 14일 지난 백업 탭은 지운다.

백업 위치 (위에서부터 먼저 있는 것)
  1) BACKUP_SPREADSHEET_ID — 새 스프레드시트를 만들어 서비스 계정에 '편집자'로 공유
  2) SYSTEM_SPREADSHEET_ID — 토큰·발송기록용 비공개 시트가 따로 있으면 거기에
되살릴 때: 백업 탭에서 '## 탭이름' 아래 줄들을 복사해 본 시트 같은 탭에 붙여 넣는다.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from ..core.sheet_schema import ALL_TABS
from ..core.timeutil import today

log = logging.getLogger(__name__)
PREFIX = "백업 "
KEEP_DAYS = 14


def backup_target(ctx: Any):
    """백업을 쓸 시트 백엔드. 없으면 None."""
    custom = ctx.services.get("backup_backend")  # 테스트에서 끼워 넣기
    if custom is not None:
        return custom
    cfg = ctx.config
    if cfg.sheets_backend != "gspread":
        return None
    from ..core.sheets import GspreadBackend

    if getattr(cfg, "backup_spreadsheet_id", ""):
        return GspreadBackend(cfg.backup_spreadsheet_id, cfg.service_account_info)
    if cfg.system_spreadsheet_id:
        return ctx.system_sheets.backend
    return None


def where(ctx: Any) -> str:
    cfg = ctx.config
    if getattr(cfg, "backup_spreadsheet_id", ""):
        return "백업용 시트 (BACKUP_SPREADSHEET_ID)"
    if cfg.sheets_backend == "gspread" and cfg.system_spreadsheet_id:
        return "비공개 시스템 시트 (SYSTEM_SPREADSHEET_ID)"
    return ""


def run_backup(ctx: Any, keep_days: int = KEEP_DAYS) -> dict:
    target = backup_target(ctx)
    if target is None:
        return {"skipped": "백업할 시트가 없어요. Render에 BACKUP_SPREADSHEET_ID 를 넣어 주세요."}
    src = ctx.sheets.backend
    have = set(src.list_tabs())
    rows: list[list[Any]] = [[f"가염식품 시트 백업 — {today().isoformat()}"], []]
    counts: dict[str, int] = {}
    for spec in ALL_TABS:
        title = spec.title
        if title not in have or spec.name == "images":  # 사진 조각은 크고 다시 올리면 되니 빼요
            continue
        values = src.get_values(title)
        counts[title] = max(len(values) - 1, 0)
        rows.append([f"## {title}", f"{counts[title]}줄"])
        rows.extend(values)
        rows.append([])
    name = f"{PREFIX}{today().isoformat()}"
    existing = target.list_tabs()
    if name in existing:  # 같은 날 다시 돌리면 새로 씀
        target.delete_tab(name)
    target.write_tab(name, rows)
    cutoff = today() - timedelta(days=keep_days)
    removed = []
    for t in existing:
        if t.startswith(PREFIX) and t != name and t[len(PREFIX):] < cutoff.isoformat():
            target.delete_tab(t)
            removed.append(t)
    log.info("시트 백업 %s: %s", name, counts)
    return {"tab": name, "tabs": counts, "rows": sum(counts.values()), "removed": removed}
