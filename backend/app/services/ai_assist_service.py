"""
app/services/ai_assist_service.py

Dua fitur AI-assisted:

  1. ai_dedupe() -- Pipeline 3 step sesuai README:

     Step 1 — Blocking (cheap, exact match): phone + email (union)
     Step 2 — Fuzzy similarity (cheap, vectorized): rapidfuzz cdist
     Step 3 — LLM name-match (HANYA kalau use_llm_justification=True):
       - Score ~110 pasangan yang nama identik tapi phone+email beda
         secara BATCH (25 pairs per LLM call, bukan satu-satu)
       - Pasangan dengan score >= 60 masuk sebagai llm_name_match candidates
       - Generate satu SUMMARY: berapa dievaluasi, berapa lolos,
         skor rata-rata, dan temuan umum dari LLM

  2. ai_extraction() -- 3-layer source extraction
"""

import itertools
from collections import defaultdict
from statistics import mean
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.llm.client import get_llm, get_structured_llm, is_mock_provider
from app.models.lead import Lead
from app.schemas.ai_assist import (
    DedupeCandidate,
    DedupeLeadSummary,
    DedupeMethod,
    ExtractedSource,
)
from app.services.extraction_rules import rule_based_extract
from app.services.origin_mapping import map_original_source

FUZZY_THRESHOLD = 85
LLM_BATCH_SIZE = 25
LLM_NAME_MATCH_THRESHOLD = 60.0


# ---------------------------------------------------------------------------
# LLM STRUCTURED OUTPUT SCHEMAS
# ---------------------------------------------------------------------------

class LLMPairResult(BaseModel):
    pair_id: str = Field(description="Exact PAIR_ID from the input.")
    score: float = Field(
        ge=0, le=100,
        description="0=certainly different, 100=certainly same person.",
    )
    reason: str = Field(description="One concise sentence explaining the score.")


class LLMBatchResponse(BaseModel):
    results: List[LLMPairResult] = Field(
        description="One result per supplied pair."
    )


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _to_summary(lead: Lead) -> DedupeLeadSummary:
    return DedupeLeadSummary(
        record_id=lead.record_id,
        name=lead.name,
        company_name=lead.company_name,
        lead_status=lead.lead_status,
    )


def _pair_key(a: str, b: str) -> Tuple[str, str]:
    return tuple(sorted((a, b)))


def _pair_id(a: str, b: str) -> str:
    k = _pair_key(a, b)
    return f"{k[0]}|{k[1]}"


# ---------------------------------------------------------------------------
# STEP 1: Blocking
# ---------------------------------------------------------------------------

def _block_by_field(leads: List[Lead], field: str) -> List[Tuple[str, str]]:
    buckets: Dict[str, List[str]] = defaultdict(list)
    for lead in leads:
        value = getattr(lead, field)
        if value:
            buckets[value].append(lead.record_id)
    pairs = []
    for ids in buckets.values():
        if len(ids) >= 2:
            pairs.extend(itertools.combinations(ids, 2))
    return pairs


def block_by_phone(leads: List[Lead]) -> List[Tuple[str, str]]:
    return _block_by_field(leads, "phone_number")


def block_by_email(leads: List[Lead]) -> List[Tuple[str, str]]:
    return _block_by_field(leads, "email")


# ---------------------------------------------------------------------------
# STEP 2: Fuzzy similarity
# ---------------------------------------------------------------------------

def fuzzy_similarity_pairs(leads: List[Lead]) -> List[Tuple[str, str, float]]:
    ids = [lead.record_id for lead in leads]
    texts = [
        f"{lead.name or ''} {lead.company_name or ''}".strip().lower()
        for lead in leads
    ]
    score_matrix = process.cdist(texts, texts, scorer=fuzz.token_sort_ratio)
    pairs = []
    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            score = float(score_matrix[i][j])
            if score >= FUZZY_THRESHOLD:
                pairs.append((ids[i], ids[j], score))
    return pairs


# ---------------------------------------------------------------------------
# STEP 3A: Collect name-match candidates
# ---------------------------------------------------------------------------

