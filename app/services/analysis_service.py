"""문의와 가상 GHD 업무 판단 기준을 연결하는 1차 분석 로직.

⚠ 이 모듈의 결과는 최종 판단이 아니라 "1차 시스템 분석(자동 규칙 기반)"이다.
   최종 판단은 이후 GHD 담당자의 Double-check에서 확정한다.

현재는 카테고리 일치 + 키워드 일치 점수 방식의 단순 규칙 기반으로 동작하며,
외부 AI API는 연결되어 있지 않다. 향후 AI API로 교체하거나 보완할 때는
analyze_inquiry()의 입력/출력 형태를 유지한 채 내부 구현만 바꾸면 된다.
"""

from app.services import rule_service

ANALYSIS_LABEL = "GHD 1차 업무 판단 (시스템 자동 분석, 최종 판단 아님)"

# 판단 기준의 처리 주체(handler) 문구를 GHD Direct / Situation Check / HR Flag 3분류로 매핑
HANDLER_TO_FLAG_TYPE = {
    "GHD 직접 처리": "GHD_DIRECT",
    "GHD 상황확인 필요": "SITUATION_CHECK",
    "고객사 HR 확인 필요": "HR_FLAG",
}

DEFAULT_CATEGORY = "기타"

# 카테고리 분류용 일반 키워드. ghd_rules.xlsx의 세부 키워드(특정 판단 기준 매칭용)와는
# 별도로, 문의 전체의 대분류(카테고리)를 정하기 위한 넓은 범위의 키워드 사전이다.
CATEGORY_KEYWORDS = {
    "증명서·세무": ["증명서", "원천징수", "연말정산", "세금", "tax", "certificate", "소득금액"],
    "급여": ["급여", "월급", "salary", "payroll", "상여금", "수당", "payslip", "명세서"],
    "휴가·병가": ["휴가", "병가", "연차", "leave", "sick", "vacation", "출산휴가", "반차"],
    "비자·체류": ["비자", "visa", "체류", "출입국", "외국인등록증", "재입국"],
    "보험": ["보험", "insurance", "산재", "국민연금", "건강보험", "4대보험"],
    "주거": ["사택", "기숙사", "dormitory", "임대", "housing", "숙소", "보증금"],
    "생활지원": ["은행", "계좌", "행정기관", "통역", "정착", "한국어 교육", "동사무소"],
    "기타": ["고충", "갈등", "동호회", "게시판"],
}


def classify_category(inquiry_text):
    """문의 전체 텍스트만 보고 8개 카테고리 중 가장 가능성이 높은 것을 고른다.
    (이미 카테고리가 정해진 기존 문의 데이터가 아니라, 새로 들어온 raw 문의처럼
    카테고리를 아직 모르는 경우에 사용)"""
    text_lower = (inquiry_text or "").lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for kw in keywords if kw.lower() in text_lower)

    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        return DEFAULT_CATEGORY
    return best_category


def _score_rule(rule, inquiry_text):
    """문의 텍스트에 판단 기준 키워드가 몇 개 포함되는지로 관련성 점수를 매긴다."""
    text_lower = (inquiry_text or "").lower()
    matched_keywords = [kw for kw in rule["keywords"] if kw.lower() in text_lower]
    return len(matched_keywords), matched_keywords


def _analyze_inquiry_rule_based(inquiry_text, category):
    """현재 구현: 카테고리 일치 + 키워드 일치 점수 기반 규칙 매칭.

    1) 문의 카테고리와 동일한 카테고리의 판단 기준만 후보로 삼는다.
    2) 각 후보 기준에 대해 키워드 일치 개수로 점수를 매긴다.
    3) 가장 점수가 높은 기준을 최종 매칭 기준으로 선택한다.
       (동점이면 기준ID가 빠른 순서, 키워드가 하나도 안 맞으면 카테고리의
       첫 번째 기준을 참고용으로 반환하고 match_type을 "category_only"로 표시)
    """
    candidates = rule_service.get_rules_by_category(category)
    if not candidates:
        return None

    scored = []
    for rule in candidates:
        score, matched_keywords = _score_rule(rule, inquiry_text)
        scored.append((score, rule, matched_keywords))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_rule, best_matched_keywords = scored[0]

    match_type = "keyword" if best_score > 0 else "category_only"

    flag_type = HANDLER_TO_FLAG_TYPE.get(best_rule["handler"], "SITUATION_CHECK")

    return {
        "analysis_type": ANALYSIS_LABEL,
        "category": category,
        "matched_rule": best_rule["rule_id"],
        "matched_rule_name": best_rule["rule_name"],
        "match_type": match_type,
        "matched_keywords": best_matched_keywords,
        "flag_type": flag_type,
        "hr_flag": best_rule["hr_flag"],
        "urgency": best_rule["urgency"],
        "is_urgent": best_rule["urgency"] == "HIGH",
        "reasoning": best_rule["reasoning"],
        "handler": best_rule["handler"],
    }


def analyze_inquiry(inquiry_text, category):
    """문의 1건에 대한 1차 시스템 분석 결과를 반환한다.

    현재는 규칙 기반(_analyze_inquiry_rule_based)으로 동작하지만, 이 함수의
    입력(inquiry_text, category)과 출력 딕셔너리 구조는 향후 외부 AI API로
    교체·보완하더라도 그대로 유지하는 것을 전제로 한다.
    """
    return _analyze_inquiry_rule_based(inquiry_text, category)


def get_related_rules(category, inquiry_text, limit=3):
    """문의와 관련된 판단 기준을 점수순으로 여러 개(기본 최대 3개) 반환한다.
    (analyze_inquiry가 "가장 관련성 높은 1건"만 골랐다면, 이 함수는 화면에
    "관련 규정/판단 기준" 목록으로 보여줄 후보들을 반환한다.)

    카테고리에 판단 기준이 아예 없으면 빈 리스트를 반환한다 — 화면에서는
    "관련 규정이 없습니다"로 처리해야 한다.
    """
    candidates = rule_service.get_rules_by_category(category)
    if not candidates:
        return []

    scored = []
    for rule in candidates:
        score, matched_keywords = _score_rule(rule, inquiry_text)
        scored.append((score, rule, matched_keywords))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, rule, matched_keywords in scored[:limit]:
        results.append(
            {
                "rule_id": rule["rule_id"],
                "rule_name": rule["rule_name"],
                "situation": rule["situation"],
                "keywords": rule["keywords"],
                "hr_flag": rule["hr_flag"],
                "urgency": rule["urgency"],
                "reasoning": rule["reasoning"],
                "note": rule["note"],
                "handler": rule["handler"],
                "flag_type": HANDLER_TO_FLAG_TYPE.get(rule["handler"], "SITUATION_CHECK"),
                "match_score": score,
                "matched_keywords": matched_keywords,
                "is_primary_match": score > 0,
            }
        )
    return results
