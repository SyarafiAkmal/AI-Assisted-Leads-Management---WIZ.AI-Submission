"""
app/schemas/lead.py

Pydantic schemas untuk request/response endpoint GET /leads.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: str
    name: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    country_region: Optional[str] = None
    city: Optional[str] = None
    lead_status: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    original_source: Optional[str] = None
    contact_owner: Optional[str] = None
    create_date: Optional[date] = None
    last_modified_date: Optional[date] = None
    notes: Optional[str] = None
    annual_revenue: Optional[float] = None
    marketing_contact_status: Optional[str] = None
    gdpr_consent: Optional[bool] = None
    lead_score: Optional[float] = None


class LeadListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: List[LeadResponse]


class LeadFilterOptions(BaseModel):
    statuses: List[str]
    countries: List[str]


class LeadUpdate(BaseModel):
    """Sesuai spec: PATCH hanya untuk update status, owner, atau notes."""

    lead_status: Optional[str] = None
    contact_owner: Optional[str] = None
    notes: Optional[str] = None