def _get_name_match_candidates(
    leads: List[Lead],
    already_caught: set,
) -> List[Tuple[Lead, Lead]]:
    """
    Pasangan nama identik tapi phone DAN email keduanya berbeda.
    Tidak tertangkap step 1+2 -- butuh LLM untuk resolve.
    """
    name_buckets: Dict[str, List[Lead]] = defaultdict(list)
    for lead in leads:
        if lead.name:
            name_buckets[lead.name.strip().lower()].append(lead)

    candidates = []
    seen = set()
    for group in name_buckets.values():
        if len(group) < 2:
            continue
        for a, b in itertools.combinations(group, 2):
            key = _pair_key(a.record_id, b.record_id)
            if key in already_caught or key in seen:
                continue
            seen.add(key)
            phone_same = (
                a.phone_number and b.phone_number
                and a.phone_number == b.phone_number
            )
            email_same = (
                a.email and b.email
                and a.email == b.email
            )
            if not phone_same and not email_same:
                candidates.append((a, b))
    return candidates


# ---------------------------------------------------------------------------
# STEP 3B: LLM batch scoring
# ---------------------------------------------------------------------------

def _build_name_match_prompt(batch: List[Tuple[Lead, Lead]]) -> str:
    blocks = []
    for a, b in batch:
        blocks.append(
            f"PAIR_ID: {_pair_id(a.record_id, b.record_id)}\n"
            f"Lead A — name: {a.name}, company: {a.company_name or 'unknown'}, "
            f"notes: {a.notes or '(none)'}\n"
            f"Lead B — name: {b.name}, company: {b.company_name or 'unknown'}, "
            f"notes: {b.notes or '(none)'}"
        )
    return f"""You are a conservative CRM entity-resolution system.

Each pair below has IDENTICAL names but DIFFERENT phone numbers and emails.
The identical name is a candidate-generation signal ONLY — not sufficient evidence.

Scoring guide (confidence that BOTH records = same real person):
90-100 = extremely strong evidence (multiple independent clues)
75-89  = strong evidence
60-74  = plausible, some uncertainty
40-59  = ambiguous / insufficient
20-39  = probably different people
0-19   = strong evidence they are different

Rules:
- Never score above 60 based on identical name alone.
- Different company + different contact info + no contextual overlap → below 30.
- Return exactly one result per pair. pair_id MUST exactly match the PAIR_ID.

Pairs:

{"".join(chr(10) + "---" + chr(10) + b for b in blocks).lstrip("-" + chr(10))}"""


def _run_llm_batch(batch: List[Tuple[Lead, Lead]]) -> List[LLMPairResult]:
    structured_llm = get_structured_llm(LLMBatchResponse)
    prompt = _build_name_match_prompt(batch)
    result = structured_llm.invoke(prompt)
    return result.results


def _score_all_candidates(
    candidates: List[Tuple[Lead, Lead]],
) -> Dict[str, LLMPairResult]:
    results: Dict[str, LLMPairResult] = {}
    for start in range(0, len(candidates), LLM_BATCH_SIZE):
        batch = candidates[start:start + LLM_BATCH_SIZE]
        try:
            for r in _run_llm_batch(batch):
                results[r.pair_id] = r
        except Exception:
            pass
    return results


# ---------------------------------------------------------------------------
# STEP 3C: Generate summary dari hasil LLM
# ---------------------------------------------------------------------------

def _generate_llm_summary(
    total_evaluated: int,
    passed: List[LLMPairResult],
    failed: List[LLMPairResult],
) -> str:
    """
    Buat summary singkat dari hasil LLM name-match pass.
    Dikerjain programatik dulu (stats), lalu LLM nulis narasinya.
    """
    all_scores = [r.score for r in passed + failed]
    avg_score = mean(all_scores) if all_scores else 0
    passed_count = len(passed)
    failed_count = len(failed)

    # Stats programatik sebagai konteks ke LLM
    passed_reasons = "\n".join(f"- {r.reason}" for r in passed[:5])
    failed_reasons = "\n".join(f"- {r.reason}" for r in failed[:5])

    if is_mock_provider():
        return (
            f"LLM evaluated {total_evaluated} name-match candidates "
            f"(mock mode: scoring skipped). "
            f"{passed_count} would have been promoted past threshold."
        )

    llm = get_llm()
    prompt = (
        f"Summarize the following entity-resolution results in 2-3 sentences. "
        f"Be specific about the pattern you observe.\n\n"
        f"Total evaluated: {total_evaluated} pairs with identical names but different phone/email\n"
        f"Passed threshold (score >= 60): {passed_count}\n"
        f"Did not pass (score < 60): {failed_count}\n"
        f"Average confidence score: {avg_score:.1f}/100\n\n"
        f"Sample reasons for PASSED pairs:\n{passed_reasons or '(none)'}\n\n"
        f"Sample reasons for FAILED pairs:\n{failed_reasons or '(none)'}\n\n"
        f"Write a brief summary of what the LLM found and why most candidates "
        f"did or did not qualify as likely duplicates."
    )
    response = llm.invoke(prompt)
    return getattr(response, "content", str(response)).strip()


