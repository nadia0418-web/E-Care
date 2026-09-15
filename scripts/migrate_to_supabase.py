"""로컬 Demo 데이터(엑셀 3종 + hr_workflow_state.json)를 Supabase로 1회 이전한다.

사전 조건:
1. supabase/schema.sql을 Supabase 대시보드 > SQL Editor에서 먼저 실행해 테이블을 만든다.
2. .env에 SUPABASE_URL / SUPABASE_KEY(service_role 권장 — 서버 전용, 절대 브라우저에 노출 금지)가
   설정되어 있어야 한다.

실행:
    python scripts/migrate_to_supabase.py

⚠ 여기서 옮기는 데이터는 전부 프로젝트 시연용 가상 데이터다 (실제 ETNERS/고객사 정보 아님).
이 스크립트는 여러 번 실행해도 안전하도록(idempotent) upsert를 사용한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import employee_service, inquiry_service, rule_service, supabase_client, workflow_service


def _chunks(items, size=200):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def migrate_employees(client):
    rows = employee_service._load_from_excel()
    for chunk in _chunks(rows):
        client.table("employees").upsert(chunk).execute()
    print(f"employees: {len(rows)}건 이전 완료")


def migrate_inquiries(client):
    rows = inquiry_service._load_from_excel()
    for chunk in _chunks(rows):
        client.table("inquiries").upsert(chunk).execute()
    print(f"inquiries: {len(rows)}건 이전 완료")


def migrate_rules(client):
    rows = rule_service._load_from_excel()
    for chunk in _chunks(rows):
        client.table("rules").upsert(chunk).execute()
    print(f"rules: {len(rows)}건 이전 완료")


def migrate_workflow_state(client):
    """기존 hr_workflow_state.json에 남아 있는 진행 상태(있다면)를 옮긴다.
    Demo 프로젝트 특성상 보통 비어 있거나 테스트 흔적만 있을 수 있다."""
    if not workflow_service.DATA_PATH.exists():
        print("hr_workflow_state.json 없음: 이전할 진행 상태 없음")
        return

    data = workflow_service._load_json()
    if not data:
        print("hr_workflow_state.json 비어 있음: 이전할 진행 상태 없음")
        return

    migrated = 0
    for inquiry_id, state in data.items():
        for step in state.get("completed_steps", []):
            client.table("action_steps").upsert(
                {"inquiry_id": inquiry_id, "step_number": step, "completed": True}
            ).execute()
        for entry in state.get("email_log", []):
            client.table("hr_communications").insert({"inquiry_id": inquiry_id, **entry}).execute()
        hr_reply = state.get("hr_reply")
        final_guidance = state.get("final_guidance")
        if hr_reply:
            payload = dict(hr_reply)
            payload["inquiry_id"] = inquiry_id
            if final_guidance:
                payload["final_guidance_content"] = final_guidance["content"]
                payload["final_guidance_confirmed_at"] = final_guidance["confirmed_at"]
            client.table("hr_replies").upsert(payload).execute()
        resolution = state.get("resolution")
        if resolution:
            client.table("processing_results").upsert({"inquiry_id": inquiry_id, **resolution}).execute()
        migrated += 1
    print(f"hr_workflow_state: {migrated}건 문의의 진행 상태 이전 완료")


def main():
    client = supabase_client.get_client()
    if client is None:
        print("SUPABASE_URL / SUPABASE_KEY가 .env에 설정되어 있지 않습니다. 먼저 설정해주세요.")
        sys.exit(1)

    migrate_employees(client)
    migrate_inquiries(client)
    migrate_rules(client)
    migrate_workflow_state(client)
    print("모든 이전 작업 완료.")


if __name__ == "__main__":
    main()
