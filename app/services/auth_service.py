"""관리자 로그인 (단순 세션 기반).

⚠ Demo/MVP 수준의 최소 인증이다. 관리자 계정 1개만 지원하며, 아이디/비밀번호는
반드시 .env(ADMIN_USERNAME/ADMIN_PASSWORD)에서만 읽고 코드에 하드코딩하지 않는다.
"""

import os
from functools import wraps

from flask import redirect, request, session, url_for


def check_credentials(username, password):
    admin_user = os.environ.get("ADMIN_USERNAME")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if not admin_user or not admin_pass:
        return False
    return username == admin_user and password == admin_pass


def is_logged_in():
    return session.get("logged_in") is True


def current_username():
    return session.get("username")


def login(username):
    session["logged_in"] = True
    session["username"] = username


def logout():
    session.clear()


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("main.login_view", next=request.path))
        return view_func(*args, **kwargs)

    return wrapper
