from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Path
from sqlalchemy import Connection, text

from .authz import Principal, build_principal
from .db import resolve_tenant, tenant_tx


def get_tenant(slug: str = Path(..., pattern=r"^[a-z0-9-]{2,40}$")) -> dict:
    tenant = resolve_tenant(slug)
    if not tenant or tenant["status"] != "active":
        raise HTTPException(status_code=404, detail="Kurum bulunamadı.")
    return tenant


def tenant_conn(tenant: dict = Depends(get_tenant)) -> Iterator[Connection]:
    with tenant_tx(tenant["id"]) as conn:
        yield conn


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Oturum gerekli.")
    return authorization[7:].strip()


def _decode(token: str, scope: str) -> dict:
    from .security import decode_token

    try:
        claims = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Oturum süresi doldu veya geçersiz.")
    if claims.get("scope") != scope:
        raise HTTPException(status_code=401, detail="Oturum geçersiz.")
    return claims


@dataclass
class StaffContext:
    principal: Principal
    conn: Connection
    tenant: dict


def staff_ctx(
    tenant: dict = Depends(get_tenant),
    authorization: str | None = Header(default=None),
) -> Iterator[StaffContext]:
    claims = _decode(_bearer(authorization), "staff")
    # Belirteç başka bir kiracıya aitse URL'deki kiracıyla eşleşmez: reddedilir.
    if claims["tid"] != str(tenant["id"]):
        raise HTTPException(status_code=401, detail="Oturum geçersiz.")
    with tenant_tx(tenant["id"]) as conn:
        user = conn.execute(
            text("SELECT id, tenant_id, email, full_name, status, token_version, mfa_enabled FROM staff_users WHERE id = :id"),
            {"id": claims["sub"]},
        ).mappings().first()
        if (
            not user
            or user["status"] != "active"
            or user["token_version"] != claims.get("tv")
            or not user["mfa_enabled"]
        ):
            raise HTTPException(status_code=401, detail="Oturum sonlandırılmış.")
        yield StaffContext(principal=build_principal(conn, dict(user)), conn=conn, tenant=tenant)


@dataclass
class ApplicantContext:
    case_id: UUID
    conn: Connection
    tenant: dict


def applicant_ctx(
    tenant: dict = Depends(get_tenant),
    authorization: str | None = Header(default=None),
) -> Iterator[ApplicantContext]:
    claims = _decode(_bearer(authorization), "applicant")
    if claims["tid"] != str(tenant["id"]):
        raise HTTPException(status_code=401, detail="Oturum geçersiz.")
    with tenant_tx(tenant["id"]) as conn:
        yield ApplicantContext(case_id=UUID(claims["sub"]), conn=conn, tenant=tenant)
