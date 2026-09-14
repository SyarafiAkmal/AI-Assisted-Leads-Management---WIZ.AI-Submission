# AI-Assisted Lead Management System

A backend service for managing a leads dataset with two AI-assisted features: **deduplication** and **source extraction**. Built with Python (FastAPI) + PostgreSQL, served with Docker Compose, and includes a minimal single-page frontend.

The reason I chose those techstacks/frameworks are to simplify the development process. Especially API development.

---

## How to Run

**Prerequisites:** Docker + Docker Compose installed.

1. Clone / unzip the repo
```bash
cd submission
```

2. Generate the normalized seed SQL from raw CSV
```bash
cd backend
python data/generate_seed.py data/leads_seed.csv data/leads_seed.sql
cd ..
```
3. Add your LLM API key to a .env file (optional — see LLM section below)
```bash
echo "LLM_PROVIDER=openai" >> .env
echo "LLM_MODEL=gpt-4o-mini" >> .env
echo "OPENAI_API_KEY=sk-..." >> .env
```

4. Start everything
```bash
docker-compose up -d --build
```

- **Frontend:** http://localhost:8000
- **API docs (Swagger):** http://localhost:8000/docs
- **Database:** PostgreSQL on `localhost:5432`, DB `leads_db`

To reset the database (re-seed from scratch):
```bash
docker-compose down -v
docker-compose up -d --build
```

### Frontend Walkthrough

The frontend is a single-page app served at `http://localhost:8000`, built with Alpine.js (no build step, no `node_modules`). Below is a walkthrough of each tab and its functionality.

#### Leads Tab

| Feature | How to use | Screenshot |
|---|---|---|
| **Browse leads** | All 2,049 leads are displayed in a paginated table (15 per page). Scroll horizontally to see all 14 columns. Use Prev/Next at the bottom to navigate pages. | ![Leads tab](docs/leads_tab.png) |
| **Filter & search** | Use the search bar for free-text search across name, company, email, and notes. Use the Status and Country dropdowns to filter by specific values. The Owner field accepts partial text input. Click **Search** to apply. Filters are AND-combined. | ![Filter](docs/leads_filter.png) |
| **Edit a lead** | Click a lead's **name** (highlighted in orange) to open the edit modal. You can update Status, Contact Owner, and Notes. Click **Save changes** to persist via `PATCH`. | ![Edit modal](docs/leads_edit.png) |
| **Extract source from edit** | While the edit modal is open, click **Extract source** to run source extraction on that lead's notes. The detected channel and detail appear below the buttons. | ![Extract in edit](docs/leads_edit.png) |
| **Export CSV** | Click **Export CSV** in the filter bar. It downloads a `.csv` file containing all leads matching the current filters (not just the current page), with all columns. Null values are written as the literal string `"null"`. | ![Export](docs/leads_export.png) |

#### Ingest Tab

| Feature | How to use | Screenshot |
|---|---|---|
| **Single lead** | Fill in the form fields (Name, Company, Email, Phone, Country, Form name, Form ID, Page URL, Message) and click **Submit lead**. A confirmation card shows the new `record_id`. | ![Single ingest](docs/ingest_single.png) |
| **Bulk ingest from JSON** | Click **Choose JSON file** and select a `.json` file containing an array of lead objects (same shape as `website_form_submissions.json`). The button updates to show how many leads were parsed. Click **Submit X leads** to ingest them sequentially. A summary shows how many succeeded/failed. | ![Bulk ingest](docs/ingest_bulk.png) |

#### Dedupe Tab

