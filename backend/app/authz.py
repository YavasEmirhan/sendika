"""Personel yetkilendirmesi.

Kiracı izolasyonu veritabanında (RLS) sağlanır. Bu modül kiracı içindeki
ikinci katmanı uygular: hangi birimin vakalarını kim görebilir, kısıtlı
(hassas) vakalara kim erişebilir, kim atama yapabilir.
"""
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Connection, text

HANDLER_ROLES = {"tenant_owner", "org_admin", "branch_manager", "case_worker", "legal_reviewer"}
RESTRICTED_ROLES = {"tenant_owner", "org_admin", "legal_reviewer"}
ASSIGNER_ROLES = {"tenant_owner", "org_admin", "branch_manager"}
REPORT_ROLES = {"tenant_owner", "org_admin", "branch_manager", "auditor"}
AUDIT_ROLES = {"tenant_owner", "org_admin", "auditor"}

ROLE_LABELS = {
    "tenant_owner": "Kurum sahibi",
    "org_admin": "Kurum yöneticisi",
    "branch_manager": "Şube yöneticisi",
    "case_worker": "Temsilci",
    "legal_reviewer": "Hukuk",
    "auditor": "Denetçi",
}


@dataclass
class Principal:
    user_id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    roles: list[dict] = field(default_factory=list)  # [{role, org_unit_id}]
    # Hesaplanan kapsam
    all_units: bool = False
    unit_ids: set[UUID] = field(default_factory=set)
    can_restricted: bool = False

    @property
    def role_names(self) -> set[str]:
        return {r["role"] for r in self.roles}

    def has_any(self, roles: set[str]) -> bool:
        return bool(self.role_names & roles)

    def require_any(self, roles: set[str]) -> None:
        if not self.has_any(roles):
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok.")

    def can_handle_unit(self, unit_id: UUID) -> bool:
        return self.all_units or unit_id in self.unit_ids

    def sees_case(self, case: dict) -> bool:
        if not self.has_any(HANDLER_ROLES):
            return False
        if case["sensitivity"] == "restricted" and not self.can_restricted:
            return False
        return self.can_handle_unit(case["org_unit_id"])

    def can_assign_others(self, unit_id: UUID) -> bool:
        for r in self.roles:
            if r["role"] in ASSIGNER_ROLES and (r["org_unit_id"] is None or self._unit_in(r["org_unit_id"], unit_id)):
                return True
        return False

    # birim kapsamı alt birimleri de içerir; _children build_principal'da doldurulur
    _children: dict[UUID, set[UUID]] = field(default_factory=dict)

    def _unit_in(self, scope_unit: UUID, unit_id: UUID) -> bool:
        return unit_id == scope_unit or unit_id in self._children.get(scope_unit, set())

    def case_scope_sql(self) -> tuple[str, dict]:
        """Vaka listesi sorgularına eklenecek kapsam filtresi."""
        if not self.has_any(HANDLER_ROLES):
            return "FALSE", {}
        clauses, params = [], {}
        if not self.all_units:
            clauses.append("c.org_unit_id = ANY(:scope_units)")
            params["scope_units"] = list(self.unit_ids) or []
        if not self.can_restricted:
            clauses.append("c.sensitivity = 'normal'")
        return (" AND ".join(clauses) or "TRUE"), params


def build_principal(conn: Connection, user: dict) -> Principal:
    roles = [
        dict(r)
        for r in conn.execute(
            text("SELECT role, org_unit_id FROM role_assignments WHERE user_id = :u"), {"u": user["id"]}
        ).mappings()
    ]
    units = conn.execute(text("SELECT id, parent_id FROM org_units")).mappings().all()
    children: dict[UUID, set[UUID]] = {}
    by_parent: dict[UUID | None, list[UUID]] = {}
    for u in units:
        by_parent.setdefault(u["parent_id"], []).append(u["id"])

    def descendants(uid: UUID) -> set[UUID]:
        out, stack = set(), list(by_parent.get(uid, []))
        while stack:
            x = stack.pop()
            if x not in out:
                out.add(x)
                stack.extend(by_parent.get(x, []))
        return out

    for u in units:
        children[u["id"]] = descendants(u["id"])

    p = Principal(
        user_id=user["id"], tenant_id=user["tenant_id"], email=user["email"], full_name=user["full_name"], roles=roles
    )
    p._children = children
    for r in roles:
        if r["role"] not in HANDLER_ROLES:
            continue
        if r["org_unit_id"] is None:
            p.all_units = True
        else:
            p.unit_ids.add(r["org_unit_id"])
            # Yöneticiler alt birimleri de görür; temsilci yalnızca kendi biriminin kuyruğunu görür.
            if r["role"] != "case_worker":
                p.unit_ids |= children.get(r["org_unit_id"], set())
    p.can_restricted = p.has_any(RESTRICTED_ROLES)
    return p
