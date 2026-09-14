"""
app/routers/leads.py

GET /leads — search leads dengan filter per kolom + free-text search.

Contoh pemakaian:
  GET /leads?lead_status=new&country_region=China
  GET /leads?q=logistics
  GET /leads?q=ferrari&lead_status=new&page=1&page_size=20
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.lead import LeadFilterOptions, LeadListResponse, LeadResponse, LeadUpdate
from app.services.lead_service import (
    export_leads_csv,
    get_filter_options,
    get_lead_by_id,
    search_leads,
    update_lead,
)

router = APIRouter(prefix="/leads")


@router.get("", response_model=LeadListResponse)
def get_leads(
    q: Optional[str] = Query(
        None, description="Free-text search di name, email, company_name, job_title, notes, phone_number"
    ),
    lead_status: Optional[str] = Query(None),
    lifecycle_stage: Optional[str] = Query(None),
    country_region: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    company_name: Optional[str] = Query(None),
    contact_owner: Optional[str] = Query(None),
    original_source: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = {
        "lead_status": lead_status,
        "lifecycle_stage": lifecycle_stage,
        "country_region": country_region,
        "city": city,
        "company_name": company_name,
        "contact_owner": contact_owner,
        "original_source": original_source,
    }

    total, results = search_leads(db, filters, q, page, page_size)

    return LeadListResponse(total=total, page=page, page_size=page_size, results=results)


@router.get("/filters", response_model=LeadFilterOptions)
def get_leads_filter_options(db: Session = Depends(get_db)):
    """
    Nilai unik lead_status & country_region yang benar-benar ada di
    database -- dipakai untuk populate dropdown filter di frontend.

    PENTING: route ini harus terdaftar SEBELUM /leads/{record_id},
    kalau tidak FastAPI akan menganggap "filters" sebagai record_id.
    """
    return get_filter_options(db)


@router.get("/export")
def export_leads(
    q: Optional[str] = Query(None),
    lead_status: Optional[str] = Query(None),
    lifecycle_stage: Optional[str] = Query(None),
    country_region: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    company_name: Optional[str] = Query(None),
    contact_owner: Optional[str] = Query(None),
    original_source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    CSV export dari SEMUA lead yang match filter/search saat ini (tanpa
    pagination). Semua kolom dataset ikut di-export, value None ditulis
    literal sebagai "null".

    PENTING: route ini juga harus terdaftar SEBELUM /leads/{record_id}.
    """
    filters = {
        "lead_status": lead_status,
        "lifecycle_stage": lifecycle_stage,
        "country_region": country_region,
        "city": city,
        "company_name": company_name,
        "contact_owner": contact_owner,
        "original_source": original_source,
    }
    csv_content = export_leads_csv(db, filters, q)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@router.get("/{record_id}", response_model=LeadResponse)
def get_lead(record_id: str, db: Session = Depends(get_db)):
    lead = get_lead_by_id(db, record_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead '{record_id}' not found")
    return lead


@router.patch("/{record_id}", response_model=LeadResponse)
def patch_lead(record_id: str, payload: LeadUpdate, db: Session = Depends(get_db)):
    update_data = payload.model_dump(exclude_unset=True)
    lead = update_lead(db, record_id, update_data)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead '{record_id}' not found")
    return lead