| Feature | How to use | Screenshot |
|---|---|---|
| **Run dedupe scan** | Click **Run dedupe scan** to execute steps 1 (phone/email blocking) and 2 (fuzzy similarity). Results appear as a table showing Lead 1, Lead 2, Score, and Method. The total pair count is shown top-right. | ![Dedupe scan](docs/dedupe_scan.png) |
| **Filter by method** | Use the **All methods** dropdown to show only pairs detected by a specific method (`phone_blocking`, `fuzzy_similarity`, `llm_name_match`). | ![Dedupe scan](docs/dedupe_scan.png) |
| **Enable LLM filter** | Toggle the **LLM Filter** switch ON before clicking Run. This activates step 3: the LLM evaluates ~110 name-match candidates in batches. After completion, a summary card appears above the table describing the LLM's findings (how many evaluated, how many passed, average score, and general pattern). Pairs that passed the LLM threshold appear with method `llm_name_match` and an explanation in the LLM Reason column. | ![Dedupe LLM](docs/dedupe_llm.png) |

#### Extract Tab

| Feature | How to use | Screenshot |
|---|---|---|
| **Look up by record ID** | Enter a `record_id` (e.g. `100234811`) in the top card and click **Look up**. The system fetches that lead's notes and original_source from the database and runs the 3-layer extraction pipeline. The result shows the detected channel badge and detail text. | ![Extract by ID](docs/extract_id.png) |
| **Extract from raw text** | Type or paste any text into the **Raw text** textarea and click **Extract**. Useful for testing extraction on arbitrary text without needing a database record. | ![Extract from text](docs/extract_text.png) |
---

## Project Structure

```
submission/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── data/
│   │   ├── leads_seed.csv           # raw CSV (source of truth)
│   │   ├── leads_seed.sql           # generated, already normalized
│   │   ├── generate_seed.py         # CSV → normalized SQL
│   │   └── website_form_submissions.json
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models/lead.py
│   │   ├── schemas/
│   │   ├── routers/                 # leads, ingest, ai_assist
│   │   ├── services/
│   │   │   ├── normalization.py     # shared normalize logic
│   │   │   ├── lead_service.py
│   │   │   ├── ingest_service.py
│   │   │   ├── ai_assist_service.py # dedupe + extraction pipeline
│   │   │   ├── extraction_rules.py  # regex layer for source extraction
│   │   │   └── origin_mapping.py    # original_source → channel mapping
│   │   └── llm/client.py            # multi-provider LangChain wrapper
│   └── tests/
│       └── test_unit.py
└── frontend/
    └── index.html                   # Alpine.js, served via FastAPI StaticFiles
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/leads` | List leads with filters (`q`, `lead_status`, `country_region`, `contact_owner`) + pagination |
| `GET` | `/api/leads/filters` | Distinct status + country values for dropdown population |
| `GET` | `/api/leads/:id` | Single lead detail |
| `PATCH` | `/api/leads/:id` | Update `lead_status`, `contact_owner`, or `notes` |
| `GET` | `/api/leads/export` | CSV export of current filtered view (all columns, `null` for missing values) |
| `POST` | `/api/leads/ingest` | Ingest one lead from website form payload |
| `POST` | `/api/leads/dedupe-candidates` | Run deduplication pipeline, optionally with LLM pass |
| `POST` | `/api/leads/extract-structured` | Extract source channel from raw text |
| `GET` | `/api/leads/:id/extract-source` | Extract source for a specific lead by ID |

---

## Design Decisions

### Data Processing

**Storage choice: PostgreSQL.**
SQLite would have worked for this scale, but Postgres was chosen because it is relatively simple and easier for me to inspect and explore since I can connect it to third party software like DBeaver. It also serves the purpose of being scalable since Postgres provides many big scale features for further needs.

**Schema normalization before seeding.**
Rather than loading the raw CSV and normalizing at query time, I pre-process the data into a clean `leads_seed.sql` before it enters the database. A dedicated `generate_seed.py` script runs `normalize_lead()` on every row and writes the result as SQL `INSERT` statements. These are loaded automatically by PostgreSQL's `docker-entrypoint-initdb.d/` on first container boot.

This means the database is the single source of truth for clean data, and the same normalization function is reused at ingest time — there is no risk of the seed data and new data having different cleaning rules.

