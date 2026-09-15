# E-Care GHD 업무지원 시스템

외국인 임직원의 문의를 AI가 1차 분석하여 처리 유형을 분류하고,
필요 시 HR 전달용 요약문을 생성하며, 최종 판단은 GHD 담당자가 Double-check하는
업무지원 시스템입니다.

프로젝트 경로: `C:\Users\ETNERS\Desktop\ETNS_VIBE\EFlag`

## 현재 단계 (STEP 12 완료 — Supabase 연결)

**STEP 10 — GHD 업무 현황판 (Dashboard)**
- `/dashboard`: KPI 6종(전체 문의/미처리 문의/HR 확인 대기/HR 회신 대기/긴급 문의/오늘 처리 완료)을
  매 요청마다 실제 데이터에서 다시 계산합니다 (하드코딩 없음).
- 우선 처리 필요: 긴급 문의 → HR 회신 대기 → HR 확인 요청 → 추가 서류 요청 → 신규 문의 순으로
  정렬된 목록, 클릭 시 Inquiry Detail로 이동.
- 최근 문의 테이블도 함께 제공하며, 기존 CSS(section-card/badge/inquiry-table 등)를 그대로 재사용했습니다.

**STEP 11 — 전체 UX/Demo Flow 검증**
- "해외 발급 진단서 병가 증빙" 대표 문의로 문의→분석→관련규정→유사사례→Flag→Action Step→
  HR 이메일→Double-check→(발송)→HR 회신→최종 안내→처리 결과→완료→Timeline 전체를 실행하고,
  Dashboard KPI가 실행 전/후로 정확히 변한다는 것까지 확인했습니다 (미처리 -1, 오늘 처리 완료 +1 등).

**STEP 12 — Supabase 연결**
- 기존 저장 방식: 마스터 데이터(직원/문의/판단기준)는 엑셀 3종, 처리 상태(Step 완료/이메일/HR
  회신/최종안내/처리결과)는 JSON 파일 1개. DB·ORM은 없었습니다.
- `app/services/supabase_client.py`가 모듈 스코프에서 클라이언트를 1회만 생성하고(콜드스타트/커넥션
  재사용 관점), `.env`에 `SUPABASE_URL`/`SUPABASE_KEY`가 없으면 `None`을 반환합니다.
- `employee_service.py` / `inquiry_service.py` / `rule_service.py` / `workflow_service.py` 모두
  **듀얼 모드**로 바뀌었습니다: Supabase가 설정되어 있으면 그쪽에서 읽고 쓰고, 아니면 기존 엑셀/JSON을
  그대로 사용합니다 — 로컬 개발 환경은 STEP 1~11과 동일하게 동작합니다.
- `supabase/schema.sql`: employees / inquiries / rules / action_steps / hr_communications /
  hr_replies / processing_results 7개 테이블 (요청하신 목록 중 analyses·timelines는 항상 다른
  테이블에서 즉시 계산 가능한 파생 데이터라 별도 테이블을 만들지 않고 기존처럼 애플리케이션에서
  계산합니다 — 불필요한 중복 테이블 방지).
- `scripts/migrate_to_supabase.py`: 로컬 Demo 데이터를 Supabase로 1회 이전하는 스크립트 (여러 번
  실행해도 안전한 upsert 방식).
- `supabase-py`(PostgREST/HTTPS 기반)를 선택한 이유: 서버리스(Vercel) 환경에서 직접 Postgres
  커넥션을 오래 붙잡지 않아, 커넥션 풀 고갈 문제를 원천적으로 피할 수 있습니다.
- 실제 Supabase 프로젝트(`E-Care`)에 연결하고 `scripts/migrate_to_supabase.py`로 직원 30명·문의
  120건·판단기준 24건을 이전, 전체 라우트(13종) 재검증 + 대표 문의 1건으로 HR 회신→최종 안내→
  처리 결과 전체 흐름을 실행해 Dashboard KPI가 정확히 변하는 것까지 확인했습니다. 검증 후 테스트로
  넣은 진행 상태는 정리해 Demo 데이터를 초기 상태로 되돌렸습니다.

