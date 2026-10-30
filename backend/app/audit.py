"""Denetim kaydı. Hassas alanların değeri asla kayda yazılmaz; yalnızca olay yazılır."""
import json
from uuid import UUID

from sqlalchemy import Connection, text


def audit(
    conn: Connection,
    tenant_id: UUID,
    actor_type: str,
    actor_id: UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: UUID | None = None,
    reason: str | None = None,
    meta: dict | None = None,
) -> None:
    conn.execute(
        text(
            """INSERT INTO audit_events
               (tenant_id, actor_type, actor_id, action, target_type, target_id, reason, meta)
               VALUES (:tid, :at, :aid, :act, :tt, :tg, :r, CAST(:m AS jsonb))"""
        ),
        {
            "tid": tenant_id,
            "at": actor_type,
            "aid": actor_id,
            "act": action,
            "tt": target_type,
            "tg": target_id,
            "r": reason,
            "m": json.dumps(meta or {}),
        },
    )


def case_event(
    conn: Connection,
    tenant_id: UUID,
    case_id: UUID,
    actor_type: str,
    actor_id: UUID | None,
    event_type: str,
    from_value: str | None = None,
    to_value: str | None = None,
) -> None:
    conn.execute(
        text(
            """INSERT INTO case_events (tenant_id, case_id, actor_type, actor_id, event_type, from_value, to_value)
               VALUES (:tid, :cid, :at, :aid, :et, :f, :t)"""
        ),
        {"tid": tenant_id, "cid": case_id, "at": actor_type, "aid": actor_id, "et": event_type, "f": from_value, "t": to_value},
    )
