"""Kiracı içi yetkilendirme, gizlilik ve vaka iş akışı."""
from sqlalchemy import create_engine, text

from app.config import get_settings

from .conftest import A, staff_case_id, submit


def test_internal_note_never_reaches_applicant(client, auth):
    created = submit(client)
    h = auth.login(client, A, "ist.temsilci")
    cid = staff_case_id(client, h, created["reference_no"])
    client.post(f"/api/t/{A}/staff/cases/{cid}/messages", headers=h, json={"body": "GIZLI-IC-NOT", "visibility": "internal"})
    client.post(f"/api/t/{A}/staff/cases/{cid}/messages", headers=h, json={"body": "Merhaba", "visibility": "public"})

    r = client.post(f"/api/t/{A}/track", json={"code": created["tracking_code"]})
    assert r.status_code == 200
    assert "GIZLI-IC-NOT" not in r.text
    assert [m["body"] for m in r.json()["case"]["messages"]] == ["Merhaba"]


def test_branch_worker_cannot_see_other_branch(client, auth):
    bursa = submit(client, city="Bursa")
    h_ist = auth.login(client, A, "ist.temsilci")
    h_bur = auth.login(client, A, "bur.temsilci")
    cid = staff_case_id(client, h_bur, bursa["reference_no"])
    assert client.get(f"/api/t/{A}/staff/cases/{cid}", headers=h_ist).status_code == 404
    listed = client.get(f"/api/t/{A}/staff/cases", params={"view": "all"}, headers=h_ist).json()["items"]
    assert bursa["reference_no"] not in {i["reference_no"] for i in listed}


def test_restricted_case_only_for_legal_and_admin(client, auth):
    created = submit(client, category_key="taciz", city="İstanbul")
    h_legal = auth.login(client, A, "hukuk")
    cid = staff_case_id(client, h_legal, created["reference_no"])
    for handle in ("ist.temsilci", "ist.mudur", "genel.temsilci"):
        h = auth.login(client, A, handle)
        assert client.get(f"/api/t/{A}/staff/cases/{cid}", headers=h).status_code == 404, handle
    h_admin = auth.login(client, A, "admin")
    assert client.get(f"/api/t/{A}/staff/cases/{cid}", headers=h_admin).status_code == 200


def test_case_worker_can_only_self_assign(client, auth):
    created = submit(client)
    h = auth.login(client, A, "ist.temsilci")
    h_mgr = auth.login(client, A, "ist.mudur")
    cid = staff_case_id(client, h, created["reference_no"])
    mgr_id = client.get(f"/api/t/{A}/staff/me", headers=h_mgr).json()["id"]
    me_id = client.get(f"/api/t/{A}/staff/me", headers=h).json()["id"]
    assert client.post(f"/api/t/{A}/staff/cases/{cid}/assign", headers=h, json={"assignee_id": mgr_id}).status_code == 403
    r = client.post(f"/api/t/{A}/staff/cases/{cid}/assign", headers=h, json={"assignee_id": me_id})
    assert r.status_code == 200 and r.json()["status"] == "assigned"


def test_cannot_assign_someone_who_cannot_see_case(client, auth):
    created = submit(client, city="İstanbul")
    h_admin = auth.login(client, A, "admin")
    h_bur = auth.login(client, A, "bur.temsilci")
    cid = staff_case_id(client, h_admin, created["reference_no"])
    bur_id = client.get(f"/api/t/{A}/staff/me", headers=h_bur).json()["id"]
    r = client.post(f"/api/t/{A}/staff/cases/{cid}/assign", headers=h_admin, json={"assignee_id": bur_id})
    assert r.status_code == 422


def test_auditor_sees_reports_but_not_case_content(client, auth):
    created = submit(client)
    h_admin = auth.login(client, A, "admin")
    cid = staff_case_id(client, h_admin, created["reference_no"])
    h_aud = auth.login(client, A, "denetci")
    assert client.get(f"/api/t/{A}/staff/cases", headers=h_aud).status_code == 403
    assert client.get(f"/api/t/{A}/staff/cases/{cid}", headers=h_aud).status_code == 404
    r = client.get(f"/api/t/{A}/staff/reports/summary", headers=h_aud)
    assert r.status_code == 200 and r.json()["kpi"]["created"] > 0


def test_case_worker_has_no_reports(client, auth):
    h = auth.login(client, A, "ist.temsilci")
    assert client.get(f"/api/t/{A}/staff/reports/summary", headers=h).status_code == 403


