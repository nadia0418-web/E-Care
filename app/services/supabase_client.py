"""Supabase 클라이언트 — 모듈 스코프에서 1회만 생성해 재사용한다.

서버리스(Vercel) 환경에서는 요청마다 함수가 새로 뜰 수 있으므로, 매 요청마다
클라이언트를 새로 만들지 않고 웜(warm) 인스턴스 안에서 재사용하는 것이 중요하다
(Flask 성능 체크리스트 1장 참고). supabase-py는 PostgREST(HTTPS) 기반이라
직접 Postgres 커넥션을 유지하지 않으므로, 커넥션 풀 고갈 문제도 없다.

SUPABASE_URL / SUPABASE_KEY가 .env에 설정되어 있지 않으면 get_client()는
None을 반환하고, 각 서비스는 로컬 엑셀/JSON 파일로 자동 폴백한다 — 로컬
개발 환경에서는 Supabase 없이도 그대로 동작한다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

_client = None
_client_initialized = False


def get_client():
    global _client, _client_initialized
    if _client_initialized:
        return _client

    _client_initialized = True
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        _client = None
        return None

    from supabase import create_client  # 실제로 필요할 때만 import (콜드 스타트 절감)

    _client = create_client(url, key)
    return _client


def is_enabled():
    return get_client() is not None
