import os

from flask import Flask


def create_app():
    app = Flask(__name__)
    app.json.ensure_ascii = False
    # 세션(로그인 상태) 서명에 사용. 배포 환경에서는 .env/Vercel 환경변수로 반드시 고정값을 준다.
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key-change-me")

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
