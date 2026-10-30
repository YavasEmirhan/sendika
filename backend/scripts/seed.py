"""Sentetik demo verisi.

İçerikteki tüm kişi, işyeri ve olaylar kurgusaldır. Gerçek kişisel veri
kullanılmaz (PROJE_PLANI.md §15.3, §23.6).

Kullanım:  python -m scripts.seed           (veritabanı boşsa)
           python -m scripts.seed --reset   (tüm demo verisini silip yeniden kurar)
"""
import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import Connection, create_engine, text

from app.audit import case_event
from app.config import get_settings
from app.schemas import CaseCreate
from app.security import enc, hash_password, new_totp_secret
from app.services.cases import create_case

DEMO_PASSWORD = "Pilot.Demo2026!"
MFA_FILE = Path(os.environ.get("DEMO_MFA_FILE", Path(__file__).resolve().parent.parent / ".demo-mfa.json"))

PRIVACY_NOTICE = {
    "version": "taslak-0.1",
    "title": "Kişisel verilerinizin işlenmesi hakkında aydınlatma",
    "summary": (
        "Başvurunuzu yanıtlamak için yalnızca bu formda verdiğiniz bilgileri işliyoruz. "
        "Bilgilerinizi işvereninizle paylaşmıyoruz. Başvurunuzu yalnızca sendikanın yetkili personeli görür."
    ),
    "body": (
        "TASLAK — hukuk incelemesinden geçmemiştir; pilot öncesi KVKK danışmanı tarafından yazılacaktır.\n\n"
        "Veri sorumlusu: [Sendika unvanı ve adresi]\n"
        "İşleme amacı: Başvurunuzu almak, değerlendirmek ve size geri dönmek.\n"
        "İşlenen veriler: Konu, açıklama, isteğe bağlı işyeri ve il bilgisi, bıraktıysanız iletişim bilgisi.\n"
        "Hukuki sebep: [Hukuk danışmanı tarafından belirlenecek]\n"
        "Aktarım: Verileriniz işvereninize aktarılmaz. Barındırma hizmeti sağlayıcısı veri işleyen sıfatıyla erişebilir.\n"
        "Saklama süresi: [Saklama ve imha politikasına göre belirlenecek]\n"
        "Haklarınız: KVKK m.11 kapsamındaki taleplerinizi [iletişim kanalı] üzerinden iletebilirsiniz."
    ),
}

EXPLICIT_CONSENT = {
    "version": "taslak-0.1",
    "title": "Hassas bilgiler için açık rıza (isteğe bağlı)",
    "summary": (
        "Açıklamanızda sağlık durumu veya sendika üyeliği gibi özel nitelikli bilgiler varsa, "
        "bunların başvurunuzu değerlendirmek amacıyla işlenmesine izin veriyorum. "
        "Bu izni vermeden de başvuru yapabilirsiniz ve izninizi istediğiniz zaman geri çekebilirsiniz."
    ),
    "body": "TASLAK — açık rızanın gerekip gerekmediği ve metni hukuk danışmanıyla netleştirilecektir.",
}

CANNED = [
    ("İlk yanıt — bilgi alındı",
     "Merhaba, başvurunuzu aldık ve inceledik. Size yardımcı olabilmemiz için birkaç bilgiye ihtiyacımız var: "
     "olayın tarihi, işyerinizdeki göreviniz ve varsa yazılı bir bildirim aldınız mı? Bilgilerinizi bu ekrandan iletebilirsiniz."),
    ("Ücret — belge talebi",
     "Ödenmeyen ücretle ilgili değerlendirme yapabilmemiz için son üç aya ait bordro veya banka hesap dökümünüzün "
     "ilgili satırlarını hazırlamanızı rica ederiz. Belgeleri şubemize getirebilir ya da görüşmede gösterebilirsiniz."),
    ("Hukuk birimine aktarım",
     "Başvurunuz hukuk birimimizin değerlendirmesine aktarıldı. Avukatımız en kısa sürede bu ekran üzerinden size dönüş yapacak."),
    ("Kapsam dışı — yönlendirme",
     "Sorununuz sendikamızın doğrudan yardımcı olabileceği konuların dışında görünüyor. "
     "Bu konuda ALO 170 hattından veya ilgili kurumdan destek alabilirsiniz."),
]

