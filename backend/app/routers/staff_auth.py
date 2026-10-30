"""Personel girişi: parola + zorunlu TOTP (iki adımlı doğrulama)."""
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text

from ..audit import audit
from ..authz import ROLE_LABELS
from ..config import get_settings
from ..db import tenant_tx
from ..deps import StaffContext, get_tenant, staff_ctx
from ..ratelimit import enforce
from ..schemas import LoginRequest, MfaVerifyRequest
from ..security import (
    burn_password_check,
    dec,
    decode_token,
    enc,
    mfa_token,
    new_totp_secret,
    staff_access_token,
    totp_uri,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix="/api/t/{slug}/staff", tags=["staff-auth"])

_GENERIC = "E-posta veya parola hatalı."


@router.post("/login")
def login(body: LoginRequest, request: Request, tenant: dict = Depends(get_tenant)):
    enforce(request, f"login:{tenant['id']}", limit=10, window_seconds=900)
    s = get_settings()
    email = body.email.strip().lower()
    now = datetime.now(UTC)

    # Başarısız deneme sayacının kalıcı olması için kendi transaction'ında çalışır.
    with tenant_tx(tenant["id"]) as conn:
        user = conn.execute(
            text("SELECT * FROM staff_users WHERE lower(email) = :e FOR UPDATE"), {"e": email}
        ).mappings().first()
        if not user:
            burn_password_check(body.password)
            outcome = "bad"
        elif user["locked_until"] and user["locked_until"] > now:
            outcome = "locked"
        elif user["status"] != "active" or not verify_password(user["password_hash"], body.password):
            failures = user["failed_logins"] + 1
            locked = now + timedelta(minutes=s.login_lock_minutes) if failures >= s.login_max_failures else None
            conn.execute(
                text("UPDATE staff_users SET failed_logins = :f, locked_until = :l WHERE id = :id"),
                {"f": 0 if locked else failures, "l": locked, "id": user["id"]},
            )
            audit(conn, tenant["id"], "staff", user["id"], "auth.login_failed", "staff_user", user["id"],
                  meta={"locked": bool(locked)})
            outcome = "bad"
        else:
            conn.execute(text("UPDATE staff_users SET failed_logins = 0, locked_until = NULL WHERE id = :id"), {"id": user["id"]})
            outcome = "ok"
            setup = not user["mfa_enabled"]
            secret = None
            if setup:
                secret = new_totp_secret()
                conn.execute(text("UPDATE staff_users SET totp_secret_enc = :s WHERE id = :id"),
                             {"s": enc(secret), "id": user["id"]})
            token = mfa_token(user["id"], tenant["id"], user["token_version"], setup)

    if outcome == "locked":
        raise HTTPException(status_code=423, detail="Çok sayıda hatalı deneme. Hesap geçici olarak kilitlendi.")
    if outcome == "bad":
        raise HTTPException(status_code=401, detail=_GENERIC)

    if setup:
        return {
            "step": "mfa_setup",
            "mfa_token": token,
            "otpauth_uri": totp_uri(secret, user["email"], f"HakKöprü · {tenant['name']}"),
            "secret": secret,
        }
    return {"step": "mfa", "mfa_token": token}


@router.post("/mfa/verify")
def verify_mfa(body: MfaVerifyRequest, request: Request, tenant: dict = Depends(get_tenant)):
    enforce(request, f"mfa:{tenant['id']}", limit=10, window_seconds=600)
    try:
        claims = decode_token(body.mfa_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Doğrulama süresi doldu. Lütfen yeniden giriş yapın.")
    if claims.get("scope") not in ("mfa", "mfa_setup") or claims["tid"] != str(tenant["id"]):
        raise HTTPException(status_code=401, detail="Oturum geçersiz.")

    with tenant_tx(tenant["id"]) as conn:
        user = conn.execute(text("SELECT * FROM staff_users WHERE id = :id FOR UPDATE"), {"id": claims["sub"]}).mappings().first()
        if not user or user["status"] != "active" or user["token_version"] != claims["tv"] or not user["totp_secret_enc"]:
            raise HTTPException(status_code=401, detail="Oturum geçersiz.")
        step = verify_totp(dec(user["totp_secret_enc"]), body.code, user["totp_last_step"])
        if step is None:
            audit(conn, tenant["id"], "staff", user["id"], "auth.mfa_failed", "staff_user", user["id"])
            ok = False
        else:
            conn.execute(
                text("""UPDATE staff_users SET totp_last_step = :st, mfa_enabled = true, last_login_at = now()
                        WHERE id = :id"""),
                {"st": step, "id": user["id"]},
            )
            action = "auth.mfa_enrolled" if claims["scope"] == "mfa_setup" else "auth.login"
            audit(conn, tenant["id"], "staff", user["id"], action, "staff_user", user["id"])
            ok = True
    if not ok:
        raise HTTPException(status_code=401, detail="Doğrulama kodu hatalı.")
    return {"access_token": staff_access_token(user["id"], tenant["id"], user["token_version"])}


@router.get("/me")
def me(ctx: StaffContext = Depends(staff_ctx)):
    p = ctx.principal
    units = {u["id"]: u["name"] for u in ctx.conn.execute(text("SELECT id, name FROM org_units")).mappings()}
    return {
        "id": p.user_id,
        "email": p.email,
        "full_name": p.full_name,
        "tenant": {"slug": ctx.tenant["slug"], "name": ctx.tenant["name"]},
        "roles": [
            {"role": r["role"], "label": ROLE_LABELS[r["role"]], "org_unit": units.get(r["org_unit_id"]) if r["org_unit_id"] else None}
            for r in p.roles
        ],
        "permissions": {
            "handle_cases": p.has_any({"tenant_owner", "org_admin", "branch_manager", "case_worker", "legal_reviewer"}),
            "view_reports": p.has_any({"tenant_owner", "org_admin", "branch_manager", "auditor"}),
            "view_restricted": p.can_restricted,
        },
    }


@router.post("/logout")
def logout(ctx: StaffContext = Depends(staff_ctx)):
    """Tüm cihazlardaki oturumları sonlandırır (token_version artırılır)."""
    ctx.conn.execute(
        text("UPDATE staff_users SET token_version = token_version + 1 WHERE id = :id"), {"id": ctx.principal.user_id}
    )
    audit(ctx.conn, ctx.tenant["id"], "staff", ctx.principal.user_id, "auth.logout_all", "staff_user", ctx.principal.user_id)
    return {"ok": True}
