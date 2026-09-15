from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from app.services import (
    analysis_service,
    auth_service,
    care_profile_service,
    dashboard_service,
    employee_service,
    inquiry_service,
    mail_service,
    rule_service,
    structuring_service,
    workflow_service,
)

# Double-check 체크리스트 (7개 항목 모두 체크해야 이메일 전송 가능)
DOUBLE_CHECK_ITEMS = [
    ("dc_target", "대상 임직원 확인"),
    ("dc_content", "문의 내용 확인"),
    ("dc_hr_request", "HR 확인 요청사항 확인"),
    ("dc_documents", "필요 서류 확인"),
    ("dc_urgency", "긴급도 확인"),
    ("dc_recipient", "이메일 수신자 확인"),
    ("dc_subject_body", "이메일 제목 및 본문 확인"),
]

main_bp = Blueprint("main", __name__)

# /login, /logout, 정적 파일을 제외한 모든 페이지는 로그인해야 접근 가능하다.
_PUBLIC_ENDPOINTS = {"main.login_view", "main.logout_view", "static"}


@main_bp.before_request
def _require_login():
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if not auth_service.is_logged_in():
        return redirect(url_for("main.login_view", next=request.path))
    return None


@main_bp.context_processor
def _inject_current_user():
    """모든 템플릿(admin_base.html 등)에서 로그인 사용자 이름을 바로 쓸 수 있게 한다."""
    return {"current_user": auth_service.current_username()}


@main_bp.route("/login", methods=["GET", "POST"])
def login_view():
    next_url = request.values.get("next") or url_for("main.index")
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if auth_service.check_credentials(username, password):
            auth_service.login(username)
            return redirect(next_url)
        error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("login.html", error=error, next_url=next_url)


@main_bp.route("/logout")
def logout_view():
    auth_service.logout()
    return redirect(url_for("main.login_view"))


@main_bp.route("/")
def index():
    """홈: GHD 업무 현황판을 겸한다 (KPI + Proactive Care + 우선 처리 필요 + 최근 문의).
    모든 수치는 매 요청마다 문의 데이터와 처리 상태에서 동적으로 계산한다 (하드코딩 없음)."""
    data = dashboard_service.get_dashboard_data()
    return render_template(
        "home.html",
        active_nav="home",
        status_badge_class=workflow_service.STATUS_BADGE_CLASS,
        **data,
    )


@main_bp.route("/dashboard")
def dashboard_redirect():
    """이전 /dashboard 링크(공유된 데모 URL 등) 호환용 리다이렉트. 홈과 통합되었다."""
    return redirect(url_for("main.index"))


@main_bp.route("/employees")
def employees():
    """직원 데이터 로딩 확인용 테스트 라우트 (JSON 반환)."""
    data = employee_service.get_all_employees()
    return jsonify({"count": len(data), "employees": data})


@main_bp.route("/employees-view")
def employees_view():
    """직원 데이터 화면: 목록 조회 + 수기 입력/엑셀 업로드로 신규 직원을 등록한다."""
    data = employee_service.get_all_employees()
    return render_template(
        "employees_view.html",
        employees=data,
        active_nav="employees",
        employment_period_choices=employee_service.EMPLOYMENT_PERIOD_CHOICES,
        form_result=None,
    )


@main_bp.route("/employees-view/add", methods=["POST"])
def add_employee_view():
    """직원 1명을 수기 입력 폼으로 추가한다."""
    record = {
        "name": request.form.get("name", ""),
        "nationality": request.form.get("nationality", ""),
        "client_company": request.form.get("client_company", ""),
        "position": request.form.get("position", ""),
        "start_date": request.form.get("start_date", ""),
        "employment_period": request.form.get("employment_period", ""),
        "family_accompanied": request.form.get("family_accompanied") == "on",
        "visa_type": request.form.get("visa_type", ""),
    }
    added = employee_service.add_employees([record])
    if added:
        form_result = {
            "success": True,
            "message": f"{added[0]['employee_id']} ({added[0]['name']}) 직원이 추가되었습니다.",
        }
    else:
        form_result = {"success": False, "message": "이름이 입력되지 않아 추가하지 못했습니다."}

    data = employee_service.get_all_employees()
    return render_template(
        "employees_view.html",
        employees=data,
        active_nav="employees",
        employment_period_choices=employee_service.EMPLOYMENT_PERIOD_CHOICES,
        form_result=form_result,
    )


