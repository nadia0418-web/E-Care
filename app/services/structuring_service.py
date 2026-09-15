"""문의 원문을 구조화하고, GHD 담당자가 다음에 할 일(Action)을 제안하는 로직.

⚠ 이 모듈의 결과도 최종 판단이 아니라 "1차 분석 / 업무지원 제안"이다.
   실제 회사의 규정을 임의로 판단하거나 확정하지 않으며, 참고하는 판단 기준도
   프로젝트 시연용 가상 데이터(가상 GHD 업무 판단 기준)이다.
   최종 Action은 GHD 담당자가 검토 후 확정한다.

처리 흐름:
    문의 원문
      -> 문의 내용 구조화 (문의 유형 / 관련 날짜 / 필요 서류 / 긴급도 / 핵심 내용 / 추가 확인사항)
      -> 관련 판단 기준 확인 (analysis_service)
      -> GHD 다음 액션 제안 (recommend_actions)
"""

import os
import re

from app.services import analysis_service, inquiry_service, rule_service

# 실제 고객사 정보가 없는 Demo 환경이므로, HR 수신자는 절대 발송되지 않는
# 예약 도메인(example.com, RFC 2606)의 가상 주소만 사용한다.
DEMO_HR_EMAIL = "hr-demo@example.com"

STRUCTURE_LABEL = "1차 분석 / 업무지원 제안 (최종 판단 아님)"

# Action 후보 (STEP 6 초기 MVP 고정 목록)
ACTIONS = [
    {
        "code": "ACTION_1",
        "label": "직접 안내",
        "guidance": "GHD가 문의자에게 절차·답변을 직접 안내합니다.",
    },
    {
        "code": "ACTION_2",
        "label": "추가 서류 요청",
        "guidance": "판단에 필요한 서류를 문의자에게 요청하고 제출받습니다.",
    },
    {
        "code": "ACTION_3",
        "label": "HR 확인",
        "guidance": "고객사 HR 담당자에게 사안을 공유하고 확인·승인을 요청합니다.",
    },
    {
        "code": "ACTION_4",
        "label": "긴급 에스컬레이션",
        "guidance": "긴급 사안으로 판단해 상위 담당자/관련 부서에 즉시 공유합니다.",
    },
]
ACTION_LABEL_BY_CODE = {a["code"]: a["label"] for a in ACTIONS}
ACTION_GUIDANCE_BY_CODE = {a["code"]: a["guidance"] for a in ACTIONS}

# 문의 텍스트에서 필요 서류를 유추하기 위한 키워드 → 서류명 매핑
DOCUMENT_KEYWORDS = {
    "진단서": "의료기관 진단서(해외 발급 포함)",
    "재직증명서": "재직증명서",
    "경력증명서": "경력증명서",
    "원천징수영수증": "원천징수영수증",
    "소득금액증명원": "소득금액증명원",
    "여권": "여권 사본",
    "외국인등록증": "외국인등록증 사본",
    "계약서": "임대차 계약서",
    "가족관계": "가족관계증명서",
}

# 관련 날짜 표현을 그대로 추출하기 위한 패턴 (실제 날짜 계산은 하지 않고 표현만 추출)
DATE_PATTERNS = [
    r"다음\s?주\s?[월화수목금토일]요일",
    r"이번\s?주\s?[월화수목금토일]요일",
    r"다음\s?달",
    r"이번\s?달",
    r"\d{4}[-./]\d{1,2}[-./]\d{1,2}",
    r"\d{1,2}월\s?\d{1,2}일",
    r"오늘",
    r"내일",
    r"모레",
]

# 특정 판단 기준(rule_id)에 대한 추가 확인사항 예시 (없으면 아래 기본 로직으로 생성)
ADDITIONAL_INFO_OVERRIDES = {
    "R007": ["진단서 인정 여부", "병가 신청 절차"],
    "R010": ["출입국사무소 방문 가능 일정", "여권/체류 관련 서류 유효기간"],
    "R014": ["사고 경위 확인", "산재 처리 대상 여부"],
    "R024": ["구체적 사건 경위 확인", "관련자 진술 확보 필요 여부"],
}


def extract_required_documents(inquiry_text):
    text = inquiry_text or ""
    found = []
    for keyword, doc_name in DOCUMENT_KEYWORDS.items():
        if keyword in text and doc_name not in found:
            found.append(doc_name)
    return found