### STEP 7~9 상세 (Inquiry Detail 전체 처리 흐름)

문의 상세 화면의 전체 처리 흐름이 접수부터 완료까지 끝까지 이어집니다.

```
문의 -> AI 문의 구조화 -> 관련 규정/판단 기준 -> 유사 사례 -> Flag
     -> 추천 업무 절차(Step) -> HR 이메일 작성 -> Double-check -> 이메일 전송
     -> HR 회신 등록 -> 최종 안내 확정 -> 처리 결과 등록 -> 완료 -> Timeline
```

**STEP 7 — 관련 규정 / 유사 사례**
- 관련 규정: 같은 카테고리의 판단 기준을 키워드 일치 점수순으로 최대 3개까지 보여주고,
  각각 규정명/적용 상황/주요 키워드/HR 확인 필요 여부/긴급도/판단 근거/참고사항을 표시합니다.
- 유사 사례: 같은 카테고리의 다른 Demo 문의 중 텍스트가 비슷한 것을 최대 3건까지 찾아
  문의ID/유형/핵심 문의/당시 Flag/당시 Action/처리 결과를 보여줍니다.
- 관련 규정·유사 사례가 없을 때도 화면이 깨지지 않고 "없습니다" 안내가 표시됩니다.

**STEP 8 — 업무 절차(Step) + HR 이메일 발송**
- Action 추천을 담당자가 실제로 밟을 세부 Step(번호/이름/할 일/완료 체크/관련 자료)으로 확장했습니다.
- 긴급도 HIGH면 "긴급 에스컬레이션"이 항상 Step 1이 됩니다.
- HR 확인이 필요한 문의는 "HR 확인 요청" Step에서 이메일 초안(제목/본문 자동 생성)이 이어지고,
  Double-check 7개 항목을 모두 확인해야 "이메일 전송" 버튼이 활성화됩니다 (서버에서도 재검증).
- 실제 발송은 Gmail SMTP(`mail_service.py`, STEP5-2에서 만든 `260915_mailsender` 스킬 기반)를
  그대로 사용하며, 성공/실패 모두 화면에 안내하고 앱이 죽지 않습니다.

**STEP 9 — HR 회신 → 최종 안내 → 처리 완료 → Timeline**
- 이메일 전송에 성공한 문의는 **HR 회신 등록**(회신 일시/회신자/회신 내용/추가 요청사항)이 가능합니다.
- HR 회신이 등록되면 **최종 안내** 작성이 열립니다. AI는 HR 회신 내용을 옮긴 초안만 제안하고,
  GHD 담당자가 검토·수정 후 확정해야 저장됩니다 (AI가 최종 답변을 자동 확정하지 않음).
- 모든 문의는 **처리 결과**(6종 중 선택 + 메모)를 등록할 수 있으며, 등록 즉시 상태가
  "처리 완료"로 바뀝니다.
- **Timeline**이 문의 접수부터 완료까지 전체 과정을 시간순으로 보여줍니다.
- 문의 상태는 `GHD 직접 처리 / HR 확인 요청 / 추가 서류 요청 / HR 회신 대기 / 처리 완료`
  중 하나로 계산되어 Flag 섹션에 표시됩니다 (분석이 즉시 자동 실행되는 구조라 "신규 문의"/
  "분석 완료"는 순간적으로만 존재해 실제로는 관측되지 않습니다).
- STEP 1~8 기능은 그대로 유지했고, 이메일 전송 기능을 새로 만들지 않고 STEP 8의 것을
  그대로 재사용했습니다.

새로운 AI 모델 학습 없이, 기존 Demo 데이터와 가상 GHD 업무 판단 기준만으로 구현했습니다.

직원·문의·판단 기준 데이터 모두 현업에서 바로 열람·편집할 수 있도록 **엑셀(.xlsx) 파일**로 관리합니다.
Dashboard, 문의 전체 목록의 정식 GHD 처리 화면은 아직 포함되어 있지 않습니다.

