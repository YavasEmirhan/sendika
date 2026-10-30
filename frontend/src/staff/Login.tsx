import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { BrandMark, ErrorAlert, Field } from "../components";
import { saveToken } from "./auth";

type LoginResponse =
  | { step: "mfa"; mfa_token: string }
  | { step: "mfa_setup"; mfa_token: string; otpauth_uri: string; secret: string };

export default function Login() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as { from?: string; expired?: boolean };

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<LoginResponse | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(state.expired ? "Oturumunuz sona erdi. Lütfen yeniden giriş yapın." : null);
  const [busy, setBusy] = useState(false);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = "Sendika paneli | Giriş";
  }, []);

  useEffect(() => {
    if (stage?.step === "mfa_setup") QRCode.toDataURL(stage.otpauth_uri, { margin: 1, width: 188 }).then(setQr);
    if (stage) setTimeout(() => codeRef.current?.focus(), 0);
  }, [stage]);

  async function submitPassword(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setStage(await api<LoginResponse>(`/api/t/${slug}/staff/login`, { body: { email, password } }));
      setPassword("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Giriş yapılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: React.FormEvent) {
    e.preventDefault();
    if (!stage) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ access_token: string }>(`/api/t/${slug}/staff/mfa/verify`, {
        body: { mfa_token: stage.mfa_token, code },
      });
      saveToken(slug, r.access_token);
      navigate(state.from && state.from.includes("/panel") ? state.from : `/t/${slug}/panel`, { replace: true });
    } catch (err) {
      setCode("");
      if (err instanceof ApiError && err.status === 401 && err.message.includes("süresi doldu")) setStage(null);
      setError(err instanceof ApiError ? err.message : "Doğrulama yapılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <main className="login-card">
        <BrandMark size={36} />
        {!stage && (
          <form className="form-stack" style={{ gap: 16 }} onSubmit={submitPassword}>
            <div>
              <h1>Sendika paneli</h1>
              <p className="sub">Temsilci ve yöneticiler için giriş</p>
            </div>
            <ErrorAlert message={error} />
            <Field id="email" label="E-posta">
              <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field id="password" label="Parola">
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            <button className="btn block" type="submit" disabled={busy}>
              {busy ? "Kontrol ediliyor…" : "Devam et"}
            </button>
          </form>
        )}

        {stage?.step === "mfa_setup" && (
          <form className="form-stack" style={{ gap: 14 }} onSubmit={submitCode}>
            <div>
              <h1>İki adımlı doğrulamayı kurun</h1>
              <p className="sub">
                Başvurular hassas bilgi içerdiği için panel girişinde telefonunuzdaki doğrulama uygulaması zorunludur.
              </p>
            </div>
            <ol style={{ margin: 0, paddingLeft: 20, fontSize: "var(--t-s)", display: "grid", gap: 6 }}>
              <li>Google Authenticator, Microsoft Authenticator veya benzeri bir uygulama açın.</li>
              <li>Aşağıdaki kodu okutun.</li>
              <li>Uygulamada görünen 6 haneli kodu girin.</li>
            </ol>
            {qr && <img className="qr" src={qr} width={188} height={188} alt="Doğrulama uygulaması için QR kod" />}
            <details style={{ fontSize: "var(--t-s)" }}>
              <summary>QR okutamıyorum</summary>
              <p style={{ margin: "8px 0 4px" }}>Uygulamaya bu anahtarı elle girin:</p>
              <div className="secret">{stage.secret}</div>
            </details>
            <ErrorAlert message={error} />
            <CodeField code={code} setCode={setCode} inputRef={codeRef} />
            <button className="btn block" type="submit" disabled={busy || code.length !== 6}>
              Kurulumu tamamla
            </button>
          </form>
        )}

        {stage?.step === "mfa" && (
          <form className="form-stack" style={{ gap: 14 }} onSubmit={submitCode}>
            <div>
              <h1>Doğrulama kodu</h1>
              <p className="sub">Telefonunuzdaki doğrulama uygulamasında görünen 6 haneli kodu girin.</p>
            </div>
            <ErrorAlert message={error} />
            <CodeField code={code} setCode={setCode} inputRef={codeRef} />
            <button className="btn block" type="submit" disabled={busy || code.length !== 6}>
              {busy ? "Doğrulanıyor…" : "Giriş yap"}
            </button>
            <button type="button" className="btn quiet" onClick={() => { setStage(null); setCode(""); setError(null); }}>
              Farklı hesapla giriş yap
            </button>
          </form>
        )}
      </main>
    </div>
  );
}

function CodeField({
  code,
  setCode,
  inputRef,
}: {
  code: string;
  setCode: (v: string) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  return (
    <Field id="otp" label="6 haneli kod">
      <input
        id="otp"
        ref={inputRef}
        className="otp-input"
        inputMode="numeric"
        autoComplete="one-time-code"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
      />
    </Field>
  );
}
