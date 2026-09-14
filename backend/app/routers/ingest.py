"""
app/routers/ingest.py

POST /leads/ingest — terima payload berbentuk website form submission
(lihat data/website_form_submissions.json untuk contoh bentuknya),
lalu buat lead baru.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.ingest import LeadIngestPayload
from app.schemas.lead import LeadResponse
from app.services.ingest_service import ingest_lead

router = APIRouter(prefix="/leads")


@router.post("/ingest", response_model=LeadResponse, status_code=201)
def ingest(payload: LeadIngestPayload, db: Session = Depends(get_db)):
    lead = ingest_lead(db, payload.model_dump())
    return lead