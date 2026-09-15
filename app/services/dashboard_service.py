"""GHD 업무 현황판(Dashboard)에 필요한 집계 데이터를 계산한다.

모든 숫자는 항상 현재 문의 데이터(엑셀) + 처리 진행 상태(workflow_service)에서
그때그때 다시 계산한다. 하드코딩된 값은 없다.
"""

from collections import Counter
from datetime import date, timedelta

from app.services import (
    employee_service,
    inquiry_service,
    proactive_care_service,
    structuring_service,
    workflow_service,
)

# 우선 처리 필요 영역 정렬 순서 (요청 순서 그대로)
PRIORITY_ORDER = ["긴급 문의", "HR 회신 대기", "HR 확인 요청", "추가 서류 요청", "신규 문의"]

CARE_ACTIVITY_DAYS = 7

# 요일 표기 (X축 라벨용)
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _get_care_activity(inquiries, days=CARE_ACTIVITY_DAYS):
    """최근 N일간의 Care 활동량(신규 문의 접수 + GHD 처리 활동)을 날짜별로 집계한다.
    새 DB 테이블 없이 기존 문의 데이터(inquiry_date)와 워크플로우 처리 기록
    (Step 완료/이메일 발송/HR 회신/처리 결과)만으로 계산한다."""
    today = date.today()
    day_list = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    counts = {d.isoformat(): 0 for d in day_list}

    for inq in inquiries:
        if inq["inquiry_date"] in counts:
            counts[inq["inquiry_date"]] += 1

    activity_counts = workflow_service.get_recent_activity_counts(days=days, today=today)
    for day_str, n in activity_counts.items():
        if day_str in counts:
            counts[day_str] += n

    series = [
        {
            "date": d.isoformat(),
            "label": f"{d.month}/{d.day}",
            "weekday": _WEEKDAY_KO[d.weekday()],
            "count": counts[d.isoformat()],
        }
        for d in day_list
    ]
    return {"series": series, "total": sum(counts.values())}


def _get_care_by_category(inquiries):
    """문의의 기존 category 값을 그대로 사용해 카테고리별 건수를 집계한다
    (새로운 카테고리 체계를 만들지 않고 기존 data/inquiries.xlsx의 category를 그대로 사용)."""
    counter = Counter(inq["category"] for inq in inquiries)
    ranked = counter.most_common()
    series = [{"category": category, "count": count} for category, count in ranked]
    return {"series": series, "total": sum(counter.values())}


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
        "employee_id": inquiry["employee_id"],
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
        "resolution": state["resolution"],
    }


# ---------------------------------------------------------------------------
# Feature 1: AI Priority — 기존 데이터(카테고리/긴급도/HR 확인 필요/처리 상태/비자 임박)를
# 조합한 Rule-based 점수로 HIGH/MEDIUM/LOW와 "왜 중요한지" 이유를 함께 계산한다.
# 실제 AI 모델을 호출하지 않고, 결과를 "AI Priority"로 표기해 우선순위 판단을 지원한다.
# ---------------------------------------------------------------------------
def employee_visa_signal(employee, today=None):
    """직원의 비자/체류기간 만료 임박 여부를 반환한다 (없으면 None).
    proactive_care_service의 만료 추정 로직을 그대로 재사용한다."""
    if not employee:
        return None
    today = today or date.today()
    expiry = proactive_care_service.estimate_visa_expiry(employee)
    if not expiry:
        return None
    days_left = (expiry - today).days
    if 0 <= days_left <= proactive_care_service.VISA_EXPIRY_WARNING_DAYS:
        severity = "HIGH" if days_left <= 30 else "MEDIUM"
        return {"expiry": expiry, "days_left": days_left, "severity": severity}
    return None


