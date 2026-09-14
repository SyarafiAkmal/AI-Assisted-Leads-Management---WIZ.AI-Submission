"""
app/services/extraction_rules.py

Rule-based (keyword/regex) pass untuk mendeteksi channel dari teks notes.
Dicek DULU sebelum fallback ke LLM -- kalau notes-nya eksplisit menyebut
istilah yang jelas (mis. "LinkedIn", "booth", "referred by"), kita nggak
perlu LLM call sama sekali untuk baris itu.

Urutan pengecekan penting: channel yang lebih spesifik dicek duluan,
supaya notes seperti "found via LinkedIn ad" nggak kepental ke Website.
"""

import re
from typing import Optional

from app.schemas.ai_assist import ExtractedSource

# Pola prefix label EKSPLISIT di awal notes -- ini paling dipercaya, karena
# manusia yang input data sendiri sudah nulis kategorinya langsung
# (mis. "Manual - added after inbound phone call.", "Other - walked into
# our office without an appointment."). Dicek PALING PERTAMA, sebelum
# CHANNEL_PATTERNS di bawah, supaya label eksplisit ini tidak keskip
# gara-gara kebetulan ada keyword lain di kalimat lanjutannya.
PREFIX_LABEL_PATTERNS = [
    (r"^manual\b", "Manual/Sales"),  # cocok untuk "Manual - ..." maupun "Manually added..."
    (r"^other\b", "Other"),
]

# Urutan list ini adalah urutan prioritas pengecekan.
CHANNEL_PATTERNS = [
    (
        "Event",
        [
            r"\bbooth\b",
            r"\bconference\b",
            r"\bsummit\b",
            r"\bfestival\b",
            r"\bexpo\b",
            r"\btrade show\b",
            r"\bscanned (our |the )?qr code\b",
            r"\bmet (him|her|them|us) at\b",
        ],
    ),
    (
        "LinkedIn",
        [
            r"\blinkedin\b",
        ],
    ),
    (
        "Referral",
        [
            r"\breferr(ed|al)\b",
            r"\brecommended by\b",
            r"\bfriend (of|from|recommended)\b",
            r"\bcolleague (recommended|referred)\b",
        ],
    ),
    (
        "Organic Search",
        [
            r"\borganic search\b",
            r"\bgoogle search\b",
            r"\bsearched (on )?google\b",
            r"\bfound (us|you) (via |through )?(a )?search\b",
            r"\bgoogled us\b",
        ],
    ),
    (
        "Manual/Sales",
        [
            r"\bcold call\b",
            r"\bcold outreach\b",
            r"\boutbound\b",
            r"\bsales (team|rep) reached out\b",
            r"\baccount executive\b",
            r"\bour sdr\b",
            r"\binbound phone call\b",
            r"\bphone call from\b",
        ],
    ),
    (
        "Website",
        [
            r"\bcontact form\b",
            r"\bwebsite form\b",
            r"\bfilled out (the |our )?form\b",
            r"\bsubmitted (the |a )?form\b",
        ],
    ),
]


def rule_based_extract(text: str) -> Optional[ExtractedSource]:
    """
    Coba deteksi channel dari keyword/regex eksplisit di teks.
    Return None kalau tidak ada pattern yang cocok -- caller (ai_extraction)
    yang harus fallback ke LLM kalau ini None.

    `detail` diisi dengan teks notes yang sudah dirapikan (trim + kapital
    huruf pertama) -- bukan hasil rephrase LLM, jadi lebih apa adanya
    dibanding contoh di README, tapi tetap informatif dan gratis/instant.
    """
    if not text or not text.strip():
        return None

    lowered = text.lower().strip()

    def build_result(channel: str) -> ExtractedSource:
        detail = text.strip()
        detail = detail[0].upper() + detail[1:] if detail else detail
        return ExtractedSource(channel=channel, detail=detail)

    # Cek prefix label eksplisit dulu (paling dipercaya)
    for pattern, channel in PREFIX_LABEL_PATTERNS:
        if re.search(pattern, lowered):
            return build_result(channel)

    # Baru cek keyword/regex di seluruh teks
    for channel, patterns in CHANNEL_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return build_result(channel)

    return None