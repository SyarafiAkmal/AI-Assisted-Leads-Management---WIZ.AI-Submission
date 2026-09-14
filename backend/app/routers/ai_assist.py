"""
app/routers/ai_assist.py

Endpoint untuk dua fitur AI-assisted:
  - POST /leads/dedupe-candidates          -> kandidat pasangan lead duplikat
  - POST /leads/extract-structured         -> ekstrak channel/detail dari teks bebas (manual)
  - GET  /leads/{record_id}/extract-source -> ekstrak channel/detail untuk SATU lead by ID
                                               (ambil notes+original_source langsung dari DB)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.ai_assist import (
    DedupeCandidatesResponse,
    DedupeRequest,
    ExtractedSource,
    ExtractionRequest,
)
from app.services.ai_assist_service import ai_dedupe, ai_extraction
from app.services.lead_service import get_lead_by_id

router = APIRouter(prefix="/leads")


@router.post("/dedupe-candidates", response_model=DedupeCandidatesResponse)
def dedupe_candidates(payload: DedupeRequest, db: Session = Depends(get_db)):
    """
    Pipeline dedup 3 step:
      1. Blocking by phone + email (cheap, exact match)
      2. Fuzzy similarity name+company (cheap, vectorized)
      3. LLM name-match (hanya kalau use_llm_justification=true):
         - Score ~110 kandidat nama identik tapi kontak beda secara batch
         - Yang lolos threshold masuk sebagai llm_name_match candidates
         - Return llm_summary: ringkasan hasil -- berapa dievaluasi,
           berapa lolos, skor rata-rata, dan temuan umum
    """
    candidates, llm_summary = ai_dedupe(
        db, use_llm_justification=payload.use_llm_justification
    )
    return DedupeCandidatesResponse(
        total_candidates=len(candidates),
        candidates=candidates,
        llm_summary=llm_summary,
    )


@router.post("/extract-structured", response_model=ExtractedSource)
def extract_structured(payload: ExtractionRequest):
    """
    Ekstrak channel + detail terstruktur dari teks bebas (biasanya isi
    kolom Notes) yang dikirim manual di body. `original_source` opsional
    -- kalau dikirim, dicek duluan (layer paling murah) sebelum regex
    notes dan LLM.

    Contoh body:
        { "text": "Met him at the SFF booth, scanned our QR code" }
        { "text": "...", "original_source": "Referrals" }
    """
    return ai_extraction(payload.text, original_source=payload.original_source)


@router.get("/{record_id}/extract-source", response_model=ExtractedSource)
def extract_source_for_lead(record_id: str, db: Session = Depends(get_db)):
    """
    Sama seperti /leads/extract-structured, tapi ambil notes +
    original_source LANGSUNG dari database berdasarkan record_id --
    nggak perlu copy-paste teks manual.

    Contoh: GET /leads/100234811/extract-source
    """
    lead = get_lead_by_id(db, record_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead '{record_id}' not found")

    return ai_extraction(lead.notes or "", original_source=lead.original_source)