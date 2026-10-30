from typing import Literal
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field, model_validator


class CaseCreate(BaseModel):
    category_key: str = Field(min_length=1, max_length=60)
    subject: str = Field(min_length=3, max_length=140)
    description: str = Field(min_length=10, max_length=5000)
    workplace: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=60)
    is_anonymous: bool
    contact_method: Literal["none", "email", "phone"]
    contact_value: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=120)
    safe_contact_note: str | None = Field(default=None, max_length=200)
    privacy_notice_id: UUID
    explicit_consent_notice_id: UUID | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.contact_method == "none":
            if not self.is_anonymous:
                raise ValueError("İletişim bilgisi bırakmayan başvuru anonim olmalıdır.")
            self.contact_value = None
        else:
            if not self.contact_value or not self.contact_value.strip():
                raise ValueError("Seçtiğiniz iletişim kanalı için bilgi girin.")
            v = self.contact_value.strip()
            if self.contact_method == "email":
                try:
                    v = validate_email(v, check_deliverability=False).normalized
                except EmailNotValidError:
                    raise ValueError("Geçerli bir e-posta adresi girin.")
            if self.contact_method == "phone":
                digits = "".join(ch for ch in v if ch.isdigit())
                if not 10 <= len(digits) <= 13:
                    raise ValueError("Geçerli bir telefon numarası girin.")
            self.contact_value = v
        if self.is_anonymous:
            self.contact_name = None
        return self


class TrackRequest(BaseModel):
    code: str = Field(min_length=8, max_length=40)


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class StaffMessageCreate(MessageCreate):
    visibility: Literal["public", "internal"]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=10)


class AssignRequest(BaseModel):
    assignee_id: UUID | None


class StatusRequest(BaseModel):
    status: Literal["triage", "waiting_info", "assigned", "in_progress", "referred", "resolved", "closed_timeout"]
    closure_code: str | None = None


class PriorityRequest(BaseModel):
    priority: Literal["P1", "P2", "P3", "P4"]


class RevealRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
