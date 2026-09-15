"""Employee Care Profile + Care Timeline (Feature 3).

특정 임직원 1명에게 지금까지 어떤 Care가 진행되었고, 현재 무엇이 남아 있는지를
한 화면에서 볼 수 있게 한다. 새로운 DB 테이블을 만들지 않고, 기존 문의/워크플로우
데이터(문의 접수일, Step 완료, HR 이메일 발송, HR 회신, 처리 결과)를 조합해서
Care Progress와 Care Timeline을 계산한다.
"""

from datetime import date

from app.services import (
    dashboard_service,
    employee_service,
    inquiry_service,
    proactive_care_service,
    structuring_service,
    workflow_service,
)


def _timeline_time_key(event):
    return event["time"] or ""


def get_employee_care_profile(employee_id):
    """직원 1명의 Care Profile(진행률/미완료 항목/HR Flag/Timeline)을 계산한다.
    직원이 없으면 None을 반환한다."""
    employee = employee_service.get_employee_by_id(employee_id)
    if employee is None:
        return None

    inquiries = inquiry_service.get_inquiries_by_employee(employee_id)
    states = workflow_service.get_states_for_inquiries([inq["inquiry_id"] for inq in inquiries])

    care_items = []
    timeline_events = []

    for inq in inquiries:
        state = states[inq["inquiry_id"]]
        structured = structuring_service.structure_inquiry(
            inq["inquiry_text"],
            category=inq["category"],
            employee=employee,
            exclude_inquiry_id=inq["inquiry_id"],
        )
        status = workflow_service.get_workflow_status(inq["inquiry_id"], structured, state=state)

        summary = {
            "inquiry_id": inq["inquiry_id"],
            "inquiry_date": inq["inquiry_date"],
            "employee_id": employee_id,
            "category": structured["extracted_type"],
            "key_issue": inq["inquiry_text"],
            "flag_type": structured["flag_type"],
            "urgency": structured["urgency"],
            "status": status,
        }
        visa_signal = dashboard_service.employee_visa_signal(employee)
        summary["ai_priority"] = dashboard_service.compute_ai_priority(summary, visa_signal)
        summary["due"] = dashboard_service.compute_due(summary["ai_priority"]["level"], visa_signal)
        care_items.append(summary)

        for event in workflow_service.build_timeline(inq, structured, state):
            timeline_events.append(
                {
                    **event,
                    "inquiry_id": inq["inquiry_id"],
                    "category": structured["extracted_type"],
                }
            )

    total = len(care_items)
    completed_items = [c for c in care_items if c["status"] == "처리 완료"]
    open_items = [c for c in care_items if c["status"] != "처리 완료"]
    open_items.sort(key=lambda c: -c["ai_priority"]["score"])

    hr_flags = [c for c in open_items if c["flag_type"] == "HR_FLAG"]

    timeline_events = [e for e in timeline_events if e.get("time")]
    timeline_events.sort(key=_timeline_time_key, reverse=True)

    proactive_items = proactive_care_service.get_proactive_items(employee, today=date.today())

    return {
        "employee": employee,
        "progress": {
            "completed": len(completed_items),
            "total": total,
            "percent": round(len(completed_items) / total * 100) if total else 0,
        },
        "open_items": open_items,
        "hr_flags": hr_flags,
        "timeline": timeline_events[:12],
        "proactive_items": proactive_items,
    }
