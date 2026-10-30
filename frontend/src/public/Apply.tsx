import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type SubmitResult } from "../api";
import { ErrorAlert, Field } from "../components";
import { dateTime } from "../format";
import { useTenant } from "./PublicLayout";

const CITIES = [
  "Adana", "Ankara", "Antalya", "Aydın", "Balıkesir", "Bilecik", "Bursa", "Denizli", "Diyarbakır", "Edirne",
  "Erzurum", "Eskişehir", "Gaziantep", "Hatay", "İstanbul", "İzmir", "Kayseri", "Kırıkkale", "Kocaeli", "Konya",
  "Manisa", "Mersin", "Muğla", "Sakarya", "Samsun", "Tekirdağ", "Trabzon", "Zonguldak",
];

type Contact = "none" | "email" | "phone";

type Form = {
  category_key: string;
  subject: string;
  description: string;
  city: string;
  workplace: string;
  contact_method: Contact;
  contact_value: string;
  share_name: boolean;
  contact_name: string;
  safe_contact_note: string;
  consent: boolean;
};

const EMPTY: Form = {
  category_key: "",
  subject: "",
  description: "",
  city: "",
  workplace: "",
  contact_method: "none",
  contact_value: "",
  share_name: false,
  contact_name: "",
  safe_contact_note: "",
  consent: false,
};

const STEP_TITLES = ["Konu", "Ne yaşadınız?", "Size nasıl ulaşalım?"];

