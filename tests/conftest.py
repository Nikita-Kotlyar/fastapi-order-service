from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DB = Path(__file__).resolve().parent / "test_orderhub.db"
os.environ.setdefault("ORDERHUB_DATABASE_URL", f"sqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("ORDERHUB_SOURCE_DIR", str(REPO_ROOT / "data" / "reference"))
os.environ.setdefault("ORDERHUB_JWT_SECRET", "test-secret-key-that-is-long-enough-1234567890")
os.environ.setdefault("ORDERHUB_PBKDF2_ITERATIONS", "1000")
os.environ.setdefault("ORDERHUB_SEED_DEFAULT_USERS", "true")
os.environ.setdefault("ORDERHUB_ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("ORDERHUB_ANALYST_PASSWORD", "test-analyst-password")
os.environ.setdefault("ORDERHUB_VIEWER_PASSWORD", "test-viewer-password")

from app.auth import seed_users  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_users(session)
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def reference_dataset() -> Path:
    path = REPO_ROOT / "data" / "reference"
    if not (path / "data" / "integration" / "1c_orders_export.csv").exists():
        pytest.skip("reference dataset is not available")
    return path


@pytest.fixture(scope="session")
def full_dataset() -> Path:
    raw = os.environ.get("ORDERHUB_INTEGRATION_DIR", "")
    if not raw:
        pytest.skip("ORDERHUB_INTEGRATION_DIR is not set")
    path = Path(raw)
    if not (path / "data" / "integration" / "1c_orders_export.csv").exists():
        pytest.skip("full integration dataset is not available")
    return path
