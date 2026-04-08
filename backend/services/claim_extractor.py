import re
import json
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

CLAIM_EXTRACTION_TOOL = {
    "name": "register_claims",
    "description": "Register every discrete factual claim found in the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": (
                                "The exact verbatim text of the claim as it appears in the source. "
                                "Do not paraphrase, summarize, or combine. "
                                "Each claim must be a single self-contained factual statement."
                            )
                        },
                        "claim_type": {
                            "type": "string",
                            "enum": [
                                "efficacy", "safety", "dosing", "moa",
                                "isi", "boilerplate", "stat", "study_design",
                                "indication", "nccn"
                            ]
                        },
                        "source_citation": {
                            "type": "string",
                            "description": "Study name, document section, or PI reference (e.g. 'FRUZAQLA PI, FRESCO-2')."
                        },
                        "numeric_values": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {"type": "string"},
                                    "unit":  {"type": "string"},
                                    "label": {"type": "string"}
                                },
                                "required": ["value", "label"]
                            }
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Concept labels for filtering (e.g. ['overall_survival','fresco-2','primary_endpoint'])."
                        }
                    },
                    "required": ["text", "claim_type", "tags"]
                }
            }
        },
        "required": ["claims"]
    }
}

EXTRACTION_SYSTEM_PROMPT = """You are a pharma regulatory content analyst. Extract every discrete factual claim from this page of a document.

Rules:
- ATOMIC: one fact per claim. "OS was 7.4 months and PFS was 2.7 months" → two separate claims.
- VERBATIM: copy the exact wording from the source including all numbers, CI bounds, p-values, and units. Do not rewrite or simplify.
- SELF-CONTAINED: each claim must be readable without context. Include the drug name, study name, and patient population in the claim text when relevant.
- ISI safety statements are claims (type "isi").
- Boilerplate connector phrases are claims (type "boilerplate") — e.g. "In a study of FRUZAQLA + BSC vs placebo + BSC in patients with previously treated mCRC".
- NCCN endorsements and indication statements are claims (types "nccn" and "indication").
- Study design details (endpoints, randomization, inclusion criteria) are claims (type "study_design").
- Tag every claim with every concept it touches — drug names, study names, endpoints, patient populations, claim category.
- Extract ALL claims — do not skip any factual statement."""


def _make_id(text: str, claim_type: str, seq: int) -> str:
    """Generate a stable human-readable claim ID."""
    words = re.sub(r'[^a-z0-9\s]', '', text.lower()).split()
    slug_words = [w for w in words if len(w) > 3][:3]
    slug = '_'.join(slug_words) if slug_words else 'claim'
    return f"{claim_type}_{slug}_{seq:03d}"


def _deduplicate(claims: list) -> list:
    """Remove near-duplicate claims by normalized text."""
    seen = set()
    result = []
    for c in claims:
        normalized = re.sub(r'\s+', ' ', c['text'].lower().strip())
        if normalized not in seen:
            seen.add(normalized)
            result.append(c)
    return result


def _extract_claims_from_page(client, page_text: str, page_number: int) -> list:
    """Send one page to Claude and return list of claim dicts with ground-truth page_number."""
    if not page_text.strip():
        return []

    try:
        with client.messages.stream(
            model='claude-sonnet-4-20250514',
            max_tokens=16000,
            system=EXTRACTION_SYSTEM_PROMPT,
            tools=[CLAIM_EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "register_claims"},
            messages=[{
                'role': 'user',
                'content': f"Extract all claims from this page (page {page_number}):\n\n{page_text}"
            }],
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == 'max_tokens':
            logger.warning("Page %d hit max_tokens — some claims may be missing", page_number)

        for block in response.content:
            if block.type == 'tool_use' and block.name == 'register_claims':
                claims = block.input.get('claims', [])
                # Override page_number with ground-truth from PDF index
                for c in claims:
                    c['page_number'] = page_number
                logger.info("Page %d: extracted %d claims", page_number, len(claims))
                return claims
    except Exception as e:
        logger.error("Page %d extraction failed: %s", page_number, e)
    return []


def extract_claims_streaming(pages: list, knowledge_id: int, app, on_page_done=None) -> list:
    """
    Extract claims from pages in parallel using ThreadPoolExecutor.
    pages: list of {"page_number": int, "text": str}
    app: Flask app for DB context in background thread
    on_page_done: optional callback(page_number, page_claims) called as each page completes
    Returns list of claim dicts ready for DB insertion.
    """
    from services.claude_service import _get_client
    client = _get_client()

    all_claims = []
    max_workers = min(5, len(pages))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {
            executor.submit(_extract_claims_from_page, client, p['text'], p['page_number']): p['page_number']
            for p in pages
        }

        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                page_claims = future.result()
                all_claims.extend(page_claims)
                if on_page_done and page_claims:
                    on_page_done(page_num, page_claims)
            except Exception as e:
                logger.error("Page %d future failed: %s", page_num, e)

    # Deduplicate across all pages
    all_claims = _deduplicate(all_claims)

    # Assign stable IDs and attach knowledge_id
    result = []
    for seq, claim in enumerate(all_claims):
        result.append({
            'id':              _make_id(claim['text'], claim['claim_type'], seq),
            'knowledge_id':    knowledge_id,
            'text':            claim['text'],
            'claim_type':      claim['claim_type'],
            'source_citation': claim.get('source_citation'),
            'page_number':     claim.get('page_number'),
            'numeric_values':  claim.get('numeric_values', []),
            'tags':            claim.get('tags', []),
            'is_approved':     True,
        })
    return result


def extract_claims(text: str, knowledge_id: int) -> list:
    """
    Backward-compatible wrapper: extracts claims from full text.
    Splits into synthetic pages of ~4000 chars for bounded output.
    """
    CHUNK_SIZE = 4000
    pages = []
    for i in range(0, len(text), CHUNK_SIZE):
        pages.append({"page_number": (i // CHUNK_SIZE) + 1, "text": text[i:i + CHUNK_SIZE]})

    return extract_claims_streaming(pages, knowledge_id, app=None)
