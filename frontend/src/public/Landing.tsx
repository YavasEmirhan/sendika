import { Link } from "react-router-dom";
import { useTenant } from "./PublicLayout";

const HOW = [
  { title: "Sorununuzu anlatırsınız", text: "Konuyu seçip yaşadığınızı kendi cümlelerinizle yazarsınız. Yaklaşık 5 dakika sürer." },
  { title: "Bir takip kodu alırsınız", text: "Kod yalnızca sizde olur. Başvurunuzu bu kodla açarsınız; hesap açmanız gerekmez." },
  { title: "Bir temsilci yanıt verir", text: "Size hangi süre içinde dönüleceğini başvuru sonunda görürsünüz." },
  { title: "Süreci kodla izlersiniz", text: "Yanıtları okur, istenirse ek bilgi gönderirsiniz." },
];

export default function Landing() {
  const { tenant } = useTenant();
  const base = `/t/${tenant.slug}`;
  return (
    <>
      <section className="hero">
        <h1>İşyerinizdeki sorunu bize anlatın.</h1>
        <p className="lede">Kim olduğunuzu söylemek zorunda değilsiniz. Başvurunuzu yalnızca sendikanın yetkili temsilcileri görür.</p>
        <div className="hero-actions">
          <Link className="btn" to={`${base}/basvuru`}>
            Başvuru yap
          </Link>
          <Link className="btn secondary" to={`${base}/takip`}>
            Başvurumu takip et
          </Link>
        </div>
      </section>

      <section className="section" aria-labelledby="nasil">
        <h2 id="nasil">Başvurunuz nasıl ilerler?</h2>
        <ol className="wire compact">
          {HOW.map((s, i) => (
            <li key={s.title} className={i === 0 ? "current" : undefined}>
              <span className="node" />
              <span className="stage-name" style={{ color: "var(--ink)", fontWeight: 600 }}>
                {s.title}
                <span className="stage-meta">{s.text}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section className="section" aria-labelledby="gizlilik">
        <h2 id="gizlilik">Bilgileriniz nasıl korunur?</h2>
        <ul className="promise-list">
          <li>
            <Check />
            <div>
              <strong>İşvereninizle paylaşılmaz</strong>
              <span>Başvurunuz sendika dışında kimseye iletilmez.</span>
            </div>
          </li>
          <li>
            <Check />
            <div>
              <strong>İletişim bilgisi bırakmak isteğe bağlı</strong>
              <span>Adınızı ve telefonunuzu vermeden başvurabilir, yanıtları takip koduyla okuyabilirsiniz.</span>
            </div>
          </li>
          <li>
            <Check />
            <div>
              <strong>Hassas konular ayrı tutulur</strong>
              <span>Taciz ve ayrımcılık başvurularını yalnızca hukuk birimi görür.</span>
            </div>
          </li>
          <li>
            <Check />
            <div>
              <strong>Kim baktıysa kayda geçer</strong>
              <span>Başvurunuzu açan ve iletişim bilginizi görüntüleyen her temsilci sistemde kayıtlıdır.</span>
            </div>
          </li>
        </ul>
        <p className="hint" style={{ color: "var(--ink-2)", fontSize: "var(--t-s)" }}>
          Şirket bilgisayarı veya şirket e-postası kullanıyorsanız, başvurunuzu kişisel telefonunuzdan yapmanızı öneririz.
        </p>
      </section>

      <div className="emergency">
        <strong>Acil bir tehlike varsa</strong> bu formu kullanmayın, hemen <a href="tel:112">112</a>'yi arayın. Bu hat
        acil durumlar için izlenmez.
      </div>
    </>
  );
}

function Check() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" style={{ marginTop: 2 }}>
      <circle cx="11" cy="11" r="11" fill="#e2eeee" />
      <path d="M6.5 11.3l3 3 6-6.3" fill="none" stroke="#0e5a62" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