> ⚠ 모든 직원·문의·판단 기준 데이터는 프로젝트 시연/테스트를 위한 **가상 데이터**입니다.
> 실제 ETNERS 또는 고객사의 임직원·문의 정보, 공식 규정이 아닙니다.
> "가상 GHD 업무 판단 기준"은 어디까지나 프로젝트용으로 만든 예시 기준이며,
> 실제 내부 규정을 제공받아 작성한 것이 아닙니다.

## 프로젝트 구조

```
EFlag/
├── app/
│   ├── __init__.py         # Flask 앱 팩토리 (create_app)
│   ├── routes.py           # 라우트 (Blueprint)
│   ├── services/
│   │   ├── employee_service.py  # 직원 데이터 로딩 계층 (엑셀 → dict, 추후 DB 전환 대비)
│   │   ├── inquiry_service.py   # 문의 데이터 로딩 계층 (엑셀 → dict, 추후 규정/AI 연결 대비)
│   │   ├── rule_service.py      # 가상 GHD 업무 판단 기준 로딩 계층 (엑셀 → dict)
│   │   ├── analysis_service.py  # 문의×판단기준 1차 시스템 분석 로직 (규칙 기반, 향후 AI로 교체/보완 가능)
│   │   ├── structuring_service.py       # 문의 구조화 + 업무 절차(Step) + HR 이메일 초안 생성
│   │   ├── mail_service.py      # Gmail SMTP 이메일 발송 (260915_mailsender 스킬 기반)
│   │   └── workflow_service.py  # Step 완료/이메일 발송/HR 회신/최종 안내/처리 결과/Timeline 상태 저장소
│   ├── templates/
│   │   ├── index.html          # 홈페이지 템플릿
│   │   ├── inquiries_view.html # 문의 목록 화면
│   │   ├── inquiry_detail.html # Inquiry Detail 화면 (전체 처리 흐름 UI)
│   │   └── not_found.html      # 존재하지 않는 ID 접근 시 안내 화면
│   └── static/
│       ├── css/style.css  # 스타일시트
│       └── js/main.js     # Double-check 체크박스로 전송 버튼 활성화하는 스크립트
├── data/
│   ├── employees.xlsx      # 가상 직원 데이터 30명 (엑셀, 현업 편집 가능)
│   ├── inquiries.xlsx      # 가상 문의 데이터 120건 (엑셀, 현업 편집 가능)
│   ├── ghd_rules.xlsx      # 가상 GHD 업무 판단 기준 24건 (엑셀, 현업 편집 가능)
│   └── hr_workflow_state.json  # 문의별 처리 진행 상태 (앱이 자동 생성/갱신하는 상태 저장소)
├── .env                    # 실제 비밀값 (Git 추적 제외, 직접 만들어야 함)
├── .env.example            # .env 작성용 템플릿 (커밋 대상)
├── run.py                  # 실행 진입점
├── requirements.txt         # 의존성 목록
└── README.md
```

### 이메일 발송 (`app/services/mail_service.py`)

Gmail SMTP(`smtplib.SMTP_SSL`)로 이메일을 보내는 재사용 모듈입니다. GHD 담당자가
각 고객사별 HR 담당자에게 연락할 때 쓸 목적으로 만들었으며, 자세한 사용 원칙은
`260915_mailsender` 스킬(`C:\Users\ETNERS\Desktop\ETNS_VIBE\.claude\skills\260915_mailsender\SKILL.md`)에
정리되어 있습니다.

- 발신 계정/앱 비밀번호는 `.env`의 `GMAIL_SENDER_EMAIL` / `GMAIL_APP_PASSWORD`에서만 읽습니다 (코드에 하드코딩 없음).
- `send_email(to_email, subject, body)` — 단건 발송, 성공 여부와 에러 메시지를 반환합니다.
- STEP 8부터 `/inquiries/<id>/send-hr-email` 라우트가 이 함수를 그대로 호출합니다 (Double-check
  통과 시에만). 실제 고객사 HR 담당자 이메일 데이터는 아직 없어 수신자는 Demo 주소
  (`hr-demo@example.com`, RFC 2606 예약 도메인)를 기본값으로 쓰고, 화면에서 직접 수정할 수 있습니다.
