from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Yalnızca yerel geliştirme için. Üretimde bu değerlerle başlatılırsa uygulama durur.
_DEV_JWT_SECRET = "dev-only-jwt-secret-change-me-0123456789abcdef"
_DEV_FIELD_KEY = "q2bW6l3y7kM1y0n8l2b5mHn4o8bq1W9tYwVwQ0b5c3E="
_DEV_PEPPER = "dev-only-tracking-pepper"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # dev | test | prod

    # Uygulama rolü (RLS'e tabi, tablo sahibi değil)
    database_url: str = "postgresql+psycopg://hk_app:app_dev_pw@localhost:5432/hakkopru"
    # Migration/seed rolü (tablo sahibi)
    database_admin_url: str = "postgresql+psycopg://hk_owner:owner_dev_pw@localhost:5432/hakkopru"

    jwt_secret: str = _DEV_JWT_SECRET
    field_encryption_key: str = _DEV_FIELD_KEY
    tracking_pepper: str = _DEV_PEPPER

    staff_token_minutes: int = 240
    mfa_token_minutes: int = 5
    applicant_token_minutes: int = 30

    login_max_failures: int = 5
    login_lock_minutes: int = 15

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    timezone: str = "Europe/Istanbul"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    def assert_safe_for_env(self) -> None:
        if not self.jwt_secret or not self.field_encryption_key or not self.tracking_pepper:
            raise RuntimeError("JWT_SECRET, FIELD_ENCRYPTION_KEY ve TRACKING_PEPPER boş olamaz.")
        if self.env == "prod":
            insecure = {
                "JWT_SECRET": self.jwt_secret == _DEV_JWT_SECRET,
                "FIELD_ENCRYPTION_KEY": self.field_encryption_key == _DEV_FIELD_KEY,
                "TRACKING_PEPPER": self.tracking_pepper == _DEV_PEPPER,
            }
            bad = [k for k, v in insecure.items() if v]
            if bad:
                raise RuntimeError(f"Üretimde geliştirme anahtarı kullanılamaz: {', '.join(bad)}")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.assert_safe_for_env()
    return s
