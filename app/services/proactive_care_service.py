"""국적/소속기업/비자유형/재직기간 등 임직원 속성을 기준으로 GHD가 선제적으로
확인하면 좋은 항목을 미리 안내한다 (Proactive Care).

⚠ 여기서 쓰는 기준은 전부 프로젝트 시연용 가상 기준이다. 실제 출입국 규정이나
고객사 정책이 아니며, AI가 법적/행정적 최종 판단을 내리는 것도 아니다. GHD 담당자가
미리 확인해볼 만한 항목을 참고용으로 안내할 뿐이고, 실제 처리 여부는 담당자가 판단한다.
"""

from datetime import date

VISA_EXPIRY_WARNING_DAYS = 60

# 비자유형별 평균 체류/갱신 유효기간(개월) — 비자·체류기간 만료 예상일 추정에 사용
# (Demo 가정치, 실제 출입국 규정이 아니다). 재직기간(입사일 기준 경과 기간)은 이
# 추정과 무관하게 화면에는 별도로 자동 계산해 보여준다.
VISA_TYPE_VALIDITY_MONTHS = {
    "E-9": 12,
    "E-7": 24,
    "F-2": 36,
    "F-4": 36,
    "D-8": 24,
    "D-10": 6,
    "H-2": 58,
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

# 소속(파견) 고객사별 가상 Proactive Care 안내 (Demo 예시 — 실제 고객사 정책 아님)
CLIENT_POLICY_NOTES = {
    "그린로지스틱스": "물류센터 교대근무(주/야간) 배정 시 야간근무수당 산정 기준을 사전 안내 권장",
    "대성정밀": "정밀공정 투입 전 보호구 착용 교육 이수 여부 사전 확인 필요",
    "대한중공업부품": "중량물 취급 공정 배치 시 법정 안전교육 이수 여부 사전 확인 필요",
    "신성테크": "3교대 근무표 변경 시 사전 공지 절차 안내 권장",
    "우리식품": "식품위생법상 보건증(건강진단서) 유효기간을 사전 확인 필요",
    "청우물류": "성수기(명절 전후) 연장근무 동의 여부를 사전 확인 권장",
    "코스모스틸": "고온·분진 작업환경 보호구 지급 여부를 입사 초기 안내 권장",
    "하나바이오": "위생복 착용·출입 보안 절차 교육 이수 여부 사전 확인 필요",
    "한빛전자(주)": "정전기 방지(ESD) 교육 이수 여부 사전 확인 필요",
}

# 비자 유형별 가상 Proactive Care 안내 (Demo 예시 — 실제 출입국 규정 아님)
VISA_TYPE_NOTES = {
    "E-9": "고용허가제(E-9) 특성상 사업장 변경 시 별도 허가 절차가 필요 — 이직·전근 관련 문의 시 사전 안내 권장",
    "E-7": "특정활동(E-7) 비자는 등록된 직무 범위와 실제 업무가 일치하는지 주기적 확인 권장",
    "F-2": "거주(F-2) 비자는 상대적으로 자유로운 체류자격이나, 갱신 주기 및 요건 변경 여부 확인 권장",
    "F-4": "재외동포(F-4) 비자는 일부 단순노무 업종 종사에 제한이 있어 배치 직무 확인 필요",
    "D-8": "기업투자(D-8) 비자는 투자 유지 요건 충족 여부를 주기적으로 확인 필요",
    "D-10": "구직(D-10) 비자는 체류기간이 짧고 정식 취업 시 비자 변경 절차가 필요 — 미리 안내 권장",
    "H-2": "방문취업(H-2) 비자는 사업장 변경 가능 횟수에 제한이 있어 이직 문의 시 사전 확인 필요",
}

# 가족 동반 시 가상 Proactive Care 안내 (Demo 예시 — 개별 자녀·배우자 정보까지는 다루지 않음)
FAMILY_ACCOMPANIED_NOTE = (
    "가족 동반 임직원 — 자녀 학교 배정, 배우자 비자 상태, 가족 건강보험 가입 여부를 "
    "선제적으로 확인하면 좋음"
)


def _add_months(d, months):
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


def estimate_visa_expiry(employee):
    """start_date + 비자유형별 평균 유효기간으로 비자/체류기간 만료 예상일을 추정한다.
    (실제 출입국 기록이 아닌, Demo 데이터 기반의 단순 추정치)"""
    start = employee.get("start_date")
    if isinstance(start, str):
        try:
            start = date.fromisoformat(start)
        except ValueError:
            return None
    months = VISA_TYPE_VALIDITY_MONTHS.get(employee.get("visa_type"))
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

    client_note = CLIENT_POLICY_NOTES.get(employee.get("client_company"))
    if client_note:
        items.append({"type": "client_policy_note", "message": client_note, "severity": "LOW"})

    visa_note = VISA_TYPE_NOTES.get(employee.get("visa_type"))
    if visa_note:
        items.append({"type": "visa_type_note", "message": visa_note, "severity": "LOW"})

    if employee.get("family_accompanied"):
        items.append({"type": "family_note", "message": FAMILY_ACCOMPANIED_NOTE, "severity": "LOW"})

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
