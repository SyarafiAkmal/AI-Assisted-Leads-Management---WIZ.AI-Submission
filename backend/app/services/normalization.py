"""
app/services/normalization.py

Kumpulan fungsi normalization untuk data leads.
Modul ini dipakai di DUA tempat supaya konsisten:
  1. Endpoint POST /leads/ingest      (data baru yang masuk)
  2. Script pembuat leads_seed.sql    (data lama/seed)

Semua fungsi di sini idempotent (aman dipanggil berkali-kali ke data yang sama).
"""

import re
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Lead Status: banyak variasi casing & whitespace -> mapping ke enum baku
# ---------------------------------------------------------------------------
LEAD_STATUS_MAP = {
    "new": "new",
    "contacted": "contacted",
    "connected": "connected",
    "qualified": "qualified",
    "opportunity": "opportunity",
    "closed won": "closed_won",
    "closed lost": "closed_lost",
}


def normalize_lead_status(value: Optional[str]) -> Optional[str]:
    if not value or not value.strip():
        return None
    key = value.strip().lower()
    return LEAD_STATUS_MAP.get(key, key)  # fallback: nilai asli (lowercase) kalau ada status baru yang belum dipetakan


# ---------------------------------------------------------------------------
# Country/Region: banyak variasi casing -> title case
# ---------------------------------------------------------------------------
def normalize_country(value: Optional[str]) -> Optional[str]:
    if not value or not value.strip():
        return None
    return value.strip().title()


# ---------------------------------------------------------------------------
# Email: sudah lowercase dari sumbernya, tapi tetap trim jaga-jaga
# ---------------------------------------------------------------------------
def normalize_email(value: Optional[str]) -> Optional[str]:
    if not value or not value.strip():
        return None
    return value.strip().lower()


# ---------------------------------------------------------------------------
# Phone Number: normalize ke format E.164-ish (+<digits>, tanpa spasi/dash)
# Semua digit di dataset ini sudah termasuk kode negara (mis. "34636702600"
# = Spanyol), jadi "+" SELALU ditambahkan di depan, terlepas dari format asli.
# ---------------------------------------------------------------------------
def normalize_phone(value: Optional[str]) -> Optional[str]:
    if not value or not value.strip():
        return None

    raw = value.strip()

    # Buang semua karakter selain digit
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return None

    return f"+{digits}"


# ---------------------------------------------------------------------------
# Contact Owner / nama-nama lain: trim whitespace berlebih
# ---------------------------------------------------------------------------
def normalize_name(value: Optional[str]) -> Optional[str]:
    if not value or not value.strip():
        return None
    # trim + rapikan multiple spaces jadi satu spasi
    return re.sub(r"\s+", " ", value.strip())


# ---------------------------------------------------------------------------
# Tanggal: 3 format campur -> ISO 8601 (YYYY-MM-DD)
#   - "2025-09-29"              (ISO date only)
#   - "2025-11-25T00:00:00Z"    (ISO with timestamp)
#   - "5/30/2026"               (US format M/D/YYYY)
# ---------------------------------------------------------------------------
DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",  # ISO with timestamp
    "%Y-%m-%d",             # ISO date only
    "%m/%d/%Y",             # US format
]


def normalize_date(value) -> Optional[str]:
    if value is None:
        return None

    # Kalau sudah datetime.date atau datetime (misal dari Pydantic parsing),
    # langsung convert ke ISO string — nggak perlu parse ulang.
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "isoformat"):  # datetime.date
        return value.isoformat()

    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Kalau semua format gagal, kembalikan None daripada nyimpen data korup
    return None


# ---------------------------------------------------------------------------
# Name reconciliation: first_name + last_name + full_name -> satu kolom `name`
# Beberapa baris cuma punya Full Name terisi, First/Last kosong (atau sebaliknya)
# ---------------------------------------------------------------------------
def reconcile_name(
    first_name: Optional[str], last_name: Optional[str], full_name: Optional[str]
) -> Optional[str]:
    """
    Gabungkan first_name + last_name jadi satu string kalau ada.
    Kalau first_name/last_name kosong tapi full_name ada, pakai full_name.
    """
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    full_name = normalize_name(full_name)

    if first_name or last_name:
        combined = " ".join(part for part in [first_name, last_name] if part)
        return combined or None

    return full_name  # fallback kalau first/last kosong tapi full_name ada


# ---------------------------------------------------------------------------
# Fungsi utama: normalize satu record lead secara keseluruhan
# raw dict pakai key snake_case (sesuai kolom tabel `leads`)
# ---------------------------------------------------------------------------
def normalize_lead(raw: dict) -> dict:
    name = reconcile_name(
        raw.get("first_name"), raw.get("last_name"), raw.get("full_name")
    )

    # Buang first_name/last_name/full_name dari hasil akhir, ganti dengan `name`
    cleaned = {k: v for k, v in raw.items() if k not in ("first_name", "last_name", "full_name")}

    return {
        **cleaned,
        "name": name,
        "job_title": normalize_name(raw.get("job_title")),
        "company_name": normalize_name(raw.get("company_name")),
        "email": normalize_email(raw.get("email")),
        "phone_number": normalize_phone(raw.get("phone_number")),
        "country_region": normalize_country(raw.get("country_region")),
        "lead_status": normalize_lead_status(raw.get("lead_status")),
        "contact_owner": normalize_name(raw.get("contact_owner")),
        "create_date": normalize_date(raw.get("create_date")),
        "last_modified_date": normalize_date(raw.get("last_modified_date")),
    }