export default function Apply() {
  const info = useTenant();
  // Bilinçli olarak yalnızca bellekte tutulur: paylaşılan cihazda taslak iz bırakmaz.
  const [form, setForm] = useState<Form>(EMPTY);
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [step, result]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setErrors((e) => ({ ...e, [k]: undefined }));
  };

  function validate(s: number): boolean {
    const e: Partial<Record<keyof Form, string>> = {};
    if (s === 0 && !form.category_key) e.category_key = "Devam etmek için bir konu seçin.";
    if (s === 1) {
      if (form.subject.trim().length < 3) e.subject = "Kısa bir başlık yazın (en az 3 karakter).";
      if (form.description.trim().length < 10) e.description = "Yaşadığınızı biraz daha anlatın (en az 10 karakter).";
    }
    if (s === 2) {
      if (form.contact_method === "email" && !/^\S+@\S+\.\S+$/.test(form.contact_value.trim()))
        e.contact_value = "Geçerli bir e-posta adresi girin.";
      if (form.contact_method === "phone" && form.contact_value.replace(/\D/g, "").length < 10)
        e.contact_value = "Telefon numaranızı alan koduyla birlikte girin.";
      if (form.share_name && form.contact_method !== "none" && !form.contact_name.trim())
        e.contact_name = "Adınızı yazın ya da adınızı paylaşmama seçeneğine dönün.";
    }
    setErrors(e);
    const first = Object.keys(e)[0];
    if (first) document.getElementById(`f-${first}`)?.focus();
    return !first;
  }

  function next() {
    if (validate(step)) setStep((s) => s + 1);
  }

  async function submit() {
    if (!validate(2) || !info.privacy_notice) return;
    setSubmitting(true);
    setServerError(null);
    const anonymous = form.contact_method === "none" || !form.share_name;
    try {
      const r = await api<SubmitResult>(`/api/t/${info.tenant.slug}/cases`, {
        body: {
          category_key: form.category_key,
          subject: form.subject,
          description: form.description,
          city: form.city || null,
          workplace: form.workplace || null,
          is_anonymous: anonymous,
          contact_method: form.contact_method,
          contact_value: form.contact_method === "none" ? null : form.contact_value,
          contact_name: anonymous ? null : form.contact_name,
          safe_contact_note: form.safe_contact_note || null,
          privacy_notice_id: info.privacy_notice.id,
          explicit_consent_notice_id: form.consent && info.explicit_consent ? info.explicit_consent.id : null,
        },
      });
      setResult(r);
      setForm(EMPTY);
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : "Başvuru gönderilemedi.");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) return <Success result={result} slug={info.tenant.slug} headingRef={headingRef} />;

  const category = info.categories.find((c) => c.key === form.category_key);

  return (
    <div>
      <div className="steps-head">
        <div className="steps-bar" aria-hidden="true">
          {STEP_TITLES.map((t, i) => (
            <span key={t} className={i <= step ? "on" : undefined} />
          ))}
        </div>
        <p className="steps-count">
          Adım {step + 1} / {STEP_TITLES.length}
        </p>
        <h1 ref={headingRef} tabIndex={-1} style={{ fontSize: "var(--t-xl)", outline: "none" }}>
          {STEP_TITLES[step]}
        </h1>
      </div>

      {step === 0 && (
        <div className="form-stack">
          <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="visually-hidden">Başvurunuzun konusu</legend>
            <p className="hint" style={{ marginBottom: 10 }}>
              Size en yakın olanı seçin. Emin değilseniz "Genel bilgi ve soru" seçeneği uygundur.
            </p>
            <div className="choice-list" id="f-category_key" tabIndex={-1}>
              {info.categories.map((c) => (
                <label key={c.key} className="choice">
                  <input
                    type="radio"
                    name="category"
                    value={c.key}
                    checked={form.category_key === c.key}
                    onChange={() => set("category_key", c.key)}
                  />
                  <div>
                    <strong>{c.label}</strong>
                    {c.help_text && <span>{c.help_text}</span>}
                  </div>
                </label>
              ))}
            </div>
            {errors.category_key && (
              <p className="error-text" role="alert" style={{ marginTop: 8 }}>
                {errors.category_key}
              </p>
            )}
          </fieldset>
        </div>
      )}

      {step === 1 && (
        <div className="form-stack">
          <p className="hint" style={{ color: "var(--ink-2)" }}>
            Konu: <strong style={{ color: "var(--ink)" }}>{category?.label}</strong>
          </p>
          <Field id="f-subject" label="Kısaca başlık" hint="Örneğin: Üç aydır fazla mesai ücreti ödenmiyor" error={errors.subject}>
            <input
              id="f-subject"
              value={form.subject}
              maxLength={140}
              onChange={(e) => set("subject", e.target.value)}
              aria-invalid={!!errors.subject}
              aria-describedby="f-subject-hint"
            />
          </Field>
          <Field
            id="f-description"
            label="Ne oldu?"
            hint="Ne zaman başladığını ve kimleri etkilediğini yazmanız yardımcı olur. Kimlik numarası, sağlık raporu gibi bilgileri yazmanıza gerek yok."
            error={errors.description}
          >
            <textarea
              id="f-description"
              value={form.description}
              maxLength={5000}
              onChange={(e) => set("description", e.target.value)}
              aria-invalid={!!errors.description}
              aria-describedby="f-description-hint"
            />
            <span className="counter">{form.description.length} / 5000</span>
          </Field>
          <Field id="f-city" label="Çalıştığınız il" optional hint="Başvurunuzu size en yakın şubeye yönlendirmek için kullanılır.">
            <input id="f-city" list="cities" value={form.city} maxLength={60} onChange={(e) => set("city", e.target.value)} />
            <datalist id="cities">
              {CITIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </Field>
          <Field id="f-workplace" label="İşyeri" optional hint="Sorunu doğru değerlendirmemize yardımcı olur; yazmak zorunda değilsiniz.">
            <input id="f-workplace" value={form.workplace} maxLength={200} onChange={(e) => set("workplace", e.target.value)} />
          </Field>
        </div>
      )}

      {step === 2 && (
        <div className="form-stack">
          <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="label" style={{ fontWeight: 600, marginBottom: 8 }}>
              Size nasıl dönelim?
            </legend>
            <div className="choice-list">
              <label className="choice">
                <input type="radio" name="contact" checked={form.contact_method === "none"} onChange={() => set("contact_method", "none")} />
                <div>
                  <strong>İletişim bilgisi bırakmıyorum</strong>
                  <span>Tamamen anonim kalırsınız. Yanıtları takip kodunuzla bu sitede okursunuz.</span>
                </div>
              </label>
              <label className="choice">
                <input type="radio" name="contact" checked={form.contact_method === "email"} onChange={() => set("contact_method", "email")} />
                <div>
                  <strong>E-posta adresimi bırakıyorum</strong>
                  <span>Temsilci gerekirse size yazar. İş e-postanızı kullanmamanızı öneririz.</span>
                </div>
              </label>
              <label className="choice">
                <input type="radio" name="contact" checked={form.contact_method === "phone"} onChange={() => set("contact_method", "phone")} />
                <div>
                  <strong>Telefon numaramı bırakıyorum</strong>
                  <span>Temsilci gerekirse sizi arar. Hangi saatlerde aranabileceğinizi belirtebilirsiniz.</span>
                </div>
              </label>
            </div>
          </fieldset>

          {form.contact_method !== "none" && (
            <>
              <Field
                id="f-contact_value"
                label={form.contact_method === "email" ? "E-posta adresiniz" : "Telefon numaranız"}
                error={errors.contact_value}
              >
                <input
                  id="f-contact_value"
                  type={form.contact_method === "email" ? "email" : "tel"}
                  autoComplete={form.contact_method === "email" ? "email" : "tel"}
                  value={form.contact_value}
                  maxLength={200}
                  onChange={(e) => set("contact_value", e.target.value)}
                  aria-invalid={!!errors.contact_value}
                />
              </Field>
              <Field
                id="f-safe_contact_note"
                label="Size ne zaman ulaşmamız güvenli?"
                optional
                hint="Örneğin: Hafta içi 18:00'den sonra"
              >
                <input
                  id="f-safe_contact_note"
                  value={form.safe_contact_note}
                  maxLength={200}
                  onChange={(e) => set("safe_contact_note", e.target.value)}
                />
              </Field>
              <label className="check">
                <input type="checkbox" checked={form.share_name} onChange={(e) => set("share_name", e.target.checked)} />
                <span>Adımı da paylaşmak istiyorum</span>
              </label>
              {form.share_name && (
                <Field id="f-contact_name" label="Adınız" error={errors.contact_name}>
                  <input
                    id="f-contact_name"
                    autoComplete="name"
                    value={form.contact_name}
                    maxLength={120}
                    onChange={(e) => set("contact_name", e.target.value)}
                    aria-invalid={!!errors.contact_name}
                  />
                </Field>
              )}
            </>
          )}

          {info.privacy_notice && (
            <div className="notice-box">
              <h3>{info.privacy_notice.title}</h3>
              <p>{info.privacy_notice.summary}</p>
              <details>
                <summary>Metnin tamamını oku</summary>
                <pre>{info.privacy_notice.body}</pre>
              </details>
            </div>
          )}

          {info.explicit_consent && (
            <div className="notice-box">
              <label className="check">
                <input type="checkbox" checked={form.consent} onChange={(e) => set("consent", e.target.checked)} />
                <span>
                  <strong>{info.explicit_consent.title}</strong>
                  <br />
                  {info.explicit_consent.summary}
                </span>
              </label>
            </div>
          )}

          <ErrorAlert message={serverError} />
        </div>
      )}

      <div className="form-actions" style={{ marginTop: 28 }}>
        {step > 0 ? (
          <button className="btn secondary" onClick={() => setStep((s) => s - 1)} disabled={submitting}>
            Geri
          </button>
        ) : (
          <Link className="btn quiet" to={`/t/${info.tenant.slug}`}>
            Vazgeç
          </Link>
        )}
        {step < 2 ? (
          <button className="btn" onClick={next}>
            Devam et
          </button>
        ) : (
          <button className="btn" onClick={submit} disabled={submitting}>
            {submitting ? "Gönderiliyor…" : "Başvuruyu gönder"}
          </button>
        )}
      </div>
      <p className="hint" style={{ color: "var(--ink-3)", fontSize: "var(--t-xs)", marginTop: 14 }}>
        Yazdıklarınız bu cihaza kaydedilmez. Sayfayı kapatırsanız baştan başlamanız gerekir.
      </p>
    </div>
  );
}

