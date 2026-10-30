"""Vaka durum makinesi ve kullanıcıya gösterilen sade durum etiketleri."""

STATUS_LABELS = {
    "received": "Alındı",
    "triage": "Ön inceleme",
    "waiting_info": "Bilgi bekleniyor",
    "assigned": "Atandı",
    "in_progress": "İnceleniyor",
    "referred": "Yönlendirildi",
    "resolved": "Sonuçlandı",
    "closed_timeout": "Yanıt gelmediği için kapandı",
}

# Başvuru sahibi iç operasyon ayrıntısını görmez; beş sade aşama görür.
PUBLIC_STAGE = {
    "received": "received",
    "triage": "reviewing",
    "assigned": "reviewing",
    "in_progress": "reviewing",
    "waiting_info": "waiting_info",
    "referred": "referred",
    "resolved": "resolved",
    "closed_timeout": "resolved",
}
PUBLIC_STAGE_LABELS = {
    "received": "Alındı",
    "reviewing": "İnceleniyor",
    "waiting_info": "Sizden bilgi bekleniyor",
    "referred": "Yönlendirildi",
    "resolved": "Sonuçlandı",
}
PUBLIC_STAGE_ORDER = ["received", "reviewing", "waiting_info", "referred", "resolved"]

TRANSITIONS: dict[str, set[str]] = {
    "received": {"triage", "assigned", "in_progress", "waiting_info", "referred", "resolved"},
    "triage": {"assigned", "in_progress", "waiting_info", "referred", "resolved"},
    "assigned": {"in_progress", "waiting_info", "referred", "resolved"},
    "in_progress": {"waiting_info", "referred", "resolved"},
    "waiting_info": {"triage", "in_progress", "referred", "resolved", "closed_timeout"},
    "referred": {"in_progress", "resolved"},
    "resolved": {"in_progress"},          # yeniden açma
    "closed_timeout": {"in_progress"},    # yeniden açma
}

CLOSED_STATUSES = {"resolved", "closed_timeout"}

CLOSURE_CODES = {
    "resolved_info_given": "Bilgi verildi",
    "resolved_action_taken": "Sendika işlem yaptı",
    "referred_external": "Başka kuruma yönlendirildi",
    "referred_legal": "Hukuk sürecine yönlendirildi",
    "out_of_scope": "Sendika kapsamı dışında",
    "duplicate": "Mükerrer başvuru",
    "no_response": "Başvuru sahibinden yanıt gelmedi",
}


def public_stage(status: str) -> dict:
    key = PUBLIC_STAGE[status]
    return {"key": key, "label": PUBLIC_STAGE_LABELS[key]}
