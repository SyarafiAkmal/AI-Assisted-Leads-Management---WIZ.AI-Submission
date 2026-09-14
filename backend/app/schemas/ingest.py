"""
app/schemas/ingest.py

Schema untuk payload POST /leads/ingest.
Bentuknya mengikuti persis satu entry di data/website_form_submissions.json.
"""

from pydantic import BaseModel


class LeadIngestPayload(BaseModel):
    name: str
    company: str
    email: str
    phone: str
    country: str
    form_id: str
    form_name: str
    page_url: str
    message: str
    submitted_at: str  # ISO 8601 string, mis. "2026-06-12T18:17:00Z"