from pathlib import Path

from openpyxl import load_workbook

from app.services import supabase_client

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "employees.xlsx"

# 엑셀 컬럼 순서와 내부에서 사용할 필드명 매핑
COLUMNS = [
    "employee_id",
    "name",
    "nationality",
    "client_company",
    "position",
    "start_date",
    "employment_period",
    "family_accompanied",
    "visa_type",
]

HEADER_ROW = 3  # 1행: 안내 타이틀, 2행: 공백, 3행: 헤더

_employees_cache = None


def _load_from_excel():
    wb = load_workbook(DATA_PATH, data_only=True)
    ws = wb["직원명단"]

    employees = []
    for row in ws.iter_rows(min_row=HEADER_ROW + 1, values_only=True):
        if row[0] is None:
            continue
        record = dict(zip(COLUMNS, row))
        record["family_accompanied"] = record["family_accompanied"] == "예"
        if hasattr(record["start_date"], "strftime"):
            record["start_date"] = record["start_date"].strftime("%Y-%m-%d")
        employees.append(record)
    return employees


def _load_from_supabase(client):
    result = client.table("employees").select("*").order("employee_id").execute()
    return result.data


def get_all_employees():
    """전체 직원 목록을 반환한다. Supabase가 설정되어 있으면 그쪽에서, 아니면
    로컬 엑셀 파일(data/employees.xlsx)에서 읽는다 (배포 환경에서는 Supabase,
    로컬 개발 환경에서는 엑셀을 그대로 사용할 수 있도록 둘 다 지원)."""
    global _employees_cache
    if _employees_cache is None:
        client = supabase_client.get_client()
        _employees_cache = _load_from_supabase(client) if client else _load_from_excel()
    return _employees_cache


def get_employee_by_id(employee_id):
    for employee in get_all_employees():
        if employee["employee_id"] == employee_id:
            return employee
    return None
