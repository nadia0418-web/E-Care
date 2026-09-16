"""활동 로그 (Feature: Activity Log).

담당자별 개별 계정으로 로그인하더라도 모든 담당자는 전체 임직원 데이터에 동일하게
접근한다 (담당자별 배분/접근 제한은 하지 않음). 이 로그의 목적은 오직 "누가 어떤
임직원의 데이터를 언제 수정했는지"에 대한 책임소재 추적이다.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services import supabase_client

LOCAL_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "activity_log.json"


def _load_local_log():
    if LOCAL_LOG_PATH.exists():
        with open(LOCAL_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_local_log(entries):
    LOCAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def log_activity(actor, action, target_type=None, target_id=None, target_label=None, detail=None):
    """활동 1건을 기록한다. actor는 담당자 표시 이름(auth_service.current_display_name())."""
    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "target_label": target_label,
        "detail": detail,
    }

    client = supabase_client.get_client()
    if client:
        client.table("activity_log").insert(entry).execute()
    else:
        entries = _load_local_log()
        entries.append(entry)
        _save_local_log(entries)


def get_recent_activity(limit=100):
    """최근 활동을 최신순으로 반환한다."""
    client = supabase_client.get_client()
    if client:
        result = (
            client.table("activity_log")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data

    entries = _load_local_log()
    return list(reversed(entries))[:limit]
