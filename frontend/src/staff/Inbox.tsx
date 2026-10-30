import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, type CaseList } from "../api";
import { ErrorAlert } from "../components";
import { relative, slaText } from "../format";
import { useAuth } from "./auth";
import { useShell } from "./Shell";

const TITLES: Record<string, { title: string; empty: string }> = {
  open: { title: "Açık başvurular", empty: "Açık başvuru yok." },
  mine: { title: "Bana atananlar", empty: "Size atanmış açık başvuru yok. Atanmamış başvurulara bakabilirsiniz." },
  unassigned: { title: "Atanmamış", empty: "Tüm başvuruların bir sorumlusu var." },
  overdue: { title: "İlk yanıt hedefini geçenler", empty: "Hedefi geçen başvuru yok." },
  waiting: { title: "Başvuru sahibinden bilgi beklenenler", empty: "Bilgi beklenen başvuru yok." },
  closed: { title: "Sonuçlananlar", empty: "Henüz sonuçlanan başvuru yok." },
};

const PRIO_LABEL: Record<string, string> = { P1: "Kritik", P2: "Yüksek", P3: "Normal", P4: "Bilgi" };

export default function Inbox() {
  const { call, slug } = useAuth();
  const { meta, setCounts } = useShell();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const view = params.get("view") ?? "open";
  const [data, setData] = useState<CaseList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filters = {
    org_unit_id: params.get("unit") ?? "",
    category_id: params.get("cat") ?? "",
    priority: params.get("prio") ?? "",
    q: params.get("q") ?? "",
  };

  const load = useCallback(() => {
    const qs = new URLSearchParams({ view });
    if (filters.org_unit_id) qs.set("org_unit_id", filters.org_unit_id);
    if (filters.category_id) qs.set("category_id", filters.category_id);
    if (filters.priority) qs.set("priority", filters.priority);
    if (filters.q) qs.set("q", filters.q);
    call<CaseList>(`/cases?${qs}`)
      .then((d) => {
        setData(d);
        setCounts(d.counts);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Liste yüklenemedi."));
  }, [call, view, filters.org_unit_id, filters.category_id, filters.priority, filters.q, setCounts]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  function setFilter(k: string, v: string) {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  }

  const t = TITLES[view] ?? TITLES.open;
  const base = `/t/${slug}/panel`;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t.title}</h1>
          <p>Öncelik ve ilk yanıt hedefine göre sıralı. Liste her dakika yenilenir.</p>
        </div>
      </div>

      <div className="filters" role="group" aria-label="Filtreler">
        <label className="visually-hidden" htmlFor="flt-unit">Birim</label>
        <select id="flt-unit" value={filters.org_unit_id} onChange={(e) => setFilter("unit", e.target.value)}>
          <option value="">Tüm birimler</option>
          {meta?.org_units.map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
        <label className="visually-hidden" htmlFor="flt-cat">Konu</label>
        <select id="flt-cat" value={filters.category_id} onChange={(e) => setFilter("cat", e.target.value)}>
          <option value="">Tüm konular</option>
          {meta?.categories.map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
        <label className="visually-hidden" htmlFor="flt-prio">Öncelik</label>
        <select id="flt-prio" value={filters.priority} onChange={(e) => setFilter("prio", e.target.value)}>
          <option value="">Tüm öncelikler</option>
          {meta?.priorities.map((p) => (
            <option key={p.key} value={p.key}>{p.label}</option>
          ))}
        </select>
        <label className="visually-hidden" htmlFor="flt-q">Başvuru numarası</label>
        <input
          id="flt-q"
          placeholder="Başvuru no ara"
          defaultValue={filters.q}
          onKeyDown={(e) => {
            if (e.key === "Enter") setFilter("q", (e.target as HTMLInputElement).value.trim());
          }}
          onBlur={(e) => setFilter("q", e.target.value.trim())}
        />
      </div>

      <ErrorAlert message={error} />

      {!data ? (
        <p className="loading">Yükleniyor…</p>
      ) : data.items.length === 0 ? (
        <div className="table-wrap">
          <p className="empty">{t.empty}</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="cases">
            <thead>
              <tr>
                <th scope="col">Öncelik</th>
                <th scope="col">Başvuru</th>
                <th scope="col" className="hide-sm">No</th>
                <th scope="col" className="hide-sm">Birim</th>
                <th scope="col">Durum</th>
                <th scope="col" className="hide-sm">Sorumlu</th>
                <th scope="col">İlk yanıt</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => {
                const sla = slaText(c.first_response_due_at, c.first_responded_at, ["resolved", "closed_timeout"].includes(c.status));
                const href = `${base}/vaka/${c.id}`;
                return (
                  <tr key={c.id} onClick={() => navigate(href)}>
                    <td>
                      <span className={`prio ${c.priority}`}>{PRIO_LABEL[c.priority]}</span>
                    </td>
                    <td className="subject">
                      <Link to={href} onClick={(e) => e.stopPropagation()}>
                        {c.subject}
                      </Link>
                      <span className="sub">
                        {c.category}
                        {c.city ? `, ${c.city}` : ""}, {relative(c.created_at)}
                        {c.sensitivity === "restricted" && (
                          <>
                            {" "}
                            <span className="pill restricted">Kısıtlı</span>
                          </>
                        )}
                      </span>
                    </td>
                    <td className="ref-cell hide-sm">{c.reference_no}</td>
                    <td className="hide-sm">{c.org_unit}</td>
                    <td>
                      <span className={`pill ${c.status}`}>{c.status_label}</span>
                    </td>
                    <td className="hide-sm">{c.assignee ?? <span className="muted">Atanmadı</span>}</td>
                    <td>
                      <span className={`sla ${sla.tone}`}>{sla.text}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
