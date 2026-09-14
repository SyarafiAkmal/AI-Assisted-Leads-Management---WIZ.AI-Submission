"""
app/services/origin_mapping.py

Mapping dari nilai kolom `original_source` (+ `original_source_drill_down_1`)
ke channel enum. Ini layer DETERMINISTIC PERTAMA yang dicek sebelum regex
notes maupun LLM -- kalau original_source sudah cukup jelas, kita nggak
perlu baca notes/panggil LLM sama sekali.

PENTING: sesuai catatan di README, original_source dari CSV seed SERING
tidak reliable (kosong atau terlalu generik -- lihat contoh "Offline
Sources" untuk event lead). Jadi HANYA nilai yang benar-benar 1:1 jelas
yang dipetakan langsung di sini; sisanya sengaja di-return None supaya
caller lanjut ke regex notes / LLM, bukan dipaksakan.

Pengecualian: original_source = "Website Form" itu 100% reliable, karena
nilai ini kita sendiri yang tulis di app/services/ingest_service.py saat
POST /leads/ingest -- bukan data mentah dari CSV yang perlu diragukan.
"""

import re
from typing import Optional


# Mapping 1:1 yang confident -- HANYA untuk nilai yang benar-benar jelas.
# Nilai yang tidak ada di sini (termasuk "Other Campaigns", "Direct Traffic",
# "Offline Sources", "") sengaja TIDAK dipetakan langsung -- caller lanjut
# ke regex notes / LLM untuk cari sinyal yang lebih jelas.
DIRECT_SOURCE_MAP = {
    "referrals": "Referral",
    "organic search": "Organic Search",
    "paid search": "Other",  # tidak ada padanan persis di 7 channel; "Other" paling aman
    "website form": "Website",  # nilai yang KITA tulis sendiri saat ingest -- selalu reliable
}


def map_original_source(
    original_source: Optional[str],
    notes: Optional[str] = None,
) -> Optional[str]:
    """
    Return channel string kalau original_source cukup jelas untuk dipetakan
    langsung, atau None kalau tidak (caller lanjut ke regex notes / LLM).

    Kasus khusus "Social Media": nilai ini generik (bisa LinkedIn, Facebook,
    Instagram, dst), jadi HARUS dicek dulu apakah notes menyebut "linkedin"
    secara eksplisit sebelum dipetakan -- kalau tidak disebut, return None
    (jangan asal tebak platform mana).
    """
    if not original_source or not original_source.strip():
        return None

    key = original_source.strip().lower()

    if key == "social media":
        if notes and re.search(r"\blinkedin\b", notes.lower()):
            return "LinkedIn"
        return None  # generik, platform-nya tidak jelas -- lanjut ke regex/LLM

    return DIRECT_SOURCE_MAP.get(key)