def compute_ai_priority(summary, visa_signal):
    score = 0
    reasons = []

    if summary["category"] == "비자·체류":
        score += 3
        reasons.append("비자·체류 관련 업무")
    if visa_signal:
        score += 3 if visa_signal["severity"] == "HIGH" else 2
        reasons.append(f"비자 만료까지 {visa_signal['days_left']}일 남음")
    if summary["urgency"] == "HIGH":
        score += 3
        reasons.append("긴급도 HIGH로 분류된 문의")
    elif summary["urgency"] == "MEDIUM":
        score += 1
    if summary["flag_type"] == "HR_FLAG":
        score += 2
        reasons.append("HR 확인이 필요한 사안")
    if summary["status"] in ("HR 확인 요청", "HR 회신 대기", "추가 서류 요청"):
        score += 2
        reasons.append("아직 처리가 완료되지 않은 상태")

    if score >= 6:
        level = "HIGH"
    elif score >= 3:
        level = "MEDIUM"
    else:
        level = "LOW"

    if not reasons:
        reasons.append("안내성·참고성 문의로 긴급성이 낮음")

    return {"level": level, "score": score, "reason": " · ".join(reasons[:3])}


# ---------------------------------------------------------------------------
# Feature 2: Upcoming / Due Soon — 실제 deadline 필드가 없으므로, 비자 만료 예상일
# (실제 데이터 기반)을 우선 사용하고, 그 외에는 AI Priority 수준에서 자연스러운
# 처리 기한을 역산한다 (HIGH=오늘, MEDIUM=3일 후, LOW=이번 주) — 데모 목적의
# 규칙 기반 추정치이며, 실제 SLA 규정이 아니다.
# ---------------------------------------------------------------------------
_DUE_OFFSET_BY_PRIORITY = {"HIGH": 0, "MEDIUM": 3, "LOW": 7}


def compute_due(ai_priority_level, visa_signal, today=None):
    today = today or date.today()
    due_date = visa_signal["expiry"] if visa_signal else today + timedelta(
        days=_DUE_OFFSET_BY_PRIORITY[ai_priority_level]
    )

    days = (due_date - today).days
    if days <= 0:
        label, bucket = "오늘", "today"
    elif days == 1:
        label, bucket = "내일", "tomorrow"
    elif days <= 7:
        label, bucket = f"{days}일 후", "this_week"
    elif days <= 60:
        label, bucket = f"{days}일 후", "later"
    else:
        label, bucket = f"{due_date.month}/{due_date.day}", "later"

    return {"date": due_date.isoformat(), "label": label, "bucket": bucket}


def _get_upcoming_care(priority_items, limit=6):
    bucket_order = ["today", "tomorrow", "this_week", "later"]
    bucket_labels = {"today": "오늘", "tomorrow": "내일", "this_week": "이번 주", "later": "추후"}
    counts = {b: 0 for b in bucket_order}
    for item in priority_items:
        counts[item["due"]["bucket"]] += 1

    ranked = sorted(priority_items, key=lambda s: (-s["ai_priority"]["score"], s["due"]["date"]))

    return {
        "counts": [
            {"bucket": b, "label": bucket_labels[b], "count": counts[b]} for b in bucket_order if counts[b] > 0
        ],
        "top_items": ranked[:limit],
        "total": len(priority_items),
    }


