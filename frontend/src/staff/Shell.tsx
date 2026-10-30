import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import type { CaseList, Meta } from "../api";
import { BrandMark } from "../components";
import { useAuth } from "./auth";

type Counts = CaseList["counts"];
type ShellState = { meta: Meta | null; counts: Counts | null; setCounts: (c: Counts) => void; refreshCounts: () => void };
const ShellContext = createContext<ShellState>({ meta: null, counts: null, setCounts: () => {}, refreshCounts: () => {} });
export const useShell = () => useContext(ShellContext);

const VIEWS: { key: string; label: string; count?: keyof Counts; alert?: boolean }[] = [
  { key: "open", label: "Açık başvurular", count: "open" },
  { key: "mine", label: "Bana atananlar", count: "mine" },
  { key: "unassigned", label: "Atanmamış", count: "unassigned", alert: true },
  { key: "overdue", label: "Hedefi geçenler", count: "overdue", alert: true },
  { key: "waiting", label: "Bilgi beklenenler", count: "waiting" },
  { key: "closed", label: "Sonuçlananlar" },
];

export default function Shell() {
  const { me, call, logout, slug } = useAuth();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const base = `/t/${slug}/panel`;
  const onInbox = location.pathname === base || location.pathname === `${base}/`;
  const activeView = params.get("view") ?? "open";

  const refreshCounts = useCallback(() => {
    if (!me.permissions.handle_cases) return;
    call<CaseList>("/cases?view=open").then((r) => setCounts(r.counts)).catch(() => {});
  }, [call, me.permissions.handle_cases]);

  useEffect(() => {
    call<Meta>("/meta").then(setMeta).catch(() => {});
    refreshCounts();
    document.title = `${me.tenant.name} | Panel`;
  }, [call, refreshCounts, me.tenant.name]);

  useEffect(() => {
    if (!me.permissions.handle_cases && onInbox && me.permissions.view_reports) navigate(`${base}/rapor`, { replace: true });
  }, [me, onInbox, navigate, base]);

  return (
    <ShellContext.Provider value={{ meta, counts, setCounts, refreshCounts }}>
      <div className="staff-app">
        <aside className="sidebar">
          <div className="brand">
            <BrandMark onDark />
            <span className="brand-name">
              {me.tenant.name}
              <span className="brand-sub">Başvuru masası</span>
            </span>
          </div>
          <nav className="side-nav" aria-label="Panel">
            {me.permissions.handle_cases && (
              <>
                <span className="group-label">Başvurular</span>
                {VIEWS.map((v) => {
                  const n = v.count && counts ? counts[v.count] : null;
                  const current = onInbox && activeView === v.key;
                  return (
                    <Link
                      key={v.key}
                      to={`${base}?view=${v.key}`}
                      aria-current={current ? "page" : undefined}
                     
                    >
                      <span>{v.label}</span>
                      {n !== null && n !== undefined && (
                        <span className={`count ${v.alert && n > 0 ? "alert-count" : ""}`}>{n}</span>
                      )}
                    </Link>
                  );
                })}
              </>
            )}
            {me.permissions.view_reports && (
              <>
                <span className="group-label">Yönetim</span>
                <Link to={`${base}/rapor`} aria-current={location.pathname.endsWith("/rapor") ? "page" : undefined}>
                  <span>Hizmet raporu</span>
                </Link>
              </>
            )}
            <span className="group-label">Kamu sayfası</span>
            <a href={`/t/${slug}`} target="_blank" rel="noreferrer">
              <span>Başvuru sayfasını aç</span>
            </a>
          </nav>
          <div className="side-user">
            <strong>{me.full_name}</strong>
            <span className="roles">
              {me.roles.map((r) => (r.org_unit ? `${r.label}, ${r.org_unit}` : r.label)).join("; ")}
            </span>
            <button onClick={() => logout()} title="Tüm cihazlardaki oturumlarınız kapanır">
              Çıkış yap
            </button>
          </div>
        </aside>
        <main className="staff-main" id="icerik">
          <Outlet />
        </main>
      </div>
    </ShellContext.Provider>
  );
}
