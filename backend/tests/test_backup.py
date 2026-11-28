"""구글 시트 매일 백업"""
from datetime import date

from app.core.sheets import MemoryBackend
from app.services import backup


def test_backup_writes_dated_tab_and_keeps_14_days(full_ctx, monkeypatch):
    # 처음엔 백업할 곳이 없으면 건너뜀 (메모리 모드)
    assert "skipped" in full_ctx.jobs.run("sheet_backup", full_ctx)

    target = MemoryBackend()
    target.tabs["백업 2026-11-01"] = [["옛것"]]  # 14일 넘은 것 → 지움
    target.tabs["백업 2026-11-20"] = [["최근"]]  # 남김
    target.tabs["메모"] = [["백업 아님"]]
    full_ctx.services["backup_backend"] = target
    monkeypatch.setattr(backup, "today", lambda: date(2026, 11, 28))

    r = full_ctx.jobs.run("sheet_backup", full_ctx)
    assert r["ok"] and r["tab"] == "백업 2026-11-28" and r["removed"] == ["백업 2026-11-01"]
    rows = target.tabs["백업 2026-11-28"]
    titles = [x[0] for x in rows if x and str(x[0]).startswith("## ")]
    assert "## 주문장" in titles and "## 거래처" in titles and "## _설정" in titles
    # 주문장 헤더가 '## 주문장' 바로 다음 줄에 그대로
    i = [x[0] if x else "" for x in rows].index("## 주문장")
    assert rows[i + 1] == full_ctx.sheets.backend.get_values("주문장")[0]
    assert set(target.tabs) == {"백업 2026-11-20", "백업 2026-11-28", "메모"}

    # 같은 날 다시 돌려도 탭 하나
    full_ctx.jobs.run("sheet_backup", full_ctx)
    assert sum(1 for t in target.tabs if t == "백업 2026-11-28") == 1