def extract_date_phrase(inquiry_text):
    text = inquiry_text or ""
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _build_additional_information(rule, match_type):
    if rule["rule_id"] in ADDITIONAL_INFO_OVERRIDES:
        info = list(ADDITIONAL_INFO_OVERRIDES[rule["rule_id"]])
    else:
        info = [f"{rule['rule_name']} 관련 세부 사실관계 확인"]
        if rule["hr_flag"]:
            info.append("고객사 HR 확인 필요 여부")
        else:
            info.append("추가 서류·증빙 필요 여부")

    if match_type == "category_only":
        info.append("문의 카테고리만 일치하여 정확한 문의 취지 추가 확인 필요")
    return info


# ---- 유사 사례 검색 (같은 카테고리 + 텍스트 유사도, 머신러닝 미사용) ----
SIMILAR_CASE_LIMIT = 3
SIMILAR_CASE_MIN_SCORE = 3


def _char_bigrams(text):
    """한국어는 조사가 어간에 바로 붙어(예: '진단서의'/'진단서도') 단어 단위 비교가
    잘 안 맞으므로, 공백/기호를 제거한 뒤 2글자 단위(bigram)로 잘라 비교한다.
    형태소 분석기나 별도 AI 모델 없이도 같은 어간("진단서", "병가" 등)이 겹치면
    잡아낼 수 있는 가장 단순한 방식이다."""
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", text or "")
    if len(cleaned) < 2:
        return set()
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def _text_similarity_score(text_a, text_b):
    bigrams_a = _char_bigrams(text_a)
    bigrams_b = _char_bigrams(text_b)
    return len(bigrams_a & bigrams_b)


def find_similar_cases(
    category, inquiry_text, exclude_inquiry_id=None, limit=SIMILAR_CASE_LIMIT
):
    """현재 문의와 내용이 비슷한 과거 Demo 문의를 찾는다.

    같은 카테고리 안에서만 후보를 찾고(다른 카테고리끼리는 비교 대상에서 제외),
    문자 2-gram 겹침 개수로 유사도 점수를 매긴다. 일정 점수(SIMILAR_CASE_MIN_SCORE)
    이상인 것만 "유사 사례"로 인정하며, 하나도 없으면 빈 리스트를 반환한다
    (화면에서는 "유사 사례가 없습니다"로 처리).
    """
    candidates = [
        inq
        for inq in inquiry_service.get_all_inquiries()
        if inq["category"] == category and inq["inquiry_id"] != exclude_inquiry_id
    ]

    scored = []
    for inq in candidates:
        score = _text_similarity_score(inquiry_text, inq["inquiry_text"])
        if score >= SIMILAR_CASE_MIN_SCORE:
            scored.append((score, inq))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, inq in scored[:limit]:
        # 그 사례 당시의 flag/긴급도를 기준으로, 지금과 동일한 추천 로직으로
        # "당시 상황이라면 추천되었을 Action"을 계산한다 (실제 발생 이력이 아니라
        # 일관된 규칙을 과거 사례에도 동일하게 적용한 참고용 표시).
        past_docs = extract_required_documents(inq["inquiry_text"])
        past_actions = recommend_actions(inq["flag"], inq["urgency"], past_docs)
        results.append(
            {
                "inquiry_id": inq["inquiry_id"],
                "category": inq["category"],
                "inquiry_text": inq["inquiry_text"],
                "flag": inq["flag"],
                "past_recommended_actions": past_actions,
                "final_result": inq["final_result"],
                "similarity_score": score,
            }
        )
    return results


