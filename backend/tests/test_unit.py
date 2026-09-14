"""
tests/test_unit.py

Unit tests untuk logic core yang tidak butuh DB, HTTP, atau LLM:
  - normalization (U-01 sampai U-04)
  - extraction_rules (U-04, U-05)

Jalankan dari root backend/:
    pytest tests/test_unit.py -v

Atau dari dalam container:
    docker exec -it leads-backend pytest tests/test_unit.py -v
"""

import datetime
import sys
from pathlib import Path

# Pastikan root backend/ ada di sys.path biar import app.* bisa resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest

from app.services.normalization import (
    normalize_date,
    normalize_lead_status,
    normalize_phone,
    reconcile_name,
)
from app.services.extraction_rules import rule_based_extract


# =============================================================================
# U-01  normalize_date — menerima datetime.date object tanpa crash
# (bug nyata yang pernah terjadi di PATCH endpoint: Pydantic parse string
# "2025-12-21" jadi datetime.date, lalu normalize_date() panggil .strip() → crash)
# =============================================================================

class TestNormalizeDate:

    def test_accepts_datetime_date_object(self):
        """U-01a: datetime.date harus dikonversi ke ISO string, bukan crash."""
        value = datetime.date(2025, 12, 21)
        result = normalize_date(value)
        assert result == "2025-12-21"

    def test_accepts_datetime_datetime_object(self):
        """U-01b: datetime.datetime juga harus aman."""
        value = datetime.datetime(2025, 11, 25, 0, 0, 0)
        result = normalize_date(value)
        assert result == "2025-11-25"

    def test_iso_string_with_timestamp(self):
        """U-01c: Format ISO dengan timestamp (dari CSV seed) → YYYY-MM-DD."""
        result = normalize_date("2025-11-25T00:00:00Z")
        assert result == "2025-11-25"

    def test_iso_date_only_string(self):
        """U-01d: Format ISO date only tetap aman."""
        result = normalize_date("2025-09-29")
        assert result == "2025-09-29"

    def test_us_format_string(self):
        """U-01e: Format US (M/D/YYYY dari CSV seed) → YYYY-MM-DD."""
        result = normalize_date("5/30/2026")
        assert result == "2026-05-30"

    def test_none_returns_none(self):
        """U-01f: None tetap None — bukan crash, bukan string 'None'."""
        assert normalize_date(None) is None

    def test_empty_string_returns_none(self):
        """U-01g: String kosong → None, bukan error."""
        assert normalize_date("") is None

    def test_unparseable_string_returns_none(self):
        """U-01h: Format tidak dikenali → None, bukan exception."""
        assert normalize_date("not-a-date") is None


# =============================================================================
# U-02  normalize_lead_status — variasi casing & whitespace → lowercase baku
# (dataset seed penuh variasi ini; kalau salah, seluruh filter status broken)
# =============================================================================

