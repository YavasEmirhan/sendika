-- HakKöprü — pilot (MVP-0) şeması
--
-- Güvenlik modeli:
--   * Tabloların sahibi migration rolüdür (hk_owner). Uygulama, sahibi olmadığı
--     ve BYPASSRLS yetkisi olmayan hk_app rolüyle bağlanır.
--   * Kiracıya ait her tabloda tenant_id zorunludur ve Row Level Security açıktır.
--   * Kiracı bağlamı her istekte transaction içinde `SET LOCAL app.tenant_id` ile
--     verilir. Bağlam yoksa current_setting(...) NULL döner ve hiçbir satır
--     görünmez: sistem "kapalı başarısız" olur.
--   * Serbest metin ve iletişim bilgileri uygulama katmanında şifrelenir
--     (*_enc kolonları); veritabanında açık metin tutulmaz.
--   * audit_events uygulama rolü için yalnızca INSERT/SELECT'tir; güncellenemez,
--     silinemez.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Kiracı bağlamını tek yerden okuyan yardımcı fonksiyon.
CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

-- ---------------------------------------------------------------------------
-- Kiracılar (kamuya açık profil bilgisi; RLS yok, uygulama yalnızca okur)
-- ---------------------------------------------------------------------------
CREATE TABLE tenants (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{2,40}$'),
    name            text NOT NULL,
    short_code      text NOT NULL UNIQUE CHECK (short_code ~ '^[A-Z]{2,5}$'),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    public_intro    text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Organizasyon birimleri: genel merkez / şube / birim (kuyruk sahibi)
-- ---------------------------------------------------------------------------
CREATE TABLE org_units (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    parent_id   uuid REFERENCES org_units(id),
    kind        text NOT NULL CHECK (kind IN ('headquarters', 'branch', 'unit')),
    name        text NOT NULL,
    -- Kural tabanlı yönlendirme: bu birimin hizmet verdiği iller
    service_cities text[] NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- Sendika personeli
-- ---------------------------------------------------------------------------
CREATE TABLE staff_users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    email           text NOT NULL,
    full_name       text NOT NULL,
    password_hash   text NOT NULL,
    totp_secret_enc text,
    mfa_enabled     boolean NOT NULL DEFAULT false,
    totp_last_step  bigint,                       -- aynı kodun tekrar kullanımını engeller
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    token_version   integer NOT NULL DEFAULT 0,   -- artırılınca tüm oturumlar düşer
    failed_logins   integer NOT NULL DEFAULT 0,
    locked_until    timestamptz,
    last_login_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email),
    UNIQUE (tenant_id, id)
);

CREATE TABLE role_assignments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    user_id     uuid NOT NULL,
    role        text NOT NULL CHECK (role IN (
                    'tenant_owner', 'org_admin', 'branch_manager',
                    'case_worker', 'legal_reviewer', 'auditor')),
    -- NULL: kiracı genelinde geçerli; dolu: yalnızca o birimde geçerli
    org_unit_id uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, user_id) REFERENCES staff_users(tenant_id, id),
    FOREIGN KEY (tenant_id, org_unit_id) REFERENCES org_units(tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- Başvuru konuları (kiracıya özel kategori ve varsayılan yönlendirme)
-- ---------------------------------------------------------------------------
CREATE TABLE categories (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL REFERENCES tenants(id),
    key                  text NOT NULL,
    label                text NOT NULL,
    help_text            text,
    default_priority     text NOT NULL CHECK (default_priority IN ('P1', 'P2', 'P3', 'P4')),
    default_org_unit_id  uuid,
    default_sensitivity  text NOT NULL DEFAULT 'normal' CHECK (default_sensitivity IN ('normal', 'restricted')),
    sort_order           integer NOT NULL DEFAULT 0,
    active               boolean NOT NULL DEFAULT true,
    UNIQUE (tenant_id, key),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, default_org_unit_id) REFERENCES org_units(tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- Aydınlatma / açık rıza metinleri (sürümlü)
-- ---------------------------------------------------------------------------
CREATE TABLE notices (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    kind        text NOT NULL CHECK (kind IN ('privacy_notice', 'explicit_consent')),
    version     text NOT NULL,
    title       text NOT NULL,
    summary     text NOT NULL,
    body        text NOT NULL,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, kind, version),
    UNIQUE (tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- Vakalar
-- ---------------------------------------------------------------------------
CREATE TABLE tenant_counters (
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    year        integer NOT NULL,
    last_value  integer NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, year)
);

CREATE TABLE cases (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               uuid NOT NULL REFERENCES tenants(id),
    reference_no            text NOT NULL,             -- insanların konuşurken kullandığı numara
    tracking_code_hash      text NOT NULL,             -- takip kodunun HMAC'i; kod saklanmaz
    channel                 text NOT NULL DEFAULT 'web' CHECK (channel IN ('web', 'phone', 'in_person', 'email')),
    category_id             uuid NOT NULL,
    org_unit_id             uuid NOT NULL,
    subject_enc             text NOT NULL,
    description_enc         text NOT NULL,
    workplace_enc           text,
    city                    text,
    status                  text NOT NULL DEFAULT 'received' CHECK (status IN (
                                'received', 'triage', 'waiting_info', 'assigned',
                                'in_progress', 'referred', 'resolved', 'closed_timeout')),
    priority                text NOT NULL CHECK (priority IN ('P1', 'P2', 'P3', 'P4')),
    sensitivity             text NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal', 'restricted')),
    assignee_id             uuid,
    is_anonymous            boolean NOT NULL,
    contact_method          text NOT NULL CHECK (contact_method IN ('none', 'email', 'phone')),
    contact_value_enc       text,
    contact_name_enc        text,
    safe_contact_note_enc   text,                      -- "hafta içi 18:00 sonrası" gibi
    first_response_due_at   timestamptz NOT NULL,
    first_responded_at      timestamptz,
    resolved_at             timestamptz,
    closure_code            text CHECK (closure_code IN (
                                'resolved_info_given', 'resolved_action_taken', 'referred_external',
                                'referred_legal', 'out_of_scope', 'duplicate', 'no_response')),
    tracking_failed_attempts integer NOT NULL DEFAULT 0,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, reference_no),
    UNIQUE (tenant_id, tracking_code_hash),
    UNIQUE (tenant_id, id),
    CHECK (is_anonymous OR contact_method <> 'none'),
    CHECK (contact_method = 'none' OR contact_value_enc IS NOT NULL),
    FOREIGN KEY (tenant_id, category_id) REFERENCES categories(tenant_id, id),
    FOREIGN KEY (tenant_id, org_unit_id) REFERENCES org_units(tenant_id, id),
    FOREIGN KEY (tenant_id, assignee_id) REFERENCES staff_users(tenant_id, id)
);
CREATE INDEX cases_queue_idx ON cases (tenant_id, org_unit_id, status, first_response_due_at);
CREATE INDEX cases_assignee_idx ON cases (tenant_id, assignee_id) WHERE assignee_id IS NOT NULL;

CREATE TABLE case_messages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    case_id     uuid NOT NULL,
    author_type text NOT NULL CHECK (author_type IN ('applicant', 'staff', 'system')),
    author_id   uuid,
    -- public: başvuru sahibi görür; internal: yalnızca personel (iç not)
    visibility  text NOT NULL CHECK (visibility IN ('public', 'internal')),
    body_enc    text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (author_type <> 'applicant' OR visibility = 'public'),
    FOREIGN KEY (tenant_id, case_id) REFERENCES cases(tenant_id, id),
    FOREIGN KEY (tenant_id, author_id) REFERENCES staff_users(tenant_id, id)
);
CREATE INDEX case_messages_case_idx ON case_messages (tenant_id, case_id, created_at);

