import { useState } from "react";
import { api, ApiError, type ApplicantCase } from "../api";
import { ErrorAlert, Field, StageWire } from "../components";
import { dateTime } from "../format";
import { useTenant } from "./PublicLayout";

function formatCode(raw: string): string {
  const clean = raw.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 12);
  return clean.match(/.{1,4}/g)?.join("-") ?? "";
}

export default function Track() {
  const info = useTenant();
  const slug = info.tenant.slug;
  const [code, setCode] = useState("");
  // Belirteç yalnızca bellekte: sekme kapanınca oturum biter.
  const [token, setToken] = useState<string | null>(null);
  const [data, setData] = useState<ApplicantCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState("");
  const [replyError, setReplyError] = useState<string | null>(null);

  async function open(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (code.replace(/-/g, "").length < 12) {
      setError("Takip kodu 12 karakterdir. Örnek: K7QM-4XRT-9PWC");
      return;
    }
    setBusy(true);
    try {
      const r = await api<{ applicant_token: string; case: ApplicantCase }>(`/api/t/${slug}/track`, { body: { code } });
      setToken(r.applicant_token);
      setData(r.case);
      setCode("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Başvuru açılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!reply.trim()) {
      setReplyError("Göndermek için bir mesaj yazın.");
      return;
    }
    setBusy(true);
    setReplyError(null);
    try {
      const r = await api<ApplicantCase>(`/api/t/${slug}/track/messages`, { body: { body: reply }, token });
      setData(r);
      setReply("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        close("Oturumunuzun süresi doldu. Takip kodunuzla yeniden girin.");
        return;
      }
      setReplyError(err instanceof ApiError ? err.message : "Mesaj gönderilemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function withdraw() {
    if (!window.confirm("Açık rızanızı geri çekmek istediğinize emin misiniz?")) return;
    try {
      setData(await api<ApplicantCase>(`/api/t/${slug}/track/consent/withdraw`, { method: "POST", token }));
    } catch (err) {
      setReplyError(err instanceof ApiError ? err.message : "İşlem yapılamadı.");
    }
  }

  function close(msg: string | null = null) {
    setToken(null);
    setData(null);
    setError(msg);
  }

  if (!data) {
    return (
      <form className="form-stack" onSubmit={open} noValidate>
        <div className="case-head">
          <h1>Başvurumu takip et</h1>
          <p style={{ color: "var(--ink-2)" }}>Başvuru sonunda size verilen 12 karakterlik kodu girin.</p>
        </div>
        <Field id="code" label="Takip kodu" error={error}>
          <input
            id="code"
            value={code}
            onChange={(e) => setCode(formatCode(e.target.value))}
            placeholder="XXXX-XXXX-XXXX"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            inputMode="text"
            style={{ fontSize: "1.35rem", letterSpacing: "0.08em", fontVariantNumeric: "tabular-nums" }}
            aria-invalid={!!error}
          />
        </Field>
        <div>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Açılıyor…" : "Başvurumu aç"}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="form-stack">
      <div className="case-head">
        <span className="ref">{`${data.reference_no}, ${data.category}`}</span>
        <h1>{data.subject}</h1>
      </div>

      <section className="panel" aria-labelledby="durum">
        <h2 id="durum" style={{ fontSize: "var(--t-m)", marginBottom: 16 }}>
          Durum: {data.stage.label}
        </h2>
        <StageWire timeline={data.timeline} current={data.stage} stages={info.stages} />
      </section>

      <section aria-labelledby="mesajlar" className="form-stack" style={{ gap: 14 }}>
        <h2 id="mesajlar" style={{ fontSize: "var(--t-l)" }}>
          Mesajlar
        </h2>
        {data.messages.length === 0 ? (
          <p style={{ color: "var(--ink-2)" }}>
            Henüz yanıt yok. Bir temsilci yanıt verdiğinde burada görünecek.
          </p>
        ) : (
          <div className="thread" aria-live="polite">
            {data.messages.map((m) => (
              <div key={m.id} className={`bubble ${m.from === "applicant" ? "mine" : ""}`}>
                <span className="who">{m.from === "applicant" ? "Siz" : `${m.author ?? "Temsilci"}, sendika temsilcisi`}</span>
                <p>{m.body}</p>
                <span className="when">{dateTime(m.at)}</span>
              </div>
            ))}
          </div>
        )}

        {data.can_reply ? (
          <form className="form-stack" style={{ gap: 10 }} onSubmit={send} noValidate>
            <Field id="reply" label={data.stage.key === "waiting_info" ? "İstenen bilgiyi gönderin" : "Mesaj yazın"} error={replyError}>
              <textarea
                id="reply"
                value={reply}
                maxLength={5000}
                style={{ minHeight: 110 }}
                onChange={(e) => setReply(e.target.value)}
                aria-invalid={!!replyError}
              />
            </Field>
            <div>
              <button className="btn" type="submit" disabled={busy}>
                {busy ? "Gönderiliyor…" : "Mesajı gönder"}
              </button>
            </div>
          </form>
        ) : (
          <div className="alert info">Bu başvuru sonuçlandı. Yeni bir sorun için yeni başvuru yapabilirsiniz.</div>
        )}
      </section>

      {data.consent_status === "given" && (
        <p style={{ fontSize: "var(--t-s)", color: "var(--ink-2)" }}>
          Hassas bilgileriniz için açık rıza verdiniz.{" "}
          <button className="btn quiet small" style={{ padding: 0, minHeight: 0, color: "var(--petrol)", textDecoration: "underline" }} onClick={withdraw}>
            Rızamı geri çek
          </button>
        </p>
      )}
      {data.consent_status === "withdrawn" && (
        <p style={{ fontSize: "var(--t-s)", color: "var(--ink-2)" }}>Açık rızanızı geri çektiniz.</p>
      )}

      <ErrorAlert message={error} />
      <div>
        <button className="btn secondary" onClick={() => close()}>
          Başvurudan çık
        </button>
      </div>
    </div>
  );
}
