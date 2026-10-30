"""İlk yanıt hedefleri.

Bu süreler hukuki süre değildir; pilot kurumun kapasitesiyle birlikte
kesinleştirilecek hizmet hedefleridir (PROJE_PLANI.md §13.4).
Resmî tatiller henüz hesaba katılmıyor; yalnızca hafta sonları atlanıyor.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import get_settings

# Öncelik -> (değer, birim)
TARGETS: dict[str, tuple[int, str]] = {
    "P1": (4, "hours"),
    "P2": (1, "business_days"),
    "P3": (2, "business_days"),
    "P4": (3, "business_days"),
}

PRIORITY_LABELS = {"P1": "Kritik", "P2": "Yüksek", "P3": "Normal", "P4": "Bilgi"}


def add_business_days(start: datetime, days: int) -> datetime:
    tz = ZoneInfo(get_settings().timezone)
    local = start.astimezone(tz)
    # Hafta sonu gelen başvurunun saati pazartesi sabahından başlar.
    while local.weekday() >= 5:
        local = (local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    added = 0
    while added < days:
        local += timedelta(days=1)
        if local.weekday() < 5:
            added += 1
    return local


def first_response_due(created_at: datetime, priority: str) -> datetime:
    amount, unit = TARGETS[priority]
    if unit == "hours":
        return created_at + timedelta(hours=amount)
    return add_business_days(created_at, amount)