def recommend_actions(flag_type, urgency, required_documents):
    """분석 결과(Flag)를 바탕으로 GHD 담당자가 순서대로 밟아야 할 다음 Action을 제안한다.
    Flag(관리 수준)와 Action(다음 할 일)은 서로 다른 개념이며, 이 함수가 그 변환을 담당한다.

    긴급도가 HIGH인 경우 즉시 대응이 우선이므로 "긴급 에스컬레이션"을 1순위로 두고,
    이후 서류 확보 -> (HR 확인 또는 직접 안내) 순서로 단계를 구성한다."""
    codes = []
    if urgency == "HIGH":
        codes.append("ACTION_4")  # 긴급 에스컬레이션 (즉시 대응 최우선)

    if required_documents:
        codes.append("ACTION_2")  # 추가 서류 요청

    if flag_type == "HR_FLAG":
        codes.append("ACTION_3")  # HR 확인
    else:
        codes.append("ACTION_1")  # 직접 안내 (GHD Direct / Situation Check 공통 1차 대응)

    seen = set()
    ordered = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)

    return [
        {
            "code": c,
            "label": ACTION_LABEL_BY_CODE[c],
            "guidance": ACTION_GUIDANCE_BY_CODE[c],
            "step": idx + 1,
        }
        for idx, c in enumerate(ordered)
    ]


# ---- Step 8: Action을 담당자의 실제 업무 절차(Step)로 확장 ----
# Action 코드 1개가 실제로는 여러 세부 업무 Step으로 구성될 수 있다.
# (예: "HR 확인" = HR 확인 필요 여부 판단 -> HR에 확인 요청(이메일) -> 회신 확인 -> 임직원 안내)
# requires_hr_email=True인 Step이 바로 "HR 커뮤니케이션(이메일 작성/Double-check/전송)"
# 화면과 연결되는 지점이다.
STEP_TEMPLATES = {
    "ACTION_4": [
        {
            "label": "긴급 에스컬레이션",
            "task": "비자 만료 등 긴급 사안이므로 우선 담당자 및 관련 부서 확인이 필요합니다.",
            "requires_hr_email": False,
        },
    ],
    "ACTION_2": [
        {
            "label": "추가 서류 요청",
            "task": "판단에 필요한 서류를 문의자에게 요청합니다.",
            "requires_hr_email": False,
        },
        {
            "label": "제출 서류 확인",
            "task": "문의자가 제출한 서류를 확인합니다.",
            "requires_hr_email": False,
        },
    ],
    "ACTION_3": [
        {
            "label": "HR 확인",
            "task": "해당 문의가 고객사 HR의 판단을 필요로 하는 사안인지 확인합니다.",
            "requires_hr_email": False,
        },
        {
            "label": "HR 확인 요청",
            "task": "문의 내용과 확인이 필요한 사항을 정리하여 고객사 HR에 확인을 요청합니다.",
            "requires_hr_email": True,
        },
        {
            "label": "회신 확인",
            "task": "HR의 회신 내용을 확인하고 처리 결과에 반영합니다.",
            "requires_hr_email": False,
        },
        {
            "label": "임직원 안내",
            "task": "확인된 내용을 바탕으로 임직원에게 최종 안내합니다.",
            "requires_hr_email": False,
        },
    ],
    "ACTION_1": [
        {
            "label": "직접 안내",
            "task": "GHD가 문의자에게 절차·답변을 직접 안내합니다.",
            "requires_hr_email": False,
        },
    ],
}


def build_workflow_steps(recommended_actions, required_documents, related_rules):
    """추천 Action(코드)을 GHD 담당자가 실제로 밟을 세부 업무 Step 목록으로 펼친다.
    각 Step은 {step, label, task, action_code, requires_hr_email, related_materials}를 갖는다."""
    steps = []
    for action in recommended_actions:
        for tpl in STEP_TEMPLATES.get(action["code"], []):
            step = dict(tpl)
            step["action_code"] = action["code"]
            step["related_materials"] = []
            if action["code"] == "ACTION_2":
                step["related_materials"] = list(required_documents)
            elif action["code"] == "ACTION_3" and step["label"] == "HR 확인":
                primary = [r["rule_name"] for r in related_rules if r["is_primary_match"]]
                if not primary and related_rules:
                    primary = [related_rules[0]["rule_name"]]
                step["related_materials"] = primary
            steps.append(step)

    for idx, step in enumerate(steps, start=1):
        step["step"] = idx
    return steps


