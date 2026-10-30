"""Vaka iş kuralları: oluşturma, yönlendirme, başvuru sahibi görünümü."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Connection, text

from ..audit import audit, case_event
from ..domain import CLOSED_STATUSES, PUBLIC_STAGE, public_stage
from ..schemas import CaseCreate
from ..security import dec, enc, new_tracking_code, tracking_code_hash
from ..sla import first_response_due


def _next_reference(conn: Connection, tenant: dict, now: datetime) -> str:
    year = now.year
    value = conn.execute(
        text(
            """INSERT INTO tenant_counters (tenant_id, year, last_value) VALUES (:t, :y, 1)
               ON CONFLICT (tenant_id, year) DO UPDATE SET last_value = tenant_counters.last_value + 1
               RETURNING last_value"""
        ),
        {"t": tenant["id"], "y": year},
    ).scalar_one()
    return f"{tenant['short_code']}-{year}-{value:05d}"


def route_case(conn: Connection, category: dict, city: str | None) -> tuple[UUID, str]:
    """Açıklanabilir, kural tabanlı yönlendirme. Döner: (birim, kural açıklaması)."""
    if category["default_org_unit_id"]:
        return category["default_org_unit_id"], "Konu bu birime yönlendirilir"
    if city:
        row = conn.execute(
            text(
                """SELECT id FROM org_units
                   WHERE lower(:c) = ANY(SELECT lower(x) FROM unnest(service_cities) x)
                   ORDER BY kind = 'branch' DESC LIMIT 1"""
            ),
            {"c": city.strip()},
        ).first()
        if row:
            return row[0], "İl bu şubenin hizmet alanında"
    hq = conn.execute(text("SELECT id FROM org_units WHERE kind = 'headquarters' LIMIT 1")).scalar_one()
    return hq, "Eşleşen şube yok, genel merkeze yönlendirildi"


def active_notice(conn: Connection, kind: str) -> dict | None:
    row = conn.execute(
        text(
            """SELECT id, kind, version, title, summary, body FROM notices
               WHERE kind = :k AND active ORDER BY created_at DESC LIMIT 1"""
        ),
        {"k": kind},
    ).mappings().first()
    return dict(row) if row else None


def create_case(
    conn: Connection,
    tenant: dict,
    data: CaseCreate,
    *,
    channel: str = "web",
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    category = conn.execute(
        text("SELECT * FROM categories WHERE key = :k AND active"), {"k": data.category_key}
    ).mappings().first()
    if not category:
        raise HTTPException(status_code=422, detail="Geçersiz konu.")

    notice = active_notice(conn, "privacy_notice")
    if not notice or notice["id"] != data.privacy_notice_id:
        # Kullanıcıya gösterilen metin güncel değilse başvuruyu almıyoruz: kanıt tutarlılığı.
        raise HTTPException(status_code=409, detail="Aydınlatma metni güncellendi. Lütfen sayfayı yenileyin.")
    consent_notice = None
    if data.explicit_consent_notice_id:
        consent_notice = active_notice(conn, "explicit_consent")
        if not consent_notice or consent_notice["id"] != data.explicit_consent_notice_id:
            raise HTTPException(status_code=409, detail="Açık rıza metni güncellendi. Lütfen sayfayı yenileyin.")

    org_unit_id, route_reason = route_case(conn, dict(category), data.city)
    priority = category["default_priority"]
    tracking_code = new_tracking_code()
    reference_no = _next_reference(conn, tenant, now)

    case_id = conn.execute(
        text(
            """INSERT INTO cases (
                   tenant_id, reference_no, tracking_code_hash, channel, category_id, org_unit_id,
                   subject_enc, description_enc, workplace_enc, city, status, priority, sensitivity,
                   is_anonymous, contact_method, contact_value_enc, contact_name_enc, safe_contact_note_enc,
                   first_response_due_at, created_at, updated_at)
               VALUES (
                   :tid, :ref, :th, :ch, :cat, :unit,
                   :subj, :desc, :wp, :city, 'received', :prio, :sens,
                   :anon, :cm, :cv, :cn, :sn,
                   :due, :now, :now)
               RETURNING id"""
        ),
        {
            "tid": tenant["id"],
            "ref": reference_no,
            "th": tracking_code_hash(tracking_code),
            "ch": channel,
            "cat": category["id"],
            "unit": org_unit_id,
            "subj": enc(data.subject.strip()),
            "desc": enc(data.description.strip()),
            "wp": enc(data.workplace.strip() if data.workplace else None),
            "city": data.city.strip() if data.city else None,
            "prio": priority,
            "sens": category["default_sensitivity"],
            "anon": data.is_anonymous,
            "cm": data.contact_method,
            "cv": enc(data.contact_value),
            "cn": enc(data.contact_name),
            "sn": enc(data.safe_contact_note),
            "due": first_response_due(now, priority),
            "now": now,
        },
    ).scalar_one()

    conn.execute(
        text("INSERT INTO notice_receipts (tenant_id, case_id, notice_id, shown_at) VALUES (:t, :c, :n, :now)"),
        {"t": tenant["id"], "c": case_id, "n": notice["id"], "now": now},
    )
    if consent_notice:
        conn.execute(
            text(
                """INSERT INTO consent_records (tenant_id, case_id, notice_id, status, given_at)
                   VALUES (:t, :c, :n, 'given', :now)"""
            ),
            {"t": tenant["id"], "c": case_id, "n": consent_notice["id"], "now": now},
        )
    case_event(conn, tenant["id"], case_id, "applicant", None, "created", None, "received")
    case_event(conn, tenant["id"], case_id, "system", None, "routed", None, route_reason)
    audit(conn, tenant["id"], "applicant", None, "case.created", "case", case_id, meta={"channel": channel})

    case = conn.execute(text("SELECT * FROM cases WHERE id = :id"), {"id": case_id}).mappings().one()
    return {"case": dict(case), "tracking_code": tracking_code}


def find_by_tracking_code(conn: Connection, code: str) -> dict | None:
    row = conn.execute(
        text("SELECT * FROM cases WHERE tracking_code_hash = :h"), {"h": tracking_code_hash(code)}
    ).mappings().first()
    return dict(row) if row else None


def applicant_view(conn: Connection, case_id: UUID) -> dict:
    """Başvuru sahibinin gördüğü her şey. İç notlar ve iç durumlar burada yer almaz."""
    c = conn.execute(
        text(
            """SELECT c.*, cat.label AS category_label FROM cases c
               JOIN categories cat ON cat.id = c.category_id WHERE c.id = :id"""
        ),
        {"id": case_id},
    ).mappings().first()
    if not c:
        raise HTTPException(status_code=404, detail="Başvuru bulunamadı.")

    events = conn.execute(
        text(
            """SELECT to_value, created_at FROM case_events
               WHERE case_id = :id AND event_type IN ('created', 'status_changed') ORDER BY created_at"""
        ),
        {"id": case_id},
    ).mappings().all()
    timeline = []
    for e in events:
        if e["to_value"] not in PUBLIC_STAGE:
            continue
        st = public_stage(e["to_value"])
        if timeline and timeline[-1]["key"] == st["key"]:
            continue
        timeline.append({**st, "at": e["created_at"]})

    messages = conn.execute(
        text(
            """SELECT m.id, m.author_type, m.body_enc, m.created_at, s.full_name
               FROM case_messages m LEFT JOIN staff_users s ON s.id = m.author_id
               WHERE m.case_id = :id AND m.visibility = 'public' ORDER BY m.created_at"""
        ),
        {"id": case_id},
    ).mappings().all()

    consent = conn.execute(
        text("SELECT status FROM consent_records WHERE case_id = :id ORDER BY given_at DESC LIMIT 1"),
        {"id": case_id},
    ).scalar()

    return {
        "reference_no": c["reference_no"],
        "category": c["category_label"],
        "subject": dec(c["subject_enc"]),
        "created_at": c["created_at"],
        "stage": public_stage(c["status"]),
        "timeline": timeline,
        "messages": [
            {
                "id": m["id"],
                "from": m["author_type"],
                # Personelin tam adı yerine yalnızca ilk adı gösterilir.
                "author": (m["full_name"] or "").split(" ")[0] if m["author_type"] == "staff" else None,
                "body": dec(m["body_enc"]),
                "at": m["created_at"],
            }
            for m in messages
        ],
        "can_reply": c["status"] not in CLOSED_STATUSES,
        "is_anonymous": c["is_anonymous"],
        "consent_status": consent,
    }


def applicant_reply(conn: Connection, tenant: dict, case_id: UUID, body: str) -> None:
    c = conn.execute(text("SELECT id, status, assignee_id FROM cases WHERE id = :id FOR UPDATE"), {"id": case_id}).mappings().one()
    if c["status"] in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="Bu başvuru sonuçlandı; yeni mesaj gönderilemez.")
    conn.execute(
        text(
            """INSERT INTO case_messages (tenant_id, case_id, author_type, visibility, body_enc)
               VALUES (:t, :c, 'applicant', 'public', :b)"""
        ),
        {"t": tenant["id"], "c": case_id, "b": enc(body.strip())},
    )
    if c["status"] == "waiting_info":
        new_status = "in_progress" if c["assignee_id"] else "triage"
        conn.execute(text("UPDATE cases SET status = :s, updated_at = now() WHERE id = :id"), {"s": new_status, "id": case_id})
        case_event(conn, tenant["id"], case_id, "applicant", None, "status_changed", "waiting_info", new_status)
    else:
        conn.execute(text("UPDATE cases SET updated_at = now() WHERE id = :id"), {"id": case_id})
    audit(conn, tenant["id"], "applicant", None, "case.applicant_message", "case", case_id)
