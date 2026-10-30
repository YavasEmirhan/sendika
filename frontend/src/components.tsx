import type { ReactNode } from "react";
import type { Stage } from "./api";
import { dateTime } from "./format";

export function BrandMark({ size = 30, onDark = false }: { size?: number; onDark?: boolean }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill={onDark ? "#ffffff" : "#0e5a62"} />
      <path
        d="M6 22c3.2-6.5 6.6-9.5 10-9.5s6.8 3 10 9.5"
        fill="none"
        stroke={onDark ? "#0e5a62" : "#ffffff"}
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path d="M6 22h20" stroke={onDark ? "#0e5a62" : "#ffffff"} strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="16" cy="12.5" r="3.2" fill="#e2a93b" />
    </svg>
  );
}

const MAIN_PATH = ["received", "reviewing", "resolved"];

/** Başvurunun ilerleyişi: geçilen aşamalar, şu anki aşama ve kalan ana aşamalar. */
export function StageWire({
  timeline,
  current,
  stages,
}: {
  timeline: (Stage & { at: string })[];
  current: Stage;
  stages: Stage[];
}) {
  const labels = Object.fromEntries(stages.map((s) => [s.key, s.label]));
  const finished = current.key === "resolved";
  const seen = new Set(timeline.map((t) => t.key));
  const idx = MAIN_PATH.indexOf(current.key);
  const upcoming = MAIN_PATH.filter((k, i) => !seen.has(k) && (idx === -1 ? i > 0 : i > idx));

  return (
    <ol className="wire" aria-label="Başvurunuzun aşamaları">
      {timeline.map((t, i) => {
        const isCurrent = !finished && i === timeline.length - 1;
        return (
          <li key={`${t.key}-${i}`} className={isCurrent ? "current" : "done"} aria-current={isCurrent ? "step" : undefined}>
            <span className="node" />
            <span className="stage-name">
              {t.label}
              <span className="stage-meta">
                {isCurrent ? "Şu anki aşama, " : ""}
                {dateTime(t.at)}
              </span>
            </span>
          </li>
        );
      })}
      {upcoming.map((k) => (
        <li key={k}>
          <span className="node" />
          <span className="stage-name">
            {labels[k] ?? k}
            <span className="stage-meta">Henüz değil</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export function Field({
  id,
  label,
  hint,
  optional,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  optional?: boolean;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>
        {label} {optional && <span className="optional">(isteğe bağlı)</span>}
      </label>
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {children}
      {error && (
        <p className="error-text" id={`${id}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function ErrorAlert({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="alert error" role="alert">
      {message}
    </div>
  );
}
