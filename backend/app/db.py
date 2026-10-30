"""Veritabanı bağlantısı ve kiracı bağlamı.

Her istek kendi transaction'ında çalışır ve kiracı kimliği `SET LOCAL` ile
yalnızca o transaction'a bağlanır. Böylece havuzdaki bir bağlantı başka bir
isteğe geçtiğinde önceki kiracının bağlamını taşımaz.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10)


@contextmanager
def tenant_tx(tenant_id: UUID | str) -> Iterator[Connection]:
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        yield conn


@contextmanager
def no_tenant_tx() -> Iterator[Connection]:
    """Kiracı bağlamı olmayan işlemler (yalnızca `tenants` tablosu okunabilir)."""
    with get_engine().begin() as conn:
        yield conn


def resolve_tenant(slug: str) -> dict | None:
    with no_tenant_tx() as conn:
        row = conn.execute(
            text("SELECT id, slug, name, short_code, status, public_intro FROM tenants WHERE slug = :s"),
            {"s": slug},
        ).mappings().first()
    return dict(row) if row else None
