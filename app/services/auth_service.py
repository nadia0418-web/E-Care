"""관리자/담당자 로그인 (단순 세션 기반, 다중 계정 지원).

⚠ Demo/MVP 수준의 최소 인증이다. 계정 목록은 반드시 .env에서만 읽고 코드에
하드코딩하지 않는다.

계정 구성:
- ADMIN_USERNAME / ADMIN_PASSWORD: 총괄 관리자 계정 (기존과 동일하게 유지)
- STAFF_ACCOUNTS: 담당자 계정 목록. "아이디:비밀번호:표시이름"을 콤마(,)로
  나열한다. 예) STAFF_ACCOUNTS=kim:pw123:김민수,lee:pw456:이지은

모든 계정은 전체 임직원 데이터에 동일하게 접근한다 (담당자별 배분/접근 제한은
하지 않음) — 계정을 구분하는 목적은 활동 로그에서 "누가" 처리했는지 추적하기
위함뿐이다.
"""

import os
from functools import wraps

from flask import redirect, request, session, url_for


def _load_accounts():
    accounts = {}

    admin_user = os.environ.get("ADMIN_USERNAME")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if admin_user and admin_pass:
        accounts[admin_user] = {
            "password": admin_pass,
            "display_name": os.environ.get("ADMIN_DISPLAY_NAME") or "총괄관리자",
        }

    raw = os.environ.get("STAFF_ACCOUNTS", "")
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 3:
            continue
        username, password, display_name = (p.strip() for p in parts)
        if username and password:
            accounts[username] = {"password": password, "display_name": display_name or username}

    return accounts


def check_credentials(username, password):
    account = _load_accounts().get(username)
    return account is not None and account["password"] == password


def is_logged_in():
    return session.get("logged_in") is True


def current_username():
    """세션에 저장된 로그인 아이디(원본)를 반환한다."""
    return session.get("username")


def current_display_name():
    """화면 표시/활동 로그에 쓰는 담당자 표시 이름을 반환한다."""
    return session.get("display_name") or session.get("username")


def login(username):
    account = _load_accounts().get(username, {})
    session["logged_in"] = True
    session["username"] = username
    session["display_name"] = account.get("display_name") or username


def logout():
    session.clear()


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("main.login_view", next=request.path))
        return view_func(*args, **kwargs)

    return wrapper
