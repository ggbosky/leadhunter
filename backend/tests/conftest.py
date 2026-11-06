import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="leadhunter-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["WORKER_ENABLED"] = "false"
os.environ["TEXT_PROVIDER"] = "none"
os.environ["VISION_PROVIDER"] = "none"
os.environ["API_TOKEN"] = ""
# volitelně testy proti PostgreSQL: TEST_DATABASE_URL=postgresql://user:pass@localhost/db
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    import sqlalchemy as _sa

    _url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    _eng = _sa.create_engine(_url)
    with _eng.begin() as _c:
        _c.execute(_sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    _eng.dispose()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def app_client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(app_client):
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()