@main_bp.route("/employees-view/upload", methods=["POST"])
def upload_employees_view():
    """엑셀 파일로 직원 데이터를 일괄 등록한다."""
    file = request.files.get("employees_file")
    if not file or not file.filename:
        form_result = {"success": False, "message": "업로드할 엑셀(.xlsx) 파일을 선택해주세요."}
    else:
        try:
            records = employee_service.parse_upload_workbook(file.stream)
            added = employee_service.add_employees(records)
            if added:
                form_result = {"success": True, "message": f"{len(added)}건이 업로드되었습니다."}
            else:
                form_result = {
                    "success": False,
                    "message": "업로드한 파일에서 추가할 직원 데이터를 찾지 못했습니다 (이름 컬럼 확인).",
                }
        except Exception as e:  # 잘못된 파일 형식이 앱 전체 오류로 번지지 않도록 방어
            form_result = {"success": False, "message": f"업로드 처리 중 오류가 발생했습니다: {e}"}

    data = employee_service.get_all_employees()
    return render_template(
        "employees_view.html",
        employees=data,
        active_nav="employees",
        employment_period_choices=employee_service.EMPLOYMENT_PERIOD_CHOICES,
        form_result=form_result,
    )


@main_bp.route("/employees/<employee_id>")
def employee_detail(employee_id):
    employee = employee_service.get_employee_by_id(employee_id)
    if employee is None:
        return jsonify({"error": "employee not found"}), 404
    return jsonify(employee)


@main_bp.route("/employees/<employee_id>/profile")
def employee_profile_view(employee_id):
    """Employee Care Profile: 이 직원에게 지금까지 어떤 Care가 진행되었고
    현재 무엇이 남아 있는지를 Care Progress + Open Care Items + HR Flag +
    Care Timeline으로 한 화면에서 보여준다."""
    profile = care_profile_service.get_employee_care_profile(employee_id)
    if profile is None:
        return render_template("not_found.html", kind="직원", target_id=employee_id, active_nav="employees"), 404
    return render_template("employee_profile.html", active_nav="employees", **profile)


@main_bp.route("/inquiries")
def inquiries():
    """문의 데이터 로딩 확인용 테스트 라우트 (JSON 반환)."""
    data = inquiry_service.get_all_inquiries()
    return jsonify({"count": len(data), "inquiries": data})


@main_bp.route("/inquiries/<inquiry_id>")
def inquiry_detail(inquiry_id):
    inquiry = inquiry_service.get_inquiry_by_id(inquiry_id)
    if inquiry is None:
        return jsonify({"error": "inquiry not found"}), 404
    return jsonify(inquiry)


@main_bp.route("/employees/<employee_id>/inquiries")
def employee_inquiries(employee_id):
    if employee_service.get_employee_by_id(employee_id) is None:
        return jsonify({"error": "employee not found"}), 404
    data = inquiry_service.get_inquiries_by_employee(employee_id)
    return jsonify({"count": len(data), "inquiries": data})


@main_bp.route("/ghd-rules")
def ghd_rules():
    """가상 GHD 업무 판단 기준 로딩 확인용 테스트 라우트 (JSON 반환)."""
    data = rule_service.get_all_rules()
    return jsonify({"count": len(data), "rules": data})


@main_bp.route("/ghd-rules-view")
def ghd_rules_view():
    """관련 내규 화면: 가상 GHD 업무 판단 기준을 사람이 보기 쉬운 표로 보여준다."""
    data = rule_service.get_all_rules()
    return render_template("rules_view.html", rules=data, active_nav="rules")