# ---------------------------------------------------------------------------
# FUNGSI UTAMA: ai_dedupe
# ---------------------------------------------------------------------------

def ai_dedupe(
    db: Session,
    use_llm_justification: bool = False,
) -> Tuple[List[DedupeCandidate], Optional[str]]:
    """
    Return: (list of candidates, llm_summary or None)
    """
    leads = db.query(Lead).all()
    leads_by_id = {lead.record_id: lead for lead in leads}

    candidates: Dict[Tuple[str, str], DedupeCandidate] = {}

    def make(a: str, b: str, method: DedupeMethod, score: float,
             explanation: Optional[str] = None) -> DedupeCandidate:
        key = _pair_key(a, b)
        return DedupeCandidate(
            lead_a=_to_summary(leads_by_id[key[0]]),
            lead_b=_to_summary(leads_by_id[key[1]]),
            method=method,
            similarity_score=score,
            explanation=explanation,
        )

    # Step 1a: phone blocking
    for a, b in block_by_phone(leads):
        key = _pair_key(a, b)
        candidates[key] = make(key[0], key[1], DedupeMethod.phone_blocking, 100.0)

    # Step 1b: email blocking
    for a, b in block_by_email(leads):
        key = _pair_key(a, b)
        if key not in candidates:
            candidates[key] = make(key[0], key[1], DedupeMethod.email_blocking, 100.0)

    # Step 2: fuzzy similarity
    for a, b, score in fuzzy_similarity_pairs(leads):
        key = _pair_key(a, b)
        if key not in candidates:
            candidates[key] = make(key[0], key[1], DedupeMethod.fuzzy_similarity, score)

    llm_summary: Optional[str] = None

    if use_llm_justification:
        # Step 3a: collect name-match candidates
        name_candidates = _get_name_match_candidates(leads, set(candidates.keys()))

        if name_candidates:
            # Step 3b: score in batch
            candidate_lookup = {
                _pair_id(a.record_id, b.record_id): (a, b)
                for a, b in name_candidates
            }
            llm_results = _score_all_candidates(name_candidates)

            passed, failed = [], []
            for pid, result in llm_results.items():
                if pid not in candidate_lookup:
                    continue
                if result.score >= LLM_NAME_MATCH_THRESHOLD:
                    passed.append(result)
                    a, b = candidate_lookup[pid]
                    key = _pair_key(a.record_id, b.record_id)
                    candidates[key] = make(
                        key[0], key[1],
                        DedupeMethod.llm_name_match,
                        result.score,
                        result.reason,
                    )
                else:
                    failed.append(result)

            # Step 3c: generate summary
            llm_summary = _generate_llm_summary(
                total_evaluated=len(name_candidates),
                passed=passed,
                failed=failed,
            )
        else:
            llm_summary = "No additional name-match candidates found beyond step 1+2."

    results = list(candidates.values())
    results.sort(key=lambda c: c.similarity_score, reverse=True)
    return results, llm_summary


# ---------------------------------------------------------------------------
# FUNGSI UTAMA: ai_extraction
# ---------------------------------------------------------------------------

def ai_extraction(
    notes: str,
    original_source: Optional[str] = None,
) -> ExtractedSource:
    origin_channel = map_original_source(original_source, notes)
    if origin_channel is not None:
        detail = (
            notes.strip() if notes and notes.strip()
            else f"Identified from original_source: {original_source}"
        )
        return ExtractedSource(channel=origin_channel, detail=detail)

    rule_result = rule_based_extract(notes)
    if rule_result is not None:
        return rule_result

    if is_mock_provider():
        return ExtractedSource(
            channel="Other",
            detail="(mock mode: no LLM extraction performed)",
        )

    structured_llm = get_structured_llm(ExtractedSource)
    return structured_llm.invoke(
        "Extract the lead source channel and a short, well-phrased detail "
        "from this CRM note. If the note gives no clear indication of the "
        'channel, use "Other".\n'
        f"Note: {notes}"
    )