TENANTS = [
    {
        "slug": "ornek-enerji",
        "name": "Örnek Enerji Sendikası",
        "short_code": "OES",
        "intro": "Enerji işkolunda çalışanların sorularını ve başvurularını güvenle alıyoruz. "
                 "Kimliğinizi paylaşmadan da başvurabilirsiniz.",
        "units": [
            ("hq", "headquarters", "Genel Merkez", None, []),
            ("ist", "branch", "İstanbul Şube", "hq", ["İstanbul", "Kocaeli", "Tekirdağ"]),
            ("ank", "branch", "Ankara Şube", "hq", ["Ankara", "Kırıkkale", "Eskişehir"]),
            ("izm", "branch", "İzmir Şube", "hq", ["İzmir", "Manisa", "Aydın"]),
            ("bur", "branch", "Bursa Şube", "hq", ["Bursa", "Balıkesir", "Bilecik"]),
            ("law", "unit", "Hukuk Birimi", "hq", []),
        ],
        "categories": [
            ("ucret", "Ücret ödenmemesi veya geç ödenmesi", "Maaş, prim, ikramiye veya fazla mesai ücreti ödenmedi ya da gecikti.", "P2", None, "normal"),
            ("fesih", "İşten çıkarma / fesih", "İşten çıkarıldınız veya çıkarılma tehdidi altındasınız.", "P2", "law", "normal"),
            ("isg", "İş sağlığı ve güvenliği", "Tehlikeli çalışma koşulları, eksik koruyucu ekipman, iş kazası.", "P2", None, "normal"),
            ("calisma-suresi", "Çalışma süresi ve fazla mesai", "Uzun mesai, vardiya düzeni, dinlenme süreleri.", "P3", None, "normal"),
            ("izin", "Yıllık izin ve diğer izinler", "İzin kullandırılmaması, izin ücreti.", "P3", None, "normal"),
            ("taciz", "Taciz, ayrımcılık veya psikolojik baskı", "Bu başvurular yalnızca hukuk birimi tarafından görülür.", "P2", "law", "restricted"),
            ("uyelik", "Sendika üyeliği ve aidat", "Üyelik işlemleri, aidat, üyelik nedeniyle baskı.", "P3", None, "normal"),
            ("bilgi", "Genel bilgi ve soru", "Haklarınızla ilgili genel sorular.", "P4", None, "normal"),
        ],
        "staff": [
            ("admin", "Selin Kaya", [("org_admin", None)], True),
            ("ist.mudur", "Ayşe Yılmaz", [("branch_manager", "ist")], True),
            ("ist.temsilci", "Burak Demir", [("case_worker", "ist")], True),
            ("ank.temsilci", "Mehmet Arslan", [("case_worker", "ank")], False),  # ilk girişte MFA kurulumu gösterilir
            ("bur.temsilci", "Elif Çetin", [("case_worker", "bur")], True),
            ("genel.temsilci", "Kerem Aksoy", [("case_worker", "hq")], True),
            ("hukuk", "Av. Zeynep Şahin", [("legal_reviewer", None)], True),
            ("denetci", "Can Öztürk", [("auditor", None)], True),
        ],
        "cases": 34,
    },
    {
        "slug": "ornek-hizmet",
        "name": "Örnek Hizmet Sendikası",
        "short_code": "OHS",
        "intro": "Kiracı izolasyonunu göstermek için ikinci demo kurum.",
        "units": [
            ("hq", "headquarters", "Genel Merkez", None, ["Ankara"]),
            ("ist", "branch", "İstanbul Şube", "hq", ["İstanbul"]),
        ],
        "categories": [
            ("ucret", "Ücret sorunları", None, "P2", None, "normal"),
            ("bilgi", "Genel bilgi", None, "P4", None, "normal"),
        ],
        "staff": [
            ("admin", "Deniz Koç", [("org_admin", None)], True),
        ],
        "cases": 4,
    },
]

CITIES = ["İstanbul", "İstanbul", "İstanbul", "Ankara", "Ankara", "İzmir", "Bursa", "Kocaeli", "Manisa", "Samsun", "Adana", None]
WORKPLACES = ["Kuzey Dağıtım A.Ş.", "Mavi Enerji Üretim", "Ova Doğalgaz", "Yıldız Elektrik Hizmetleri", "Toros Enerji Taşeron Ltd.", None, None]

SCENARIOS = {
    "ucret": [
        ("Üç aydır fazla mesai ücreti ödenmiyor",
         "Vardiyalı çalışıyoruz ve son üç aydır yaptığımız fazla mesailer bordroya yansımıyor. Şefimize sorduğumuzda 'bütçe yok' deniyor. Ekipte beş kişi aynı durumdayız."),
        ("Maaş her ay geç yatıyor",
         "Sözleşmede ayın 5'i yazmasına rağmen maaşlar ayın 15-20'sinde yatıyor. Kira ve kredi ödemelerimde sorun yaşıyorum. Ne yapabilirim?"),
        ("İkramiye kesildi",
         "Toplu sözleşmede olan ikramiye bu yıl hiç açıklama yapılmadan ödenmedi. Taşeron firmada çalışıyorum, bize de uygulanıyor mu bilmiyorum."),
    ],
    "fesih": [
        ("Sözlü olarak işten çıkarıldım",
         "Dün amirim sözlü olarak yarından itibaren gelmememi söyledi. Yazılı bir şey verilmedi. 7 yıldır aynı işyerinde çalışıyorum. Tazminat hakkım var mı?"),
        ("İstifa etmem için baskı yapılıyor",
         "İnsan kaynakları beni odaya çağırıp istifa dilekçesi imzalamamı istedi, imzalamazsam performans nedeniyle çıkarılacağımı söyledi."),
    ],
    "isg": [
        ("Trafo bakımında koruyucu ekipman eksik",
         "Saha ekibinde yalıtkan eldiven ve yüz siperi yetersiz. Bir arkadaşımız geçen hafta küçük bir ark yaralanması yaşadı. Şikâyet etmekten çekiniyoruz."),
        ("Gece vardiyasında tek kişi çalıştırılıyoruz",
         "Santralde gece vardiyasında tek kişi bırakılıyoruz. Bir kaza olsa haber verecek kimse yok. Bu durum mevzuata uygun mu?"),
    ],
    "calisma-suresi": [
        ("Haftada 60 saati geçen çalışma",
         "Arıza dönemlerinde haftada 60-65 saat çalıştırılıyoruz, dinlenme günümüz de iptal ediliyor. Yazılı onayımız alınmıyor."),
        ("Vardiya değişiklikleri son dakika bildiriliyor",
         "Vardiya listesi bir gün önceden, bazen aynı gün değiştiriliyor. Çocuğumun bakımını planlayamıyorum."),
    ],
    "izin": [
        ("Yıllık iznim kullandırılmıyor",
         "İki yıldır yıllık iznimin sadece bir kısmını kullanabildim. Talep ettiğimde 'personel yetersiz' deniyor. Biriken izinlerim ne olacak?"),
    ],
    "taciz": [
        ("Amirimin sürekli aşağılayıcı tavrı",
         "Birim amirim toplantılarda beni sürekli aşağılıyor ve diğerlerinin önünde bağırıyor. Bu durum aylardır sürüyor ve psikolojik olarak çok yıprandım."),
    ],
    "uyelik": [
        ("Üye olduğum öğrenilince görev yerim değiştirildi",
         "Sendikaya üye olduğumu öğrendikten sonra müdürüm beni 80 km uzaktaki bir şantiyeye görevlendirdi. Başka bir gerekçe söylenmedi."),
        ("Aidat kesintisi iki kez yapıldı",
         "Bu ay bordromda sendika aidatı iki kez kesilmiş görünüyor. Nasıl düzeltilir?"),
    ],
    "bilgi": [
        ("Taşeron işçi olarak üye olabilir miyim?",
         "Bir enerji şirketinde taşeron firma üzerinden çalışıyorum. Sendikaya üye olabilir miyim, işverenim bunu öğrenir mi?"),
        ("Toplu sözleşme ne zaman yenileniyor?",
         "İşyerimizdeki toplu iş sözleşmesinin süresi ne zaman doluyor, yeni dönemde ne değişecek bilgi alabilir miyim?"),
    ],
}

