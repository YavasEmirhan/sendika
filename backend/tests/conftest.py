import json
import os
import tempfile
import time
from pathlib import Path

import pyotp
import pytest

# Testler ayrı veritabanında çalışır; ayarlar uygulama import edilmeden önce verilir.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://hk_app:app_dev_pw@localhost:5432/hakkopru_test")
os.environ.setdefault("DATABASE_ADMIN_URL", "postgresql+psycopg://hk_owner:owner_dev_pw@localhost:5432/hakkopru_test")
os.environ["ENV"] = "test"
os.environ["DEMO_MFA_FILE"] = str(Path(tempfile.gettempdir()) / "hakkopru-test-mfa.json")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402
from scripts import seed  # noqa: E402
from scripts.migrate import migrate  # noqa: E402

PASSWORD = seed.DEMO_PASSWORD
A = "ornek-enerji"
B = "ornek-hizmet"


@pytest.fixture(scope="session", autouse=True)
def database():
    s = get_settings()
    engine = create_engine(s.database_admin_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    migrate(s.database_admin_url)
    seed.main(reset=False)
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def mfa_secrets(database):
    return json.loads(Path(os.environ["DEMO_MFA_FILE"]).read_text())


class Auth:
    """Personel girişi yardımcı sınıfı. TOTP tekrar koruması nedeniyle her kullanıcı için
    bir sonraki kullanılabilir zaman adımının kodunu üretir ve belirteçleri önbelleğe alır."""

    def __init__(self, secrets: dict):
        self.secrets = secrets
        self.last_step: dict[str, int] = {}
        self.tokens: dict[tuple[str, str], str] = {}

    def code_for(self, email: str) -> str:
        totp = pyotp.TOTP(self.secrets[email])
        now_step = int(time.time()) // 30
        step = max(now_step - 1, self.last_step.get(email, -1) + 1)
        if step > now_step + 1:
            time.sleep(30)
            return self.code_for(email)
        self.last_step[email] = step
        return totp.generate_otp(step)

    def login(self, client: TestClient, slug: str, handle: str, fresh: bool = False) -> dict:
        email = f"{handle}@{slug}.test"
        key = (slug, email)
        if not fresh and key in self.tokens:
            return {"Authorization": f"Bearer {self.tokens[key]}"}
        r = client.post(f"/api/t/{slug}/staff/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        r = client.post(f"/api/t/{slug}/staff/mfa/verify",
                        json={"mfa_token": r.json()["mfa_token"], "code": self.code_for(email)})
        assert r.status_code == 200, r.text
        self.tokens[key] = r.json()["access_token"]
        return {"Authorization": f"Bearer {self.tokens[key]}"}


@pytest.fixture(scope="session")
def auth(mfa_secrets):
    return Auth(mfa_secrets)


def submit(client: TestClient, slug: str = A, **overrides) -> dict:
    info = client.get(f"/api/t/{slug}").json()
    payload = {
        "category_key": "ucret",
        "subject": "Test başvurusu",
        "description": "Bu otomatik testte oluşturulan bir başvurudur.",
        "city": "İstanbul",
        "is_anonymous": True,
        "contact_method": "none",
        "privacy_notice_id": info["privacy_notice"]["id"],
    }
    payload.update(overrides)
    r = client.post(f"/api/t/{slug}/cases", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def staff_case_id(client: TestClient, headers: dict, reference_no: str, slug: str = A) -> str:
    r = client.get(f"/api/t/{slug}/staff/cases", params={"view": "all", "q": reference_no}, headers=headers)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1, f"{reference_no} görünmüyor"
    return items[0]["id"]
