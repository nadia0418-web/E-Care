"""Gmail SMTP를 통한 이메일 발송 서비스.

용도: GHD 담당자 -> 각 고객사별 HR 담당자 커뮤니케이션 (예: HR 전달용 요약문 발송).

⚠ 보안 원칙
- 발신 계정/앱 비밀번호는 절대 코드에 하드코딩하지 않고 .env(GMAIL_SENDER_EMAIL,
  GMAIL_APP_PASSWORD)에서만 읽는다. .env는 .gitignore에 포함되어 Git 추적에서 제외된다.
- 실제 발송 전에는 반드시 수신자·제목·본문을 사람이 확인한 뒤 호출해야 한다.
  이 모듈 자체는 확인 절차를 포함하지 않으므로, 호출하는 쪽(라우트/스킬)에서
  발송 전 확인 단계를 반드시 넣을 것.
"""

import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL")
APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")


def send_email(to_email, subject, body):
    """이메일 1건을 발송한다. 성공 시 True, 실패 시 (False, 에러메시지)를 반환한다."""
    if not SENDER_EMAIL or not APP_PASSWORD:
        return False, "GMAIL_SENDER_EMAIL / GMAIL_APP_PASSWORD가 .env에 설정되어 있지 않습니다."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, APP_PASSWORD)
            smtp.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


def send_to_hr(hr_email, client_company, subject, body):
    """고객사별 HR 담당자에게 발송한다. (수신자 매핑은 아직 없음 — 호출부에서
    client_company에 맞는 hr_email을 직접 넘겨줄 것. 향후 고객사-HR 담당자 연락처
    데이터가 만들어지면 client_company만으로 조회하도록 확장 가능)"""
    return send_email(hr_email, f"[{client_company}] {subject}", body)