class TestNormalizeLeadStatus:

    def test_uppercase(self):
        """U-02a: 'NEW' → 'new'."""
        assert normalize_lead_status("NEW") == "new"

    def test_title_case_with_whitespace(self):
        """U-02b: ' New ' (leading/trailing space) → 'new'."""
        assert normalize_lead_status(" New ") == "new"

    def test_lowercase_passthrough(self):
        """U-02c: 'new' sudah benar, tetap 'new'."""
        assert normalize_lead_status("new") == "new"

    def test_closed_won_with_space(self):
        """U-02d: 'CLOSED WON' → 'closed_won' (dua kata, underscore)."""
        assert normalize_lead_status("CLOSED WON") == "closed_won"

    def test_closed_lost(self):
        """U-02e: 'Closed Lost' → 'closed_lost'."""
        assert normalize_lead_status("Closed Lost") == "closed_lost"

    def test_unknown_status_lowercased(self):
        """U-02f: Status tidak dikenal → dikembalikan lowercase as-is (tidak error, tidak hilang)."""
        result = normalize_lead_status("prospect")
        assert result == "prospect"

    def test_none_returns_none(self):
        assert normalize_lead_status(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_lead_status("") is None


# =============================================================================
# U-03  normalize_phone — selalu menghasilkan +<digits> tanpa spasi/dash
# (blocking logic bergantung 100% pada kesamaan string ini;
#  kalau format beda, phone_blocking miss semua pasangan duplikat)
# =============================================================================

class TestNormalizePhone:

    def test_with_plus_spaces_dashes(self):
        """U-03a: '+62 875-4899-5562' → '+6287548995562'."""
        assert normalize_phone("+62 875-4899-5562") == "+6287548995562"

    def test_without_plus_prefix(self):
        """U-03b: Tanpa '+' → selalu ditambahkan di depan."""
        assert normalize_phone("34636702600") == "+34636702600"

    def test_with_spaces_only(self):
        """U-03c: '+34 664 813 728' → '+34664813728'."""
        assert normalize_phone("+34 664 813 728") == "+34664813728"

    def test_consistency_same_person(self):
        """U-03d: Dua format berbeda yang mewakili nomor sama → hasil identik.
        Ini kondisi KRITIS: kalau hasilnya beda, phone_blocking akan miss pair."""
        a = normalize_phone("+62 875-4899-5562")
        b = normalize_phone("6287548995562")
        assert a == b, f"Format beda menghasilkan '{a}' vs '{b}' — phone blocking akan miss pair ini"

    def test_none_returns_none(self):
        assert normalize_phone(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_phone("") is None

    def test_non_digit_only_returns_none(self):
        """U-03e: String tanpa digit sama sekali → None."""
        assert normalize_phone("---") is None


# =============================================================================
# U-04  reconcile_name — first+last vs full_name reconciliation
# (107 baris di seed hanya punya full_name; kalau nggak dihandle, name jadi null)
# =============================================================================

class TestReconcileName:

    def test_first_and_last_combined(self):
        """U-04a: Ada first+last → digabung jadi satu."""
        assert reconcile_name("Yuki", "Aina", "") == "Yuki Aina"

    def test_full_name_fallback(self):
        """U-04b: first+last kosong tapi full_name ada → pakai full_name."""
        assert reconcile_name("", "", "Wei Ming Malik") == "Wei Ming Malik"

    def test_first_last_takes_priority_over_full(self):
        """U-04c: Kalau first+last ada, full_name diabaikan."""
        assert reconcile_name("Yuki", "Aina", "Yuki Aina Full") == "Yuki Aina"

    def test_all_empty_returns_none(self):
        """U-04d: Semua kosong → None."""
        assert reconcile_name("", "", "") is None

    def test_only_first_name(self):
        """U-04e: Ada first tapi tidak ada last → tetap valid."""
        assert reconcile_name("Yuki", "", "") == "Yuki"


# =============================================================================
# U-05  rule_based_extract — regex/prefix detection dari notes
# (2 contoh persis dari README + pattern 'Manual -' yang ketemu dari data asli)
# =============================================================================

class TestRuleBasedExtract:

    def test_event_booth_qr_readme_example(self):
        """U-05a: Contoh persis dari README — booth + QR code → Event."""
        result = rule_based_extract("Met him at the SFF booth, scanned our QR code")
        assert result is not None
        assert result.channel == "Event"

    def test_organic_search_readme_example(self):
        """U-05b: Contoh persis dari README — organic google search → Organic Search."""
        result = rule_based_extract(
            "Found us through organic google search then booked a demo"
        )
        assert result is not None
        assert result.channel == "Organic Search"

    def test_manual_prefix_from_real_data(self):
        """U-05c: Pattern 'Manual - ...' ditemukan dari data asli (94 baris) → Manual/Sales.
        Ini TIDAK ada di contoh README — ketemu dari analisis dataset, mudah kebreak kalau regex diubah."""
        result = rule_based_extract("Manual - added after inbound phone call.")
        assert result is not None
        assert result.channel == "Manual/Sales"

    def test_other_prefix_from_real_data(self):
        """U-05d: Pattern 'Other - ...' ditemukan dari data asli (153 baris) → Other."""
        result = rule_based_extract(
            "Other - walked into our office without an appointment."
        )
        assert result is not None
        assert result.channel == "Other"

    def test_referral_keyword(self):
        """U-05e: 'referred by' → Referral."""
        result = rule_based_extract("He was referred by an existing customer.")
        assert result is not None
        assert result.channel == "Referral"

    def test_linkedin_keyword(self):
        """U-05f: 'LinkedIn' → LinkedIn."""
        result = rule_based_extract(
            "Connected with him on LinkedIn after his post went viral."
        )
        assert result is not None
        assert result.channel == "LinkedIn"

    def test_ambiguous_returns_none(self):
        """U-05g: Notes implisit tanpa keyword → None (LLM yang handle, bukan regex).
        Ini memastikan regex TIDAK over-match dan salah klasifikasi."""
        result = rule_based_extract(
            "He seemed really interested after our call last week."
        )
        assert result is None

    def test_empty_text_returns_none(self):
        """U-05h: Teks kosong → None tanpa crash."""
        assert rule_based_extract("") is None

    def test_none_text_returns_none(self):
        """U-05i: None → None tanpa crash."""
        assert rule_based_extract(None) is None

    def test_detail_is_original_text(self):
        """U-05j: Field 'detail' berisi teks notes asli (bukan rephrase/ringkasan)."""
        notes = "He scanned our QR code at the SaaStr Annual booth."
        result = rule_based_extract(notes)
        assert result is not None
        assert result.detail == notes  # detail = teks asli, bukan diubah