@main_bp.route("/ghd-rules/<rule_id>")
def ghd_rule_detail(rule_id):
    rule = rule_service.get_rule_by_id(rule_id)
    if rule is None:
        return jsonify({"error": "rule not found"}), 404
    return jsonify(rule)


@main_bp.route("/inquiries/<inquiry_id>/analysis")
def inquiry_analysis(inquiry_id):
    """문의 1건에 대한 1차 시스템 분석 결과 확인용 테스트 라우트 (JSON 반환).
    ⚠ 최종 판단이 아니며, GHD 담당자의 Double-check로 확정된다."""
    inquiry = inquiry_service.get_inquiry_by_id(inquiry_id)
    if inquiry is None:
        return jsonify({"error": "inquiry not found"}), 404
    result = analysis_service.analyze_inquiry(inquiry["inquiry_text"], inquiry["category"])
    return jsonify({"inquiry": inquiry, "analysis": result})


@main_bp.route("/structure-test")
def structure_test():
    """카테고리가 아직 정해지지 않은 새 문의(raw text)의 구조화 결과를 확인하는
    테스트 라우트 (JSON 반환). 예: /structure-test?text=인도에서 받은 진단서로...
    ⚠ 1차 분석/업무지원 제안이며 최종 판단이 아니다."""
    text = request.args.get("text", "")
    if not text:
        return jsonify({"error": "text 쿼리 파라미터가 필요합니다"}), 400
    result = structuring_service.structure_inquiry(text)
    return jsonify(result)


@main_bp.route("/inquiries-view")
def inquiries_view():
    """문의 목록 화면: 전체 문의 / 선제 확인 필요 / 우선 처리 필요 / 최근 문의를
    탭으로 묶어서 보여준다. ?tab= 쿼리로 홈 화면의 배너·KPI 카드에서 바로 원하는
    탭으로 진입할 수 있다."""
    data = inquiry_service.get_all_inquiries()
    dashboard_data = dashboard_service.get_dashboard_data(
        priority_limit=200, recent_limit=50, completed_limit=200
    )
    active_tab = request.args.get("tab", "all")
    if active_tab not in ("all", "proactive", "priority", "recent", "completed"):
        active_tab = "all"
    return render_template(
        "inquiries_view.html",
        inquiries=data,
        active_nav="inquiries",
        active_tab=active_tab,
        status_badge_class=workflow_service.STATUS_BADGE_CLASS,
        proactive_items=dashboard_data["proactive_items"],
        priority_items=dashboard_data["priority_items"],
        priority_total=dashboard_data["priority_total"],
        recent_items=dashboard_data["recent_items"],
        completed_items=dashboard_data["completed_items"],
        completed_total=dashboard_data["completed_total"],
    )


def _load_inquiry_context(inquiry_id):
    """상세/처리 라우트에서 공통으로 쓰는 문의+구조화 결과 로딩 로직."""
    inquiry = inquiry_service.get_inquiry_by_id(inquiry_id)
    if inquiry is None:
        return None, None, None
    employee = employee_service.get_employee_by_id(inquiry["employee_id"])
    structured = structuring_service.structure_inquiry(
        inquiry["inquiry_text"],
        category=inquiry["category"],
        employee=employee,
        exclude_inquiry_id=inquiry_id,
    )
    return inquiry, employee, structured