function Success({
  result,
  slug,
  headingRef,
}: {
  result: SubmitResult;
  slug: string;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(result.tracking_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      /* panoya erişim yoksa kullanıcı kodu elle not eder */
    }
  }
  return (
    <div className="form-stack">
      <div className="case-head">
        <h1 ref={headingRef} tabIndex={-1} style={{ outline: "none" }}>
          Başvurunuz alındı.
        </h1>
        <p style={{ color: "var(--ink-2)" }}>Aşağıdaki takip kodunu şimdi bir yere not edin.</p>
      </div>

      <div className="ticket">
        <span className="label">Takip kodunuz</span>
        <span className="code" aria-label={`Takip kodu: ${result.tracking_code.split("").join(" ")}`}>
          {result.tracking_code}
        </span>
        <div className="row">
          <button className="btn small" onClick={copy}>
            {copied ? "Kopyalandı" : "Kodu kopyala"}
          </button>
        </div>
        <div className="perforation" />
        <dl>
          <dt>Başvuru numarası</dt>
          <dd>{result.reference_no}</dd>
          <dt>İlk yanıt hedefi</dt>
          <dd>{dateTime(result.first_response_due_at)}</dd>
        </dl>
      </div>

      <div className="alert warn">
        <strong>Bu kodu kaybederseniz geri getiremeyiz.</strong> Gizliliğiniz için kodu biz de saklamıyoruz. Ekran
        görüntüsü almak yerine kodu güvendiğiniz bir yere yazmanızı öneririz.
      </div>

      <p>
        Yanıt geldiğinde okumak için <Link to={`/t/${slug}/takip`}>Başvurumu takip et</Link> sayfasına bu kodla girin.
      </p>
    </div>
  );
}
