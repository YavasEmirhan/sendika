"""SQL migration dosyalarını sırayla uygular (tablo sahibi rolüyle).

Kullanım:  python -m scripts.migrate
"""
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import get_settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def migrate(admin_url: str | None = None) -> list[str]:
    engine = create_engine(admin_url or get_settings().database_admin_url)
    applied_now = []
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz DEFAULT now())"))
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in done:
            continue
        with engine.begin() as conn:
            # Parametresiz çalıştırılır ki SQL içindeki format('%I') yer tutucu sanılmasın.
            conn.connection.driver_connection.execute(path.read_text(encoding="utf-8"))
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": path.name})
        applied_now.append(path.name)
    engine.dispose()
    return applied_now


if __name__ == "__main__":
    applied = migrate()
    print("Uygulanan migration'lar:", ", ".join(applied) if applied else "yok (güncel)")
