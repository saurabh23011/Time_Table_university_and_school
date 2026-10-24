import os
import tempfile

import pytest

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db}")
os.environ["SCHEDULER_TIME_LIMIT"] = "6"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app import seed
    from app.main import app

    seed.run(reset=True)
    with TestClient(app) as c:
        yield c


def login(client, email, password="Demo@1234"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin@ait.edu.in")


@pytest.fixture(scope="session")
def ait(admin):
    return admin[1]["institution_id"]
