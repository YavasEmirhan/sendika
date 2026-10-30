"""Operasyon panosu: yalnızca toplulaştırılmış veri, vaka içeriği yok."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from ..authz import REPORT_ROLES
from ..deps import StaffContext, staff_ctx
from ..domain import STATUS_LABELS
from ..sla import PRIORITY_LABELS

router = APIRouter(prefix="/api/t/{slug}/staff/reports", tags=["reports"])


def _scope(ctx: StaffContext) -> tuple[str, dict]:
    p = ctx.principal
    tenant_wide = any(r["org_unit_id"] is None and r["role"] in REPORT_ROLES for r in p.roles)
    if tenant_wide:
        return "TRUE", {}
    units = set()
    for r in p.roles:
        if r["role"] in REPORT_ROLES and r["org_unit_id"]:
            units.add(r["org_unit_id"])
            units |= p._children.get(r["org_unit_id"], set())
    return "c.org_unit_id = ANY(:units)", {"units": list(units)}


@router.get("/summary")
def summary(ctx: StaffContext = Depends(staff_ctx), days: int = Query(30, ge=7, le=365)):
    ctx.principal.require_any(REPORT_ROLES)
    scope, params = _scope(ctx)
    params = {**params, "days": days}
    conn = ctx.conn
    window = "c.created_at >= now() - make_interval(days => :days)"

    kpi = conn.execute(
        text(
            f"""SELECT
                  count(*) AS created,
                  count(*) FILTER (WHERE c.first_responded_at IS NOT NULL) AS responded,
                  count(*) FILTER (WHERE c.first_responded_at <= c.first_response_due_at) AS responded_in_sla,
                  count(*) FILTER (WHERE c.first_responded_at IS NULL AND c.first_response_due_at < now()
                                   AND c.status NOT IN ('resolved','closed_timeout')) AS overdue_now,
                  count(*) FILTER (WHERE c.status IN ('resolved','closed_timeout')) AS closed,
                  count(*) FILTER (WHERE c.is_anonymous) AS anonymous,
                  percentile_cont(0.5) WITHIN GROUP (
                      ORDER BY extract(epoch FROM c.first_responded_at - c.created_at) / 3600.0
                  ) FILTER (WHERE c.first_responded_at IS NOT NULL) AS median_first_response_hours,
                  percentile_cont(0.5) WITHIN GROUP (
                      ORDER BY extract(epoch FROM c.resolved_at - c.created_at) / 86400.0
                  ) FILTER (WHERE c.resolved_at IS NOT NULL) AS median_resolution_days
                FROM cases c WHERE {scope} AND {window}"""
        ),
        params,
    ).mappings().one()

    open_by_status = conn.execute(
        text(
            f"""SELECT c.status, count(*) AS n FROM cases c
                WHERE {scope} AND c.status NOT IN ('resolved','closed_timeout')
                GROUP BY c.status"""
        ),
        params,
    ).mappings().all()

    by_category = conn.execute(
        text(
            f"""SELECT cat.label, count(*) AS n,
                       percentile_cont(0.5) WITHIN GROUP (
                           ORDER BY extract(epoch FROM c.first_responded_at - c.created_at) / 3600.0
                       ) FILTER (WHERE c.first_responded_at IS NOT NULL) AS median_hours
                FROM cases c JOIN categories cat ON cat.id = c.category_id
                WHERE {scope} AND {window}
                GROUP BY cat.label, cat.sort_order ORDER BY n DESC, cat.sort_order"""
        ),
        params,
    ).mappings().all()

    by_unit = conn.execute(
        text(
            f"""SELECT u.name, count(*) FILTER (WHERE c.status NOT IN ('resolved','closed_timeout')) AS open,
                       count(*) FILTER (WHERE c.first_responded_at IS NULL AND c.first_response_due_at < now()
                                        AND c.status NOT IN ('resolved','closed_timeout')) AS overdue,
                       count(*) FILTER (WHERE {window}) AS created
                FROM cases c JOIN org_units u ON u.id = c.org_unit_id
                WHERE {scope} GROUP BY u.name ORDER BY open DESC"""
        ),
        params,
    ).mappings().all()

    daily = conn.execute(
        text(
            f"""SELECT d::date AS day, count(c.id) AS n
                FROM generate_series((now() AT TIME ZONE 'Europe/Istanbul')::date - 13,
                                     (now() AT TIME ZONE 'Europe/Istanbul')::date, interval '1 day') d
                LEFT JOIN cases c ON (c.created_at AT TIME ZONE 'Europe/Istanbul')::date = d::date AND {scope}
                GROUP BY d ORDER BY d"""
        ),
        params,
    ).mappings().all()

    by_priority = conn.execute(
        text(
            f"""SELECT c.priority, count(*) AS n,
                       count(*) FILTER (WHERE c.first_responded_at <= c.first_response_due_at) AS in_sla,
                       count(*) FILTER (WHERE c.first_responded_at IS NOT NULL) AS responded
                FROM cases c WHERE {scope} AND {window} GROUP BY c.priority ORDER BY c.priority"""
        ),
        params,
    ).mappings().all()

    def r1(x):
        return round(float(x), 1) if x is not None else None

    return {
        "days": days,
        "kpi": {
            **{k: kpi[k] for k in ("created", "responded", "responded_in_sla", "overdue_now", "closed", "anonymous")},
            "sla_rate": round(kpi["responded_in_sla"] / kpi["responded"], 3) if kpi["responded"] else None,
            "median_first_response_hours": r1(kpi["median_first_response_hours"]),
            "median_resolution_days": r1(kpi["median_resolution_days"]),
        },
        "open_by_status": [{"status": r["status"], "label": STATUS_LABELS[r["status"]], "n": r["n"]} for r in open_by_status],
        "by_category": [{"label": r["label"], "n": r["n"], "median_hours": r1(r["median_hours"])} for r in by_category],
        "by_unit": [dict(r) for r in by_unit],
        "by_priority": [
            {"priority": r["priority"], "label": PRIORITY_LABELS[r["priority"]], "n": r["n"],
             "sla_rate": round(r["in_sla"] / r["responded"], 3) if r["responded"] else None}
            for r in by_priority
        ],
        "daily": [{"day": r["day"].isoformat(), "n": r["n"]} for r in daily],
    }