def build_hr_email_draft(inquiry, employee, structured):
    """HR 확인 요청 이메일 초안을 생성한다 (요청된 고정 서식 사용).
    ⚠ AI는 서류/문의 내용을 정리해 "확인 요청"만 할 뿐, HR의 최종 판단을 대신하지 않는다."""
    staff_name = os.environ.get("GHD_STAFF_NAME", "담당자")
    employee_name = employee["name"] if employee else inquiry.get("employee_id", "-")
    client_company = employee["client_company"] if employee else "-"
    nationality = employee["nationality"] if employee else "-"
    category = structured["extracted_type"]

    subject = f"[확인 요청] {category} 관련 확인 부탁드립니다 - {employee_name}"

    confirm_items = "\n".join(f"- {info}" for info in structured["additional_information"])
    if not confirm_items:
        confirm_items = "- 관련 사실관계 확인"

    reference_lines = [f"- 시스템 1차 분석 근거: {structured['reasoning']}"]
    if structured["required_documents"]:
        reference_lines.append("- 제출 필요 서류: " + ", ".join(structured["required_documents"]))
    reference_text = "\n".join(reference_lines)

    body = (
        "안녕하세요.\n"
        f"GHD {staff_name}입니다.\n\n"
        "아래와 같이 외국인 임직원 문의사항이 접수되어 확인 요청드립니다.\n\n"
        "1. 대상 임직원\n"
        f"- 성명: {employee_name}\n"
        f"- 소속: {client_company}\n"
        f"- 국적: {nationality}\n"
        f"- 문의 유형: {category}\n\n"
        "2. 문의 내용\n"
        f"- {structured['key_issue']}\n\n"
        "3. 확인 요청 사항\n"
        f"{confirm_items}\n\n"
        "4. 참고 사항\n"
        f"{reference_text}\n\n"
        "확인 후 회신 부탁드립니다.\n"
        "감사합니다.\n\n"
        f"GHD {staff_name} 드림"
    )

    return {"subject": subject, "body": body, "recipient": DEMO_HR_EMAIL}


def structure_inquiry(inquiry_text, category=None, employee=None, exclude_inquiry_id=None):
    """문의 원문 하나를 구조화하고, 관련 판단 기준·유사 사례·추천 Action까지 반환한다.

    전체 흐름: 문의 -> AI 문의 구조화 -> 관련 규정/판단 기준 -> 유사 사례 -> Flag -> 다음 Action

    category를 주지 않으면(=아직 분류되지 않은 새 문의) 카테고리부터 자동 분류한다.
    employee(선택)를 주면 구조화 결과의 employee_name에 반영한다.
    exclude_inquiry_id(선택)를 주면 유사 사례 검색에서 자기 자신은 제외한다.
    """
    resolved_category = category or analysis_service.classify_category(inquiry_text)

    analysis = analysis_service.analyze_inquiry(inquiry_text, resolved_category)
    matched_rule = rule_service.get_rule_by_id(analysis["matched_rule"]) if analysis else None

    required_documents = extract_required_documents(inquiry_text)
    extracted_date = extract_date_phrase(inquiry_text)
    key_issue = matched_rule["situation"] if matched_rule else inquiry_text
    additional_information = (
        _build_additional_information(matched_rule, analysis["match_type"])
        if matched_rule
        else []
    )

    related_rules = analysis_service.get_related_rules(resolved_category, inquiry_text)
    similar_cases = find_similar_cases(
        resolved_category, inquiry_text, exclude_inquiry_id=exclude_inquiry_id
    )

    recommended = recommend_actions(
        analysis["flag_type"], analysis["urgency"], required_documents
    )
    workflow_steps = build_workflow_steps(recommended, required_documents, related_rules)
    requires_hr_email = any(s["requires_hr_email"] for s in workflow_steps)

    return {
        "structure_label": STRUCTURE_LABEL,
        "extracted_type": resolved_category,
        "employee_name": employee["name"] if employee else None,
        "extracted_date": extracted_date,
        "required_documents": required_documents,
        "urgency": analysis["urgency"],
        "is_urgent": analysis["is_urgent"],
        "key_issue": key_issue,
        "additional_information": additional_information,
        "matched_rule": analysis["matched_rule"],
        "matched_rule_name": analysis["matched_rule_name"],
        "match_type": analysis["match_type"],
        "related_rules": related_rules,
        "similar_cases": similar_cases,
        "flag_type": analysis["flag_type"],
        "hr_flag": analysis["hr_flag"],
        "reasoning": analysis["reasoning"],
        "recommended_actions": recommended,
        "workflow_steps": workflow_steps,
        "requires_hr_email": requires_hr_email,
    }
