"""입사 초기 정착 체크리스트 (Feature: Initial Settlement Checklist).

외국인 임직원이 입사 초기에 반드시 처리해야 하는 행정/생활 정착 항목을 정해두고,
GHD 담당자가 직접 확인·완료한 항목을 체크할 수 있게 한다. 항목 자체는 전 직원
공통 고정 목록이며(Demo 기준), 직원별 체크 상태만 employees 데이터의
settlement_checklist 컬럼(JSON 문자열)에 저장한다.
"""

import json

from app.services import employee_service

# (key, label) — Demo 기준 공통 정착 체크리스트 항목. 실제 사내 규정이 아니다.
SETTLEMENT_CHECKLIST_ITEMS = [
    ("arc", "외국인등록증(ARC) 신청/발급 확인"),
    ("bank_account", "급여 계좌 개설"),
    ("mobile_plan", "휴대폰 개통"),
    ("housing", "거주지 계약/입주 확인"),
    ("insurance", "4대보험 가입 안내"),
    ("system_account", "사내 시스템 계정 및 출입증 발급"),
    ("emergency_contact", "GHD 비상연락망 안내"),
]


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
    state = _parse_state(employee)
    checklist_items = [
        {"key": key, "label": label, "checked": bool(state.get(key))}
        for key, label in SETTLEMENT_CHECKLIST_ITEMS
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
    state = {key: (key in checked_keys) for key, _label in SETTLEMENT_CHECKLIST_ITEMS}
    employee_service.update_employee(employee_id, {"settlement_checklist": json.dumps(state, ensure_ascii=False)})
