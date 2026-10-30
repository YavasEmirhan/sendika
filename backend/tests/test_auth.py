"""Kimlik doğrulama: kaba kuvvet, kilitleme, TOTP tekrar koruması, oturum sonlandırma."""
import pyotp

from .conftest import A, PASSWORD


def test_tracking_code_bruteforce_is_rate_limited(client):
    statuses = [client.post(f"/api/t/{A}/track", json={"code": f"AAAA-BBBB-{i:04d}"}).status_code for i in range(12)]
    assert statuses[:10] == [404] * 10
    assert statuses[10:] == [429, 429]


def test_account_locks_after_repeated_failures(client):
    email = f"genel.temsilci@{A}.test"
    for _ in range(5):
        assert client.post(f"/api/t/{A}/staff/login", json={"email": email, "password": "yanlis"}).status_code == 401
    r = client.post(f"/api/t/{A}/staff/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 423


def test_unknown_user_gets_same_error(client):
    r1 = client.post(f"/api/t/{A}/staff/login", json={"email": "yok@x.test", "password": "a"})
    r2 = client.post(f"/api/t/{A}/staff/login", json={"email": f"admin@{A}.test", "password": "a"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


def test_totp_code_cannot_be_reused(client, mfa_secrets):
    email = f"hukuk@{A}.test"
    totp = pyotp.TOTP(mfa_secrets[email])
    import time

    step = int(time.time()) // 30 + 1  # bir sonraki adım; diğer testlerle çakışmaz
    code = totp.generate_otp(step)
    t1 = client.post(f"/api/t/{A}/staff/login", json={"email": email, "password": PASSWORD}).json()["mfa_token"]
    assert client.post(f"/api/t/{A}/staff/mfa/verify", json={"mfa_token": t1, "code": code}).status_code == 200
    t2 = client.post(f"/api/t/{A}/staff/login", json={"email": email, "password": PASSWORD}).json()["mfa_token"]
    assert client.post(f"/api/t/{A}/staff/mfa/verify", json={"mfa_token": t2, "code": code}).status_code == 401


def test_mfa_token_is_not_an_access_token(client):
    t = client.post(f"/api/t/{A}/staff/login", json={"email": f"ist.mudur@{A}.test", "password": PASSWORD}).json()["mfa_token"]
    assert client.get(f"/api/t/{A}/staff/me", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_first_login_requires_mfa_setup(client):
    r = client.post(f"/api/t/{A}/staff/login", json={"email": f"ank.temsilci@{A}.test", "password": PASSWORD})
    body = r.json()
    assert body["step"] == "mfa_setup" and body["otpauth_uri"].startswith("otpauth://totp/")
    code = pyotp.TOTP(body["secret"]).now()
    r = client.post(f"/api/t/{A}/staff/mfa/verify", json={"mfa_token": body["mfa_token"], "code": code})
    assert r.status_code == 200
    # Kurulum tamamlandıktan sonra artık normal MFA adımı istenir
    r = client.post(f"/api/t/{A}/staff/login", json={"email": f"ank.temsilci@{A}.test", "password": PASSWORD})
    assert r.json()["step"] == "mfa"


def test_logout_ends_all_sessions(client, auth):
    h = auth.login(client, A, "bur.temsilci", fresh=True)
    assert client.get(f"/api/t/{A}/staff/me", headers=h).status_code == 200
    assert client.post(f"/api/t/{A}/staff/logout", headers=h).status_code == 200
    assert client.get(f"/api/t/{A}/staff/me", headers=h).status_code == 401
    auth.tokens.pop((A, f"bur.temsilci@{A}.test"), None)