def _render_detail(inquiry, employee, structured, send_result=None, email_draft_override=None):
    """Inquiry Detail 화면 렌더링에 필요한 모든 조회를 모아 처리하는 공통 헬퍼."""
    inquiry_id = inquiry["inquiry_id"]
    workflow_state = workflow_service.get_state(inquiry_id)
    workflow_status = workflow_service.get_workflow_status(inquiry_id, structured, state=workflow_state)
    status_badge_class = workflow_service.STATUS_BADGE_CLASS.get(workflow_status, "SITUATION_CHECK")
    last_email = workflow_state["email_log"][-1] if workflow_state["email_log"] else None
    timeline = workflow_service.build_timeline(inquiry, structured, workflow_state)

    if email_draft_override is not None:
        email_draft = email_draft_override
    elif structured["requires_hr_email"]:
        if last_email:
            email_draft = {
                "subject": last_email["subject"],
                "body": last_email["body"],
                "recipient": last_email["recipient"],
            }
        else:
            email_draft = structuring_service.build_hr_email_draft(inquiry, employee, structured)
    else:
        email_draft = None

    hr_reply = workflow_state["hr_reply"]
    final_guidance = workflow_state["final_guidance"]
    final_guidance_draft = ""
    if final_guidance:
        final_guidance_draft = final_guidance["content"]
    elif hr_reply:
        reply_content = hr_reply["content"].strip()
        # HR 회신이 이미 "HR 확인 결과"로 시작하면 접두어를 중복해서 붙이지 않는다.
        final_guidance_draft = (
            reply_content if reply_content.startswith("HR 확인") else f"HR 확인 결과, {reply_content}"
        )

    return render_template(
        "inquiry_detail.html",
        active_nav="inquiries",
        inquiry=inquiry,
        employee=employee,
        structured=structured,
        completed_steps=workflow_state["completed_steps"],
        workflow_status=workflow_status,
        status_badge_class=status_badge_class,
        email_log=workflow_state["email_log"],
        email_draft=email_draft,
        double_check_items=DOUBLE_CHECK_ITEMS,
        send_result=send_result,
        hr_reply=hr_reply,
        final_guidance=final_guidance,
        final_guidance_draft=final_guidance_draft,
        resolution=workflow_state["resolution"],
        resolution_options=workflow_service.RESOLUTION_OPTIONS,
        timeline=timeline,
    )


@main_bp.route("/inquiries/<inquiry_id>/detail")
def inquiry_detail_view(inquiry_id):
    """Inquiry Detail 화면: 문의 내용 -> AI 문의 구조화 -> 관련 규정 -> 유사 사례 ->
    Flag -> 추천 업무 절차(Step) -> HR 커뮤니케이션(이메일 작성/Double-check/전송) ->
    HR 회신 -> 최종 안내 -> 처리 결과 -> Timeline."""
    inquiry, employee, structured = _load_inquiry_context(inquiry_id)
    if inquiry is None:
        return render_template("not_found.html", kind="문의", target_id=inquiry_id, active_nav="inquiries"), 404
    return _render_detail(inquiry, employee, structured)


@main_bp.route("/inquiries/<inquiry_id>/update-steps", methods=["POST"])
def update_steps(inquiry_id):
    """담당자가 업무 절차(Step)의 완료 여부를 체크·저장한다."""
    inquiry, _, structured = _load_inquiry_context(inquiry_id)
    if inquiry is None:
        return render_template("not_found.html", kind="문의", target_id=inquiry_id, active_nav="inquiries"), 404

    completed = [int(v) for v in request.form.getlist("completed_step")]
    workflow_service.save_completed_steps(inquiry_id, completed)
    return redirect(url_for("main.inquiry_detail_view", inquiry_id=inquiry_id))


