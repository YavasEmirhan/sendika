import { useEffect, useState } from "react";
import { ApiError, type Summary } from "../api";
import { ErrorAlert } from "../components";
import { hours } from "../format";
import { useAuth } from "./auth";

const pct = (x: number | null) => (x === null ? "—" : `%${Math.round(x * 100)}`);

export default function Reports() {
  const { call } = useAuth();
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    call<Summary>(`/reports/summary?days=${days}`)
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Rapor yüklenemedi."));
  }, [call, days]);

  if (error) return <ErrorAlert message={error} />;
  if (!data) return <p className="loading">Yükleniyor…</p>;
  const k = data.kpi;
  const maxCat = Math.max(1, ...data.by_category.map((x) => x.n));
  const maxDay = Math.max(1, ...data.daily.map((x) => x.n));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Hizmet raporu</h1>
          <p>Kişisel veri içermez; yalnızca sayılar. Yetkinizdeki birimleri kapsar.</p>
        </div>
        <label>
          <span className="visually-hidden">Dönem</span>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: "auto", minHeight: 38, padding: "6px 10px" }}>
            <option value={7}>Son 7 gün</option>
            <option value={30}>Son 30 gün</option>
            <option value={90}>Son 90 gün</option>
          </select>
        </label>
      </div>

      <section className="kpis" aria-label="Özet göstergeler">
        <div className="kpi">
          <span className="v">{k.created}</span>
          <span className="k">Yeni başvuru</span>
          <span className="d">{k.anonymous} tanesi anonim</span>
        </div>
        <div className="kpi">
          <span className="v">{hours(k.median_first_response_hours)}</span>
          <span className="k">Medyan ilk yanıt süresi</span>
          <span className="d">Otomatik mesaj değil, insan yanıtı</span>
        </div>
        <div className="kpi">
          <span className="v">{pct(k.sla_rate)}</span>
          <span className="k">Hedef içinde yanıt</span>
          <span className="d">{k.responded_in_sla} / {k.responded} yanıtlanan başvuru</span>
        </div>
        <div className={`kpi ${k.overdue_now > 0 ? "bad" : ""}`}>
          <span className="v">{k.overdue_now}</span>
          <span className="k">Şu an hedefi geçmiş</span>
          <span className="d">Henüz ilk yanıtı verilmemiş</span>
        </div>
      </section>

      <div className="report-grid">
        <section className="report-card">
          <h2>Günlük yeni başvuru</h2>
          <div className="daily" role="img" aria-label={`Son 14 günde günlük başvurular: ${data.daily.map((d) => d.n).join(", ")}`}>
            {data.daily.map((d, i) => (
              <div className="col" key={d.day} title={`${d.day}: ${d.n}`}>
                <span>{d.n || ""}</span>
                <div className={`stick ${i === data.daily.length - 1 ? "today" : ""}`} style={{ height: `${Math.round((d.n / maxDay) * 84)}px` }} />
                <span>{d.day.slice(8)}</span>
              </div>
            ))}
          </div>
          <p className="note">Son 14 gün. Sarı sütun bugünü gösterir.</p>
        </section>

        <section className="report-card">
          <h2>Konulara göre</h2>
          <div className="bars">
            {data.by_category.map((c) => (
              <div className="bar-row" key={c.label}>
                <span className="name" title={c.label}>{c.label}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(c.n / maxCat) * 100}%` }} />
                </div>
                <span className="val">
                  {c.n} <span className="muted">({hours(c.median_hours)})</span>
                </span>
              </div>
            ))}
          </div>
          <p className="note">Başvuru sayısı; parantez içinde medyan ilk yanıt süresi.</p>
        </section>

        <section className="report-card">
          <h2>Birimlere göre iş yükü</h2>
          <table className="simple">
            <thead>
              <tr>
                <th>Birim</th>
                <th>Açık</th>
                <th>Hedefi geçen</th>
                <th>Dönemde gelen</th>
              </tr>
            </thead>
            <tbody>
              {data.by_unit.map((u) => (
                <tr key={u.name}>
                  <td>{u.name}</td>
                  <td>{u.open}</td>
                  <td style={{ color: u.overdue ? "var(--red)" : undefined, fontWeight: u.overdue ? 700 : undefined }}>{u.overdue}</td>
                  <td>{u.created}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="report-card">
          <h2>Önceliğe göre hedef uyumu</h2>
          <table className="simple">
            <thead>
              <tr>
                <th>Öncelik</th>
                <th>Başvuru</th>
                <th>Hedef içinde</th>
              </tr>
            </thead>
            <tbody>
              {data.by_priority.map((p) => (
                <tr key={p.priority}>
                  <td>
                    <span className={`prio ${p.priority}`}>{p.label}</span>
                  </td>
                  <td>{p.n}</td>
                  <td>{pct(p.sla_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2 style={{ marginTop: 8 }}>Açık başvuruların durumu</h2>
          <div className="bars">
            {data.open_by_status.map((s) => (
              <div className="bar-row" key={s.status}>
                <span className="name">{s.label}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(s.n / Math.max(1, ...data.open_by_status.map((x) => x.n))) * 100}%` }} />
                </div>
                <span className="val">{s.n}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