**What was normalized:**
- `lead_status` — mixed casing and whitespace (`"NEW"`, `" New "`, `"new"`) → lowercase enum (`new`, `closed_won`, etc.)
- `phone_number` — stripped all non-digits, always prefixed `+` regardless of original format (critical for phone blocking — if two formats produce different strings, blocking misses the pair)
- `country_region` — title-cased
- `create_date` / `last_modified_date` — parsed from three different formats (ISO, ISO+timestamp, US `M/D/YYYY`) → `YYYY-MM-DD`
- `first_name` + `last_name` + `full_name` → merged into single `name` column (107 rows had only `full_name` populated)
- Five columns (`city`, `annual_revenue`, `marketing_contact_status`, `gdpr_consent`, `original_source_drill_down_1`) were 100% empty across all 2,049 rows and preserved as nullable rather than dropped, in case ingest fills them later.

### Assumptions & Design Choices

**Ingest: `original_source` set to `"Website Form"`.**
All ingested leads receive `original_source = "Website Form"` because the ingest endpoint only accepts payloads shaped like website form submissions (`data/website_form_submissions.json`). Since the payload itself is evidence that the lead came from a website form, this is a factual assignment rather than an assumption. This value is treated as always reliable in the extraction pipeline (layer 1 maps it directly to `channel = "Website"`) — unlike the CSV's `"Offline Sources"` which is often wrong.

**Ingest: `lead_status` and `lifecycle_stage` set to `null`.**
A newly submitted form entry has not been triaged yet — no human has reviewed or categorized it. Setting a default like `"new"` or `"Lead"` would be the system assuming a qualification decision that hasn't happened. `null` means "not yet triaged" — semantically distinct from any actual status value.

**Ingest: `form_name` stored in `original_source_drill_down_1`.**
The payload contains `form_id` and `form_name` (e.g. `"Newsletter Signup"`, `"Contact Us"`). Since there is no dedicated column for form metadata, `form_name` is stored in `original_source_drill_down_1` as a drill-down detail under the `"Website Form"` source — consistent with how the column is named in the original schema.

**Ingest: `page_url` and `message` merged into `notes`.**
The payload's `page_url` and `message` fields have no dedicated columns in the leads schema. Rather than losing this context, they are combined into the `notes` field as `"<message> (submitted via <page_url>)"`, preserving the information for future reference and extraction.

**Ingest: deduplication uses exact email match only.**
The ingest endpoint needs a fast, deterministic response per request. Exact email match (after normalization) is the strongest single identifier available and is computationally trivial. Fuzzy/semantic matching is reserved for the batch `dedupe-candidates` endpoint where processing time is not a constraint.

**PATCH: limited to `lead_status`, `contact_owner`, `notes`.**
Per the brief's specification. Other fields are not editable through the API — they are set at ingest/seed time and remain as-is.

---

### AI Feature 1 — Deduplication (`POST /leads/dedupe-candidates`)

**The problem with naïve approaches:**
- Exact email match misses cases where the same person was entered with two different emails (common in this dataset).
- A full pairwise LLM comparison over 2,000 rows would require ~2,000² = 4,000,000 comparisons — not feasible.

**Pipeline (3 steps, cost-ordered):**

**Step 1 — Blocking (exact match, free):**
Group leads by normalized phone number and by normalized email independently, then union the resulting pairs. Any leads sharing a phone or email are flagged as candidates at 100% confidence. This catches 294 pairs in the seed data — all follow the pattern of the same person entered twice with a slightly different company name suffix (`"Huang Analytics and Co"` vs `"Huang Analytics and Pte. Ltd."`).

Observation: all 58 email-duplicate pairs are a strict subset of the phone-duplicate pairs, so `email_blocking` never appears in the output for this dataset. This is not a bug — it reflects the structure of the data.

