"""GHD 업무 현황판(Dashboard)에 필요한 집계 데이터를 계산한다.

모든 숫자는 항상 현재 문의 데이터(엑셀) + 처리 진행 상태(workflow_service)에서
그때그때 다시 계산한다. 하드코딩된 값은 없다.
"""

from datetime import date

from app.services import (
    employee_service,
    inquiry_service,
    proactive_care_service,
    structuring_service,
    workflow_service,
)

# 우선 처리 필요 영역 정렬 순서 (요청 순서 그대로)
PRIORITY_ORDER = ["긴급 문의", "HR 회신 대기", "HR 확인 요청", "추가 서류 요청", "신규 문의"]


def _summarize_inquiry(inquiry, state):
    employee = employee_service.get_employee_by_id(inquiry["employee_id"])
    structured = structuring_service.structure_inquiry(
        inquiry["inquiry_text"],
        category=inquiry["category"],
        employee=employee,
        exclude_inquiry_id=inquiry["inquiry_id"],
    )
    status = workflow_service.get_workflow_status(inquiry["inquiry_id"], structured, state=state)

    completed = set(state["completed_steps"])
    next_step = next((s for s in structured["workflow_steps"] if s["step"] not in completed), None)
    next_action = next_step["label"] if next_step else "완료"

    if status == "처리 완료":
        priority = None
    elif structured["urgency"] == "HIGH":
        priority = "긴급 문의"
    elif status == "HR 회신 대기":
        priority = "HR 회신 대기"
    elif status == "HR 확인 요청":
        priority = "HR 확인 요청"
    elif status == "추가 서류 요청":
        priority = "추가 서류 요청"
    else:
        priority = "신규 문의"

    resolved_today = bool(
        state["resolution"] and state["resolution"]["recorded_at"][:10] == date.today().isoformat()
    )

    return {
        "inquiry_id": inquiry["inquiry_id"],
        "inquiry_date": inquiry["inquiry_date"],
        "employee_name": employee["name"] if employee else inquiry["employee_id"],
        "category": structured["extracted_type"],
        # 대시보드는 여러 건을 한눈에 훑어보는 화면이라, 규정 문구로 대체된 key_issue보다
        # 실제 문의 원문을 보여줘야 각 행을 구분하기 쉽다 (Inquiry Detail은 key_issue 유지).
        "key_issue": inquiry["inquiry_text"],
        "flag_type": structured["flag_type"],
        "urgency": structured["urgency"],
        "status": status,
        "next_action": next_action,
        "priority": priority,
        "resolved_today": resolved_today,
    }


def get_dashboard_data(priority_limit=15, recent_limit=15):
    inquiries = inquiry_service.get_all_inquiries()
    # 문의 건수만큼 진행 상태를 반복 조회(N+1)하면 Supabase 호출이 폭증하므로,
    # 배치로 한 번에 가져와 각 문의에 매칭한다.
    states = workflow_service.get_states_for_inquiries([inq["inquiry_id"] for inq in inquiries])
    summaries = [_summarize_inquiry(inq, states[inq["inquiry_id"]]) for inq in inquiries]

    kpi = {
        "total": len(summaries),
        "unresolved": sum(1 for s in summaries if s["status"] != "처리 완료"),
        "hr_confirm_waiting": sum(1 for s in summaries if s["status"] == "HR 확인 요청"),
        "hr_reply_waiting": sum(1 for s in summaries if s["status"] == "HR 회신 대기"),
        "urgent": sum(1 for s in summaries if s["urgency"] == "HIGH" and s["status"] != "처리 완료"),
        "resolved_today": sum(1 for s in summaries if s["resolved_today"]),
    }

    priority_rank = {label: i for i, label in enumerate(PRIORITY_ORDER)}
    priority_items = [s for s in summaries if s["priority"] is not None]
    priority_items.sort(key=lambda s: (priority_rank.get(s["priority"], 99), s["inquiry_date"]))

    recent_items = sorted(summaries, key=lambda s: s["inquiry_date"], reverse=True)

    employees = employee_service.get_all_employees()
    proactive_items = proactive_care_service.get_all_proactive_items(employees)

    return {
        "kpi": kpi,
        "priority_items": priority_items[:priority_limit],
        "priority_total": len(priority_items),
        "recent_items": recent_items[:recent_limit],
        "proactive_items": proactive_items,
    }