def test_contact_is_masked_and_reveal_is_audited(client, auth):
    created = submit(client, is_anonymous=False, contact_method="phone", contact_value="0555 123 45 67", contact_name="Deneme Kişi")
    h = auth.login(client, A, "ist.temsilci")
    cid = staff_case_id(client, h, created["reference_no"])
    detail = client.get(f"/api/t/{A}/staff/cases/{cid}", headers=h).json()
    assert "123" not in (detail["contact"]["masked"] or "")
    assert client.post(f"/api/t/{A}/staff/cases/{cid}/reveal-contact", headers=h, json={"reason": ""}).status_code == 422
    r = client.post(f"/api/t/{A}/staff/cases/{cid}/reveal-contact", headers=h, json={"reason": "Geri arama talebi"})
    assert r.json()["value"] == "0555 123 45 67"
    h_admin = auth.login(client, A, "admin")
    log = client.get(f"/api/t/{A}/staff/cases/{cid}", headers=h_admin).json()["access_log"]
    assert any(e["action"] == "case.contact_revealed" and e["reason"] == "Geri arama talebi" for e in log)


def test_sensitive_text_is_encrypted_at_rest(client):
    created = submit(client, description="SIFRELI-ACIKLAMA-12345 ücret ödenmedi", is_anonymous=False,
                     contact_method="email", contact_value="kisi@example.com")
    engine = create_engine(get_settings().database_admin_url)
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', (SELECT id::text FROM tenants WHERE slug = :s), true)"), {"s": A})
        row = conn.execute(text("SELECT row_to_json(c)::text FROM cases c WHERE reference_no = :r"),
                           {"r": created["reference_no"]}).scalar_one()
    engine.dispose()
    assert "SIFRELI-ACIKLAMA" not in row
    assert "kisi@example.com" not in row
    assert created["tracking_code"].replace("-", "") not in row


def test_status_machine_and_first_response(client, auth):
    created = submit(client)
    h = auth.login(client, A, "ist.temsilci")
    cid = staff_case_id(client, h, created["reference_no"])
    assert client.post(f"/api/t/{A}/staff/cases/{cid}/status", headers=h, json={"status": "resolved"}).status_code == 422
    r = client.post(f"/api/t/{A}/staff/cases/{cid}/messages", headers=h, json={"body": "Yanıt", "visibility": "public"})
    assert r.json()["first_responded_at"] is not None and r.json()["status"] == "in_progress"
    r = client.post(f"/api/t/{A}/staff/cases/{cid}/status", headers=h, json={"status": "waiting_info"})
    assert r.status_code == 200
    # Başvuru sahibi yanıtlayınca vaka tekrar işleme döner
    token = client.post(f"/api/t/{A}/track", json={"code": created["tracking_code"]}).json()["applicant_token"]
    r = client.post(f"/api/t/{A}/track/messages", headers={"Authorization": f"Bearer {token}"}, json={"body": "Bilgi ekledim"})
    assert r.status_code == 201 and r.json()["stage"]["key"] == "reviewing"
    r = client.post(f"/api/t/{A}/staff/cases/{cid}/status", headers=h,
                    json={"status": "resolved", "closure_code": "resolved_info_given"})
    assert r.json()["status"] == "resolved"
    r = client.post(f"/api/t/{A}/track/messages", headers={"Authorization": f"Bearer {token}"}, json={"body": "x"})
    assert r.status_code == 409


def test_consent_is_recorded_and_withdrawable(client):
    info = client.get(f"/api/t/{A}").json()
    created = submit(client, explicit_consent_notice_id=info["explicit_consent"]["id"])
    tr = client.post(f"/api/t/{A}/track", json={"code": created["tracking_code"]}).json()
    assert tr["case"]["consent_status"] == "given"
    h = {"Authorization": f"Bearer {tr['applicant_token']}"}
    r = client.post(f"/api/t/{A}/track/consent/withdraw", headers=h)
    assert r.status_code == 200 and r.json()["consent_status"] == "withdrawn"


def test_stale_privacy_notice_is_rejected(client):
    import uuid

    info = client.get(f"/api/t/{A}").json()
    r = client.post(f"/api/t/{A}/cases", json={
        "category_key": "ucret", "subject": "Deneme", "description": "Eski metinle gönderim denemesi.",
        "is_anonymous": True, "contact_method": "none", "privacy_notice_id": str(uuid.uuid4()),
    })
    assert r.status_code == 409
    assert info["privacy_notice"]["id"]


def test_non_anonymous_requires_contact(client):
    info = client.get(f"/api/t/{A}").json()
    r = client.post(f"/api/t/{A}/cases", json={
        "category_key": "ucret", "subject": "Deneme", "description": "İletişim olmadan isimli başvuru.",
        "is_anonymous": False, "contact_method": "none", "privacy_notice_id": info["privacy_notice"]["id"],
    })
    assert r.status_code == 422