**Step 2 — Fuzzy similarity (vectorized, cheap):**
Concatenate `name + company_name` for every lead into a text string, then compute pairwise similarity using `rapidfuzz.process.cdist` with `token_sort_ratio`. This is a C-level vectorized operation — for 2,000 rows it completes in sub-second time (not a loop over pairs). Pairs scoring ≥ 85 that are not already in step 1 are added as `fuzzy_similarity` candidates.

This catches 20 additional pairs: cases where the same person appears with different phones and emails but similar name+company text (e.g. `Lucas Schmidt @ Chua Textiles Retail Group` with two completely different contact details).

**Step 3 — LLM name-match filter (expensive, only when `use_llm_justification: true`):**

From the dataset analysis, there are approximately 110 pairs where the name is identical but both phone and email differ — these are genuinely ambiguous (could be the same person at a new company, or two different people with the same name). Steps 1 and 2 cannot resolve these because there is no shared contact info and fuzzy string matching on name+company alone isn't sufficient to make a determination.

When the LLM filter is enabled, these candidates are processed in three sub-steps:

**3a. Candidate collection:** Identify all pairs where `name` is identical (case-insensitive) but both `phone_number` and `email` differ, excluding any pair already caught by step 1 or 2.

**3b. Batched LLM scoring:** Candidates are sent to the LLM in **batches of 25 pairs per API call** using LangChain's `.with_structured_output()` against a Pydantic schema (`LLMBatchResponse` containing a list of `LLMPairResult`). Each result includes a `pair_id`, a `score` (0–100), and a `reason` (one sentence). The prompt is deliberately conservative:
- Identical name alone is never sufficient for a score above 60
- Different company + different contact info + no contextual overlap in notes → score below 30
- Only pairs with contextual evidence in the notes (same event mentioned, same interaction referenced, etc.) score above the threshold

This batching approach reduces 110 individual LLM calls down to **5 API calls**, keeping the cost and latency tractable.

**3c. Summary generation:** After scoring, a summary is generated describing the overall findings: how many pairs were evaluated, how many passed the threshold (score ≥ 60), the average confidence score, and the general pattern observed (e.g. "most candidates share only a name — different companies, different contact info, no contextual overlap in notes"). This summary is returned alongside the candidate list, not per-pair, to give reviewers a high-level picture before diving into individual pairs.

Pairs scoring ≥ 60 are promoted to `llm_name_match` candidates in the output with their LLM-generated reason as the `explanation` field. Pairs scoring below 60 are excluded from the output — the LLM determined they are likely different people who happen to share a name.

**Why this approach:**
The key constraint from the brief is tractability at scale. Blocking narrows 2,000 rows to 314 candidates before any semantic comparison happens. Fuzzy matching is vectorized and adds no API cost. The LLM is only invoked for the genuinely ambiguous remainder (110 pairs that no cheaper method can resolve), and batched structured output reduces that to ~5 API calls rather than 110 individual ones. This reflects the "narrow the candidate set first, then apply expensive comparison to survivors" pattern described in the brief.

---

### AI Feature 2 — Source Extraction (`POST /leads/extract-structured`)

**The problem:**
`Original Source` is often blank (`""`) or misleading (`"Offline Sources"` for an event lead). The real signal is in the free-text `Notes` column, but its language is inconsistent and implicit.

**Three-layer hybrid approach (cost-ordered):**

**Layer 1 — Origin mapping (free, deterministic):**
If `original_source` is one of a small set of reliable values (`"Referrals"`, `"Organic Search"`, `"Website Form"`), map it directly to the channel enum. "Website Form" is always reliable because we set it ourselves on ingest. Ambiguous values like `"Other Campaigns"`, `"Offline Sources"`, and `""` are explicitly not mapped — they fall through to layer 2 rather than being trusted.

`"Social Media"` is a special case: it only maps to `LinkedIn` if the notes text explicitly mentions "linkedin"; otherwise it falls through, because "Social Media" could mean any platform.

**Layer 2 — Regex/keyword pass (free, deterministic):**
Scan the notes text for explicit keywords. Two tiers of patterns:

