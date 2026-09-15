# E-Care 프로젝트 인수인계 문서

> 이 문서는 다른 AI 에이전트/세션에서 이 프로젝트 작업을 이어갈 수 있도록
> 지금까지의 전체 맥락을 정리한 것입니다. 최신 상태 기준(작성 시각: 진행 중)이며,
> 실제 코드/배포 상태가 우선합니다 — 이 문서와 다르면 코드를 신뢰하세요.

## 프로젝트 개요

**E-Care**는 GHD(Global HR Desk)의 외국인 임직원 문의 대응 업무를 지원하는
Flask 기반 Demo/MVP 웹 애플리케이션입니다.

- **목적**: 외국인 임직원 문의를 AI가 1차 분석(구조화/관련 규정/유사 사례/Flag
  판단)하고, 담당자가 실제로 밟을 업무 절차(Step)를 안내하며, 필요 시 고객사 HR에게
  확인 이메일을 보내고, HR 회신 → 최종 안내 → 처리 결과 등록 → 완료까지 전체
  흐름을 지원. 최종 판단은 항상 GHD 담당자가 한다 (AI는 보조).
- **로컬 경로**: `C:\Users\ETNERS\Desktop\ETNS_VIBE\EFlag`
- **⚠ 모든 직원/문의/판단 기준 데이터는 프로젝트 시연용 가상 데이터**이며 실제
  ETNERS 또는 고객사 정보가 아닙니다.

## 기술 스택

| 구성 | 선택 |
|---|---|
| 백엔드 | Flask (Python), Jinja2 템플릿 |
| DB | Supabase (Postgres) — `supabase-py`(PostgREST/HTTPS) 사용. `.env`에 `SUPABASE_URL`/`SUPABASE_KEY` 없으면 로컬 엑셀/JSON으로 자동 폴백하는 듀얼 모드 |
| 이메일 | Gmail SMTP (`smtplib`), `260915_mailsender` 스킬 기반 |
| 배포 | Vercel (서버리스, `@vercel/python`) |
| 버전관리 | GitHub — https://github.com/nadia0418-web/E-Care (private) |

## 지금까지 완료한 단계 (STEP 1~14)

각 STEP은 이전 단계를 깨뜨리지 않고 누적 확장되었습니다.

- **STEP 1**: Flask 기본 프로젝트 구조, 홈페이지
- **STEP 2**: 가상 직원 데이터 30명 (`data/employees.xlsx`)
- **STEP 3**: 가상 문의 데이터 120건 (`data/inquiries.xlsx`)
- **STEP 4**: 가상 GHD 업무 판단 기준 24건 (`data/ghd_rules.xlsx`) — R001~R024, 8개 카테고리 × 3건
- **STEP 5**: 문의×판단기준 1차 분석 로직 (`analysis_service.py`) — 카테고리+키워드 점수 매칭, 규칙 기반 (ML 미사용)
- **STEP 6**: 문의 구조화 + 다음 Action 추천 (`structuring_service.py`)
- **STEP 7**: 관련 규정(복수) + 유사 사례(Demo 데이터) 연결
- **STEP 8**: Action → 담당자 실제 업무 Step으로 확장 + HR 이메일 초안 생성 + Double-check 게이팅 + 실제 발송(`mail_service.py`)
- **STEP 9**: HR 회신 등록 → 최종 안내 확정 → 처리 결과 등록 → 완료 → Timeline (`workflow_service.py`)
- **STEP 10**: GHD 업무 현황판 Dashboard (`dashboard_service.py`, `/dashboard`) — KPI 6종, 우선순위 목록, 최근 문의
- **STEP 11**: 전체 UX/Demo Flow 검증 (대표 문의로 전체 파이프라인 + Dashboard 반영 확인)
- **STEP 12**: Supabase 연결 — 스키마(`supabase/schema.sql`), 듀얼 모드 서비스, 마이그레이션 스크립트(`scripts/migrate_to_supabase.py`), 실제 데이터 이전 완료 (직원 30/문의 120/규정 24건)
- **STEP 13**: GitHub 저장소 생성 + Vercel 배포 (진행 중 — 아래 "현재 이슈" 참고)
- **STEP 14**: 배포 후 최종 검증 (진행 중)

## 핵심 아키텍처 결정 사항

1. **듀얼 모드 데이터 계층**: `employee_service.py` / `inquiry_service.py` /
   `rule_service.py` / `workflow_service.py` 모두 `supabase_client.get_client()`가
   `None`이 아니면 Supabase, `None`이면 로컬 엑셀/JSON을 쓴다. 로컬 개발은 Supabase
   없이도 그대로 동작.
2. **`supabase_client.py`**: 모듈 스코프에서 클라이언트를 1회만 생성(서버리스 콜드
   스타트/커넥션 재사용 고려). `supabase-py`(PostgREST)를 선택해 서버리스 환경에서
   직접 Postgres 커넥션을 오래 쥐지 않도록 함 (커넥션 풀 고갈 회피).
3. **워크플로우 상태 테이블 7개** (`supabase/schema.sql`): `employees`, `inquiries`,
   `rules`, `action_steps`, `hr_communications`, `hr_replies`, `processing_results`.
   `analyses`/`timelines`는 항상 다른 테이블에서 즉시 계산 가능한 파생 데이터라 별도
   테이블을 만들지 않고 애플리케이션에서 계산 (`workflow_service.build_timeline()`,
   `workflow_service.get_workflow_status()`).
4. **Flag vs Action 분리**: Flag(GHD_DIRECT/SITUATION_CHECK/HR_FLAG)는 "어떤 수준으로
   관리해야 하는가", Action/Step은 "다음에 무엇을 해야 하는가"로 명확히 구분.
