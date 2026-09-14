"""
app/services/lead_service.py

Logic query untuk GET /leads:
  - Filter per kolom (exact-ish, pakai ILIKE partial match)
  - Free-text search `q` di beberapa kolom sekaligus
  - Pagination

Juga berisi get_lead_by_id(), update_lead(), dan export_leads_csv()
untuk endpoint GET /leads/:id, PATCH /leads/:id, GET /leads/export.
"""

import csv
import io
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.services.normalization import (
    normalize_country,
    normalize_date,
    normalize_email,
    normalize_lead_status,
    normalize_name,
    normalize_phone,
)

# Kolom yang boleh difilter langsung per-kolom lewat query param
FILTERABLE_FIELDS = [
    "lead_status",
    "lifecycle_stage",
    "country_region",
    "city",
    "company_name",
    "contact_owner",
    "original_source",
]

# Kolom yang ikut di-scan kalau user pakai free-text search (`q`)
SEARCHABLE_FIELDS = [
    "name",
    "email",
    "company_name",
    "job_title",
    "notes",
    "phone_number",
]

# Urutan SEMUA kolom tabel `leads` -- dipakai untuk CSV export supaya
# semua kolom dataset ikut ke-export, bukan cuma yang ditampilkan di tabel.
ALL_COLUMNS = [
    "record_id", "name", "job_title", "company_name", "email", "phone_number",
    "country_region", "city", "lead_status", "lifecycle_stage", "original_source",
    "original_source_drill_down_1", "contact_owner", "create_date",
    "last_modified_date", "notes", "annual_revenue", "marketing_contact_status",
    "gdpr_consent", "lead_score",
]

# Mapping field -> fungsi normalize yang sesuai.
# Dipakai di update_lead() supaya field yang di-PATCH tetap konsisten
# dengan normalization yang sama seperti saat ingest/seed.
FIELD_NORMALIZERS = {
    "name": normalize_name,
    "job_title": normalize_name,
    "company_name": normalize_name,
    "contact_owner": normalize_name,
    "email": normalize_email,
    "phone_number": normalize_phone,
    "country_region": normalize_country,
    "lead_status": normalize_lead_status,
    "create_date": normalize_date,
    "last_modified_date": normalize_date,
}


def _apply_filters(query, filters: dict, q: Optional[str]):
    """Logic filter yang dipakai bareng oleh search_leads() dan export_leads_csv()."""
    for field, value in filters.items():
        if not value:
            continue
        column = getattr(Lead, field)
        query = query.filter(column.ilike(f"%{value}%"))

    if q:
        like_pattern = f"%{q}%"
        conditions = [getattr(Lead, field).ilike(like_pattern) for field in SEARCHABLE_FIELDS]
        query = query.filter(or_(*conditions))

    return query


def search_leads(
    db: Session,
    filters: dict,
    q: Optional[str],
    page: int,
    page_size: int,
):
    query = _apply_filters(db.query(Lead), filters, q)

    total = query.count()

    results = (
        query.order_by(Lead.create_date.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return total, results


def get_lead_by_id(db: Session, record_id: str) -> Optional[Lead]:
    """Ambil satu lead berdasarkan record_id. Return None kalau tidak ditemukan."""
    return db.query(Lead).filter(Lead.record_id == record_id).first()


def get_dashboard(db: Session) -> dict:
    """Lead counts grouped by status and by source channel."""
    from sqlalchemy import func

    by_status = dict(
        db.query(Lead.lead_status, func.count())
        .group_by(Lead.lead_status)
        .all()
    )
    by_source = dict(
        db.query(Lead.original_source, func.count())
        .group_by(Lead.original_source)
        .all()
    )

    # Replace None keys with "unset" for cleaner JSON
    by_status = {k or "unset": v for k, v in by_status.items()}
    by_source = {k or "unset": v for k, v in by_source.items()}

    return {"by_status": by_status, "by_source": by_source}


def get_filter_options(db: Session) -> dict:
    """
    Ambil daftar nilai unik untuk lead_status dan country_region yang
    BENERAN ada di database -- dipakai untuk populate dropdown filter
    di frontend, supaya opsinya selalu sinkron sama data asli (bukan
    hardcoded list yang bisa basi).
    """
    statuses = (
        db.query(Lead.lead_status)
        .filter(Lead.lead_status.isnot(None), Lead.lead_status != "")
        .distinct()
        .order_by(Lead.lead_status)
        .all()
    )
    countries = (
        db.query(Lead.country_region)
        .filter(Lead.country_region.isnot(None), Lead.country_region != "")
        .distinct()
        .order_by(Lead.country_region)
        .all()
    )
    return {
        "statuses": [s[0] for s in statuses],
        "countries": [c[0] for c in countries],
    }


def export_leads_csv(db: Session, filters: dict, q: Optional[str]) -> str:
    """
    Export SEMUA lead yang match filter/search saat ini (tanpa pagination)
    jadi CSV string, dengan SEMUA kolom dataset (bukan cuma yang tampil di
    tabel UI). Value None ditulis literal sebagai string "null", sesuai
    permintaan -- bukan cell kosong.
    """
    query = _apply_filters(db.query(Lead), filters, q)
    leads = query.order_by(Lead.create_date.desc().nullslast()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ALL_COLUMNS)

    for lead in leads:
        row = []
        for col in ALL_COLUMNS:
            value = getattr(lead, col)
            row.append("null" if value is None else value)
        writer.writerow(row)

    return buffer.getvalue()


def update_lead(db: Session, record_id: str, update_data: dict) -> Optional[Lead]:
    """
    Update field-field lead yang ada di update_data (partial update).
    Setiap field yang punya normalizer di FIELD_NORMALIZERS otomatis
    dinormalize dulu sebelum disimpan, supaya konsisten dengan data
    hasil ingest/seed.

    Field dengan value None di update_data DIABAIKAN (tidak menimpa
    jadi NULL) — kalau memang mau clear suatu field, kirim string kosong "".
    """
    lead = get_lead_by_id(db, record_id)
    if lead is None:
        return None

    for field, value in update_data.items():
        if value is None:
            continue  # skip field yang tidak dikirim / sengaja None

        if not hasattr(Lead, field):
            continue  # abaikan field asing yang bukan kolom tabel

        normalizer = FIELD_NORMALIZERS.get(field)
        cleaned_value = normalizer(value) if normalizer else value

        setattr(lead, field, cleaned_value)

    db.commit()
    db.refresh(lead)
    return lead