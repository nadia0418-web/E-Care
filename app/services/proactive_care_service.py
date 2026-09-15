"""국적/비자유형/근무기간 등 임직원 속성을 기준으로 GHD가 선제적으로 확인하면
좋은 항목을 미리 안내한다 (Proactive Care).

⚠ 여기서 쓰는 기준은 전부 프로젝트 시연용 가상 기준이다. 실제 출입국 규정이나
고객사 정책이 아니며, AI가 법적/행정적 최종 판단을 내리는 것도 아니다. GHD 담당자가
미리 확인해볼 만한 항목을 참고용으로 안내할 뿐이고, 실제 처리 여부는 담당자가 판단한다.
"""

from datetime import date

VISA_EXPIRY_WARNING_DAYS = 60

# employees.xlsx의 "근무기간" 값(고정 5종)을 개월 수로 환산 (STEP 2 Demo 데이터 기준)
EMPLOYMENT_PERIOD_MONTHS = {
    "1년": 12,
    "1년 6개월": 18,
    "2년": 24,
    "3년": 36,
    "4년 10개월": 58,
}

# 국적별 가상 Proactive Care 안내 (Demo 예시 — 실제 규정 아님)
NATIONALITY_NOTES = {
    "베트남": "서류 제출 시 베트남어 원본은 국문 번역 공증본 첨부 여부를 미리 안내",
    "네팔": "여권과 서류상 영문 성명 표기가 다른 사례가 있어 사전 대조 권장",
    "우즈베키스탄": "가족관계증명서 등 현지 발급 서류는 아포스티유 확인이 필요할 수 있음",
    "인도네시아": "이슬람 공휴일 기간 중 고향 방문 휴가 문의가 몰리는 경향이 있어 사전 안내 권장",
    "캄보디아": "서류 제출 시 크메르어 원본의 번역 공증 필요 여부를 미리 안내",
    "미얀마": "여권 갱신 절차가 상대적으로 오래 걸려 만료 임박 시 조기 안내 권장",
}


def _add_months(d, months):
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


def estimate_visa_expiry(employee):
    """start_date + employment_period로 비자/체류기간 만료 예상일을 추정한다.
    (실제 출입국 기록이 아닌, Demo 데이터 기반의 단순 추정치)"""
    start = employee.get("start_date")
    if isinstance(start, str):
        try:
            start = date.fromisoformat(start)
        except ValueError:
            return None
    months = EMPLOYMENT_PERIOD_MONTHS.get(employee.get("employment_period"))
    if not start or not months:
        return None
    return _add_months(start, months)


def get_proactive_items(employee, today=None):
    """직원 1명에 대한 선제 확인 항목 리스트를 반환한다. 없으면 빈 리스트."""
    today = today or date.today()
    items = []

    expiry = estimate_visa_expiry(employee)
    if expiry:
        days_left = (expiry - today).days
        if 0 <= days_left <= VISA_EXPIRY_WARNING_DAYS:
            items.append(
                {
                    "type": "visa_expiry",
                    "message": (
                        f"비자/체류기간 만료 예상일 {expiry.isoformat()} "
                        f"({days_left}일 남음) — 연장 절차 사전 확인 필요"
                    ),
                    "severity": "HIGH" if days_left <= 30 else "MEDIUM",
                }
            )

    note = NATIONALITY_NOTES.get(employee.get("nationality"))
    if note:
        items.append({"type": "nationality_note", "message": note, "severity": "LOW"})

    return items


def get_all_proactive_items(employees, today=None):
    """전체 직원 중 선제 확인 항목이 있는 건만 모아, 긴급도 높은 순으로 정렬해 반환한다."""
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    results = []
    for employee in employees:
        for item in get_proactive_items(employee, today=today):
            results.append(
                {
                    "employee_id": employee["employee_id"],
                    "employee_name": employee["name"],
                    "nationality": employee["nationality"],
                    "client_company": employee["client_company"],
                    **item,
                }
            )
    results.sort(key=lambda r: severity_rank.get(r["severity"], 9))
    return results