5. **AI는 절대 최종 판단을 대신하지 않음**: 이메일 초안, 최종 안내 초안 모두 AI가
   제안만 하고 GHD 담당자가 검토/수정/확정해야 저장됨.
6. **문의 상태 체계**: `GHD 직접 처리 / HR 확인 요청 / 추가 서류 요청 / HR 회신 대기 /
   처리 완료` (신규 문의/분석 완료는 분석이 즉시 자동 실행되는 구조라 실제로 관측 안 됨)

## 환경변수 (`.env`, 로컬 전용 — 깃에 커밋 안 됨)

`.env.example`에 목록이 있고, 실제 값은 로컬 `.env`와 Vercel 프로젝트 환경변수에만
저장되어 있습니다 (이 문서에는 값을 적지 않습니다 — 보안):

- `GMAIL_SENDER_EMAIL`, `GMAIL_APP_PASSWORD` — HR 이메일 발송용 Gmail 계정
- `GHD_STAFF_NAME` — 이메일 서명에 쓸 담당자 이름 (기본값 "담당자")
- `SUPABASE_URL`, `SUPABASE_KEY`(service_role) — Supabase 프로젝트 "E-Care" (Project ID: `jnbwozexyeaqniyfbxts`, region ap-northeast-1)

Vercel 프로젝트(`alice-0d56/e-care`)에도 동일한 4개 값이 Production 환경변수로
등록되어 있습니다.

## 배포 정보

- **GitHub**: https://github.com/nadia0418-web/E-Care (private repo, main 브랜치)
- **Vercel 프로젝트**: `alice-0d56/e-care`
- **Production 별칭 URL**: https://e-care-zeta.vercel.app (공개, 로그인 없이 접근 가능)
- 개별 배포 URL(예: `e-care-xxxxx-alice-0d56.vercel.app`)은 Vercel Deployment
  Protection(SSO)에 걸려 팀 멤버가 아니면 접근 불가 — **반드시 위 별칭 URL을 공유할 것**.

## 현재 이슈 (다음 세션이 이어받을 부분)

1. **Dashboard N+1 쿼리 버그 (수정 완료, 재배포 검증 중)**: `/dashboard`가 문의
   120건마다 `workflow_service.get_state()`를 개별 호출(건당 Supabase 쿼리 4회 =
   최대 480회)해서 "Server disconnected" 500 에러 발생. `get_states_for_inquiries()`
   배치 조회 함수를 추가해 테이블당 1회 `in_()` 질의로 수정하고 커밋/푸시 완료
   (commit `6c16be6`, "Fix N+1 Supabase queries in dashboard").
2. **Vercel 재배포가 계속 `UNKNOWN` 상태에 멈춤**: N+1 수정 이후 `vercel --prod --yes`로
   재배포를 시도했는데, 새 배포들이 빌드 로그도 없이 `UNKNOWN` 상태로 멈춰 있음
   (git push로 인한 자동 배포 + CLI 수동 배포가 겹쳐서 큐가 꼬였을 가능성). 최초
   배포(`e-care-cmpwxej7j-...`, 현재 `e-care-zeta.vercel.app`이 가리키는 배포)는
   **정상(Ready)** 이고 Dashboard를 제외한 모든 페이지가 잘 동작함.
   → **다음 세션 확인할 것**: Vercel 대시보드(https://vercel.com/alice-0d56/e-care)에서
   최신 배포 상태 확인. 계속 멈춰 있으면 `vercel --prod --yes`를 한 번 더 시도하거나,
   Vercel 웹 대시보드에서 직접 "Redeploy" 버튼을 눌러본다. Hobby 플랜의 동시 빌드
   제한 때문일 수 있으니 이전 배포들이 다 끝난 뒤 재시도.
3. STEP 14의 최종 PASS/FAIL 표는 Dashboard 재배포가 확인된 뒤 작성 예정.

## 남은 작업 체크리스트

- [ ] Dashboard 재배포 완료 확인 (`/dashboard` 200 응답 + KPI 정상 표시)
- [ ] 실제 배포 URL에서 대표 Demo 문의 전체 흐름 재실행 (문의→분석→...→Timeline→Dashboard)
- [ ] 새로고침 후 데이터 유지 확인 (Supabase 기반이라 이미 구조적으로 보장되지만 배포본에서 한 번 더 확인)
- [ ] 오류 처리 시나리오 확인 (분석/규정/유사사례/HR메일/회신/처리결과 없음 → graceful empty state)
- [ ] GitHub/Vercel에 API 키·비밀번호·개인정보 노출 안 됐는지 최종 확인 (`.env`는 `.gitignore`에 있음, 이미 확인됨)
- [ ] 최종 PASS/FAIL 보고 (사용자가 요청한 형식대로: Dashboard/전체 UX/Supabase/GitHub/Vercel/AI Analysis/Rules·Similar Cases/Action Steps/HR Email/Email Send/HR Reply/Final Guidance/Processing Result/Timeline/전체 Demo Flow/최종 Vercel URL)

## 사용자가 명시적으로 요청한 원칙 (반드시 지킬 것)

- 각 단계 완료마다 장황한 설명 없이 바로 다음 단계로 진행 (GitHub/Vercel/Supabase
  로그인·권한 승인이 필요한 때만 사용자에게 묻고 대기)
- 새로운 대형 기능 추가 금지 (Proactive Care, 예측 모델, ML, 모바일 앱, 실제
  ETNERS 연동, 실제 개인정보 등 절대 추가하지 않음)
- 기존 이메일 전송 기능을 새로 만들지 않고 그대로 재사용
- AI 판단과 GHD 담당자의 최종 처리 결과는 항상 구분해서 표시
