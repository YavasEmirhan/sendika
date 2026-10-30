export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  opts: { method?: string; body?: unknown; token?: string | null } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.");
  }
  if (!res.ok) {
    let message = "Beklenmeyen bir hata oluştu.";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      /* gövde JSON değil */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

// ---- Tipler -------------------------------------------------------------
export type Stage = { key: string; label: string };
export type Notice = { id: string; kind: string; version: string; title: string; summary: string; body: string };

export type TenantInfo = {
  tenant: { slug: string; name: string; intro: string | null };
  categories: { key: string; label: string; help_text: string | null }[];
  privacy_notice: Notice | null;
  explicit_consent: Notice | null;
  stages: Stage[];
};

export type SubmitResult = {
  reference_no: string;
  tracking_code: string;
  first_response_due_at: string;
  priority_label: string;
  stage: Stage;
};

export type ApplicantCase = {
  reference_no: string;
  category: string;
  subject: string;
  created_at: string;
  stage: Stage;
  timeline: (Stage & { at: string })[];
  messages: { id: string; from: "applicant" | "staff" | "system"; author: string | null; body: string; at: string }[];
  can_reply: boolean;
  is_anonymous: boolean;
  consent_status: "given" | "withdrawn" | null;
};

export type Me = {
  id: string;
  email: string;
  full_name: string;
  tenant: { slug: string; name: string };
  roles: { role: string; label: string; org_unit: string | null }[];
  permissions: { handle_cases: boolean; view_reports: boolean; view_restricted: boolean };
};

export type CaseRow = {
  id: string;
  reference_no: string;
  subject: string;
  category: string;
  org_unit: string;
  city: string | null;
  status: string;
  status_label: string;
  priority: "P1" | "P2" | "P3" | "P4";
  sensitivity: "normal" | "restricted";
  is_anonymous: boolean;
  assignee: string | null;
  assignee_id: string | null;
  first_response_due_at: string;
  first_responded_at: string | null;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
  awaiting_reply: boolean;
};

export type CaseList = {
  counts: Record<"open" | "mine" | "unassigned" | "overdue" | "waiting", number>;
  items: CaseRow[];
};

export type CaseDetail = {
  id: string;
  reference_no: string;
  channel: string;
  category: string;
  org_unit: string;
  org_unit_id: string;
  subject: string;
  description: string;
  workplace: string | null;
  city: string | null;
  status: string;
  status_label: string;
  public_stage: Stage;
  allowed_transitions: string[];
  priority: "P1" | "P2" | "P3" | "P4";
  sensitivity: "normal" | "restricted";
  assignee_id: string | null;
  assignee: string | null;
  is_anonymous: boolean;
  contact: { method: "none" | "email" | "phone"; masked: string | null; has_name: boolean; safe_contact_note: string | null };
  first_response_due_at: string;
  first_responded_at: string | null;
  is_overdue: boolean;
  closure_code: string | null;
  closure_label: string | null;
  created_at: string;
  messages: { id: string; author_type: string; author: string | null; visibility: "public" | "internal"; body: string; created_at: string }[];
  events: { event_type: string; from_value: string | null; to_value: string | null; actor_type: string; created_at: string; full_name: string | null; assignee_name: string | null }[];
  privacy: {
    notice_version: string | null;
    notice_shown_at: string | null;
    consent: { status: string; given_at: string; withdrawn_at: string | null; version: string } | null;
  };
  permissions: { assign_others: boolean };
  access_log: { action: string; reason: string | null; created_at: string; actor: string | null }[] | null;
};

export type Meta = {
  statuses: { key: string; label: string }[];
  priorities: { key: string; label: string }[];
  closure_codes: { key: string; label: string }[];
  org_units: { id: string; name: string; kind: string }[];
  categories: { id: string; key: string; label: string }[];
  canned_responses: { id: string; title: string; body: string }[];
};

export type Summary = {
  days: number;
  kpi: {
    created: number;
    responded: number;
    responded_in_sla: number;
    overdue_now: number;
    closed: number;
    anonymous: number;
    sla_rate: number | null;
    median_first_response_hours: number | null;
    median_resolution_days: number | null;
  };
  open_by_status: { status: string; label: string; n: number }[];
  by_category: { label: string; n: number; median_hours: number | null }[];
  by_unit: { name: string; open: number; overdue: number; created: number }[];
  by_priority: { priority: string; label: string; n: number; sla_rate: number | null }[];
  daily: { day: string; n: number }[];
};
