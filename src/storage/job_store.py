from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from common.errors import AppError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobStore:
    data_root: Path

    def _jobs_dir(self) -> Path:
        d = self.data_root / "jobs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _job_file(self, job_id: str) -> Path:
        return self._jobs_dir() / f"{job_id}.json"

    def create(self, payload: Dict[str, Any]) -> None:
        jf = self._job_file(payload["id"])
        jf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, job_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get(job_id)
        current.update(patch)
        current["updated_at"] = _utc_now()
        self._job_file(job_id).write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        return current

    def get(self, job_id: str) -> Dict[str, Any]:
        jf = self._job_file(job_id)
        if not jf.exists():
            raise AppError("JOB_NOT_FOUND", "job not found", {"job_id": job_id})
        return json.loads(jf.read_text(encoding="utf-8"))

    def list_recent(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        d = self.data_root / "jobs"
        if not d.is_dir():
            return []
        rows: List[Dict[str, Any]] = []
        for jf in d.glob("*.json"):
            try:
                rows.append(json.loads(jf.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        rows.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        return rows[: max(1, min(limit, 500))]
