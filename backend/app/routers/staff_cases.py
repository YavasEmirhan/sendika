"""Sendika paneli: gelen kutusu, vaka detayı ve vaka işlemleri."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from ..audit import audit, case_event
from ..authz import AUDIT_ROLES, HANDLER_ROLES, ROLE_LABELS, build_principal
from ..deps import StaffContext, staff_ctx
from ..domain import CLOSED_STATUSES, CLOSURE_CODES, STATUS_LABELS, TRANSITIONS, public_stage
from ..schemas import AssignRequest, PriorityRequest, RevealRequest, StaffMessageCreate, StatusRequest
from ..security import dec, enc
from ..sla import PRIORITY_LABELS, first_response_due

router = APIRouter(prefix="/api/t/{slug}/staff", tags=["staff-cases"])


def _mask(value: str | None, method: str) -> str | None:
    if not value:
        return None
    if method == "email" and "@" in value:
        name, domain = value.split("@", 1)
        return f"{name[:1]}***@{domain}"
    digits = "".join(ch for ch in value if ch.isdigit())
    return f"*** *** {digits[-4:-2]} {digits[-2:]}" if len(digits) >= 4 else "***"


def _load_case(ctx: StaffContext, case_id: UUID, lock: bool = False) -> dict:
    row = ctx.conn.execute(
        text("SELECT * FROM cases WHERE id = :id" + (" FOR UPDATE" if lock else "")), {"id": case_id}
    ).mappings().first()
    # Başka kiracının vakası RLS nedeniyle zaten görünmez; kapsam dışı vaka da
    # "bulunamadı" döner ki varlığı sızmasın.
    if not row or not ctx.principal.sees_case(row):
        raise HTTPException(status_code=404, detail="Vaka bulunamadı.")
    return dict(row)


@router.get("/meta")
def meta(ctx: StaffContext = Depends(staff_ctx)):
    conn = ctx.conn
    return {
        "statuses": [{"key": k, "label": v} for k, v in STATUS_LABELS.items()],
        "transitions": {k: sorted(v) for k, v in TRANSITIONS.items()},
        "priorities": [{"key": k, "label": v} for k, v in PRIORITY_LABELS.items()],
        "closure_codes": [{"key": k, "label": v} for k, v in CLOSURE_CODES.items()],
        "org_units": [
            dict(r) for r in conn.execute(text("SELECT id, name, kind, parent_id FROM org_units ORDER BY kind, name")).mappings()
            if ctx.principal.can_handle_unit(r["id"]) or ctx.principal.has_any(AUDIT_ROLES)
        ],
        "categories": [dict(r) for r in conn.execute(text("SELECT id, key, label FROM categories ORDER BY sort_order")).mappings()],
        "canned_responses": [dict(r) for r in conn.execute(text("SELECT id, title, body FROM canned_responses ORDER BY title")).mappings()],
    }


@router.get("/cases")
def list_cases(
    ctx: StaffContext = Depends(staff_ctx),
    view: str = Query("open", pattern="^(open|mine|unassigned|overdue|waiting|closed|all)$"),
    org_unit_id: UUID | None = None,
    category_id: UUID | None = None,
    priority: str | None = Query(None, pattern="^P[1-4]$"),
    q: str | None = Query(None, max_length=40),
):
    p = ctx.principal
    p.require_any(HANDLER_ROLES)
    scope_sql, params = p.case_scope_sql()
    where = [scope_sql]
    closed = "('resolved','closed_timeout')"
    if view == "open":
        where.append(f"c.status NOT IN {closed}")
    elif view == "mine":
        where.append(f"c.assignee_id = :me AND c.status NOT IN {closed}")
        params["me"] = p.user_id
    elif view == "unassigned":
        where.append(f"c.assignee_id IS NULL AND c.status NOT IN {closed}")
    elif view == "overdue":
        where.append(f"c.first_responded_at IS NULL AND c.first_response_due_at < now() AND c.status NOT IN {closed}")
    elif view == "waiting":
        where.append("c.status = 'waiting_info'")
    elif view == "closed":
        where.append(f"c.status IN {closed}")
    if org_unit_id:
        where.append("c.org_unit_id = :unit")
        params["unit"] = org_unit_id
    if category_id:
        where.append("c.category_id = :cat")
        params["cat"] = category_id
    if priority:
        where.append("c.priority = :prio")
        params["prio"] = priority
    if q:
        # Serbest metin şifreli olduğu için yalnızca başvuru numarasıyla arama yapılır.
        where.append("c.reference_no ILIKE :q")
        params["q"] = f"%{q.strip()}%"

    rows = ctx.conn.execute(
        text(
            f"""SELECT c.id, c.reference_no, c.subject_enc, c.status, c.priority, c.sensitivity, c.city,
                       c.is_anonymous, c.first_response_due_at, c.first_responded_at, c.created_at, c.updated_at,
                       cat.label AS category, u.name AS org_unit, s.full_name AS assignee, c.assignee_id,
                       (SELECT max(m.created_at) FROM case_messages m
                         WHERE m.case_id = c.id AND m.author_type = 'applicant') AS last_applicant_message_at
                FROM cases c
                JOIN categories cat ON cat.id = c.category_id
                JOIN org_units u ON u.id = c.org_unit_id
                LEFT JOIN staff_users s ON s.id = c.assignee_id
                WHERE {' AND '.join(where)}
                ORDER BY (c.first_responded_at IS NULL AND c.status NOT IN {closed}) DESC,
                         c.priority, c.first_response_due_at
                LIMIT 200"""
        ),
        params,
    ).mappings().all()

    now = datetime.now(UTC)
    counts = ctx.conn.execute(
        text(
            f"""SELECT
                  count(*) FILTER (WHERE c.status NOT IN {closed}) AS open,
                  count(*) FILTER (WHERE c.assignee_id = :me2 AND c.status NOT IN {closed}) AS mine,
                  count(*) FILTER (WHERE c.assignee_id IS NULL AND c.status NOT IN {closed}) AS unassigned,
                  count(*) FILTER (WHERE c.first_responded_at IS NULL AND c.first_response_due_at < now()
                                   AND c.status NOT IN {closed}) AS overdue,
                  count(*) FILTER (WHERE c.status = 'waiting_info') AS waiting
                FROM cases c WHERE {scope_sql}"""
        ),
        {**p.case_scope_sql()[1], "me2": p.user_id},
    ).mappings().one()

    return {
        "counts": dict(counts),
        "items": [
            {
                "id": r["id"],
                "reference_no": r["reference_no"],
                "subject": dec(r["subject_enc"]),
                "category": r["category"],
                "org_unit": r["org_unit"],
                "city": r["city"],
                "status": r["status"],
                "status_label": STATUS_LABELS[r["status"]],
                "priority": r["priority"],
                "sensitivity": r["sensitivity"],
                "is_anonymous": r["is_anonymous"],
                "assignee": r["assignee"],
                "assignee_id": r["assignee_id"],
                "first_response_due_at": r["first_response_due_at"],
                "first_responded_at": r["first_responded_at"],
                "is_overdue": r["first_responded_at"] is None
                and r["status"] not in CLOSED_STATUSES
                and r["first_response_due_at"] < now,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "awaiting_reply": bool(r["last_applicant_message_at"]),
            }
            for r in rows
        ],
    }


def _case_detail(ctx: StaffContext, case_id: UUID) -> dict:
    conn = ctx.conn
    c = conn.execute(
        text(
            """SELECT c.*, cat.label AS category, u.name AS org_unit, s.full_name AS assignee
               FROM cases c JOIN categories cat ON cat.id = c.category_id
               JOIN org_units u ON u.id = c.org_unit_id
               LEFT JOIN staff_users s ON s.id = c.assignee_id WHERE c.id = :id"""
        ),
        {"id": case_id},
    ).mappings().one()
    messages = conn.execute(
        text(
            """SELECT m.id, m.author_type, m.visibility, m.body_enc, m.created_at, s.full_name
               FROM case_messages m LEFT JOIN staff_users s ON s.id = m.author_id
               WHERE m.case_id = :id ORDER BY m.created_at"""
        ),
        {"id": case_id},
    ).mappings().all()
    events = conn.execute(
        text(
            """SELECT e.event_type, e.from_value, e.to_value, e.actor_type, e.created_at, s.full_name,
                      a.full_name AS assignee_name
               FROM case_events e LEFT JOIN staff_users s ON s.id = e.actor_id
               LEFT JOIN staff_users a ON e.event_type = 'assigned' AND a.id::text = e.to_value
               WHERE e.case_id = :id ORDER BY e.created_at"""
        ),
        {"id": case_id},
    ).mappings().all()
    consent = conn.execute(
        text(
            """SELECT r.status, r.given_at, r.withdrawn_at, n.version FROM consent_records r
               JOIN notices n ON n.id = r.notice_id WHERE r.case_id = :id ORDER BY r.given_at DESC LIMIT 1"""
        ),
        {"id": case_id},
    ).mappings().first()
    notice = conn.execute(
        text(
            """SELECT n.version, r.shown_at FROM notice_receipts r JOIN notices n ON n.id = r.notice_id
               WHERE r.case_id = :id ORDER BY r.shown_at DESC LIMIT 1"""
        ),
        {"id": case_id},
    ).mappings().first()

    access_log = None
    if ctx.principal.has_any(AUDIT_ROLES):
        access_log = [
            dict(r)
            for r in conn.execute(
                text(
                    """SELECT a.action, a.reason, a.created_at, s.full_name AS actor
                       FROM audit_events a LEFT JOIN staff_users s ON s.id = a.actor_id
                       WHERE a.target_type = 'case' AND a.target_id = :id AND a.actor_type = 'staff'
                       ORDER BY a.created_at DESC LIMIT 50"""
                ),
                {"id": case_id},
            ).mappings()
        ]

    now = datetime.now(UTC)
    return {
        "id": c["id"],
        "reference_no": c["reference_no"],
        "channel": c["channel"],
        "category": c["category"],
        "category_id": c["category_id"],
        "org_unit": c["org_unit"],
        "org_unit_id": c["org_unit_id"],
        "subject": dec(c["subject_enc"]),
        "description": dec(c["description_enc"]),
        "workplace": dec(c["workplace_enc"]),
        "city": c["city"],
        "status": c["status"],
        "status_label": STATUS_LABELS[c["status"]],
        "public_stage": public_stage(c["status"]),
        "allowed_transitions": sorted(TRANSITIONS[c["status"]]),
        "priority": c["priority"],
        "sensitivity": c["sensitivity"],
        "assignee_id": c["assignee_id"],
        "assignee": c["assignee"],
        "is_anonymous": c["is_anonymous"],
        "contact": {
            "method": c["contact_method"],
            "masked": _mask(dec(c["contact_value_enc"]), c["contact_method"]),
            "has_name": c["contact_name_enc"] is not None,
            "safe_contact_note": dec(c["safe_contact_note_enc"]),
        },
        "first_response_due_at": c["first_response_due_at"],
        "first_responded_at": c["first_responded_at"],
        "is_overdue": c["first_responded_at"] is None and c["status"] not in CLOSED_STATUSES and c["first_response_due_at"] < now,
        "closure_code": c["closure_code"],
        "closure_label": CLOSURE_CODES.get(c["closure_code"]) if c["closure_code"] else None,
        "created_at": c["created_at"],
        "updated_at": c["updated_at"],
        "messages": [
            {
                "id": m["id"],
                "author_type": m["author_type"],
                "author": m["full_name"],
                "visibility": m["visibility"],
                "body": dec(m["body_enc"]),
                "created_at": m["created_at"],
            }
            for m in messages
        ],
        "events": [dict(e) for e in events],
        "privacy": {
            "notice_version": notice["version"] if notice else None,
            "notice_shown_at": notice["shown_at"] if notice else None,
            "consent": dict(consent) if consent else None,
        },
        "permissions": {
            "assign_others": ctx.principal.can_assign_others(c["org_unit_id"]),
        },
        "access_log": access_log,
    }


@router.get("/cases/{case_id}")
def get_case(case_id: UUID, ctx: StaffContext = Depends(staff_ctx)):
    _load_case(ctx, case_id)
    audit(ctx.conn, ctx.tenant["id"], "staff", ctx.principal.user_id, "case.viewed", "case", case_id)
    return _case_detail(ctx, case_id)


@router.post("/cases/{case_id}/reveal-contact")
def reveal_contact(case_id: UUID, body: RevealRequest, ctx: StaffContext = Depends(staff_ctx)):
    """İletişim bilgisi varsayılan olarak maskelidir; açmak gerekçe ister ve kayda geçer."""
    c = _load_case(ctx, case_id)
    audit(ctx.conn, ctx.tenant["id"], "staff", ctx.principal.user_id, "case.contact_revealed", "case", case_id,
          reason=body.reason.strip())
    return {
        "method": c["contact_method"],
        "value": dec(c["contact_value_enc"]),
        "name": dec(c["contact_name_enc"]),
    }


@router.get("/cases/{case_id}/assignees")
def assignees(case_id: UUID, ctx: StaffContext = Depends(staff_ctx)):
    c = _load_case(ctx, case_id)
    rows = ctx.conn.execute(
        text(
            """SELECT DISTINCT s.id, s.full_name, r.role, r.org_unit_id FROM staff_users s
               JOIN role_assignments r ON r.user_id = s.id
               WHERE s.status = 'active' AND r.role = ANY(:roles)"""
        ),
        {"roles": list(HANDLER_ROLES)},
    ).mappings().all()
    # Atanacak kişi vakayı görebilmeli: birim kapsamı ve hassasiyet kontrolü.
    out: dict = {}
    for r in rows:
        if r["id"] in out:
            continue
        candidate = build_principal(ctx.conn, {"id": r["id"], "tenant_id": ctx.tenant["id"], "email": "", "full_name": r["full_name"]})
        if candidate.sees_case(c):
            out[r["id"]] = {
                "id": r["id"],
                "full_name": r["full_name"],
                "roles": sorted({ROLE_LABELS[x["role"]] for x in candidate.roles}),
            }
    return sorted(out.values(), key=lambda x: x["full_name"])


@router.post("/cases/{case_id}/assign")
def assign(case_id: UUID, body: AssignRequest, ctx: StaffContext = Depends(staff_ctx)):
    p = ctx.principal
    c = _load_case(ctx, case_id, lock=True)
    if c["status"] in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="Kapalı vaka atanamaz; önce yeniden açın.")
    target = body.assignee_id
    releasing_own = target is None and c["assignee_id"] == p.user_id
    if target != p.user_id and not releasing_own and not p.can_assign_others(c["org_unit_id"]):
        raise HTTPException(status_code=403, detail="Yalnızca kendinize atama yapabilirsiniz.")
    if target is not None:
        u = ctx.conn.execute(
            text("SELECT id, tenant_id, email, full_name FROM staff_users WHERE id = :id AND status = 'active'"),
            {"id": target},
        ).mappings().first()
        if not u or not build_principal(ctx.conn, dict(u)).sees_case(c):
            raise HTTPException(status_code=422, detail="Bu kişi vakayı göremeyeceği için atanamaz.")
    old = c["assignee_id"]
    new_status = c["status"]
    if target and c["status"] in ("received", "triage"):
        new_status = "assigned"
    ctx.conn.execute(
        text("UPDATE cases SET assignee_id = :a, status = :s, updated_at = now() WHERE id = :id"),
        {"a": target, "s": new_status, "id": case_id},
    )
    case_event(ctx.conn, ctx.tenant["id"], case_id, "staff", p.user_id, "assigned",
               str(old) if old else None, str(target) if target else None)
    if new_status != c["status"]:
        case_event(ctx.conn, ctx.tenant["id"], case_id, "staff", p.user_id, "status_changed", c["status"], new_status)
    audit(ctx.conn, ctx.tenant["id"], "staff", p.user_id, "case.assigned", "case", case_id,
          meta={"assignee_id": str(target) if target else None})
    return _case_detail(ctx, case_id)


@router.post("/cases/{case_id}/status")
def change_status(case_id: UUID, body: StatusRequest, ctx: StaffContext = Depends(staff_ctx)):
    p = ctx.principal
    c = _load_case(ctx, case_id, lock=True)
    if body.status not in TRANSITIONS[c["status"]]:
        raise HTTPException(
            status_code=409,
            detail=f"'{STATUS_LABELS[c['status']]}' durumundan '{STATUS_LABELS[body.status]}' durumuna geçilemez.",
        )
    closure = None
    if body.status in CLOSED_STATUSES:
        closure = body.closure_code or ("no_response" if body.status == "closed_timeout" else None)
        if closure not in CLOSURE_CODES:
            raise HTTPException(status_code=422, detail="Vakayı kapatmak için bir sonuç kodu seçin.")
    reopened = c["status"] in CLOSED_STATUSES
    ctx.conn.execute(
        text(
            """UPDATE cases SET status = :s, closure_code = :cc,
                   resolved_at = CASE WHEN :closing THEN now() ELSE NULL END,
                   updated_at = now()
               WHERE id = :id"""
        ),
        {"s": body.status, "cc": closure, "closing": body.status in CLOSED_STATUSES, "id": case_id},
    )
    case_event(ctx.conn, ctx.tenant["id"], case_id, "staff", p.user_id, "reopened" if reopened else "status_changed",
               c["status"], body.status)
    if reopened:
        case_event(ctx.conn, ctx.tenant["id"], case_id, "staff", p.user_id, "status_changed", c["status"], body.status)
    audit(ctx.conn, ctx.tenant["id"], "staff", p.user_id, "case.status_changed", "case", case_id,
          meta={"from": c["status"], "to": body.status, "closure_code": closure})
    return _case_detail(ctx, case_id)


@router.post("/cases/{case_id}/priority")
def change_priority(case_id: UUID, body: PriorityRequest, ctx: StaffContext = Depends(staff_ctx)):
    p = ctx.principal
    c = _load_case(ctx, case_id, lock=True)
    if body.priority == c["priority"]:
        return _case_detail(ctx, case_id)
    # Henüz yanıt verilmediyse ilk yanıt hedefi yeni önceliğe göre yeniden hesaplanır.
    due = c["first_response_due_at"]
    if c["first_responded_at"] is None:
        due = first_response_due(c["created_at"], body.priority)
    ctx.conn.execute(
        text("UPDATE cases SET priority = :p, first_response_due_at = :d, updated_at = now() WHERE id = :id"),
        {"p": body.priority, "d": due, "id": case_id},
    )
    case_event(ctx.conn, ctx.tenant["id"], case_id, "staff", p.user_id, "priority_changed", c["priority"], body.priority)
    audit(ctx.conn, ctx.tenant["id"], "staff", p.user_id, "case.priority_changed", "case", case_id,
          meta={"from": c["priority"], "to": body.priority})
    return _case_detail(ctx, case_id)


@router.post("/cases/{case_id}/messages", status_code=201)
def add_message(case_id: UUID, body: StaffMessageCreate, ctx: StaffContext = Depends(staff_ctx)):
    p = ctx.principal
    c = _load_case(ctx, case_id, lock=True)
    if body.visibility == "public" and c["status"] in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="Kapalı vakaya yanıt gönderilemez; önce yeniden açın.")
    ctx.conn.execute(
        text(
            """INSERT INTO case_messages (tenant_id, case_id, author_type, author_id, visibility, body_enc)
               VALUES (:t, :c, 'staff', :a, :v, :b)"""
        ),
        {"t": ctx.tenant["id"], "c": case_id, "a": p.user_id, "v": body.visibility, "b": enc(body.body.strip())},
    )
    updates = "updated_at = now()"
    # "Anlamlı ilk yanıt": otomatik mesaj değil, başvuru sahibine giden ilk insan yanıtı.
    if body.visibility == "public" and c["first_responded_at"] is None:
        updates += ", first_responded_at = now()"
    if body.visibility == "public" and c["status"] in ("received", "triage", "assigned"):
        updates += ", status = 'in_progress'"
        case_event(ctx.conn, ctx.tenant["id"], case_id, "staff", p.user_id, "status_changed", c["status"], "in_progress")
    ctx.conn.execute(text(f"UPDATE cases SET {updates} WHERE id = :id"), {"id": case_id})
    action = "case.replied" if body.visibility == "public" else "case.internal_note"
    audit(ctx.conn, ctx.tenant["id"], "staff", p.user_id, action, "case", case_id)
    return _case_detail(ctx, case_id)
