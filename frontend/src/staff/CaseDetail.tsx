import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, type CaseDetail as Detail } from "../api";
import { ErrorAlert } from "../components";
import { dateTime, relative, slaText } from "../format";
import { useAuth } from "./auth";
import { useShell } from "./Shell";

type Assignee = { id: string; full_name: string; roles: string[] };

const CHANNEL: Record<string, string> = { web: "Web formu", phone: "Telefon", in_person: "Yüz yüze", email: "E-posta" };
const PRIO_LABEL: Record<string, string> = { P1: "Kritik", P2: "Yüksek", P3: "Normal", P4: "Bilgi" };
const ACTION_LABEL: Record<string, string> = {
  "case.viewed": "Vakayı açtı",
  "case.contact_revealed": "İletişim bilgisini görüntüledi",
  "case.assigned": "Atama yaptı",
  "case.status_changed": "Durumu değiştirdi",
  "case.priority_changed": "Önceliği değiştirdi",
  "case.replied": "Yanıt gönderdi",
  "case.internal_note": "İç not ekledi",
};

export default function CaseDetail() {
  const { id = "" } = useParams();
  const { call, me, slug } = useAuth();
  const { meta, refreshCounts } = useShell();
  const [c, setC] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [mode, setMode] = useState<"public" | "internal">("public");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [nextStatus, setNextStatus] = useState("");
  const [closure, setClosure] = useState("");
  const [contact, setContact] = useState<{ value: string | null; name: string | null } | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");

  const statusLabel = (k: string | null) => meta?.statuses.find((s) => s.key === k)?.label ?? k ?? "";

  const load = useCallback(() => {
    call<Detail>(`/cases/${id}`)
      .then((d) => {
        setC(d);
        document.title = `${d.reference_no} | Panel`;
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Vaka yüklenemedi."));
  }, [call, id]);

  useEffect(() => {
    setC(null);
    setContact(null);
    load();
    call<Assignee[]>(`/cases/${id}/assignees`).then(setAssignees).catch(() => setAssignees([]));
  }, [load, call, id]);

  async function act(path: string, payload: unknown) {
    setActionError(null);
    try {
      const d = await call<Detail>(`/cases/${id}${path}`, { body: payload });
      setC(d);
      refreshCounts();
      return true;
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "İşlem yapılamadı.");
      return false;
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setSending(true);
    const ok = await act("/messages", { body, visibility: mode });
    if (ok) setBody("");
    setSending(false);
  }

  async function applyStatus() {
    if (!nextStatus) return;
    const ok = await act("/status", { status: nextStatus, closure_code: closure || null });
    if (ok) {
      setNextStatus("");
      setClosure("");
    }
  }

  async function reveal(e: React.FormEvent) {
    e.preventDefault();
    try {
      const r = await call<{ value: string | null; name: string | null }>(`/cases/${id}/reveal-contact`, { body: { reason } });
      setContact(r);
      setReason("");
      dialogRef.current?.close();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "İletişim bilgisi açılamadı.");
      dialogRef.current?.close();
    }
  }

  if (error) return <ErrorAlert message={error} />;
  if (!c) return <p className="loading">Yükleniyor…</p>;

  const closed = ["resolved", "closed_timeout"].includes(c.status);
  const sla = slaText(c.first_response_due_at, c.first_responded_at, closed);
  const needsClosure = ["resolved", "closed_timeout"].includes(nextStatus);

  // Mesajlar ve durum değişiklikleri tek akışta, zamana göre
  type Item = { at: string; kind: "msg"; m: Detail["messages"][number] } | { at: string; kind: "event"; text: string };
  const feed: Item[] = [
    ...c.messages.map((m) => ({ at: m.created_at, kind: "msg" as const, m })),
    ...c.events
      .filter((e) => e.event_type !== "created" && e.event_type !== "reopened")
      .map((e) => {
        const who = e.full_name ?? (e.actor_type === "applicant" ? "Başvuru sahibi" : "Sistem");
        let text = "";
        if (e.event_type === "routed") text = `Yönlendirme: ${e.to_value}`;
        else if (e.event_type === "status_changed") text = `${who}, durumu "${statusLabel(e.from_value)}" iken "${statusLabel(e.to_value)}" yaptı`;
        else if (e.event_type === "assigned")
          text = !e.assignee_name
            ? `${who}, atamayı kaldırdı`
            : e.assignee_name === e.full_name
              ? `${who}, vakayı üzerine aldı`
              : `${who}, vakayı ${e.assignee_name} kişisine atadı`;
        else if (e.event_type === "priority_changed") text = `${who}, önceliği ${PRIO_LABEL[e.from_value ?? ""]} iken ${PRIO_LABEL[e.to_value ?? ""]} yaptı`;
        else text = e.event_type;
        return { at: e.created_at, kind: "event" as const, text };
      }),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const isMine = c.assignee_id === me.id;

  return (
    <>
      <Link className="back-link" to={`/t/${slug}/panel`}>
        Başvuru listesine dön
      </Link>
      <div className="case-title">
        <div className="meta">
          <span className="ref-cell">{c.reference_no}</span>
          <span className={`pill ${c.status}`}>{c.status_label}</span>
          {c.sensitivity === "restricted" && <span className="pill restricted">Kısıtlı: yalnızca hukuk ve yönetim</span>}
          <span>
            Başvuru sahibi şunu görüyor: <strong>{c.public_stage.label}</strong>
          </span>
        </div>
        <h1>{c.subject}</h1>
      </div>

      <div className="case-layout">
        <div>
          <section className="statement" aria-label="Başvuru metni">
            <div className="facts">
              <span>{c.category}</span>
              <span>{CHANNEL[c.channel] ?? c.channel}</span>
              {c.city && <span>{c.city}</span>}
              {c.workplace && <span>İşyeri: {c.workplace}</span>}
              <span>{dateTime(c.created_at)}</span>
            </div>
            <p className="body">{c.description}</p>
          </section>

          <div className="timeline-feed" aria-label="Yazışmalar ve geçmiş">
            {feed.map((item, i) =>
              item.kind === "event" ? (
                <p key={`e${i}`} className="event-line">
                  {dateTime(item.at)}: {item.text}
                </p>
              ) : (
                <article
                  key={item.m.id}
                  className={`msg ${item.m.visibility === "internal" ? "internal" : item.m.author_type}`}
                >
                  <div className="head">
                    <span>
                      <strong>
                        {item.m.author_type === "applicant" ? "Başvuru sahibi" : item.m.author ?? "Personel"}
                      </strong>
                      {item.m.visibility === "internal" ? ", iç not (başvuru sahibi görmez)" : item.m.author_type === "staff" ? ", başvuru sahibine yanıt" : ""}
                    </span>
                    <span>{dateTime(item.m.created_at)}</span>
                  </div>
                  <p>{item.m.body}</p>
                </article>
              ),
            )}
          </div>

          <form className={`composer ${mode === "internal" ? "internal" : ""}`} onSubmit={send}>
            <div className="composer-tabs" role="tablist" aria-label="Mesaj türü">
              <button type="button" role="tab" aria-selected={mode === "public"} onClick={() => setMode("public")}>
                Başvuru sahibine yanıt
              </button>
              <button type="button" role="tab" aria-selected={mode === "internal"} onClick={() => setMode("internal")}>
                İç not
              </button>
            </div>
            <div className="composer-body">
              {mode === "public" && meta && meta.canned_responses.length > 0 && (
                <select
                  aria-label="Hazır yanıt ekle"
                  value=""
                  onChange={(e) => {
                    const r = meta.canned_responses.find((x) => x.id === e.target.value);
                    if (r) setBody((b) => (b ? `${b}\n\n${r.body}` : r.body));
                  }}
                  style={{ minHeight: 38, padding: "6px 10px", fontSize: "var(--t-s)" }}
                >
                  <option value="">Hazır yanıt ekle…</option>
                  {meta.canned_responses.map((r) => (
                    <option key={r.id} value={r.id}>{r.title}</option>
                  ))}
                </select>
              )}
              <label className="visually-hidden" htmlFor="composer-text">
                {mode === "public" ? "Yanıt metni" : "İç not metni"}
              </label>
              <textarea
                id="composer-text"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={mode === "public" ? "Başvuru sahibinin göreceği yanıtı yazın" : "Yalnızca sendika personelinin göreceği notu yazın"}
                disabled={mode === "public" && closed}
              />
              <div className="composer-foot">
                <span className="hint">
                  {mode === "public"
                    ? closed
                      ? "Sonuçlanan vakaya yanıt göndermek için önce vakayı yeniden açın."
                      : c.contact.method === "none"
                        ? "Başvuru sahibi anonim; yanıtı takip koduyla okuyacak."
                        : "Başvuru sahibi yanıtı takip koduyla okuyacak."
                    : "İç notlar başvuru sahibine hiçbir koşulda gösterilmez."}
                </span>
                <button className="btn small" type="submit" disabled={sending || !body.trim() || (mode === "public" && closed)}>
                  {mode === "public" ? "Yanıtı gönder" : "Notu kaydet"}
                </button>
              </div>
            </div>
          </form>
        </div>

        <aside className="rail" aria-label="Vaka bilgileri ve işlemler">
          <ErrorAlert message={actionError} />

          <div className={`rail-block sla-block ${sla.tone === "late" ? "late" : ""}`}>
            <h2>İlk yanıt</h2>
            <span className="big">
              {c.first_responded_at ? `Yanıtlandı (${relative(c.first_responded_at)})` : sla.text}
            </span>
            <span className="muted">Hedef: {dateTime(c.first_response_due_at)}</span>
          </div>

          <div className="rail-block">
            <h2>Sorumlu</h2>
            <p>{c.assignee ?? <span className="muted">Henüz atanmadı</span>}</p>
            {!closed &&
              (c.permissions.assign_others ? (
                <>
                  <label htmlFor="assignee">Atama</label>
                  <select
                    id="assignee"
                    value={c.assignee_id ?? ""}
                    onChange={(e) => act("/assign", { assignee_id: e.target.value || null })}
                  >
                    <option value="">Atanmadı</option>
                    {assignees.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.full_name} ({a.roles.join(", ")})
                      </option>
                    ))}
                  </select>
                </>
              ) : isMine ? (
                <button className="btn secondary small" onClick={() => act("/assign", { assignee_id: null })}>
                  Üzerimden bırak
                </button>
              ) : (
                <button className="btn small" onClick={() => act("/assign", { assignee_id: me.id })}>
                  Bana ata
                </button>
              ))}
          </div>

          <div className="rail-block">
            <h2>Durum ve öncelik</h2>
            <label htmlFor="prio">Öncelik</label>
            <select id="prio" value={c.priority} onChange={(e) => act("/priority", { priority: e.target.value })}>
              {meta?.priorities.map((p) => (
                <option key={p.key} value={p.key}>{p.label}</option>
              ))}
            </select>
            <label htmlFor="status">Durumu değiştir</label>
            <select id="status" value={nextStatus} onChange={(e) => setNextStatus(e.target.value)}>
              <option value="">{closed ? "Yeniden açmak için seçin" : "Yeni durumu seçin"}</option>
              {c.allowed_transitions.map((s) => (
                <option key={s} value={s}>
                  {s === "in_progress" && closed ? "Yeniden aç (İnceleniyor)" : statusLabel(s)}
                </option>
              ))}
            </select>
            {needsClosure && (
              <>
                <label htmlFor="closure">Sonuç</label>
                <select id="closure" value={closure} onChange={(e) => setClosure(e.target.value)}>
                  <option value="">Sonucu seçin</option>
                  {meta?.closure_codes.map((x) => (
                    <option key={x.key} value={x.key}>{x.label}</option>
                  ))}
                </select>
              </>
            )}
            <button className="btn small" disabled={!nextStatus || (needsClosure && nextStatus === "resolved" && !closure)} onClick={applyStatus}>
              Durumu güncelle
            </button>
            {c.closure_label && <p className="muted">Sonuç: {c.closure_label}</p>}
          </div>

          <div className="rail-block">
            <h2>Başvuru sahibi</h2>
            <dl className="kv">
              <dt>Kimlik</dt>
              <dd>{c.is_anonymous ? "Anonim" : "Adını paylaştı"}</dd>
              <dt>İletişim</dt>
              <dd>
                {c.contact.method === "none" ? "Bırakmadı" : c.contact.method === "email" ? "E-posta" : "Telefon"}
              </dd>
              {c.contact.method !== "none" && (
                <>
                  <dt>Bilgi</dt>
                  <dd>{contact ? contact.value : c.contact.masked}</dd>
                </>
              )}
              {contact?.name && (
                <>
                  <dt>Ad</dt>
                  <dd>{contact.name}</dd>
                </>
              )}
              {c.contact.safe_contact_note && (
                <>
                  <dt>Güvenli saat</dt>
                  <dd>{c.contact.safe_contact_note}</dd>
                </>
              )}
            </dl>
            {c.contact.method !== "none" && !contact && (
              <button className="btn secondary small" onClick={() => dialogRef.current?.showModal()}>
                İletişim bilgisini göster
              </button>
            )}
          </div>

          <div className="rail-block">
            <h2>Kişisel veri kayıtları</h2>
            <dl className="kv">
              <dt>Aydınlatma</dt>
              <dd>{c.privacy.notice_version ? `${c.privacy.notice_version} gösterildi` : "Kayıt yok"}</dd>
              <dt>Açık rıza</dt>
              <dd>
                {c.privacy.consent
                  ? c.privacy.consent.status === "given"
                    ? `Verildi (${c.privacy.consent.version})`
                    : "Geri çekildi"
                  : "Verilmedi"}
              </dd>
            </dl>
          </div>

          {c.access_log && (
            <div className="rail-block">
              <h2>Erişim kaydı</h2>
              <ul className="log">
                {c.access_log.map((l, i) => (
                  <li key={i}>
                    <strong>{l.actor ?? "Personel"}</strong>: {ACTION_LABEL[l.action] ?? l.action}
                    {l.reason ? ` ("${l.reason}")` : ""}, {relative(l.created_at)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>

      <dialog ref={dialogRef} aria-labelledby="reveal-title">
        <form onSubmit={reveal}>
          <h2 id="reveal-title">İletişim bilgisini göster</h2>
          <p style={{ fontSize: "var(--t-s)", color: "var(--ink-2)" }}>
            Bu bilgiyi neden görüntülediğinizi yazın. Gerekçe, adınız ve saatle birlikte erişim kaydına geçer.
          </p>
          <label htmlFor="reason" className="visually-hidden">Gerekçe</label>
          <input
            id="reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Örneğin: Başvuru sahibi geri aranmak istedi"
            minLength={5}
            maxLength={300}
            required
          />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" className="btn quiet small" onClick={() => dialogRef.current?.close()}>
              Vazgeç
            </button>
            <button type="submit" className="btn small" disabled={reason.trim().length < 5}>
              Göster ve kaydet
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