STAFF_REPLIES = [
    "Merhaba, başvurunuzu inceledik. Durumu netleştirmek için olayın tarihini ve işyerinizdeki görevinizi paylaşabilir misiniz?",
    "Başvurunuz için teşekkürler. Şube temsilcimiz konuyu işyeri temsilcisiyle görüşecek; gelişmeleri buradan paylaşacağız.",
    "Bu konuda haklarınızı ve izleyebileceğiniz yolu açıklayan bir görüşme yapmak isteriz. Uygun olduğunuz saatleri yazabilir misiniz?",
    "Konuyu hukuk birimimize ilettik. Avukatımız size en kısa sürede dönüş yapacak.",
]
APPLICANT_REPLIES = [
    "Teşekkür ederim. Olay geçen ayın ortasında oldu, saha teknisyeni olarak çalışıyorum.",
    "Hafta içi akşam 18:00'den sonra görüşebilirim.",
    "Yazılı bir bildirim almadım, sadece sözlü söylendi.",
]
INTERNAL_NOTES = [
    "Aynı işyerinden bu ay ikinci benzer başvuru. İşyeri temsilcisiyle birlikte değerlendirelim.",
    "Başvuru sahibi işverenin öğrenmesinden çekiniyor; telefonla aranmadan önce yazılı yanıt verildi.",
    "Hukuk birimine danışıldı, yasal süre açısından acil değil.",
]


def _exec(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params)