# ---------------------------------------------------------------------------
# Feature 4: AI Care Insight — Chatbot이 아닌, 현재 데이터에서 가장 먼저 확인해야 할
# 상황 하나를 규칙 기반으로 골라 안내한다. 새로운 LLM 호출 없이 기존 집계 결과만 사용.
# ---------------------------------------------------------------------------
def _get_ai_care_insight(priority_items, proactive_items):
    high_due_today = [
        s for s in priority_items if s["ai_priority"]["level"] == "HIGH" and s["due"]["bucket"] == "today"
    ]
    if high_due_today:
        return {
            "message": f"{len(high_due_today)}건의 HIGH 우선순위 Care 항목이 오늘 처리가 필요합니다.",
            "recommendation": "비자·체류 관련 업무부터 먼저 확인하세요.",
            "action_label": "Care 항목 보기",
            "action_url": "/inquiries-view?tab=priority",
        }

    hr_flag_open = [s for s in priority_items if s["flag_type"] == "HR_FLAG"]
    if hr_flag_open:
        return {
            "message": f"HR 확인이 필요한 문의가 {len(hr_flag_open)}건 있습니다.",
            "recommendation": "고객사 HR 확인 요청 진행 상황을 점검하세요.",
            "action_label": "HR 확인 대기 문의 보기",
            "action_url": "/inquiries-view?tab=priority",
        }

    visa_high = [i for i in proactive_items if i["severity"] == "HIGH"]
    if visa_high:
        return {
            "message": f"비자/체류기간 만료가 임박한 임직원이 {len(visa_high)}명 있습니다.",
            "recommendation": "선제 확인 필요 목록에서 연장 절차를 안내하세요.",
            "action_label": "선제 확인 필요 보기",
            "action_url": "/inquiries-view?tab=proactive",
        }

    return None


def _get_urgent_banners(priority_items, proactive_items, recent_items):
    """홈 화면 상단에 노출할 '정말 긴급한 사안만' 요약한 짧은 배너 목록.
    각 배너는 해당 탭(문의 목록의 선제 확인/우선 처리/최근 문의 탭)으로 바로 연결된다."""
    banners = []

    high_priority_count = sum(1 for s in priority_items if s["urgency"] == "HIGH")
    if high_priority_count:
        banners.append(
            {
                "level": "critical",
                "message": f"긴급 처리가 필요한 문의 {high_priority_count}건이 있습니다.",
                "url": "/inquiries-view?tab=priority",
            }
        )

    visa_high_count = sum(1 for i in proactive_items if i["severity"] == "HIGH")
    if visa_high_count:
        banners.append(
            {
                "level": "warning",
                "message": f"비자/체류기간 만료가 임박한 임직원이 {visa_high_count}명 있습니다.",
                "url": "/inquiries-view?tab=proactive",
            }
        )

    if recent_items:
        banners.append(
            {
                "level": "info",
                "message": f"최근 접수된 문의 {len(recent_items)}건을 확인해보세요.",
                "url": "/inquiries-view?tab=recent",
            }
        )

    return banners


def get_dashboard_data(priority_limit=15, recent_limit=15, completed_limit=15):
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

    recent_items = sorted(summaries, key=lambda s: s["inquiry_date"], reverse=True)[:recent_limit]

    completed_items = [s for s in summaries if s["status"] == "처리 완료"]
    completed_items.sort(key=lambda s: (s["resolution"]["recorded_at"] if s["resolution"] else ""), reverse=True)
    completed_total = len(completed_items)
    completed_items = completed_items[:completed_limit]

    employees = employee_service.get_all_employees()
    employees_by_id = {e["employee_id"]: e for e in employees}
    proactive_items = proactive_care_service.get_all_proactive_items(employees)

    # Feature 1/2: 미해결 문의 전체(상위 노출분만이 아니라)에 AI Priority/Due를 계산해야
    # Upcoming Care 집계가 정확하다.
    for item in priority_items:
        visa_signal = employee_visa_signal(employees_by_id.get(item["employee_id"]))
        item["ai_priority"] = compute_ai_priority(item, visa_signal)
        item["due"] = compute_due(item["ai_priority"]["level"], visa_signal)

    return {
        "kpi": kpi,
        "priority_items": priority_items[:priority_limit],
        "priority_total": len(priority_items),
        "recent_items": recent_items,
        "completed_items": completed_items,
        "completed_total": completed_total,
        "proactive_items": proactive_items,
        "care_activity": _get_care_activity(inquiries),
        "care_by_category": _get_care_by_category(inquiries),
        "upcoming_care": _get_upcoming_care(priority_items),
        "ai_care_insight": _get_ai_care_insight(priority_items, proactive_items),
        "urgent_banners": _get_urgent_banners(priority_items, proactive_items, recent_items),
    }
