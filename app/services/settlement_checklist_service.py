"""초기 정착 체크리스트 (Feature: Settlement Checklist).

외국인 임직원이 입사 초기에 반드시 처리해야 하는 행정/생활 정착 항목을 정해두고,
GHD 담당자가 직접 확인·완료한 항목을 체크할 수 있게 한다. 체크리스트 항목 자체는
전 직원 공통 카탈로그이며, GHD 담당자가 직접 추가/수정할 수 있다 (Supabase가 있으면
settlement_checklist_items 테이블에, 없으면 로컬 JSON 파일에 저장). 직원별 체크
상태는 employees 데이터의 settlement_checklist 컬럼(JSON 문자열)에 저장한다.
"""

import json
import re
from pathlib import Path

from app.services import employee_service, supabase_client

LOCAL_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "settlement_checklist_items.json"

# 최초 실행 시(카탈로그가 비어 있을 때) 시딩하는 기본 항목. 실제 사내 규정이 아니다.
DEFAULT_SETTLEMENT_CHECKLIST_ITEMS = [
    ("arc", "외국인등록증(ARC) 신청/발급 확인"),
    ("bank_account", "급여 계좌 개설"),
    ("mobile_plan", "휴대폰 개통"),
    ("housing", "거주지 계약/입주 확인"),
    ("insurance", "4대보험 가입 안내"),
    ("system_account", "사내 시스템 계정 및 출입증 발급"),
    ("emergency_contact", "GHD 비상연락망 안내"),
]

_catalog_cache = None


def _default_catalog():
    return [
        {"item_key": key, "label": label, "sort_order": i}
        for i, (key, label) in enumerate(DEFAULT_SETTLEMENT_CHECKLIST_ITEMS)
    ]


def _load_local_catalog():
    if LOCAL_CATALOG_PATH.exists():
        with open(LOCAL_CATALOG_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
        return sorted(items, key=lambda r: r.get("sort_order", 0))
    items = _default_catalog()
    _save_local_catalog(items)
    return items


def _save_local_catalog(items):
    LOCAL_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def get_checklist_catalog():
    """전 직원 공통 정착 체크리스트 항목(카탈로그)을 정렬된 순서로 반환한다."""
    global _catalog_cache
    if _catalog_cache is None:
        client = supabase_client.get_client()
        if client:
            result = client.table("settlement_checklist_items").select("*").order("sort_order").execute()
            items = result.data
            if not items:
                items = _default_catalog()
                client.table("settlement_checklist_items").insert(items).execute()
        else:
            items = _load_local_catalog()
        _catalog_cache = items
    return _catalog_cache


def _make_item_key(label, existing_keys):
    base = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_") or "item"
    base = base[:40]
    key = base
    n = 2
    while key in existing_keys:
        key = f"{base}_{n}"
        n += 1
    return key


def add_checklist_item(label):
    """새 체크리스트 항목을 카탈로그 맨 뒤에 추가한다."""
    global _catalog_cache
    label = (label or "").strip()
    if not label:
        return

    catalog = get_checklist_catalog()
    key = _make_item_key(label, {item["item_key"] for item in catalog})
    next_order = max((item.get("sort_order", 0) for item in catalog), default=-1) + 1
    new_item = {"item_key": key, "label": label, "sort_order": next_order}

    client = supabase_client.get_client()
    if client:
        client.table("settlement_checklist_items").insert(new_item).execute()
    else:
        items = _load_local_catalog()
        items.append(new_item)
        _save_local_catalog(items)

    _catalog_cache = None


def update_checklist_item(item_key, label):
    """기존 체크리스트 항목의 이름(label)을 수정한다."""
    global _catalog_cache
    label = (label or "").strip()
    if not label:
        return

    client = supabase_client.get_client()
    if client:
        client.table("settlement_checklist_items").update({"label": label}).eq("item_key", item_key).execute()
    else:
        items = _load_local_catalog()
        for item in items:
            if item["item_key"] == item_key:
                item["label"] = label
        _save_local_catalog(items)

    _catalog_cache = None


def _parse_state(employee):
    raw = employee.get("settlement_checklist") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        state = json.loads(raw)
        return state if isinstance(state, dict) else {}
    except (TypeError, ValueError):
        return {}


def get_checklist(employee):
    """직원 1명의 체크리스트 항목 + 체크 상태 + 진행률을 반환한다.
    (dict의 내장 .items 메서드와 이름이 겹치지 않도록 "checklist_items"로 반환한다 —
    Jinja는 foo.items를 dict.items() 바운드 메서드로 먼저 해석해버린다.)"""
    catalog = get_checklist_catalog()
    state = _parse_state(employee)
    checklist_items = [
        {"key": item["item_key"], "label": item["label"], "checked": bool(state.get(item["item_key"]))}
        for item in catalog
    ]
    completed = sum(1 for item in checklist_items if item["checked"])
    total = len(checklist_items)
    return {
        "checklist_items": checklist_items,
        "completed": completed,
        "total": total,
        "percent": round(completed / total * 100) if total else 0,
    }


def save_checklist(employee_id, checked_keys):
    """체크된 항목 키 목록(checked_keys)을 받아 해당 직원의 체크리스트 상태를 저장한다."""
    checked_keys = set(checked_keys)
    catalog = get_checklist_catalog()
    state = {item["item_key"]: (item["item_key"] in checked_keys) for item in catalog}
    employee_service.update_employee(employee_id, {"settlement_checklist": json.dumps(state, ensure_ascii=False)})