def seed_tenant(conn: Connection, spec: dict, rng: random.Random, mfa_store: dict) -> None:
    tid = _exec(
        conn,
        "INSERT INTO tenants (slug, name, short_code, public_intro) VALUES (:s, :n, :c, :i) RETURNING id",
        s=spec["slug"], n=spec["name"], c=spec["short_code"], i=spec["intro"],
    ).scalar_one()
    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    tenant = {"id": tid, "short_code": spec["short_code"], "slug": spec["slug"], "name": spec["name"]}

    units: dict[str, UUID] = {}
    for key, kind, name, parent, cities in spec["units"]:
        units[key] = _exec(
            conn,
            """INSERT INTO org_units (tenant_id, parent_id, kind, name, service_cities)
               VALUES (:t, :p, :k, :n, :c) RETURNING id""",
            t=tid, p=units.get(parent) if parent else None, k=kind, n=name, c=cities,
        ).scalar_one()

    for i, (key, label, help_text, prio, unit, sens) in enumerate(spec["categories"]):
        _exec(
            conn,
            """INSERT INTO categories (tenant_id, key, label, help_text, default_priority,
                                       default_org_unit_id, default_sensitivity, sort_order)
               VALUES (:t, :k, :l, :h, :p, :u, :s, :o)""",
            t=tid, k=key, l=label, h=help_text, p=prio, u=units.get(unit) if unit else None, s=sens, o=i,
        )

    for kind, n in (("privacy_notice", PRIVACY_NOTICE), ("explicit_consent", EXPLICIT_CONSENT)):
        _exec(
            conn,
            "INSERT INTO notices (tenant_id, kind, version, title, summary, body) VALUES (:t, :k, :v, :ti, :s, :b)",
            t=tid, k=kind, v=n["version"], ti=n["title"], s=n["summary"], b=n["body"],
        )
    for title, body in CANNED:
        _exec(conn, "INSERT INTO canned_responses (tenant_id, title, body) VALUES (:t, :ti, :b)", t=tid, ti=title, b=body)

    pw_hash = hash_password(DEMO_PASSWORD)
    staff: dict[str, dict] = {}
    for handle, full_name, roles, mfa in spec["staff"]:
        email = f"{handle}@{spec['slug']}.test"
        secret = new_totp_secret() if mfa else None
        uid = _exec(
            conn,
            """INSERT INTO staff_users (tenant_id, email, full_name, password_hash, totp_secret_enc, mfa_enabled)
               VALUES (:t, :e, :n, :p, :s, :m) RETURNING id""",
            t=tid, e=email, n=full_name, p=pw_hash, s=enc(secret) if secret else None, m=mfa,
        ).scalar_one()
        for role, unit in roles:
            _exec(
                conn,
                "INSERT INTO role_assignments (tenant_id, user_id, role, org_unit_id) VALUES (:t, :u, :r, :o)",
                t=tid, u=uid, r=role, o=units[unit] if unit else None,
            )
        staff[handle] = {"id": uid, "roles": roles}
        if secret:
            mfa_store[email] = secret

    notices = {
        r["kind"]: r["id"]
        for r in conn.execute(text("SELECT id, kind FROM notices")).mappings()
    }
    categories = [r for r in conn.execute(text("SELECT key FROM categories")).scalars()]
    now = datetime.now(UTC)

    def handlers_for(unit_id: UUID, sensitivity: str) -> list[UUID]:
        out = []
        for h in staff.values():
            for role, unit in h["roles"]:
                if role == "auditor":
                    continue
                if sensitivity == "restricted" and role not in ("legal_reviewer", "org_admin"):
                    continue
                if unit is None or units[unit] == unit_id:
                    if role in ("case_worker", "legal_reviewer") or (unit is not None):
                        out.append(h["id"])
        return out or [h["id"] for h in staff.values() if ("org_admin", None) in h["roles"]]

    for i in range(spec["cases"]):
        cat = rng.choice(categories)
        subject, desc = rng.choice(SCENARIOS.get(cat, SCENARIOS["bilgi"]))
        # Yaş dağılımı: son 21 gün, yakın günlere daha yoğun.
        age_hours = rng.choice([rng.uniform(1, 30), rng.uniform(20, 120), rng.uniform(100, 500)])
        created = now - timedelta(hours=age_hours)
        anonymous = rng.random() < 0.45
        method = "none" if anonymous and rng.random() < 0.6 else rng.choice(["email", "phone"])
        contact = None
        if method == "email":
            contact = f"calisan{i:02d}@example.com"
        elif method == "phone":
            contact = f"0555 000 {i:02d} {rng.randint(10, 99)}"
        data = CaseCreate(
            category_key=cat,
            subject=subject,
            description=desc,
            workplace=rng.choice(WORKPLACES),
            city=rng.choice(CITIES),
            is_anonymous=anonymous,
            contact_method=method,
            contact_value=contact,
            contact_name=None if anonymous else rng.choice(["Ahmet K.", "Fatma D.", "Hasan Y.", "Gül S.", "Murat T."]),
            safe_contact_note=rng.choice([None, "Hafta içi 18:00 sonrası", "Mesai saatinde aramayın"]),
            privacy_notice_id=notices["privacy_notice"],
            explicit_consent_notice_id=notices["explicit_consent"] if rng.random() < 0.5 else None,
        )
        result = create_case(conn, tenant, data, now=created)
        case = result["case"]
        cid = case["id"]

        # Yaşam döngüsü simülasyonu
        roll = rng.random()
        handlers = handlers_for(case["org_unit_id"], case["sensitivity"])
        if age_hours < 6 and roll < 0.7:
            continue  # yeni, el değmemiş
        assignee = rng.choice(handlers)
        t = created + timedelta(minutes=rng.randint(20, 240))
        _exec(conn, "UPDATE cases SET assignee_id = :a, status = 'assigned' WHERE id = :id", a=assignee, id=cid)
        case_event(conn, tid, cid, "staff", assignee, "assigned", None, str(assignee))
        _exec(conn, "UPDATE case_events SET created_at = :t WHERE case_id = :c AND event_type = 'assigned'", t=t, c=cid)
        _exec(
            conn,
            """INSERT INTO case_events (tenant_id, case_id, actor_type, actor_id, event_type, from_value, to_value, created_at)
               VALUES (:tid, :c, 'staff', :a, 'status_changed', 'received', 'assigned', :t)""",
            tid=tid, c=cid, a=assignee, t=t,
        )

        overdue_case = roll < 0.18
        if overdue_case:
            continue  # atanmış ama yanıt verilmemiş; bazıları hedefi aşacak

        late = rng.random() < 0.2
        resp_delay = (
            timedelta(hours=rng.uniform(26, 60)) if late else timedelta(hours=rng.uniform(1, 18))
        )
        resp_at = min(created + resp_delay, now - timedelta(minutes=5))
        if resp_at <= t:
            resp_at = t + timedelta(minutes=10)
        if rng.random() < 0.35:
            _exec(
                conn,
                """INSERT INTO case_messages (tenant_id, case_id, author_type, author_id, visibility, body_enc, created_at)
                   VALUES (:tid, :c, 'staff', :a, 'internal', :b, :t)""",
                tid=tid, c=cid, a=assignee, b=enc(rng.choice(INTERNAL_NOTES)), t=resp_at - timedelta(minutes=15),
            )
        reply = STAFF_REPLIES[0] if rng.random() < 0.5 else rng.choice(STAFF_REPLIES[1:])
        _exec(
            conn,
            """INSERT INTO case_messages (tenant_id, case_id, author_type, author_id, visibility, body_enc, created_at)
               VALUES (:tid, :c, 'staff', :a, 'public', :b, :t)""",
            tid=tid, c=cid, a=assignee, b=enc(reply), t=resp_at,
        )
        status = "waiting_info" if reply == STAFF_REPLIES[0] else "in_progress"
        _exec(
            conn,
            "UPDATE cases SET first_responded_at = :t, status = :s, updated_at = :t WHERE id = :id",
            t=resp_at, s=status, id=cid,
        )
        _exec(
            conn,
            """INSERT INTO case_events (tenant_id, case_id, actor_type, actor_id, event_type, from_value, to_value, created_at)
               VALUES (:tid, :c, 'staff', :a, 'status_changed', 'assigned', :s, :t)""",
            tid=tid, c=cid, a=assignee, s=status, t=resp_at,
        )

        age_after = now - resp_at
        if status == "waiting_info" and age_after > timedelta(hours=6) and rng.random() < 0.7:
            ar = resp_at + timedelta(hours=rng.uniform(1, min(48, age_after.total_seconds() / 3600 - 0.5)))
            _exec(
                conn,
                """INSERT INTO case_messages (tenant_id, case_id, author_type, visibility, body_enc, created_at)
                   VALUES (:tid, :c, 'applicant', 'public', :b, :t)""",
                tid=tid, c=cid, b=enc(rng.choice(APPLICANT_REPLIES)), t=ar,
            )
            _exec(conn, "UPDATE cases SET status = 'in_progress', updated_at = :t WHERE id = :id", t=ar, id=cid)
            _exec(
                conn,
                """INSERT INTO case_events (tenant_id, case_id, actor_type, event_type, from_value, to_value, created_at)
                   VALUES (:tid, :c, 'applicant', 'status_changed', 'waiting_info', 'in_progress', :t)""",
                tid=tid, c=cid, t=ar,
            )
            status = "in_progress"

        if status == "in_progress" and age_after > timedelta(days=3) and rng.random() < 0.65:
            closed_at = resp_at + timedelta(hours=rng.uniform(24, min(age_after.total_seconds() / 3600 - 1, 240)))
            code = rng.choice(["resolved_info_given", "resolved_info_given", "resolved_action_taken", "referred_legal", "out_of_scope"])
            _exec(
                conn,
                "UPDATE cases SET status = 'resolved', closure_code = :cc, resolved_at = :t, updated_at = :t WHERE id = :id",
                cc=code, t=closed_at, id=cid,
            )
            _exec(
                conn,
                """INSERT INTO case_events (tenant_id, case_id, actor_type, actor_id, event_type, from_value, to_value, created_at)
                   VALUES (:tid, :c, 'staff', :a, 'status_changed', 'in_progress', 'resolved', :t)""",
                tid=tid, c=cid, a=assignee, t=closed_at,
            )