1. *Prefix labels* — checked first: `"Manual - ..."` (94 rows in the dataset) → `Manual/Sales`, `"Other - ..."` (153 rows) → `Other`. These labels were discovered by analyzing the actual dataset, not assumed from the brief.
2. *Keyword patterns* — `"booth"`, `"scanned our QR code"` → `Event`; `"organic search"`, `"googled us"` → `Organic Search`; `"referred by"` → `Referral`; `"linkedin"` → `LinkedIn`; etc.

**Layer 3 — LLM fallback (costs API credits):**
Only invoked if both layers 1 and 2 return `None` — i.e., the notes are genuinely implicit with no detectable keyword (`"He seemed really interested after our call last week"`). The LLM receives only the raw notes text, without any context from the failed layer 1/2 attempts, to avoid anchoring bias.

**Why hybrid over pure LLM:**
The majority of notes in this dataset contain explicit keywords (booth, referral, "Manual -", etc.) that a regex can catch instantly. Running an LLM call on every row would cost ~2,000 API calls for information that is largely deterministic to extract. The hybrid preserves LLM spend for genuinely ambiguous cases only.

---

### LLM Provider

- **Provider:** OpenAI (`gpt-4o-mini`) via LangChain `init_chat_model`
- **Why:** Structured output support (`.with_structured_output()`) is well-supported and reliable for the batch scoring schema used in dedup. LangChain's `init_chat_model` allows switching providers without changing application code.
- **Switching providers:** Set `LLM_PROVIDER` and `LLM_MODEL` environment variables — the `app/llm/client.py` wrapper supports any LangChain-compatible provider (Anthropic, Google, etc.) without changing application code.
- **Running without an API key:** Set `LLM_PROVIDER=mock` (the default). The application runs fully without LLM features — dedup steps 1+2 work normally, step 3 is skipped gracefully, and source extraction falls through to `channel="Other"` for ambiguous notes.
- **Estimated cost:** Running the full LLM dedup pass (~5 batch calls of 25 pairs each + 1 summary call) + a handful of manual extraction tests cost approximately **$0.02–0.05** with `gpt-4o-mini`.

---

### Tests

Unit tests cover the five functions whose correctness is most load-bearing:

```bash
docker exec -it -w /app leads-backend pytest tests/test_unit.py -v
```

**What's tested and why:**
- `normalize_date` — includes a regression test for a real bug where Pydantic parsed `"2025-12-21"` into a `datetime.date` object before it reached the normalizer, which then crashed calling `.strip()` on a non-string.
- `normalize_lead_status` — all casing variations present in the seed data.
- `normalize_phone` — includes a **consistency test**: two differently-formatted strings representing the same number must produce identical output, because phone blocking depends on exact string equality.
- `reconcile_name` — the 107-row edge case where only `full_name` is populated.
- `rule_based_extract` — includes the two examples from the brief verbatim, plus the `"Manual - ..."` and `"Other - ..."` prefix patterns discovered from dataset analysis (not in the brief), and a negative test to verify the regex does not over-match implicit notes.

---

## What I'd Do Next

- **`GET /dashboard`** — lead counts by status and by source channel. Out of scope for this submission but straightforward to add as an aggregation query.
- **Merge action on confirmed duplicates** — the current endpoint surfaces candidates; a `POST /leads/merge` that picks the canonical record and redirects the other would complete the dedup workflow.
- **Incremental dedup on ingest** — currently dedup is batch-only. On ingest, only an exact email check is done. A lightweight candidate check (phone + fuzzy name) at ingest time would catch duplicates as they come in rather than in batch.
- **Smarter LLM batching for extraction** — the extraction pipeline currently processes one record at a time. Batch extraction (similar to the dedup LLM pass) would reduce cost significantly if run across the full dataset.
- **Pagination on export** — current CSV export loads all matching rows into memory at once. For larger datasets, a streaming response would be more appropriate.