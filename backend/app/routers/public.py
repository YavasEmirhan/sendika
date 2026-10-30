"""Çalışanlara açık uçlar: kurum bilgisi, başvuru, takip."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Connection, text

from ..audit import audit
from ..deps import ApplicantContext, applicant_ctx, get_tenant, tenant_conn
from ..domain import PUBLIC_STAGE_LABELS, PUBLIC_STAGE_ORDER, public_stage
from ..ratelimit import enforce, limiter
from ..schemas import CaseCreate, MessageCreate, TrackRequest
from ..security import applicant_token
from ..services.cases import active_notice, applicant_reply, applicant_view, create_case, find_by_tracking_code
from ..sla import PRIORITY_LABELS

router = APIRouter(prefix="/api/t/{slug}", tags=["public"])


@router.get("")
def tenant_info(tenant: dict = Depends(get_tenant), conn: Connection = Depends(tenant_conn)):
    categories = conn.execute(
        text("SELECT key, label, help_text FROM categories WHERE active ORDER BY sort_order, label")
    ).mappings().all()
    return {
        "tenant": {"slug": tenant["slug"], "name": tenant["name"], "intro": tenant["public_intro"]},
        "categories": [dict(c) for c in categories],
        "privacy_notice": active_notice(conn, "privacy_notice"),
        "explicit_consent": active_notice(conn, "explicit_consent"),
        "stages": [{"key": k, "label": PUBLIC_STAGE_LABELS[k]} for k in PUBLIC_STAGE_ORDER],
    }


@router.post("/cases", status_code=201)
def submit_case(
    data: CaseCreate,
    request: Request,
    tenant: dict = Depends(get_tenant),
    conn: Connection = Depends(tenant_conn),
):
    enforce(request, f"submit:{tenant['id']}", limit=5, window_seconds=600)
    result = create_case(conn, tenant, data)
    case = result["case"]
    return {
        "reference_no": case["reference_no"],
        # Takip kodu yalnızca bu yanıtta bir kez gösterilir; veritabanında saklanmaz.
        "tracking_code": result["tracking_code"],
        "first_response_due_at": case["first_response_due_at"],
        "priority_label": PRIORITY_LABELS[case["priority"]],
        "stage": public_stage(case["status"]),
    }


@router.post("/track")
def track(
    body: TrackRequest,
    request: Request,
    tenant: dict = Depends(get_tenant),
    conn: Connection = Depends(tenant_conn),
):
    enforce(request, f"track:{tenant['id']}", limit=10, window_seconds=600)
    # Dağıtık tahmin denemelerine karşı kiracı geneli üst sınır.
    if not limiter.hit(f"track-global:{tenant['id']}", 500, 600):
        raise HTTPException(status_code=429, detail="Sistem yoğun. Lütfen biraz sonra tekrar deneyin.")
    case = find_by_tracking_code(conn, body.code)
    if not case:
        raise HTTPException(status_code=404, detail="Bu takip koduyla eşleşen başvuru bulunamadı.")
    audit(conn, tenant["id"], "applicant", None, "case.tracked", "case", case["id"])
    return {
        "applicant_token": applicant_token(case["id"], tenant["id"]),
        "case": applicant_view(conn, case["id"]),
    }


@router.get("/track/case")
def tracked_case(ctx: ApplicantContext = Depends(applicant_ctx)):
    return applicant_view(ctx.conn, ctx.case_id)


@router.post("/track/messages", status_code=201)
def tracked_reply(body: MessageCreate, request: Request, ctx: ApplicantContext = Depends(applicant_ctx)):
    enforce(request, f"reply:{ctx.tenant['id']}", limit=20, window_seconds=600)
    applicant_reply(ctx.conn, ctx.tenant, ctx.case_id, body.body)
    return applicant_view(ctx.conn, ctx.case_id)


@router.post("/track/consent/withdraw")
def withdraw_consent(ctx: ApplicantContext = Depends(applicant_ctx)):
    updated = ctx.conn.execute(
        text(
            """UPDATE consent_records SET status = 'withdrawn', withdrawn_at = now()
               WHERE case_id = :c AND status = 'given' RETURNING id"""
        ),
        {"c": ctx.case_id},
    ).first()
    if not updated:
        raise HTTPException(status_code=409, detail="Geri çekilecek bir açık rıza kaydı yok.")
    audit(ctx.conn, ctx.tenant["id"], "applicant", None, "consent.withdrawn", "case", ctx.case_id)
    return applicant_view(ctx.conn, ctx.case_id)