- ⚠ 이번에 전달받은 앱 비밀번호는 대화창에 그대로 포함되어 있었으므로, 보안을 위해
  [Google 계정 앱 비밀번호 관리](https://myaccount.google.com/apppasswords)에서 재발급(기존 값 폐기)하시는 것을 권장드립니다.

### 직원 데이터 구조 (`data/employees.xlsx` · 시트명 "직원명단")

엑셀을 직접 열어 확인·편집할 수 있으며, 1행은 안내 문구, 3행이 헤더, 4행부터 데이터입니다.

| 컬럼(한글) | 내부 필드명 | 설명 |
|---|---|---|
| 사번 | employee_id | 직원 고유 ID (EMP001~EMP030) |
| 이름 | name | 이름 (가상) |
| 국적 | nationality | 국적 (13개국 분포) |
| 파견 고객사 | client_company | 파견 고객사명 (가상, 10개사) |
| 직무 | position | 직무 (10종) |
| 근무 시작일 | start_date | 근무 시작일 |
| 근무기간 | employment_period | 계약/근무 기간 |
| 가족동반 여부 | family_accompanied | 예 / 아니오 |
| 비자유형 | visa_type | E-9, E-7, D-8, D-10, F-2, F-4, H-2 |

`app/services/employee_service.py`가 이 엑셀 파일을 읽어 Flask에서 사용할 수 있는
데이터로 변환하는 역할을 담당합니다. 추후 DB로 전환할 때 이 파일 내부만 교체하면
라우트 등 다른 코드는 그대로 유지됩니다.

### 문의 데이터 구조 (`data/inquiries.xlsx` · 시트명 "문의내역")

1행 안내 문구, 3행 헤더, 4행부터 데이터 (총 120건).

| 컬럼(한글) | 내부 필드명 | 설명 |
|---|---|---|
| 문의ID | inquiry_id | 문의 고유 ID (INQ0001~INQ0120, 문의일자 순) |
| 사번 | employee_id | 문의한 직원의 사번 (employees.xlsx와 연결) |
| 문의일자 | inquiry_date | 문의 발생일 |
| 문의내용 | inquiry_text | 문의 원문 (한국어/영어 혼재) |
| 언어 | language | ko / en / mixed |
| 카테고리 | category | 증명서·세무, 급여, 휴가·병가, 비자·체류, 보험, 주거, 생활지원, 기타 (8종) |
| Flag | flag | GHD_DIRECT / SITUATION_CHECK / HR_FLAG (임시값, 최종 판단 로직은 이후 단계에서 구현) |
| 긴급도 | urgency | LOW / MEDIUM / HIGH |
| 상태 | status | 완료 / 처리중 / 보류 |
| 최종결과 | final_result | 처리 결과 요약 |

`inquiry_id`는 `employee_id`로 직원 데이터와 연결되며, 향후 규정 데이터(예: `regulation_id`)나
AI 분석 결과 컬럼을 추가할 때도 행 단위 구조를 그대로 유지한 채 확장할 수 있습니다.
`app/services/inquiry_service.py`가 이 엑셀 파일을 읽어 Flask에 데이터를 공급합니다.

### 가상 GHD 업무 판단 기준 구조 (`data/ghd_rules.xlsx` · 시트명 "가상GHD판단기준")

1행 안내 문구, 3행 헤더, 4행부터 데이터 (총 24건, 8개 카테고리 × 3건).
**실제 ETNERS/고객사의 공식 규정이 아닌, 프로젝트 시연용 가상 판단 기준**입니다.

| 컬럼(한글) | 내부 필드명 | 설명 |
|---|---|---|
| 기준ID | rule_id | 판단 기준 고유 ID (R001~R024) |
| 카테고리 | category | 증명서·세무, 급여, 휴가·병가, 비자·체류, 보험, 주거, 생활지원, 기타 (8종, 각 3건) |
| 판단 기준명 | rule_name | 판단 기준 제목 |
| 관련 상황 | situation | 어떤 상황에서 이 기준이 적용되는지 |
| 관련 키워드 | keywords | 문의 매칭용 키워드 (한/영 혼재, 쉼표 구분) |
| 처리 주체 | handler | "GHD 직접 처리" / "GHD 상황확인 필요" / "고객사 HR 확인 필요" (GHD Direct·Situation Check·HR Flag 3분류에 대응) |
| HR Flag | hr_flag | TRUE / FALSE — 고객사 HR 확인이 필요한 사안인지 |
| 긴급도 | urgency | LOW / MEDIUM / HIGH |
| 판단 근거 | reasoning | 왜 이렇게 분류하는지에 대한 근거 |
| 비고 | note | 추가 참고사항 |

`inquiry_service.py`가 반환하는 `category` 값과 `rule_service.py`가 반환하는 `category` 값이
동일한 8종 카테고리 문자열을 사용하므로, 문의 데이터와 판단 기준 데이터는 **카테고리 기준으로
바로 연결**할 수 있습니다. `keywords`는 리스트로 파싱되어 제공되어, 향후 AI 분석 단계에서
문의 텍스트와 키워드를 대조해 관련 판단 기준을 검색하는 용도로 바로 활용할 수 있는 구조입니다.
`app/services/rule_service.py`가 이 엑셀 파일을 읽어 Flask에 데이터를 공급합니다.

### 1차 시스템 분석 로직 (`app/services/analysis_service.py`)

⚠ **이 분석 결과는 최종 판단이 아닙니다.** UI에도 항상 "GHD 1차 업무 판단
(시스템 자동 분석, 최종 판단 아님)"으로 표기하며, 최종 판단은 GHD 담당자의
Double-check에서 확정합니다.

처리 흐름:

```
문의 입력 (inquiry_text, category)
   ↓
카테고리와 동일한 가상 GHD 업무 판단 기준 후보 조회 (rule_service.get_rules_by_category)
   ↓
후보별 키워드 일치 개수로 점수화 (문의 텍스트에 rule.keywords가 포함되는지 단순 대조)
   ↓
가장 점수가 높은 기준을 매칭 결과로 선택
   (전부 0점이면 해당 카테고리의 첫 기준을 참고용으로 반환, match_type="category_only")
   ↓
매칭 기준의 handler → GHD_DIRECT / SITUATION_CHECK / HR_FLAG 로 변환하고
hr_flag / urgency / reasoning 함께 반환
```

`analyze_inquiry(inquiry_text, category)` 함수의 반환값:

| 필드 | 설명 |
|---|---|
| analysis_type | "GHD 1차 업무 판단 (시스템 자동 분석, 최종 판단 아님)" 고정 문구 |
| category | 입력받은 문의 카테고리 |
| matched_rule / matched_rule_name | 매칭된 판단 기준 ID / 이름 |
| match_type | "keyword"(키워드로 매칭) / "category_only"(키워드 불일치, 카테고리로만 매칭) |
| matched_keywords | 실제로 일치한 키워드 목록 |
| flag_type | GHD_DIRECT / SITUATION_CHECK / HR_FLAG |
| hr_flag | TRUE/FALSE |
| urgency | LOW / MEDIUM / HIGH |
| is_urgent | urgency가 HIGH인지 여부 (별도 식별용) |
| reasoning | 판단 근거 |
| handler | 처리 주체 원문 |

머신러닝 모델이나 외부 AI API는 사용하지 않았으며, `analyze_inquiry()`의 입력·출력
구조를 유지한 채 내부 구현(`_analyze_inquiry_rule_based`)만 교체하면 이후 AI API로
대체하거나 보완할 수 있도록 분리했습니다.

**알려진 한계:** 키워드 일치는 단순 부분 문자열 대조라서, 문의 문장에 조사가 섞여
키워드가 정확히 이어지지 않으면(예: "해외에서 발급받은 진단서도 인정되나요?"는
"진단서 인정"이라는 키워드와 정확히 이어지지 않음) 매칭에 실패하고 카테고리 기본값으로
대체될 수 있습니다. 이런 경우도 있다는 것을 인지하고, 추후 AI 분석 단계에서 개선할
부분입니다.

### 문의 구조화 + 관련 규정 + 유사 사례 + 다음 Action 제안 (`app/services/structuring_service.py`)

⚠ 이 결과도 최종 판단이 아닌 **"1차 분석 / 업무지원 제안"**입니다. AI는 관련 정보를
찾아 업무 판단을 보조할 뿐, 최종 판단은 GHD 담당자가 합니다.

처리 흐름:

```
문의 원문
   ↓
문의 내용 구조화 (문의 유형 / 관련 날짜 / 필요 서류 / 긴급도 / 핵심 내용 / 추가 확인사항)
   ↓
관련 규정 / 판단 기준 확인 (analysis_service.get_related_rules, 최대 3개)
   ↓
유사 사례 확인 (find_similar_cases, 같은 카테고리의 Demo 문의 중 텍스트 유사도 상위 최대 3건)
   ↓
Flag 정리 (GHD_DIRECT / SITUATION_CHECK / HR_FLAG, HR 확인 필요 여부)
   ↓
GHD 다음 액션 제안 (recommend_actions)
```

**관련 규정 (`related_rules`)**: 문의 카테고리와 같은 카테고리의 판단 기준을 키워드
일치 점수순으로 최대 3개까지 반환합니다 (`analysis_service.get_related_rules`). 각
항목에 규정명(`rule_name`)·적용 상황(`situation`)·주요 키워드(`keywords`)·HR 확인
필요 여부(`hr_flag`)·긴급도(`urgency`)·판단 근거(`reasoning`)·참고사항(`note`)이
모두 담겨 있습니다. 카테고리에 판단 기준이 전혀 없으면 빈 리스트를 반환하고, 화면은
"관련 규정이 없습니다"로 표시합니다.

**알려진 한계**: 문의 텍스트에 정확한 키워드 문구가 없어 여러 판단 기준이 0점으로
동점일 경우, "가장 관련성 높음"으로 표시되는 1건은 카테고리 내 첫 번째 기준으로
정해집니다. 이 경우에도 나머지 후보 기준들은 관련 규정 목록에 함께 표시되므로,
더 적합한 기준이 목록 안에 있는지 GHD 담당자가 확인할 수 있습니다.

**유사 사례 (`similar_cases`)**: 새 AI 모델을 학습시키지 않고, 문자 2-gram(2글자
단위) 겹침 개수로 문장 유사도를 계산하는 가장 단순한 방식을 사용합니다
(`structuring_service._text_similarity_score`). 한국어는 조사가 어간에 바로 붙어
("진단서의"/"진단서도") 단어 단위 비교가 잘 안 맞기 때문에, 2글자 단위로 잘라
비교해 같은 어간이 겹치면 잡아내도록 했습니다. 같은 카테고리 안에서만 후보를 찾고,
일정 점수(`SIMILAR_CASE_MIN_SCORE = 3`) 이상인 것만 최대 3건까지 반환하며, 현재
보고 있는 문의 자기 자신은 제외합니다(`exclude_inquiry_id`). 하나도 없으면 빈
리스트를 반환하고, 화면은 "유사 사례가 없습니다"로 표시합니다. 각 사례는 실제
ETNERS 사례가 아닌 **Demo 데이터**임을 화면에 항상 표시합니다. "당시 Action"은
실제 발생 이력이 아니라, 그 사례 당시의 flag·긴급도에 지금과 동일한
`recommend_actions()` 규칙을 적용한 참고용 값입니다.

**Flag(관리 수준)와 Action(다음 할 일)은 서로 다른 개념으로 분리**했습니다.

| 구분 | 값 | 의미 |
|---|---|---|
| Flag | GHD_DIRECT / SITUATION_CHECK / HR_FLAG | 이 문의를 어떤 수준으로 관리해야 하는가 |
| Action | ACTION_1 직접 안내 / ACTION_2 추가 서류 요청 / ACTION_3 HR 확인 / ACTION_4 긴급 에스컬레이션 | GHD 담당자가 다음에 무엇을 해야 하는가 (복수 제안 가능) |

`structure_inquiry(inquiry_text, category=None, employee=None)`가 반환하는 값에는 요청하신
`extracted_type / extracted_date / required_documents / urgency / key_issue /
additional_information / recommended_actions`가 모두 포함되며, `category`를 생략하면
(아직 분류되지 않은 새 문의) `classify_category()`가 8개 카테고리 중 하나를 먼저 추정합니다.

`recommended_actions`는 STEP 8에서 `workflow_steps`(담당자가 실제로 밟는 세부 Step)로
확장되었고, Step 완료 여부·이메일 발송 이력·HR 회신·최종 안내·처리 결과는 문의 마스터
엑셀을 매번 다시 쓰지 않도록 별도의 `data/hr_workflow_state.json`(`workflow_service.py`)에
저장합니다.

### 업무 절차(Step) 확장 + HR 처리 흐름 (`app/services/workflow_service.py`)

`structure_inquiry()`가 반환하는 `workflow_steps`는 Action 코드(ACTION_1~4) 1개를
담당자가 실제로 밟는 세부 Step 여러 개로 펼친 것입니다 (`STEP_TEMPLATES`,
`structuring_service.py`). 각 Step은 `step`(번호) / `label`(Action 이름) /
`task`(담당자가 해야 할 일) / `related_materials`(관련 자료) / `requires_hr_email`
(이 Step이 HR 이메일 작성과 연결되는지)을 가지며, 완료 여부는
`workflow_service.save_completed_steps()`로 저장합니다.

| Action | 펼쳐지는 Step |
|---|---|
| 긴급 에스컬레이션 | (1개) 긴급 에스컬레이션 |
| 추가 서류 요청 | 추가 서류 요청 → 제출 서류 확인 |
| HR 확인 | HR 확인 → **HR 확인 요청**(이메일 연결) → 회신 확인 → 임직원 안내 |
| 직접 안내 | (1개) 직접 안내 |

`build_hr_email_draft(inquiry, employee, structured)`가 요청하신 고정 서식(제목
`[확인 요청] {카테고리} 관련 확인 부탁드립니다 - {임직원명}`, 본문 1~4번 구조)으로
이메일 초안을 만들고, `/inquiries/<id>/send-hr-email`에서 Double-check 7항목이
모두 체크된 경우에만 `mail_service.send_email()`을 호출합니다. 발송 성공/실패
모두 `workflow_service.record_email_attempt()`가 기록하며, 성공 시 "HR 확인 요청"
Step이 자동으로 완료 처리됩니다.

이후 문의 상태는 `workflow_service.get_workflow_status()`가 계산합니다:

```
처리 결과 등록됨            -> 처리 완료
HR 확인 필요 + 이메일 발송됨 -> HR 회신 대기
HR 확인 필요 + 이메일 미발송 -> HR 확인 요청
서류 필요 + 미확인          -> 추가 서류 요청
그 외                       -> GHD 직접 처리
```

HR 회신 등록(`register-hr-reply`) → 최종 안내 확정(`confirm-final-guidance`) →
처리 결과 등록(`register-resolution`) 순서로 이어지며, 각 단계는 이전 단계가 있어야만
화면에 나타납니다 (이메일 미발송 시 HR 회신 등록 불가, HR 회신 없이 최종 안내 불가).
최종 안내의 초안은 HR 회신 내용을 그대로 옮긴 문장(`"HR 확인 결과, {회신내용}"`)이며,
GHD 담당자가 검토·수정 후 확정해야 저장됩니다 — **AI는 초안만 제안하고 최종 확정은
항상 사람이 합니다.**

`workflow_service.build_timeline()`이 문의 접수부터 완료까지 전 과정을 시간순으로
정리합니다. 자동으로 즉시 처리되는 항목(AI 분석, 관련 기준 확인, 유사 사례 확인, HR
Flag, Action Step, HR 이메일 작성, Double-check)은 실제 저장된 시각이 없어 시각 없이
표시되고, 실제 이력이 남는 항목(이메일 전송, HR 회신, 최종 안내, 처리 결과 등록,
완료)만 저장된 시각과 함께 표시됩니다.

### Inquiry Detail 화면 (UI)

`/inquiries/<inquiry_id>/detail`에서 아래 순서로 확인할 수 있습니다:

1. **문의 내용** — 원문, 문의자, 기존 기록
2. **AI 문의 구조화** — 문의 유형/관련 날짜/필요 서류/긴급도/핵심 내용/추가 확인사항
3. **관련 규정 / 판단 기준** — 최대 3개 (없으면 "관련 규정이 없습니다")
4. **유사 사례** — Demo 데이터 최대 3건 (없으면 "유사 사례가 없습니다")
5. **Flag** — 관리 수준 + HR 확인 필요 여부 + 현재 처리 상태 배지
6. **추천 업무 절차** — Step 1, Step 2... 순서 + 완료 체크박스 (진행 상황 저장)
7. **HR 커뮤니케이션** — 이메일 제목/본문(자동 초안, 수정 가능) + Double-check 7항목 + 이메일 전송
   (HR 확인이 필요 없는 문의는 "필요하지 않습니다" 안내로 대체)
8. **HR 회신 등록** — 이메일 전송 성공 후에만 표시 (회신 일시/회신자/내용/추가 요청사항)
9. **최종 안내** — HR 회신 등록 후에만 표시, AI가 초안 제안 + GHD 담당자 확정
10. **처리 결과** — 6종 중 선택 + 메모, 등록 즉시 "처리 완료"로 전환
11. **Timeline** — 문의 접수부터 완료까지 전체 과정을 시간순으로 표시

모든 AI/시스템 결과 영역에는 "1차 분석 / 업무지원 제안 (최종 판단 아님)" 문구를 표시했습니다.
`/inquiries-view`에서 전체 문의 목록을 보고 각 문의로 이동할 수 있습니다.

### 데이터 확인용 테스트 라우트

- `GET /employees` — 전체 직원 목록 + 개수 (JSON)
- `GET /employees/<employee_id>` — 단일 직원 조회 (JSON, 없으면 404)
- `GET /inquiries` — 전체 문의 목록 + 개수 (JSON)
- `GET /inquiries/<inquiry_id>` — 단일 문의 조회 (JSON, 없으면 404)
- `GET /employees/<employee_id>/inquiries` — 특정 직원의 문의 목록 (JSON)
- `GET /ghd-rules` — 전체 가상 GHD 업무 판단 기준 목록 + 개수 (JSON)
- `GET /ghd-rules/<rule_id>` — 단일 판단 기준 조회 (JSON, 없으면 404)
- `GET /inquiries/<inquiry_id>/analysis` — 문의 1건의 1차 시스템 분석 결과 (JSON, 없으면 404)
- `GET /structure-test?text=...` — 카테고리 없는 새 문의(raw text)의 구조화 결과 테스트 (JSON)
- `GET /inquiries-view` — 문의 목록 화면 (HTML)
- `GET /inquiries/<inquiry_id>/detail` — Inquiry Detail 화면 (HTML)
- `POST /inquiries/<inquiry_id>/update-steps` — 업무 절차 Step 완료 체크 저장
- `POST /inquiries/<inquiry_id>/send-hr-email` — Double-check 통과 시 HR 이메일 실제 발송
- `POST /inquiries/<inquiry_id>/register-hr-reply` — HR 회신 등록
- `POST /inquiries/<inquiry_id>/confirm-final-guidance` — 최종 안내 확정
- `POST /inquiries/<inquiry_id>/register-resolution` — 처리 결과 등록 (완료 처리)

## 실행 방법

1. 의존성 설치

```bash
cd C:\Users\ETNERS\Desktop\ETNS_VIBE\EFlag
pip install -r requirements.txt
```

2. 서버 실행

```bash
python run.py
```

3. 브라우저에서 접속

```
http://127.0.0.1:5050
```

> 기본 Flask 포트(5000)는 다른 프로그램과 충돌할 수 있어 5050번 포트로 설정했습니다.
> 필요 시 `run.py`의 `port=5050` 값을 변경하면 됩니다.

정상 실행 시 홈페이지에 "E-Care" 프로젝트명이 표시됩니다.
