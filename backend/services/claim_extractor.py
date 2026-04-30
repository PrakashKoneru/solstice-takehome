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


def _normalize_for_match(text: str) -> str:
    """Collapse whitespace and lowercase for verbatim matching."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def _is_verbatim(claim_text: str, source_text: str) -> bool:
    """Return True if claim_text appears as a verbatim substring in source_text.

    Checks with whitespace-normalized comparison first, then falls back to
    an alphanumeric-only comparison to tolerate minor punctuation differences
    from PDF extraction (e.g. curly quotes, em-dashes).
    """
    claim_norm = _normalize_for_match(claim_text)
    source_norm = _normalize_for_match(source_text)
    if claim_norm in source_norm:
        return True
    # Fallback: strip all punctuation, keep only alphanumeric + spaces
    claim_stripped = re.sub(r'[^a-z0-9\s]', '', claim_norm)
    source_stripped = re.sub(r'[^a-z0-9\s]', '', source_norm)
    return claim_stripped in source_stripped


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


def _extract_claims_from_page(client, page_text: str, page_number: int, verbatim_text: str = None) -> list:
    """Send one page to Claude and return list of claim dicts with ground-truth page_number.

    Args:
        verbatim_text: If provided, the verbatim gate checks against this text instead of page_text.
                       Used to pass table-free text so table-derived claims get rejected.
    """
    if not page_text.strip():
        return []

    gate_text = verbatim_text if verbatim_text is not None else page_text

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
                # Verbatim gate: reject any claim whose text is not in the source
                # When verbatim_text is provided (table-free), claims fabricated
                # from table cells will fail this check
                verified = []
                for c in claims:
                    if _is_verbatim(c['text'], gate_text):
                        verified.append(c)
                    else:
                        logger.warning(
                            "Page %d: REJECTED non-verbatim claim: %s",
                            page_number, c['text'][:120],
                        )
                logger.info(
                    "Page %d: extracted %d claims, %d passed verbatim check",
                    page_number, len(claims), len(verified),
                )
                return verified
    except Exception as e:
        logger.error("Page %d extraction failed: %s", page_number, e)
    return []


def extract_claims_streaming(pages: list, knowledge_id: int, app, on_page_done=None, verbatim_pages=None) -> list:
    """
    Extract claims from pages in parallel using ThreadPoolExecutor.
    pages: list of {"page_number": int, "text": str}
    app: Flask app for DB context in background thread
    on_page_done: optional callback(page_number, page_claims) called as each page completes
    verbatim_pages: optional table-free pages for verbatim gate checking
    Returns list of claim dicts ready for DB insertion.
    """
    from services.claude_service import _get_client
    client = _get_client()

    # Build page_number -> table-free text lookup for verbatim gate
    verbatim_lookup = {}
    if verbatim_pages:
        verbatim_lookup = {p['page_number']: p['text'] for p in verbatim_pages}

    all_claims = []
    max_workers = min(5, len(pages))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {
            executor.submit(
                _extract_claims_from_page, client, p['text'], p['page_number'],
                verbatim_text=verbatim_lookup.get(p['page_number']),
            ): p['page_number']
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


def _section_number(title: str) -> Optional[str]:
    """Extract leading numbered prefix like '5.1' from '5.1. Hypertension'."""
    m = re.match(r'^(\d+(?:\.\d+)*)', title.strip())
    return m.group(1) if m else None


def _is_non_section_entry(title: str) -> bool:
    """Filter out non-section outline entries: table captions and dashed highlight box headers."""
    t = title.strip()
    # Table/Figure captions like "Table 1: Recommended Dosage"
    if re.match(r'^(Table|Figure)\s+\d+', t, re.IGNORECASE):
        return True
    # Dashed highlight-box entries like "--- ADVERSE REACTIONS ---"
    if t.startswith('-') and t.endswith('-'):
        return True
    # Misc non-section entries (distributor info, etc.)
    if t.startswith('Distributed by') or t.startswith('Takeda'):
        return True
    return False


def _build_section_tree(doc_outline: list) -> dict:
    """Build a lookup: page_number → section_hierarchy list (full ancestor chain).

    Parses numbered prefixes to infer parent-child relationships:
      '5.1' → parent '5', '6.3.2' → parent '6.3' → grandparent '6'
    Unnumbered entries become children of the last numbered entry before them.

    Returns: {page_number: [("14. CLINICAL STUDIES", page), ("14.1. mCRC", page), ("FRESCO-2 Study", page)], ...}
    Each value is a list of (title, page) tuples representing entries up to that page.
    """
    # Sort by page, then by position in original outline (preserves document order)
    sorted_entries = sorted(
        [(i, e) for i, e in enumerate(doc_outline) if not _is_non_section_entry(e.get('title', ''))],
        key=lambda x: (x[1].get('page', 0), x[0])
    )

    # Build a map from section number → entry for parent lookups
    numbered_entries = {}  # number → (title, page)
    all_entries = []       # ordered list of (title, page, number_or_None)

    for _, entry in sorted_entries:
        title = entry.get('title', '').strip()
        page = entry.get('page', 0)
        num = _section_number(title)
        if num:
            numbered_entries[num] = (title, page)
        all_entries.append((title, page, num))

    def _get_ancestors(title, num):
        """Walk up the number hierarchy to build the ancestor chain."""
        chain = []
        if num:
            # e.g. num='6.3.2' → try '6.3', then '6'
            parts = num.split('.')
            for depth in range(1, len(parts)):
                parent_num = '.'.join(parts[:depth])
                if parent_num in numbered_entries:
                    chain.append(numbered_entries[parent_num][0])
        chain.append(title)
        return chain

    # For each entry, compute its full hierarchy
    # Then build page→hierarchy by tracking the deepest entry at or before each page
    entry_hierarchies = []  # (page, hierarchy_list)
    last_numbered_title = None
    last_numbered_num = None

    for title, page, num in all_entries:
        if num:
            hierarchy = _get_ancestors(title, num)
            last_numbered_title = title
            last_numbered_num = num
        else:
            # Unnumbered entry — child of the last numbered entry before it
            if last_numbered_num:
                hierarchy = _get_ancestors(last_numbered_title, last_numbered_num)
                hierarchy.append(title)
            else:
                hierarchy = [title]
        entry_hierarchies.append((page, hierarchy))

    return entry_hierarchies


def assign_sections_to_claims(claims: list, doc_outline: list) -> list:
    """Assign section_hierarchy (full ancestor chain) and section (leaf) to each claim."""
    if not doc_outline:
        return claims

    entry_hierarchies = _build_section_tree(doc_outline)
    if not entry_hierarchies:
        return claims

    for claim in claims:
        page = claim.get('page_number') or 0

        # Find the deepest entry at or before this claim's page
        best_hierarchy = None
        for entry_page, hierarchy in entry_hierarchies:
            if entry_page <= page:
                best_hierarchy = hierarchy
            else:
                break

        if best_hierarchy:
            claim['section_hierarchy'] = best_hierarchy
            claim['section'] = best_hierarchy[-1]  # leaf for backward compat

    return claims


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
