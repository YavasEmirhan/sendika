"""Kiracı izolasyonu: plandaki en kritik risk (PROJE_PLANI.md §15.7, test senaryosu 15)."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.config import get_settings
from app.db import resolve_tenant

from .conftest import A, B, staff_case_id, submit


@pytest.fixture(scope="module")
def app_engine():
    e = create_engine(get_settings().database_url)
    yield e
    e.dispose()


def _tenant_ids():
    return resolve_tenant(A)["id"], resolve_tenant(B)["id"]


def test_no_tenant_context_sees_nothing(app_engine):
    with app_engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM cases")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM staff_users")).scalar_one() == 0


def test_rls_hides_other_tenant_rows(app_engine):
    a, b = _tenant_ids()
    with app_engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(b)})
        assert conn.execute(text("SELECT count(*) FROM cases WHERE tenant_id = :a"), {"a": a}).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM cases")).scalar_one() > 0


def test_rls_blocks_writing_into_other_tenant(app_engine):
    a, b = _tenant_ids()
    with pytest.raises(DBAPIError):
        with app_engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(b)})
            conn.execute(
                text("INSERT INTO canned_responses (tenant_id, title, body) VALUES (:a, 'x', 'y')"), {"a": a}
            )


def test_tenant_id_is_immutable(app_engine):
    a, b = _tenant_ids()
    with pytest.raises(DBAPIError):
        with app_engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(a)})
            conn.execute(text("UPDATE canned_responses SET tenant_id = :b"), {"b": b})


def test_audit_log_is_append_only(app_engine):
    a, _ = _tenant_ids()
    for stmt in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events", "DELETE FROM case_messages"):
        with pytest.raises(ProgrammingError):
            with app_engine.begin() as conn:
                conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(a)})
                conn.execute(text(stmt))


def test_staff_token_of_tenant_b_rejected_on_tenant_a(client, auth):
    hb = auth.login(client, B, "admin")
    r = client.get(f"/api/t/{A}/staff/cases", headers=hb)
    assert r.status_code == 401


def test_case_id_from_other_tenant_is_not_found(client, auth):
    created = submit(client, slug=B, city="Ankara")
    hb = auth.login(client, B, "admin")
    b_case = staff_case_id(client, hb, created["reference_no"], slug=B)
    ha = auth.login(client, A, "admin")
    assert client.get(f"/api/t/{A}/staff/cases/{b_case}", headers=ha).status_code == 404
    r = client.post(f"/api/t/{A}/staff/cases/{b_case}/messages", headers=ha, json={"body": "x", "visibility": "public"})
    assert r.status_code == 404


def test_tracking_code_only_works_in_its_own_tenant(client):
    created = submit(client, slug=A)
    assert client.post(f"/api/t/{A}/track", json={"code": created["tracking_code"]}).status_code == 200
    assert client.post(f"/api/t/{B}/track", json={"code": created["tracking_code"]}).status_code == 404