@main_bp.route("/inquiries/<inquiry_id>/send-hr-email", methods=["POST"])
def send_hr_email(inquiry_id):
    """HR 확인 요청 이메일을 Double-check 후 실제 발송한다.

    ⚠ 여기서 만든 이메일은 GHD 담당자가 HR에 "확인을 요청"하는 것이며, AI가 HR의
    최종 판단을 대신하지 않는다. Double-check 7개 항목이 모두 체크되어야만 실제
    발송을 진행하고, 발송 성공/실패와 무관하게 이 라우트는 항상 문의 상세 화면으로
    돌아가며 오류 페이지로 넘어가지 않는다."""
    inquiry, employee, structured = _load_inquiry_context(inquiry_id)
    if inquiry is None:
        return render_template("not_found.html", kind="문의", target_id=inquiry_id, active_nav="inquiries"), 404

    subject = request.form.get("email_subject", "")
    body = request.form.get("email_body", "")
    recipient = request.form.get("email_recipient", "")

    all_checked = all(request.form.get(field) == "on" for field, _ in DOUBLE_CHECK_ITEMS)

    if not structured["requires_hr_email"]:
        send_result = {"attempted": False, "message": "이 문의는 HR 확인이 필요하지 않습니다."}
    elif not all_checked:
        send_result = {
            "attempted": False,
            "message": "Double-check 항목을 모두 확인해야 이메일을 전송할 수 있습니다.",
        }
    else:
        hr_email_step = next(
            (s for s in structured["workflow_steps"] if s["requires_hr_email"]), None
        )
        try:
            success, error = mail_service.send_email(recipient, subject, body)
        except Exception as e:  # 이메일 발송 실패가 앱 전체 오류로 번지지 않도록 방어
            success, error = False, str(e)

        workflow_service.record_email_attempt(
            inquiry_id,
            subject,
            body,
            recipient,
            success,
            error=error,
            auto_complete_step=hr_email_step["step"] if (success and hr_email_step) else None,
        )
        send_result = {
            "attempted": True,
            "success": success,
            "message": (
                "✓ HR 이메일 전송 완료"
                if success
                else "이메일 전송에 실패했습니다. 수신자 및 이메일 설정을 확인해주세요."
            ),
        }

    email_draft_override = {"subject": subject, "body": body, "recipient": recipient}
    return _render_detail(
        inquiry, employee, structured, send_result=send_result, email_draft_override=email_draft_override
    )


@main_bp.route("/inquiries/<inquiry_id>/register-hr-reply", methods=["POST"])
def register_hr_reply(inquiry_id):
    """GHD 담당자가 고객사 HR로부터 받은 회신을 등록한다. (Demo 환경 — 실제 ETNERS
    데이터가 아님)"""
    inquiry, _, _ = _load_inquiry_context(inquiry_id)
    if inquiry is None:
        return render_template("not_found.html", kind="문의", target_id=inquiry_id, active_nav="inquiries"), 404

    workflow_service.save_hr_reply(
        inquiry_id,
        replied_at=request.form.get("replied_at", ""),
        content=request.form.get("reply_content", ""),
        replier=request.form.get("replier", ""),
        additional_request=request.form.get("additional_request", ""),
    )
    return redirect(url_for("main.inquiry_detail_view", inquiry_id=inquiry_id))


@main_bp.route("/inquiries/<inquiry_id>/confirm-final-guidance", methods=["POST"])
def confirm_final_guidance(inquiry_id):
    """HR 회신을 바탕으로 GHD 담당자가 확정한 임직원 대상 최종 안내를 저장한다.
    ⚠ AI는 초안(HR 회신 내용을 옮긴 문장)만 지원하며, 실제 저장되는 내용은
    GHD 담당자가 검토·확정한 것이다."""
    inquiry, _, _ = _load_inquiry_context(inquiry_id)
    if inquiry is None:
        return render_template("not_found.html", kind="문의", target_id=inquiry_id, active_nav="inquiries"), 404

    workflow_service.save_final_guidance(inquiry_id, request.form.get("final_guidance_content", ""))
    return redirect(url_for("main.inquiry_detail_view", inquiry_id=inquiry_id))


@main_bp.route("/inquiries/<inquiry_id>/register-resolution", methods=["POST"])
def register_resolution(inquiry_id):
    """문의의 최종 처리 결과를 등록한다. 등록 즉시 상태가 "처리 완료"로 바뀐다."""
    inquiry, _, _ = _load_inquiry_context(inquiry_id)
    if inquiry is None:
        return render_template("not_found.html", kind="문의", target_id=inquiry_id, active_nav="inquiries"), 404

    workflow_service.save_resolution(
        inquiry_id,
        outcome=request.form.get("resolution_outcome", ""),
        memo=request.form.get("resolution_memo", ""),
    )
    return redirect(url_for("main.inquiry_detail_view", inquiry_id=inquiry_id))