def main(reset: bool = False) -> None:
    s = get_settings()
    engine = create_engine(s.database_admin_url)
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT count(*) FROM tenants")).scalar_one()
        if exists and not reset:
            print("Veritabanında zaten kurum var. Yeniden kurmak için: python -m scripts.seed --reset")
            return
        if reset:
            conn.execute(text(
                """TRUNCATE audit_events, case_events, case_messages, notice_receipts, consent_records,
                   cases, tenant_counters, canned_responses, notices, categories, role_assignments,
                   staff_users, org_units, tenants RESTART IDENTITY CASCADE"""
            ))
    rng = random.Random(7)
    mfa_store: dict[str, str] = {}
    for spec in TENANTS:
        with engine.begin() as conn:
            seed_tenant(conn, spec, rng, mfa_store)
    MFA_FILE.write_text(json.dumps(mfa_store, indent=2))
    engine.dispose()

    print("Demo verisi hazır.\n")
    print(f"  Personel parolası (tüm demo hesaplar): {DEMO_PASSWORD}")
    print("  İki adımlı doğrulama kodları için:     python -m scripts.demo_codes")
    print("  ank.temsilci@ornek-enerji.test ilk girişte MFA kurulumunu gösterir.\n")
    for spec in TENANTS:
        print(f"  {spec['name']}  ->  /t/{spec['slug']}")
        for handle, name, roles, _ in spec["staff"]:
            print(f"     {handle}@{spec['slug']}.test   {name}  ({', '.join(r for r, _ in roles)})")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
