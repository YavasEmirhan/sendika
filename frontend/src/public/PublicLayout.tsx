import { createContext, useContext, useEffect, useState } from "react";
import { Link, Outlet, useParams } from "react-router-dom";
import { api, type TenantInfo } from "../api";
import { BrandMark, ErrorAlert } from "../components";

const TenantContext = createContext<TenantInfo | null>(null);
export const useTenant = () => useContext(TenantContext)!;

/** Paylaşılan cihazda hızlıca ayrılmak için: sayfa geçmişte geri tuşuyla dönülemeyecek şekilde değişir. */
function quickExit() {
  window.location.replace("https://www.google.com/search?q=hava+durumu");
}

export default function PublicLayout() {
  const { slug } = useParams();
  const [info, setInfo] = useState<TenantInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInfo(null);
    api<TenantInfo>(`/api/t/${slug}`)
      .then((d) => {
        setInfo(d);
        document.title = `${d.tenant.name} | Başvuru`;
      })
      .catch((e) => setError(e.message));
  }, [slug]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && e.shiftKey) quickExit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <a className="skip-link" href="#icerik">
        İçeriğe geç
      </a>
      <header className="pub-header">
        <div className="inner">
          <Link to={`/t/${slug}`} className="brand">
            <BrandMark />
            <span className="brand-name">
              {info?.tenant.name ?? " "}
              <span className="brand-sub">Çalışan başvuru hattı</span>
            </span>
          </Link>
          <button className="quick-exit" onClick={quickExit} title="Kısayol: Shift + Esc">
            Hızlı çıkış
          </button>
        </div>
      </header>
      <main id="icerik" className="pub-main">
        {error ? (
          <ErrorAlert message={error} />
        ) : info ? (
          <TenantContext.Provider value={info}>
            <Outlet />
          </TenantContext.Provider>
        ) : (
          <p className="loading">Yükleniyor…</p>
        )}
      </main>
      <footer className="pub-footer">
        <p>Bu hat genel bilgilendirme ve sendikaya ulaşma amaçlıdır; hukuki danışmanlık yerine geçmez.</p>
        <p>
          Pilot sürüm. Hızlı çıkış düğmesi bu sayfadan hemen ayrılmanızı sağlar; tarayıcı geçmişinizi ayrıca
          temizlemeniz gerekebilir.
        </p>
      </footer>
    </>
  );
}
