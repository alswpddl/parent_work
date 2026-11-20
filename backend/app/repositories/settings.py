from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..core.repository import Repository
from ..core.sheet_schema import SETTINGS
from ..schemas.settings import SETTING_DEFS, AppSettings, SettingsPatch


class SettingsRepo(Repository[AppSettings]):
    spec = SETTINGS

    def ensure_defaults(self) -> list[str]:
        """탭에 없는 설정 키를 기본값으로 추가한다. 추가된 키 목록 반환."""
        existing = {d.get("key") for d in self.rows(fresh=True)}
        missing = [
            {"key": k, "label": label, "value": default, "description": desc}
            for k, label, default, desc in SETTING_DEFS
            if k not in existing
        ]
        self.insert_many(missing)
        return [m["key"] for m in missing]

    def load(self) -> AppSettings:
        raw = {d["key"]: d.get("value", "") for d in self.rows() if d.get("key")}
        data: dict[str, Any] = {}
        for name in AppSettings.model_fields:
            v = raw.get(name)
            if v is None or v == "":
                continue
            data[name] = str(v).replace(",", "") if name.endswith(("_kg", "_days", "_factor", "_orders")) else str(v)
        try:
            return AppSettings(**data)
        except ValidationError:
            # 시트에 잘못 들어간 값만 버리고 나머지는 살린다
            safe: dict[str, Any] = {}
            for k, v in data.items():
                try:
                    AppSettings(**{k: v})
                    safe[k] = v
                except ValidationError:
                    continue
            return AppSettings(**safe)

    def save(self, patch: SettingsPatch) -> AppSettings:
        changes = patch.model_dump(exclude_none=True)
        if changes:
            existing = {d.get("key") for d in self.rows(fresh=True)}
            to_insert = []
            updates = []
            labels = {k: (label, desc) for k, label, _, desc in SETTING_DEFS}
            for k, v in changes.items():
                value = _fmt(v)
                if k in existing:
                    updates.append(((k,), {"value": value}))
                else:
                    label, desc = labels.get(k, (k, ""))
                    to_insert.append({"key": k, "label": label, "value": value, "description": desc})
            self.update_many(updates)
            self.insert_many(to_insert)
        return self.load()


def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
