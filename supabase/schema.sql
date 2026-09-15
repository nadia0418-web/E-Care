-- E-Care Supabase 스키마
-- ⚠ 여기 담기는 모든 데이터는 프로젝트 시연용 가상 데이터입니다.
--    실제 ETNERS 또는 고객사의 임직원/문의 정보가 아닙니다.
--
-- 현재 로컬 구조(엑셀 3종 + JSON 상태 파일 1종)를 그대로 옮긴 것으로,
-- 새 테이블을 임의로 늘리지 않았습니다. "analyses"와 "timelines"는 항상
-- 다른 테이블에서 즉시 계산 가능한 파생 데이터라 별도 테이블로 만들지
-- 않고, 애플리케이션에서 계산합니다 (기존 로컬 버전과 동일한 방식).

-- 1) 직원 (기존 data/employees.xlsx)
create table if not exists employees (
    employee_id text primary key,
    name text not null,
    nationality text not null,
    client_company text not null,
    position text not null,
    start_date date not null,
    employment_period text not null,
    family_accompanied boolean not null default false,
    visa_type text not null
);

-- 2) 문의 (기존 data/inquiries.xlsx)
create table if not exists inquiries (
    inquiry_id text primary key,
    employee_id text not null references employees(employee_id),
    inquiry_date date not null,
    inquiry_text text not null,
    language text not null,
    category text not null,
    flag text not null,
    urgency text not null,
    status text not null,
    final_result text not null
);
create index if not exists idx_inquiries_employee_id on inquiries(employee_id);
create index if not exists idx_inquiries_category on inquiries(category);

-- 3) 가상 GHD 업무 판단 기준 (기존 data/ghd_rules.xlsx)
create table if not exists rules (
    rule_id text primary key,
    category text not null,
    rule_name text not null,
    situation text not null,
    keywords text not null,  -- 쉼표 구분 문자열 (기존 엑셀과 동일한 표현 방식)
    handler text not null,
    hr_flag boolean not null default false,
    urgency text not null,
    reasoning text not null,
    note text
);
create index if not exists idx_rules_category on rules(category);

-- 4) 업무 절차 Step 완료 여부 (기존 hr_workflow_state.json의 completed_steps)
create table if not exists action_steps (
    inquiry_id text not null references inquiries(inquiry_id),
    step_number int not null,
    completed boolean not null default true,
    updated_at timestamptz not null default now(),
    primary key (inquiry_id, step_number)
);

-- 5) HR 확인 요청 이메일 발송 이력 (기존 hr_workflow_state.json의 email_log)
create table if not exists hr_communications (
    id bigint generated always as identity primary key,
    inquiry_id text not null references inquiries(inquiry_id),
    sent_at timestamptz not null default now(),
    subject text not null,
    body text not null,
    recipient text not null,
    success boolean not null,
    error text
);
create index if not exists idx_hr_communications_inquiry_id on hr_communications(inquiry_id);

-- 6) HR 회신 + 최종 안내 (기존 hr_workflow_state.json의 hr_reply/final_guidance, 문의당 1건)
create table if not exists hr_replies (
    inquiry_id text primary key references inquiries(inquiry_id),
    replied_at text,
    content text not null,
    replier text,
    additional_request text,
    registered_at timestamptz not null default now(),
    final_guidance_content text,
    final_guidance_confirmed_at timestamptz
);

-- 7) 처리 결과 (기존 hr_workflow_state.json의 resolution, 문의당 1건)
create table if not exists processing_results (
    inquiry_id text primary key references inquiries(inquiry_id),
    outcome text not null,
    memo text,
    recorded_at timestamptz not null default now()
);

-- 이 프로젝트는 로그인/사용자 구분이 없는 내부 Demo 툴이며, 모든 접근이
-- 서버(Flask, service_role 키)에서만 이뤄집니다. RLS를 켜되 서버 접근만
-- 허용되도록 별도 공개 정책은 만들지 않습니다 (service_role 키는 RLS를
-- 우회하므로 서버 코드는 정상 동작하고, anon/public 키로는 아무 것도
-- 조회/변경할 수 없습니다 — 브라우저에서 직접 두드릴 수 없게 하는 것이 목적).
alter table employees enable row level security;
alter table inquiries enable row level security;
alter table rules enable row level security;
alter table action_steps enable row level security;
alter table hr_communications enable row level security;
alter table hr_replies enable row level security;
alter table processing_results enable row level security;
