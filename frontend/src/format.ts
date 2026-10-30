const TZ = "Europe/Istanbul";

export function dateTime(iso: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TZ,
  }).format(new Date(iso));
}

export function shortDate(iso: string): string {
  return new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", timeZone: TZ }).format(new Date(iso));
}

export function relative(iso: string, now = Date.now()): string {
  const diff = new Date(iso).getTime() - now;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("tr", { numeric: "auto" });
  const min = 60_000;
  const hour = 60 * min;
  const day = 24 * hour;
  if (abs < hour) return rtf.format(Math.round(diff / min), "minute");
  if (abs < day) return rtf.format(Math.round(diff / hour), "hour");
  return rtf.format(Math.round(diff / day), "day");
}

/** SLA durumunu sade dille anlatır. */
export function slaText(due: string, responded: string | null, closed: boolean): { text: string; tone: "ok" | "warn" | "late" | "done" } {
  if (responded) return { text: "Yanıtlandı", tone: "done" };
  if (closed) return { text: "Kapandı", tone: "done" };
  const ms = new Date(due).getTime() - Date.now();
  if (ms < 0) return { text: `${relative(due).replace(" önce", "")} gecikti`, tone: "late" };
  if (ms < 4 * 3_600_000) return { text: `Hedef ${relative(due)}`, tone: "warn" };
  return { text: `Hedef ${relative(due)}`, tone: "ok" };
}

export function hours(h: number | null): string {
  if (h === null) return "—";
  if (h < 1) return `${Math.round(h * 60)} dk`;
  if (h < 48) return `${h.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} sa`;
  return `${(h / 24).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} gün`;
}
