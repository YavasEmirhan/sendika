import "@fontsource-variable/schibsted-grotesk";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Apply from "./public/Apply";
import Landing from "./public/Landing";
import PublicLayout from "./public/PublicLayout";
import Track from "./public/Track";
import { RequireStaff } from "./staff/auth";
import CaseDetail from "./staff/CaseDetail";
import Inbox from "./staff/Inbox";
import Login from "./staff/Login";
import Reports from "./staff/Reports";
import Shell from "./staff/Shell";

const DEFAULT_TENANT = import.meta.env.VITE_DEFAULT_TENANT ?? "ornek-enerji";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to={`/t/${DEFAULT_TENANT}`} replace />} />
        <Route path="/t/:slug/panel/giris" element={<Login />} />
        <Route
          path="/t/:slug/panel"
          element={
            <RequireStaff>
              <Shell />
            </RequireStaff>
          }
        >
          <Route index element={<Inbox />} />
          <Route path="vaka/:id" element={<CaseDetail />} />
          <Route path="rapor" element={<Reports />} />
        </Route>
        <Route path="/t/:slug" element={<PublicLayout />}>
          <Route index element={<Landing />} />
          <Route path="basvuru" element={<Apply />} />
          <Route path="takip" element={<Track />} />
        </Route>
        <Route path="*" element={<p className="loading">Sayfa bulunamadı.</p>} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