-- Durum, atama ve öncelik değişikliklerinin geçmişi (vaka zaman çizelgesi)
CREATE TABLE case_events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    case_id     uuid NOT NULL,
    actor_type  text NOT NULL CHECK (actor_type IN ('applicant', 'staff', 'system')),
    actor_id    uuid,
    event_type  text NOT NULL,
    from_value  text,
    to_value    text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, case_id) REFERENCES cases(tenant_id, id)
);
CREATE INDEX case_events_case_idx ON case_events (tenant_id, case_id, created_at);

-- Aydınlatma gösterimi ve açık rıza kanıtı (birbirinden ayrı kayıtlar)
CREATE TABLE notice_receipts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    case_id     uuid NOT NULL,
    notice_id   uuid NOT NULL,
    shown_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, case_id) REFERENCES cases(tenant_id, id),
    FOREIGN KEY (tenant_id, notice_id) REFERENCES notices(tenant_id, id)
);

CREATE TABLE consent_records (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL REFERENCES tenants(id),
    case_id       uuid NOT NULL,
    notice_id     uuid NOT NULL,
    status        text NOT NULL CHECK (status IN ('given', 'withdrawn')),
    given_at      timestamptz NOT NULL DEFAULT now(),
    withdrawn_at  timestamptz,
    FOREIGN KEY (tenant_id, case_id) REFERENCES cases(tenant_id, id),
    FOREIGN KEY (tenant_id, notice_id) REFERENCES notices(tenant_id, id)
);

CREATE TABLE canned_responses (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    title       text NOT NULL,
    body        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Denetim kaydı (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_events (
    id           bigserial PRIMARY KEY,
    tenant_id    uuid NOT NULL REFERENCES tenants(id),
    actor_type   text NOT NULL CHECK (actor_type IN ('applicant', 'staff', 'system')),
    actor_id     uuid,
    action       text NOT NULL,
    target_type  text,
    target_id    uuid,
    reason       text,
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_target_idx ON audit_events (tenant_id, target_type, target_id, created_at);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'org_units', 'staff_users', 'role_assignments', 'categories', 'notices',
        'tenant_counters', 'cases', 'case_messages', 'case_events',
        'notice_receipts', 'consent_records', 'canned_responses', 'audit_events'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I
                 USING (tenant_id = app_current_tenant())
                 WITH CHECK (tenant_id = app_current_tenant())', t);
    END LOOP;
END $$;

-- tenant_id değiştirilemez: kiracılar arası kayıt taşıma ayrı bir süreçtir.
CREATE OR REPLACE FUNCTION forbid_tenant_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION 'tenant_id is immutable';
    END IF;
    RETURN NEW;
END $$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'org_units', 'staff_users', 'role_assignments', 'categories', 'notices',
        'cases', 'case_messages', 'consent_records', 'canned_responses'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON %I
                 FOR EACH ROW EXECUTE FUNCTION forbid_tenant_change()',
            t || '_tenant_immutable', t);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Uygulama rolü yetkileri
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO hk_app;
GRANT SELECT ON tenants TO hk_app;
GRANT SELECT, INSERT, UPDATE ON
    org_units, staff_users, role_assignments, categories, notices, tenant_counters,
    cases, consent_records, canned_responses
    TO hk_app;
GRANT DELETE ON role_assignments TO hk_app;
-- Mesajlar, olaylar, makbuzlar ve denetim kaydı değiştirilemez.
GRANT SELECT, INSERT ON case_messages, case_events, notice_receipts, audit_events TO hk_app;
GRANT USAGE ON SEQUENCE audit_events_id_seq TO hk_app;
GRANT EXECUTE ON FUNCTION app_current_tenant() TO hk_app;
