"""
app/services/ingest_service.py

Logic untuk POST /leads/ingest:
  - Terima payload berbentuk website form submission
  - Mapping field ke schema tabel `leads`
  - Normalize memakai fungsi yang sama dengan seed/update (konsistensi!)
  - Generate record_id baru, lalu insert sebagai lead baru
"""

import uuid
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.services.normalization import (
    normalize_country,
    normalize_date,
    normalize_email,
    normalize_name,
    normalize_phone,
)


def generate_record_id() -> str:
    """
    Generate record_id baru untuk lead hasil ingest.
    Prefix "WEB-" dipakai supaya gampang dibedakan dari record_id
    hasil seed (yang numeric, mis. "100234811") -- berguna untuk
    tracing asal-usul data saat debugging atau audit.
    """
    return f"WEB-{uuid.uuid4().hex[:12]}"


def map_payload_to_lead_fields(payload: dict) -> dict:
    """
    Mapping field dari payload website form -> kolom tabel `leads`.

    Field yang tidak ada padanannya di payload (job_title, contact_owner,
    annual_revenue, marketing_contact_status, gdpr_consent, lead_score)
    dibiarkan None -- akan diisi lewat proses lain (mis. PATCH manual,
    atau fitur AI extract-structured di masa depan).
    """
    submitted_date = normalize_date(payload["submitted_at"])

    # Notes gabungan: message asli + jejak sumber (page_url), supaya
    # konteks form submission tidak hilang meski tidak ada kolom khusus.
    notes = f"{payload['message']} (submitted via {payload['page_url']})"

    return {
        "record_id": generate_record_id(),
        "name": normalize_name(payload["name"]),
        "job_title": None,
        "company_name": normalize_name(payload["company"]),
        "email": normalize_email(payload["email"]),
        "phone_number": normalize_phone(payload["phone"]),
        "country_region": normalize_country(payload["country"]),
        "city": None,
        "lead_status": None,  # belum ditriase — biarkan null sampai ada keputusan eksplisit (manual/AI)
        "lifecycle_stage": None,  # sama alasannya; nilai asli di seed data pakai Title Case
                                  # ("Lead", "Sales Qualified Lead", dst), bukan lowercase
        "original_source": "Website",
        "original_source_drill_down_1": payload["form_name"],
        "contact_owner": None,  # belum ada assignment, diisi manual nanti
        "create_date": submitted_date,
        "last_modified_date": submitted_date,
        "notes": notes,
        "annual_revenue": None,
        "marketing_contact_status": None,
        "gdpr_consent": None,
        "lead_score": None,
    }


def ingest_lead(db: Session, payload: dict) -> Lead:
    """Buat lead baru dari payload website form submission."""
    lead_fields = map_payload_to_lead_fields(payload)

    lead = Lead(**lead_fields)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead