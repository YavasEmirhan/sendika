import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { api, ApiError, type Me } from "../api";

type Auth = {
  slug: string;
  token: string;
  me: Me;
  call: <T>(path: string, opts?: { method?: string; body?: unknown }) => Promise<T>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<Auth | null>(null);
export const useAuth = () => useContext(AuthContext)!;

const key = (slug: string) => `hk.staff.${slug}`;

// Pilot: belirteç sekme oturumunda tutulur (sekme kapanınca silinir).
// Üretim öncesi httpOnly çerez + CSRF korumasına geçilmesi planlanıyor.
export function saveToken(slug: string, token: string) {
  sessionStorage.setItem(key(slug), token);
}
function readToken(slug: string) {
  return sessionStorage.getItem(key(slug));
}
function clearToken(slug: string) {
  sessionStorage.removeItem(key(slug));
}

export function RequireStaff({ children }: { children: ReactNode }) {
  const { slug = "" } = useParams();
  const location = useLocation();
  const [token, setToken] = useState<string | null>(() => readToken(slug));
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) return;
    api<Me>(`/api/t/${slug}/staff/me`, { token })
      .then(setMe)
      .catch(() => {
        clearToken(slug);
        setToken(null);
        setFailed(true);
      });
  }, [slug, token]);

  const expire = useCallback(() => {
    clearToken(slug);
    setToken(null);
    setFailed(true);
  }, [slug]);

  const value = useMemo<Auth | null>(() => {
    if (!token || !me) return null;
    return {
      slug,
      token,
      me,
      call: async <T,>(path: string, opts: { method?: string; body?: unknown } = {}) => {
        try {
          return await api<T>(`/api/t/${slug}/staff${path}`, { ...opts, token });
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) expire();
          throw e;
        }
      },
      logout: async () => {
        try {
          await api(`/api/t/${slug}/staff/logout`, { method: "POST", token });
        } finally {
          clearToken(slug);
          setToken(null);
          setMe(null);
        }
      },
    };
  }, [token, me, slug, expire]);

  if (!token) {
    return <Navigate to={`/t/${slug}/panel/giris`} replace state={{ from: location.pathname, expired: failed }} />;
  }
  if (!value) return <p className="loading">Yükleniyor…</p>;
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
