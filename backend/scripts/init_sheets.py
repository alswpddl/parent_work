"""실제 구글 시트에 탭·헤더·서식·기본 설정을 만든다. (처음 한 번, 또는 열을 새로 추가한 뒤)

사용법 (backend 폴더에서)
  python -m scripts.init_sheets           # 탭/헤더/설정만
  python -m scripts.init_sheets --demo    # + 예시 품목·거래처 (빈 시트일 때만)

필요한 환경변수: GOOGLE_SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON (또는 _FILE)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import AppConfig  # noqa: E402
from app.context import bootstrap, build_context  # noqa: E402
from app.demo_data import seed_demo  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="예시 품목·거래처 넣기 (품목 탭이 비어 있을 때만)")
    args = ap.parse_args()

    cfg = AppConfig.from_env().model_copy(update={"sheets_backend": "gspread", "auto_init_sheets": True})
    ctx = build_context(cfg)
    report = bootstrap(ctx)
    if args.demo:
        if ctx.products.rows(fresh=True):
            print("품목 탭에 이미 데이터가 있어 예시 데이터는 넣지 않았어요.")
        else:
            seed_demo(ctx)
            report["demo_seeded"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("완료: 구글 시트를 열어 탭을 확인해 보세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
