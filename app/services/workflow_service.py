"""문의 1건의 GHD 업무 처리 진행 상황을 저장/조회한다.

Step 완료 여부, HR 이메일 발송 이력, HR 회신, 최종 안내, 처리 결과까지
문의 1건의 처리 흐름 전체(HR 확인 요청 -> HR 회신 -> 최종 안내 -> 처리 완료)를
이 모듈이 담당한다.

Supabase(SUPABASE_URL/SUPABASE_KEY)가 설정되어 있으면 action_steps /
hr_communications / hr_replies / processing_results 4개 테이블에 저장하고,
아니면 로컬 개발용으로 가벼운 JSON 파일(data/hr_workflow_state.json)에 둔다.
두 경로 모두 get_state()가 반환하는 모양은 완전히 동일하므로, 이 두 저장소
전환은 이 파일 안에서만 일어나고 다른 코드는 영향받지 않는다.

⚠ 여기서 등록하는 HR 회신·최종 안내·처리 결과는 GHD 담당자가 직접 입력/확인하는
값이다. AI는 최종 안내의 초안(HR 회신 내용을 그대로 옮긴 문장)만 제안할 뿐,
실제 회신 내용이나 최종 판단을 대신 만들어내지 않는다.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services import supabase_client

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "hr_workflow_state.json"

EMPTY_STATE = {
    "completed_steps": [],
    "email_log": [],
    "hr_reply": None,
    "final_guidance": None,
    "resolution": None,
}

# STEP 9: 문의 상태 체계 (참고용 전체 목록 — 실제로는 분석이 즉시 자동 실행되는
# 구조라 "신규 문의"/"분석 완료"는 순간적으로만 존재하고, 이후는 아래 4개 중
# 하나로 정리된다: GHD 직접 처리 / HR 확인 요청 / 추가 서류 요청 / HR 회신 대기 / 처리 완료)
INQUIRY_STATUSES = [
    "신규 문의",
    "분석 완료",
    "GHD 직접 처리",
    "HR 확인 요청",
    "추가 서류 요청",
    "HR 회신 대기",
    "처리 완료",
]

# 상태 배지에 재사용할 기존 badge-* CSS 색상 매핑 (GHD_DIRECT=초록, SITUATION_CHECK=노랑, HR_FLAG=주황)
STATUS_BADGE_CLASS = {
    "GHD 직접 처리": "GHD_DIRECT",
    "추가 서류 요청": "HR_FLAG",
    "HR 확인 요청": "HR_FLAG",
    "HR 회신 대기": "SITUATION_CHECK",
    "처리 완료": "GHD_DIRECT",
}

RESOLUTION_OPTIONS = [
    "GHD 직접 안내 완료",
    "추가 서류 수령 완료",
    "HR 확인 완료",
    "HR 답변 전달 완료",
    "긴급 조치 완료",
    "기타",
]


# ---------------------------------------------------------------------------
# 로컬 JSON 파일 백엔드 (Supabase 미설정 시 폴백)
# ---------------------------------------------------------------------------
def _load_json():
    if not DATA_PATH.exists():
        return {}
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_json(data):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_state_json(inquiry_id):
    data = _load_json()
    state = data.get(inquiry_id, {})
    return {
        "completed_steps": state.get("completed_steps", []),
        "email_log": state.get("email_log", []),
        "hr_reply": state.get("hr_reply"),
        "final_guidance": state.get("final_guidance"),
        "resolution": state.get("resolution"),
    }


# ---------------------------------------------------------------------------
# Supabase 백엔드
# ---------------------------------------------------------------------------
def _single_row(result):
    rows = result.data or []
    return rows[0] if rows else None


def _get_state_supabase(client, inquiry_id):
    steps_res = (
        client.table("action_steps")
        .select("step_number")
        .eq("inquiry_id", inquiry_id)
        .eq("completed", True)
        .execute()
    )
    completed_steps = sorted(r["step_number"] for r in steps_res.data)

    email_res = (
        client.table("hr_communications")
        .select("*")
        .eq("inquiry_id", inquiry_id)
        .order("sent_at")
        .execute()
    )
    email_log = [
        {
            "sent_at": e["sent_at"],
            "subject": e["subject"],
            "body": e["body"],
            "recipient": e["recipient"],
            "success": e["success"],
            "error": e["error"],
        }
        for e in email_res.data
    ]

    reply_row = _single_row(
        client.table("hr_replies").select("*").eq("inquiry_id", inquiry_id).execute()
    )
    hr_reply = None
    final_guidance = None
    if reply_row:
        hr_reply = {
            "replied_at": reply_row["replied_at"],
            "content": reply_row["content"],
            "replier": reply_row["replier"],
            "additional_request": reply_row["additional_request"],
            "registered_at": reply_row["registered_at"],
        }
        if reply_row.get("final_guidance_content"):
            final_guidance = {
                "content": reply_row["final_guidance_content"],
                "confirmed_at": reply_row["final_guidance_confirmed_at"],
            }

    result_row = _single_row(
        client.table("processing_results").select("*").eq("inquiry_id", inquiry_id).execute()
    )
    resolution = None
    if result_row:
        resolution = {
            "outcome": result_row["outcome"],
            "memo": result_row["memo"],
            "recorded_at": result_row["recorded_at"],
        }

    return {
        "completed_steps": completed_steps,
        "email_log": email_log,
        "hr_reply": hr_reply,
        "final_guidance": final_guidance,
        "resolution": resolution,
    }


# ---------------------------------------------------------------------------
# 공개 API (Supabase 있으면 Supabase, 없으면 로컬 JSON)
# ---------------------------------------------------------------------------
def get_state(inquiry_id):
    """해당 문의의 진행 상태를 반환한다. 기록이 없으면 빈 상태를 반환한다."""
    client = supabase_client.get_client()
    if client:
        return _get_state_supabase(client, inquiry_id)
    return _get_state_json(inquiry_id)


def save_completed_steps(inquiry_id, completed_step_numbers):
    numbers = sorted(set(completed_step_numbers))

    client = supabase_client.get_client()
    if client:
        client.table("action_steps").delete().eq("inquiry_id", inquiry_id).execute()
        if numbers:
            rows = [{"inquiry_id": inquiry_id, "step_number": n, "completed": True} for n in numbers]
            client.table("action_steps").insert(rows).execute()
        return get_state(inquiry_id)

    data = _load_json()
    state = data.get(inquiry_id, dict(EMPTY_STATE))
    state["completed_steps"] = numbers
    data[inquiry_id] = state
    _save_json(data)
    return state


def record_email_attempt(inquiry_id, subject, body, recipient, success, error=None, auto_complete_step=None):
    """이메일 발송 시도 결과를 기록한다. 성공 시(auto_complete_step 지정) 해당 Step을
    자동으로 완료 처리해, 문의 상태가 "HR 확인 요청 -> 회신 대기"로 바뀌도록 한다."""
    client = supabase_client.get_client()
    if client:
        client.table("hr_communications").insert(
            {
                "inquiry_id": inquiry_id,
                "subject": subject,
                "body": body,
                "recipient": recipient,
                "success": success,
                "error": error,
            }
        ).execute()
        if success and auto_complete_step is not None:
            existing = get_state(inquiry_id)["completed_steps"]
            save_completed_steps(inquiry_id, list(existing) + [auto_complete_step])
        return get_state(inquiry_id)

    data = _load_json()
    state = data.get(inquiry_id, dict(EMPTY_STATE))

    entry = {
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "subject": subject,
        "body": body,
        "recipient": recipient,
        "success": success,
        "error": error,
    }
    state.setdefault("email_log", []).append(entry)

    if success and auto_complete_step is not None:
        completed = set(state.get("completed_steps", []))
        completed.add(auto_complete_step)
        state["completed_steps"] = sorted(completed)

    data[inquiry_id] = state
    _save_json(data)
    return state


def has_successful_email(inquiry_id):
    return any(e["success"] for e in get_state(inquiry_id)["email_log"])


def get_last_email(inquiry_id):
    log = get_state(inquiry_id)["email_log"]
    return log[-1] if log else None


def save_hr_reply(inquiry_id, replied_at, content, replier, additional_request):
    """GHD 담당자가 고객사 HR로부터 받은 회신을 등록한다."""
    registered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    client = supabase_client.get_client()
    if client:
        client.table("hr_replies").upsert(
            {
                "inquiry_id": inquiry_id,
                "replied_at": replied_at,
                "content": content,
                "replier": replier,
                "additional_request": additional_request,
                "registered_at": registered_at,
            }
        ).execute()
        return get_state(inquiry_id)

    data = _load_json()
    state = data.get(inquiry_id, dict(EMPTY_STATE))
    state["hr_reply"] = {
        "replied_at": replied_at,
        "content": content,
        "replier": replier,
        "additional_request": additional_request,
        "registered_at": registered_at,
    }
    data[inquiry_id] = state
    _save_json(data)
    return state


def save_final_guidance(inquiry_id, content):
    """GHD 담당자가 확정한, 임직원에게 전달할 최종 안내 문구를 저장한다.
    ⚠ AI는 HR 회신 내용을 옮긴 초안만 제안하며, 이 저장 시점의 값은 항상
    GHD 담당자가 검토·확정한 내용이다."""
    confirmed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    client = supabase_client.get_client()
    if client:
        client.table("hr_replies").update(
            {"final_guidance_content": content, "final_guidance_confirmed_at": confirmed_at}
        ).eq("inquiry_id", inquiry_id).execute()
        return get_state(inquiry_id)

    data = _load_json()
    state = data.get(inquiry_id, dict(EMPTY_STATE))
    state["final_guidance"] = {"content": content, "confirmed_at": confirmed_at}
    data[inquiry_id] = state
    _save_json(data)
    return state


def save_resolution(inquiry_id, outcome, memo):
    """문의의 최종 처리 결과를 등록한다. 등록 즉시 상태가 "처리 완료"가 된다."""
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    client = supabase_client.get_client()
    if client:
        client.table("processing_results").upsert(
            {"inquiry_id": inquiry_id, "outcome": outcome, "memo": memo, "recorded_at": recorded_at}
        ).execute()
        return get_state(inquiry_id)

    data = _load_json()
    state = data.get(inquiry_id, dict(EMPTY_STATE))
    state["resolution"] = {"outcome": outcome, "memo": memo, "recorded_at": recorded_at}
    data[inquiry_id] = state
    _save_json(data)
    return state


def get_workflow_status(inquiry_id, structured):
    """문의 1건의 현재 처리 상태를 INQUIRY_STATUSES 중 하나로 계산한다.
    (분석 자체는 매 요청마다 즉시 자동 실행되므로 "신규 문의"/"분석 완료"는
    이 함수가 반환하지 않는다 — 이미 그 다음 단계로 넘어간 것으로 본다.)"""
    state = get_state(inquiry_id)

    if state["resolution"]:
        return "처리 완료"

    if structured["requires_hr_email"]:
        return "HR 회신 대기" if has_successful_email(inquiry_id) else "HR 확인 요청"

    if structured["required_documents"]:
        doc_step = next(
            (s["step"] for s in structured["workflow_steps"] if s["label"] == "제출 서류 확인"),
            None,
        )
        if doc_step is not None and doc_step not in state["completed_steps"]:
            return "추가 서류 요청"

    return "GHD 직접 처리"


def build_timeline(inquiry, structured, state):
    """문의 접수부터 완료까지의 처리 과정을 시간순으로 정리한다.
    자동으로 즉시 처리되는 단계(AI 분석, 관련 기준 확인 등)는 별도 시각 없이
    항상 완료된 것으로 표시하고, 실제 시각이 남는 단계(이메일 전송/HR 회신/
    최종 안내/처리 결과)만 기록된 시각을 함께 보여준다."""
    events = [
        {"label": "문의 접수", "time": inquiry["inquiry_date"], "detail": inquiry["inquiry_text"], "done": True},
        {"label": "AI 분석", "time": None, "detail": f"문의 유형: {structured['extracted_type']}", "done": True},
        {
            "label": "관련 기준 확인",
            "time": None,
            "detail": f"관련 판단 기준 {len(structured['related_rules'])}건 확인",
            "done": True,
        },
        {
            "label": "유사 사례 확인",
            "time": None,
            "detail": (
                f"유사 사례 {len(structured['similar_cases'])}건 확인"
                if structured["similar_cases"]
                else "유사 사례 없음"
            ),
            "done": True,
        },
        {"label": "HR Flag", "time": None, "detail": structured["flag_type"], "done": True},
        {
            "label": "Action Step",
            "time": None,
            "detail": f"업무 절차 {len(structured['workflow_steps'])}단계 안내",
            "done": True,
        },
    ]

    if structured["requires_hr_email"]:
        events.append({"label": "HR 이메일 작성", "time": None, "detail": "HR 확인 요청 이메일 초안 작성", "done": True})
        events.append({"label": "Double-check", "time": None, "detail": "발송 전 담당자 확인 절차", "done": True})

    for entry in state["email_log"]:
        if entry["success"]:
            events.append(
                {
                    "label": "이메일 전송",
                    "time": entry["sent_at"],
                    "detail": "HR 확인 요청 이메일 전송 완료 (수신자: Demo HR 담당자)",
                    "done": True,
                }
            )
        else:
            events.append(
                {
                    "label": "이메일 전송 실패",
                    "time": entry["sent_at"],
                    "detail": entry.get("error") or "알 수 없는 오류",
                    "done": False,
                }
            )

    if state["hr_reply"]:
        events.append(
            {
                "label": "HR 회신",
                "time": state["hr_reply"]["registered_at"],
                "detail": state["hr_reply"]["content"],
                "done": True,
            }
        )

    if state["final_guidance"]:
        events.append(
            {
                "label": "최종 안내",
                "time": state["final_guidance"]["confirmed_at"],
                "detail": state["final_guidance"]["content"],
                "done": True,
            }
        )

    if state["resolution"]:
        events.append(
            {
                "label": "처리 결과 등록",
                "time": state["resolution"]["recorded_at"],
                "detail": state["resolution"]["outcome"],
                "done": True,
            }
        )
        events.append(
            {
                "label": "완료",
                "time": state["resolution"]["recorded_at"],
                "detail": "문의 처리가 완료되었습니다.",
                "done": True,
            }
        )

    return events
