"""
app/schemas/ai_assist.py

Schema untuk hasil dua fitur AI-assisted:
  - DedupeCandidate / DedupeCandidatesResponse -> hasil ai_dedupe()
  - ExtractedSource                             -> hasil ai_extraction()
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class DedupeMethod(str, Enum):
    """Step/metode mana yang menghasilkan kandidat pair ini."""

    phone_blocking = "phone_blocking"
    email_blocking = "email_blocking"
    fuzzy_similarity = "fuzzy_similarity"
    llm_name_match = "llm_name_match"  # nama identik, kontak semua beda -> di-resolve LLM


class DedupeLeadSummary(BaseModel):
    """Info ringkas satu lead di dalam kandidat pair -- biar frontend nggak
    perlu fetch ulang detail tiap lead cuma buat nampilin nama/company/status."""

    record_id: str
    name: Optional[str] = None
    company_name: Optional[str] = None
    lead_status: Optional[str] = None


class DedupeCandidate(BaseModel):
    lead_a: DedupeLeadSummary
    lead_b: DedupeLeadSummary
    method: DedupeMethod
    similarity_score: float  # 0-100; blocking exact match diberi skor 100.0
    explanation: Optional[str] = None  # diisi kalau use_llm_justification=True


class DedupeCandidatesResponse(BaseModel):
    total_candidates: int
    candidates: List[DedupeCandidate]
    llm_summary: Optional[str] = None  # ringkasan hasil LLM name-match pass, kalau dijalankan


class DedupeRequest(BaseModel):
    use_llm_justification: bool = False


class SourceChannel(str, Enum):
    website = "Website"
    event = "Event"
    linkedin = "LinkedIn"
    organic_search = "Organic Search"
    referral = "Referral"
    manual_sales = "Manual/Sales"
    other = "Other"


class ExtractedSource(BaseModel):
    channel: SourceChannel
    detail: str


class ExtractionRequest(BaseModel):
    text: str
    original_source: Optional[str] = None  # opsional -- kalau ada, dicek duluan lewat origin_mapping.py